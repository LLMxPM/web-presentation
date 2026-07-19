"""文件功能：验证页面可视化编辑保存服务的 artifact、防并发、整批应用和事务回滚。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException
from app.schemas.page_visual_edit import (
    PageVisualEditApplyRequest,
    PageVisualEditDuplicateNodeOperation,
    PageVisualEditSetTailwindTokensOperation,
    PageVisualEditSetValueOperation,
    PageVisualEditTailwindTokenChange,
)
from app.schemas.page_visual_edit_manifest import (
    PageVisualEditManifest,
    PageVisualEditNode,
    PageVisualEditSourceRange,
    build_page_visual_edit_source_hash,
)
from app.schemas.runtime_page_visual_edit import RuntimePageVisualEditApplyResponse
from app.services.page_visual_edit_service import PageVisualEditService
from app.services.runtime_visual_edit_client import (
    serialize_runtime_visual_edit_payload,
)


SOURCE = "<template><main>旧标题</main></template>"
NEXT_SOURCE = "<template><main>新标题</main></template>"
MODULE_PATH = "src/views/PGdemo.vue"
ARTIFACT_ID = "rt_visual_edit"


def _build_manifest() -> PageVisualEditManifest:
    """构造 artifact 绑定使用的 canonical Manifest。"""

    return PageVisualEditManifest(
        protocol_version=1,
        module_path=MODULE_PATH,
        source_hash=build_page_visual_edit_source_hash(SOURCE),
        root=PageVisualEditNode(
            node_id="node_root",
            kind="root",
            tag="#document",
            source_range=PageVisualEditSourceRange(start=0, end=len(SOURCE)),
            template_actions={
                "can_duplicate": False,
                "can_delete": False,
                "readonly_reason": "STRUCTURE_ROOT_UNSUPPORTED",
            },
            children=[
                PageVisualEditNode(
                    node_id="node_main",
                    kind="element",
                    tag="main",
                    source_range=PageVisualEditSourceRange(
                        start=SOURCE.index("<main>"),
                        end=SOURCE.index("</main>") + len("</main>"),
                    ),
                    template_actions={"can_duplicate": True, "can_delete": True},
                )
            ],
        ),
        json_sources=[],
        tailwind_catalog={
            "version": 1,
            "groups": [
                {
                    "key": "padding",
                    "label": "内边距",
                    "options": [
                        {"class_name": "p-4", "label": "中等"},
                        {"class_name": "p-6", "label": "较大"},
                    ],
                }
            ],
        },
    )


def _build_artifact_manifest(*, project_id: str = "7") -> dict[str, object]:
    """构造完整绑定用户、页面、版本与源码的 Redis artifact manifest。"""

    manifest = _build_manifest()
    return {
        "artifact_id": ARTIFACT_ID,
        "artifact_kind": "page_visual_edit_preview",
        "tenant_id": "tenant_9",
        "preview_kind": "page",
        "owner_scope": {
            "scope_type": "project",
            "project_id": project_id,
            "workspace_id": "5",
        },
        "entry_descriptor": {
            "entry_type": "module",
            "module_path": MODULE_PATH,
        },
        "visual_edit": {
            "protocol_version": 1,
            "page_id": 12,
            "page_version_id": 31,
            "base_version_no": 3,
            "source_hash": manifest.source_hash,
            "module_path": MODULE_PATH,
            "manifest": serialize_runtime_visual_edit_payload(manifest),
            "component_schemas": {},
            "warnings": [],
        },
    }


def _build_payload(*, source_hash: str | None = None) -> PageVisualEditApplyRequest:
    """构造单操作可视化编辑保存请求。"""

    return PageVisualEditApplyRequest(
        protocol_version=1,
        artifact_id=ARTIFACT_ID,
        base_version_no=3,
        source_hash=source_hash or build_page_visual_edit_source_hash(SOURCE),
        operations=[
            PageVisualEditSetValueOperation(
                type="set_value",
                node_id="node_title",
                binding_id="binding_title",
                value="新标题",
            )
        ],
        change_note="可视化修改标题",
    )


def _build_service(
    *,
    artifact_manifest: dict[str, object] | None = None,
    runtime_result: RuntimePageVisualEditApplyResponse | None = None,
):
    """构造带事务、页面服务、artifact 和 Runtime 替身的保存服务。"""

    page = SimpleNamespace(
        id=12,
        code="PGdemo",
        page_content=SOURCE,
        current_version_no=3,
        file_type="vue",
        workspace_id=5,
        project_id=7,
        deleted_at=None,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=page),
        rollback=AsyncMock(),
        commit=AsyncMock(),
    )

    async def update(_page_id, payload, _user_id, *, commit):
        """模拟 PageService 在同一事务中生成一个新版本。"""

        assert commit is False
        page.page_content = payload.page_content
        page.current_version_no = 4
        return SimpleNamespace(current_version_no=4)

    page_service = SimpleNamespace(
        _get_page_or_raise=AsyncMock(return_value=page),
        _ensure_page_access=AsyncMock(),
        update=AsyncMock(side_effect=update),
    )
    repository = SimpleNamespace(
        get_by_page_and_version=AsyncMock(return_value=SimpleNamespace(id=31)),
    )
    resolved_runtime_result = runtime_result or RuntimePageVisualEditApplyResponse(
        protocol_version=1,
        base_source_hash=build_page_visual_edit_source_hash(SOURCE),
        next_source_hash=build_page_visual_edit_source_hash(NEXT_SOURCE),
        next_source=NEXT_SOURCE,
        operations_applied=1,
        canonical_diff="-旧标题\n+新标题",
    )
    runtime_client = SimpleNamespace(
        apply=AsyncMock(return_value=resolved_runtime_result)
    )
    artifact_store = SimpleNamespace(
        get_manifest=AsyncMock(
            return_value=_build_artifact_manifest()
            if artifact_manifest is None
            else artifact_manifest
        )
    )
    service = PageVisualEditService(
        session,
        page_service=page_service,
        page_version_repository=repository,
        runtime_client=runtime_client,
        preview_service=SimpleNamespace(),
        artifact_store=artifact_store,
    )
    return service, page, session, page_service, runtime_client, artifact_store


@pytest.mark.asyncio
async def test_apply_should_use_canonical_source_and_commit_one_version() -> None:
    """成功保存只能使用 Backend 规范源码，整批完成后提交一个新版本。"""

    service, page, session, page_service, runtime_client, _ = _build_service()

    response = await service.apply(page_id=12, payload=_build_payload(), user_id=9)

    runtime_request = runtime_client.apply.await_args.args[0]
    assert runtime_request.source == SOURCE
    assert "instrumented" not in runtime_request.source
    assert len(runtime_request.operations) == 1
    page_service.update.assert_awaited_once()
    lock_statement = session.scalar.await_args.args[0]
    assert lock_statement._for_update_arg is not None
    assert page.page_content == NEXT_SOURCE
    assert page.current_version_no == 4
    session.commit.assert_awaited_once()
    assert response.previous_version_no == 3
    assert response.current_version_no == 4
    assert response.refresh_required is True


@pytest.mark.asyncio
async def test_apply_should_normalize_concurrent_version_integrity_error() -> None:
    """并发写入触发版本唯一约束时应回滚并归一化为 409。"""

    service, _, session, _, _, _ = _build_service()
    session.commit.side_effect = IntegrityError(
        "version conflict", {}, RuntimeError("duplicate")
    )

    with pytest.raises(AppException) as exc_info:
        await service.apply(page_id=12, payload=_build_payload(), user_id=9)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "PAGE_VISUAL_EDIT_BASE_VERSION_STALE"
    assert session.rollback.await_count == 2


@pytest.mark.asyncio
async def test_apply_should_reject_expired_artifact() -> None:
    """Redis artifact 过期时应返回稳定错误且不调用 Runtime。"""

    service, _, session, page_service, runtime_client, artifact_store = _build_service()
    artifact_store.get_manifest.return_value = None

    with pytest.raises(AppException) as exc_info:
        await service.apply(page_id=12, payload=_build_payload(), user_id=9)

    assert exc_info.value.code == "PAGE_VISUAL_EDIT_ARTIFACT_EXPIRED"
    runtime_client.apply.assert_not_awaited()
    page_service.update.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_should_reject_cross_project_artifact() -> None:
    """artifact owner project 与页面不符时应按错域拒绝。"""

    service, _, session, page_service, runtime_client, _ = _build_service(
        artifact_manifest=_build_artifact_manifest(project_id="99")
    )

    with pytest.raises(AppException) as exc_info:
        await service.apply(page_id=12, payload=_build_payload(), user_id=9)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "PAGE_VISUAL_EDIT_ARTIFACT_SCOPE_DENIED"
    runtime_client.apply.assert_not_awaited()
    page_service.update.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_should_reject_forged_artifact_kind() -> None:
    """普通预览 artifact 伪装成编辑基线时应返回稳定非法 artifact 错误。"""

    artifact_manifest = _build_artifact_manifest()
    artifact_manifest["artifact_kind"] = "preview_artifact"
    service, _, session, page_service, runtime_client, _ = _build_service(
        artifact_manifest=artifact_manifest
    )

    with pytest.raises(AppException) as exc_info:
        await service.apply(page_id=12, payload=_build_payload(), user_id=9)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "PAGE_VISUAL_EDIT_ARTIFACT_INVALID"
    runtime_client.apply.assert_not_awaited()
    page_service.update.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_should_reject_forged_component_schema_identity() -> None:
    """artifact 内组件 schema 来源版本不一致时应按严格绑定拒绝，且 Editor 无需回传 schema。"""

    artifact_manifest = _build_artifact_manifest()
    visual_edit = artifact_manifest["visual_edit"]
    assert isinstance(visual_edit, dict)
    visual_edit["component_schemas"] = {
        "LocalCard": {
            "source": "workspace_component",
            "import_path": "@workspace-components/CMP001/v/2",
            "component_code": "CMP001",
            "version_no": 1,
            "props": None,
        }
    }
    service, _, session, page_service, runtime_client, _ = _build_service(
        artifact_manifest=artifact_manifest
    )

    with pytest.raises(AppException) as exc_info:
        await service.apply(page_id=12, payload=_build_payload(), user_id=9)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "PAGE_VISUAL_EDIT_ARTIFACT_INVALID"
    runtime_client.apply.assert_not_awaited()
    page_service.update.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_should_reject_version_or_hash_conflict() -> None:
    """版本号或规范源码 hash 任一漂移时都不得读取 artifact 或调用 Runtime。"""

    service, page, session, page_service, runtime_client, artifact_store = (
        _build_service()
    )
    page.current_version_no = 4
    with pytest.raises(AppException) as version_error:
        await service.apply(page_id=12, payload=_build_payload(), user_id=9)
    assert version_error.value.code == "PAGE_VISUAL_EDIT_BASE_VERSION_STALE"

    page.current_version_no = 3
    with pytest.raises(AppException) as hash_error:
        await service.apply(
            page_id=12,
            payload=_build_payload(
                source_hash=build_page_visual_edit_source_hash("other")
            ),
            user_id=9,
        )
    assert hash_error.value.code == "PAGE_VISUAL_EDIT_SOURCE_HASH_STALE"
    artifact_store.get_manifest.assert_not_awaited()
    runtime_client.apply.assert_not_awaited()
    page_service.update.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_should_not_write_when_runtime_fails() -> None:
    """Runtime apply 失败时应保持页面版本不变。"""

    service, page, session, page_service, runtime_client, _ = _build_service()
    runtime_client.apply.side_effect = AppException(
        status_code=502,
        code="RUNTIME_VISUAL_EDIT_FAILED",
        detail="Runtime 改写失败。",
    )

    with pytest.raises(AppException, match="Runtime 改写失败"):
        await service.apply(page_id=12, payload=_build_payload(), user_id=9)

    assert page.current_version_no == 3
    page_service.update.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_should_rollback_when_candidate_validation_fails() -> None:
    """PageService 拒绝候选源码时应回滚已 flush 的版本和依赖索引。"""

    service, page, session, page_service, _, _ = _build_service()
    page_service.update.side_effect = AppException(
        status_code=400,
        code="RUNTIME_MODULE_IMPORT_INVALID",
        detail="候选源码 import 不合法。",
    )

    with pytest.raises(AppException) as exc_info:
        await service.apply(page_id=12, payload=_build_payload(), user_id=9)

    assert exc_info.value.code == "RUNTIME_MODULE_IMPORT_INVALID"
    assert page.current_version_no == 3
    assert session.rollback.await_count == 2
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_should_reject_partial_runtime_batch() -> None:
    """Runtime 返回的应用数量少于请求操作数时不得进入保存事务。"""

    runtime_result = RuntimePageVisualEditApplyResponse(
        protocol_version=1,
        base_source_hash=build_page_visual_edit_source_hash(SOURCE),
        next_source_hash=build_page_visual_edit_source_hash(NEXT_SOURCE),
        next_source=NEXT_SOURCE,
        operations_applied=1,
        canonical_diff="diff",
    )
    service, _, session, page_service, _, _ = _build_service(
        runtime_result=runtime_result
    )
    payload = _build_payload()
    payload.operations.append(
        PageVisualEditSetValueOperation(
            type="set_value",
            node_id="node_subtitle",
            binding_id="binding_subtitle",
            value="新副标题",
        )
    )

    with pytest.raises(AppException) as exc_info:
        await service.apply(page_id=12, payload=payload, user_id=9)

    assert exc_info.value.code == "RUNTIME_VISUAL_EDIT_PARTIAL_APPLY"
    page_service.update.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("group", "class_name"),
    [
        ("unknown", "p-4"),
        ("padding", "p-[999px]"),
    ],
)
async def test_apply_should_reject_tailwind_tokens_outside_artifact_catalog(
    group: str,
    class_name: str,
) -> None:
    """不在 artifact Catalog 中的样式组或 class 必须在调用 Runtime 前拒绝。"""

    service, _, session, page_service, runtime_client, _ = _build_service()
    payload = PageVisualEditApplyRequest(
        protocol_version=1,
        artifact_id=ARTIFACT_ID,
        base_version_no=3,
        source_hash=build_page_visual_edit_source_hash(SOURCE),
        operations=[
            PageVisualEditSetTailwindTokensOperation(
                type="set_tailwind_tokens",
                node_id="node_card",
                binding_id="binding_class",
                changes=[
                    PageVisualEditTailwindTokenChange(
                        group=group, class_name=class_name
                    )
                ],
            )
        ],
    )

    with pytest.raises(AppException) as exc_info:
        await service.apply(page_id=12, payload=payload, user_id=9)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "PAGE_VISUAL_EDIT_TAILWIND_TOKEN_UNSUPPORTED"
    runtime_client.apply.assert_not_awaited()
    page_service.update.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_should_allow_tailwind_group_removal_from_catalog() -> None:
    """Catalog 已声明的组允许用 null class 移除当前 token，并交由 Runtime 最终校验。"""

    service, _, session, page_service, runtime_client, _ = _build_service()
    payload = PageVisualEditApplyRequest(
        protocol_version=1,
        artifact_id=ARTIFACT_ID,
        base_version_no=3,
        source_hash=build_page_visual_edit_source_hash(SOURCE),
        operations=[
            PageVisualEditSetTailwindTokensOperation(
                type="set_tailwind_tokens",
                node_id="node_card",
                binding_id="binding_class",
                changes=[
                    PageVisualEditTailwindTokenChange(group="padding", class_name=None)
                ],
            )
        ],
    )

    response = await service.apply(page_id=12, payload=payload, user_id=9)

    runtime_request = runtime_client.apply.await_args.args[0]
    assert runtime_request.operations[0].changes[0].class_name is None
    page_service.update.assert_awaited_once()
    session.commit.assert_awaited_once()
    assert response.operations_applied == 1


@pytest.mark.asyncio
async def test_apply_should_reject_structural_operation_not_declared_by_manifest() -> (
    None
):
    """Backend 必须在调用 Runtime 前拒绝 Manifest 未开放的结构操作。"""

    service, _, _, _, runtime_client, _ = _build_service()
    payload = PageVisualEditApplyRequest(
        protocol_version=1,
        artifact_id=ARTIFACT_ID,
        base_version_no=3,
        source_hash=build_page_visual_edit_source_hash(SOURCE),
        operations=[
            PageVisualEditDuplicateNodeOperation(
                type="duplicate_node",
                node_id="node_root",
                instance_path=[],
            )
        ],
    )

    with pytest.raises(AppException) as exc_info:
        await service.apply(page_id=12, payload=payload, user_id=9)

    assert exc_info.value.code == "PAGE_VISUAL_EDIT_TARGET_READONLY"
    runtime_client.apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_should_forward_structural_operation_declared_by_manifest() -> None:
    """Backend 复核通过后应把 Manifest 已开放的结构操作整批交给 Runtime。"""

    service, _, session, page_service, runtime_client, _ = _build_service()
    payload = PageVisualEditApplyRequest(
        protocol_version=1,
        artifact_id=ARTIFACT_ID,
        base_version_no=3,
        source_hash=build_page_visual_edit_source_hash(SOURCE),
        operations=[
            PageVisualEditDuplicateNodeOperation(
                type="duplicate_node",
                node_id="node_main",
                instance_path=[],
            )
        ],
    )

    response = await service.apply(page_id=12, payload=payload, user_id=9)

    assert (
        runtime_client.apply.await_args.args[0].operations[0].type == "duplicate_node"
    )
    page_service.update.assert_awaited_once()
    session.commit.assert_awaited_once()
    assert response.current_version_no == 4
