"""文件功能：实现内容助手可恢复、原子化的通用归档与恢复能力。"""

from __future__ import annotations

from typing import Any

from pydantic_ai import ApprovalRequired
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.auth_tokens import extract_user_id
from app.ai.platform_tools import AgentToolContext
from app.ai.tools.generic.models import EntityArchiveArguments, build_mutation_envelope
from app.ai.tools.shared import resolve_tool_context
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus
from app.models.page import Page
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_style import WorkspaceStyle
from app.models.workspace_theme import WorkspaceTheme
from app.services.asset_service import AssetService
from app.services.project_route_service import ProjectRouteService
from app.services.workspace_component_service import WorkspaceComponentService
from app.services.workspace_theme_service import WorkspaceThemeService
from app.services.agent_work_scope_service import project_is_in_work_scope


ARCHIVABLE_RESOURCE_TYPES = frozenset({"page", "component", "asset", "theme", "style"})


async def build_archive_confirmation(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: AgentToolContext,
    arguments: EntityArchiveArguments,
) -> dict[str, Any]:
    """在批量确认前只读校验全部目标，并生成名称摘要与引用影响提示。"""

    if arguments.resource_type not in ARCHIVABLE_RESOURCE_TYPES:
        raise AppException(status_code=400, code="AI_ENTITY_ARCHIVE_UNSUPPORTED", detail="该对象类型不支持通过内容助手归档。")
    dependencies, _ = await resolve_tool_context(
        session_factory,
        run_context,
        required_scopes=(),
        required_dependency_fields=("workspace_id",),
    )
    workspace_id = int(dependencies["workspace_id"])
    async with session_factory() as session:
        targets = await _load_targets_for_update(
            session,
            resource_type=arguments.resource_type,
            workspace_id=workspace_id,
            target_ids=arguments.target_ids,
        )
        await _validate_archive_targets(
            session,
            resource_type=arguments.resource_type,
            workspace_id=workspace_id,
            targets=targets,
            versions=arguments.versions,
        )
        _validate_page_work_scope(dependencies, arguments.resource_type, targets)
    return {
        "resource_type": arguments.resource_type,
        "target_count": len(targets),
        "targets": [_target_summary(arguments.resource_type, item) for item in targets[:20]],
        "targets_truncated": len(targets) > 20,
        "reference_impact": _archive_reference_impact(arguments.resource_type),
        "archive_reason": arguments.archive_reason,
    }


async def archive_entities(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: AgentToolContext,
    arguments: EntityArchiveArguments,
) -> dict[str, Any]:
    """在同一事务内校验并归档全部目标，任一失败时整批回滚。"""

    if arguments.resource_type not in ARCHIVABLE_RESOURCE_TYPES:
        raise AppException(
            status_code=400,
            code="AI_ENTITY_ARCHIVE_UNSUPPORTED",
            detail="该对象类型不支持通过内容助手归档。",
        )
    dependencies, claims = await resolve_tool_context(
        session_factory,
        run_context,
        required_scopes=(),
        required_dependency_fields=("workspace_id",),
    )
    workspace_id = int(dependencies["workspace_id"])
    operator_id = extract_user_id(str(claims.get("sub")))
    async with session_factory() as session:
        targets = await _load_targets_for_update(
            session,
            resource_type=arguments.resource_type,
            workspace_id=workspace_id,
            target_ids=arguments.target_ids,
        )
        await _validate_archive_targets(
            session,
            resource_type=arguments.resource_type,
            workspace_id=workspace_id,
            targets=targets,
            versions=arguments.versions,
        )
        _validate_page_work_scope(dependencies, arguments.resource_type, targets)
        await _apply_archive(
            session,
            resource_type=arguments.resource_type,
            targets=targets,
            archive_reason=arguments.archive_reason,
            operator_id=operator_id,
        )
        await session.commit()

    target_summaries = [_target_summary(arguments.resource_type, item) for item in targets]
    return build_mutation_envelope(
        resource_type=arguments.resource_type,
        operation="archive",
        message=f"已归档 {len(target_summaries)} 个对象。",
        targets=target_summaries,
        mutation_kind=_mutation_kind(arguments.resource_type),
        data={"archived_count": len(target_summaries), "target_ids": arguments.target_ids},
    )


async def restore_entities(
    session_factory: async_sessionmaker[AsyncSession],
    run_context: AgentToolContext,
    *,
    resource_type: str,
    target_ids: list[int],
    reason: str | None = None,
) -> dict[str, Any]:
    """在同一事务内恢复归档对象；恢复同样执行实时工作空间校验。"""

    arguments = EntityArchiveArguments(
        resource_type=resource_type,
        target_ids=target_ids,
        archive_reason=reason,
    )
    if arguments.resource_type not in ARCHIVABLE_RESOURCE_TYPES:
        raise AppException(status_code=400, code="AI_ENTITY_RESTORE_UNSUPPORTED", detail="该对象类型不支持恢复归档。")
    dependencies, claims = await resolve_tool_context(
        session_factory,
        run_context,
        required_scopes=(),
        required_dependency_fields=("workspace_id",),
    )
    workspace_id = int(dependencies["workspace_id"])
    operator_id = extract_user_id(str(claims.get("sub")))
    async with session_factory() as session:
        targets = await _load_targets_for_update(
            session,
            resource_type=arguments.resource_type,
            workspace_id=workspace_id,
            target_ids=arguments.target_ids,
            archived=True,
        )
        await _validate_restore_targets(session, resource_type=arguments.resource_type, targets=targets)
        _validate_page_work_scope(dependencies, arguments.resource_type, targets)
        _raise_cross_focus_restore_confirmation(
            run_context,
            claims,
            resource_type=arguments.resource_type,
            targets=targets,
        )
        _apply_restore(resource_type=arguments.resource_type, targets=targets, operator_id=operator_id)
        await session.commit()

    target_summaries = [_target_summary(arguments.resource_type, item) for item in targets]
    return build_mutation_envelope(
        resource_type=arguments.resource_type,
        operation="action",
        action="restore",
        message=f"已恢复 {len(target_summaries)} 个归档对象。",
        targets=target_summaries,
        mutation_kind=_mutation_kind(arguments.resource_type),
        data={"restored_count": len(target_summaries), "target_ids": arguments.target_ids},
    )


def _raise_cross_focus_restore_confirmation(
    run_context: AgentToolContext,
    claims: dict[str, Any],
    *,
    resource_type: str,
    targets: list[Any],
) -> None:
    """页面恢复写入焦点外项目时，按本次工具调用动态请求确认。"""

    if resource_type != "page" or run_context.dependencies.get("current_tool_call_approved") is True:
        return
    focus_project_id = claims.get("project_id")
    target_project_ids = sorted({int(item.project_id) for item in targets})
    if focus_project_id is None or all(project_id == int(focus_project_id) for project_id in target_project_ids):
        return
    raise ApprovalRequired(
        metadata={
            "confirmation_title": f"确认在焦点外恢复 {len(targets)} 个页面吗？",
            "current_focus": {"project_id": int(focus_project_id)},
            "targets": [{"id": int(item.id), "project_id": int(item.project_id)} for item in targets[:20]],
            "targets_truncated": len(targets) > 20,
            "impact": "恢复目标不属于当前 Run 的默认项目焦点；批准仅对本次工具调用有效。",
        }
    )


async def _load_targets_for_update(
    session: AsyncSession,
    *,
    resource_type: str,
    workspace_id: int,
    target_ids: list[int],
    archived: bool = False,
) -> list[Any]:
    """锁定同工作空间目标并按请求顺序返回，避免跨空间和部分执行。"""

    model = _resource_model(resource_type)
    statement = select(model).where(model.id.in_(target_ids)).with_for_update()
    if hasattr(model, "workspace_id"):
        statement = statement.where(model.workspace_id == workspace_id)
    rows = list((await session.scalars(statement)).all())
    by_id = {int(item.id): item for item in rows}
    missing_ids = [target_id for target_id in target_ids if target_id not in by_id]
    if missing_ids:
        raise AppException(
            status_code=404,
            code="AI_ENTITY_TARGETS_NOT_FOUND",
            detail="部分目标不存在或不属于当前工作空间。",
            data={"target_ids": missing_ids},
        )
    ordered = [by_id[target_id] for target_id in target_ids]
    if resource_type in {"theme", "style"}:
        invalid = [int(item.id) for item in ordered if (item.deleted_at is None) == archived]
    else:
        expected = RecordStatus.ARCHIVED.value if archived else RecordStatus.ACTIVE.value
        invalid = [int(item.id) for item in ordered if str(item.status) != expected]
    if invalid:
        action = "恢复" if archived else "归档"
        raise AppException(
            status_code=409,
            code="AI_ENTITY_STATUS_INVALID",
            detail=f"部分目标当前状态不允许{action}。",
            data={"target_ids": invalid},
        )
    return ordered


async def _validate_archive_targets(
    session: AsyncSession,
    *,
    resource_type: str,
    workspace_id: int,
    targets: list[Any],
    versions: dict[str, int],
) -> None:
    """执行归档前的版本、引用和对象类型校验，不产生写入。"""

    for item in targets:
        expected_version = versions.get(str(item.id))
        actual_version = getattr(item, "current_version_no", None)
        if expected_version is not None and actual_version is not None and int(actual_version) != expected_version:
            raise AppException(
                status_code=409,
                code="AI_ENTITY_VERSION_CONFLICT",
                detail="目标版本已经变化，请重新查询后再归档。",
                data={"target_id": int(item.id), "current_version": int(actual_version)},
            )
        if resource_type == "asset":
            AssetService._ensure_normal_asset_for_archive(item)
        elif resource_type == "theme":
            await WorkspaceThemeService(session).assert_theme_can_delete(workspace_id, item.key)


async def _apply_archive(
    session: AsyncSession,
    *,
    resource_type: str,
    targets: list[Any],
    archive_reason: str | None,
    operator_id: int,
) -> None:
    """在已完成全量校验后写入归档状态，由调用方统一提交。"""

    timestamp = utc_now()
    for item in targets:
        if resource_type == "page":
            if item.project_id is not None:
                await ProjectRouteService(session).remove_page_bindings(int(item.project_id), int(item.id))
            item.status = RecordStatus.ARCHIVED.value
        elif resource_type == "component":
            item.status = RecordStatus.ARCHIVED.value
        elif resource_type == "asset":
            item.status = RecordStatus.ARCHIVED.value
            item.archived_at = timestamp
            item.archive_reason = AssetService._normalize_description(archive_reason)
        else:
            item.deleted_at = timestamp
        if hasattr(item, "updated_by"):
            item.updated_by = operator_id


async def _validate_restore_targets(session: AsyncSession, *, resource_type: str, targets: list[Any]) -> None:
    """恢复前检查会重新生效的唯一性约束。"""

    if resource_type != "component":
        return
    repository = WorkspaceComponentService(session).repository
    for item in targets:
        conflict = await repository.get_active_by_import_name(
            workspace_id=int(item.workspace_id),
            import_name=str(item.import_name),
            exclude_component_id=int(item.id),
        )
        if conflict is not None:
            raise AppException(
                status_code=409,
                code="COMPONENT_IMPORT_NAME_CONFLICT",
                detail=f"组件引用名 {item.import_name} 已被启用组件占用，无法恢复。",
            )


def _apply_restore(*, resource_type: str, targets: list[Any], operator_id: int) -> None:
    """写入恢复状态，由调用方负责事务提交。"""

    for item in targets:
        if resource_type in {"theme", "style"}:
            item.deleted_at = None
        else:
            item.status = RecordStatus.ACTIVE.value
            if resource_type == "asset":
                item.archived_at = None
                item.archive_reason = None
        if hasattr(item, "updated_by"):
            item.updated_by = operator_id


def _resource_model(resource_type: str) -> type[Any]:
    """返回可归档资源对应的 ORM 模型。"""

    models: dict[str, type[Any]] = {
        "page": Page,
        "component": WorkspaceComponent,
        "asset": WorkspaceAsset,
        "theme": WorkspaceTheme,
        "style": WorkspaceStyle,
    }
    return models[resource_type]


def _target_summary(resource_type: str, item: Any) -> dict[str, Any]:
    """构造不泄露主题字体或 Logo 字段的目标摘要。"""

    summary: dict[str, Any] = {"id": int(item.id), "resource_type": resource_type}
    if resource_type == "page" and item.project_id is not None:
        summary["project_id"] = int(item.project_id)
    for field_name in ("code", "key", "name", "title", "import_name"):
        value = getattr(item, field_name, None)
        if value is not None:
            summary[field_name] = value
    return summary


def _mutation_kind(resource_type: str) -> str:
    """把逻辑对象映射为 Editor 刷新域。"""

    return {"page": "project-pages", "asset": "asset"}.get(resource_type, resource_type)


def _archive_reference_impact(resource_type: str) -> str:
    """返回确认卡使用的保守引用影响说明。"""

    return {
        "page": "页面会从普通列表隐藏，已有项目路由绑定会被移除；恢复后需重新配置路由位置。",
        "component": "组件会从普通列表隐藏；已有页面源码引用不会自动改写，需另行检查运行效果。",
        "asset": "资源会从普通列表隐藏，既有引用仍可解析。",
        "theme": "主题会从普通列表隐藏；被项目引用的主题会在预检阶段拒绝归档。",
        "style": "样式会从普通列表隐藏，引用方不会被自动改写。",
    }[resource_type]


def _validate_page_work_scope(dependencies: dict[str, Any], resource_type: str, targets: list[Any]) -> None:
    """确保页面归档和恢复覆盖工作集过滤，工作空间级对象不受项目工作集限制。"""

    if resource_type != "page":
        return
    invalid = [
        int(item.id)
        for item in targets
        if not project_is_in_work_scope(
            work_scope_mode=str(dependencies.get("work_scope_mode") or "workspace"),
            allowed_project_ids=list(dependencies.get("allowed_project_ids") or []),
            project_id=item.project_id,
        )
    ]
    if invalid:
        raise AppException(
            status_code=403,
            code="AI_PROJECT_OUTSIDE_WORK_SCOPE",
            detail="部分页面不在本轮固化的项目工作集中。",
            data={"target_ids": invalid},
        )
