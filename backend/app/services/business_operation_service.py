"""文件功能：统一封装 External API v1 业务写操作，保证 Unit of Work 事务原子性与业务约束。"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.schemas.external_api import (
    ExternalBatchArchiveRequest,
    ExternalBatchArchiveResponse,
)
from app.schemas.project import ProjectCreateRequest, ProjectItem, ProjectUpdateRequest
from app.schemas.theme import WorkspaceThemeCreateRequest, WorkspaceThemeItem, WorkspaceThemeUpdateRequest
from app.schemas.component import (
    WorkspaceComponentItem,
    WorkspaceComponentPublishRequest,
    WorkspaceComponentRestoreDraftRequest,
)
from app.schemas.workspace_style import WorkspaceStyleCreateRequest, WorkspaceStyleItem, WorkspaceStyleUpdateRequest
from app.services.asset_service import AssetService
from app.services.page_service import PageService
from app.services.project_service import ProjectService
from app.services.workspace_component_service import WorkspaceComponentService
from app.services.workspace_style_service import WorkspaceStyleService
from app.services.workspace_theme_service import WorkspaceThemeService

logger = logging.getLogger(__name__)


class BusinessOperationService:
    """业务操作分发与 Unit of Work 事务边界服务。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.project_service = ProjectService(session)
        self.page_service = PageService(session)
        self.component_service = WorkspaceComponentService(session)
        self.asset_service = AssetService(session)
        self.theme_service = WorkspaceThemeService(session)
        self.style_service = WorkspaceStyleService(session)

    # ------------------ Project Operations ------------------

    async def create_project(
        self,
        *,
        workspace_id: int,
        payload: ProjectCreateRequest,
        operator_id: int,
        commit: bool = False,
    ) -> ProjectItem:
        """创建项目。"""

        payload.workspace_id = workspace_id
        return await self.project_service.create(
            payload=payload,
            operator_id=operator_id,
            commit=commit,
        )

    async def update_project(
        self,
        *,
        project_id: int,
        payload: ProjectUpdateRequest,
        operator_id: int,
        commit: bool = False,
    ) -> ProjectItem:
        """更新项目基础属性。"""

        return await self.project_service.update(
            project_id=project_id,
            payload=payload,
            operator_id=operator_id,
            commit=commit,
        )

    async def archive_project(
        self,
        *,
        project_id: int,
        operator_id: int,
        commit: bool = False,
    ) -> None:
        """归档项目。"""

        await self.project_service.delete(
            project_id=project_id,
            user_id=operator_id,
            commit=commit,
        )

    # ------------------ Theme Operations ------------------

    async def create_theme(
        self,
        *,
        workspace_id: int,
        payload: WorkspaceThemeCreateRequest,
        operator_id: int,
        commit: bool = False,
    ) -> WorkspaceThemeItem:
        """创建工作空间主题。"""

        return await self.theme_service.create(
            workspace_id=workspace_id,
            payload=payload,
            operator_id=operator_id,
            commit=commit,
        )

    async def update_theme(
        self,
        *,
        workspace_id: int,
        theme_id: int,
        payload: WorkspaceThemeUpdateRequest,
        operator_id: int,
        commit: bool = False,
    ) -> WorkspaceThemeItem:
        """更新工作空间主题（严格禁止通过 External API 修改 theme key）。"""

        current = await self.theme_service.get(workspace_id, theme_id)
        if payload.key and payload.key != current.key:
            raise AppException(
                status_code=400,
                code="THEME_KEY_IMMUTABLE",
                detail="通过外部 API 更新主题时禁止修改主题 key。",
            )

        return await self.theme_service.update(
            workspace_id=workspace_id,
            theme_id=theme_id,
            payload=payload,
            operator_id=operator_id,
            commit=commit,
        )

    async def archive_theme(
        self,
        *,
        workspace_id: int,
        theme_id: int,
        operator_id: int,
        commit: bool = False,
    ) -> None:
        """归档主题（若被活跃项目引用则抛出 409）。"""

        await self.theme_service.archive(
            workspace_id=workspace_id,
            theme_id=theme_id,
            operator_id=operator_id,
            commit=commit,
        )

    async def restore_theme(
        self,
        *,
        workspace_id: int,
        theme_id: int,
        operator_id: int,
        commit: bool = False,
    ) -> None:
        """恢复已归档主题。"""

        await self.theme_service.restore(
            workspace_id=workspace_id,
            theme_id=theme_id,
            operator_id=operator_id,
            commit=commit,
        )

    # ------------------ Style Operations ------------------

    async def create_style(
        self,
        *,
        workspace_id: int,
        payload: WorkspaceStyleCreateRequest,
        operator_id: int,
        commit: bool = False,
    ) -> WorkspaceStyleItem:
        """创建工作空间样式方案。"""

        return await self.style_service.create(
            workspace_id=workspace_id,
            payload=payload,
            operator_id=operator_id,
            commit=commit,
        )

    async def update_style(
        self,
        *,
        workspace_id: int,
        style_id: int,
        payload: WorkspaceStyleUpdateRequest,
        operator_id: int,
        commit: bool = False,
    ) -> WorkspaceStyleItem:
        """更新工作空间样式方案。"""

        return await self.style_service.update(
            workspace_id=workspace_id,
            style_id=style_id,
            payload=payload,
            operator_id=operator_id,
            commit=commit,
        )

    async def archive_style(
        self,
        *,
        workspace_id: int,
        style_id: int,
        operator_id: int,
        commit: bool = False,
    ) -> None:
        """归档样式方案（默认方案受保护禁止归档）。"""

        await self.style_service.archive(
            workspace_id=workspace_id,
            style_id=style_id,
            operator_id=operator_id,
            commit=commit,
        )

    async def restore_style(
        self,
        *,
        workspace_id: int,
        style_id: int,
        operator_id: int,
        commit: bool = False,
    ) -> None:
        """恢复已归档样式方案。"""

        await self.style_service.restore(
            workspace_id=workspace_id,
            style_id=style_id,
            operator_id=operator_id,
            commit=commit,
        )

    # ------------------ Component Operations ------------------

    async def publish_component(
        self,
        *,
        component_id: int,
        payload: WorkspaceComponentPublishRequest,
        operator_id: int,
        commit: bool = False,
    ) -> WorkspaceComponentItem:
        """发布组件新版本。"""

        return await self.component_service.publish(
            component_id=component_id,
            payload=payload,
            operator_id=operator_id,
            commit=commit,
        )

    async def restore_component_version_to_draft(
        self,
        *,
        component_id: int,
        version_no: int,
        payload: WorkspaceComponentRestoreDraftRequest,
        operator_id: int,
        commit: bool = False,
    ) -> WorkspaceComponentItem:
        """将组件历史发布版本恢复到草稿区。"""

        return await self.component_service.restore_version_to_draft(
            component_id=component_id,
            version_no=version_no,
            payload=payload,
            operator_id=operator_id,
            commit=commit,
        )

    # ------------------ Batch Archive (Atomic Transaction) ------------------

    async def batch_archive_entities(
        self,
        *,
        workspace_id: int,
        entity_type: str,
        payload: ExternalBatchArchiveRequest,
        operator_id: int,
        commit: bool = False,
    ) -> ExternalBatchArchiveResponse:
        """在单事务中原子执行两个及以上同类型目标的整批归档。"""

        archived_ids: list[int] = []

        try:
            if entity_type == "project":
                for pid in payload.ids:
                    proj = await self.project_service.get(pid, user_id=operator_id)
                    if proj.workspace_id != workspace_id:
                        raise AppException(
                            status_code=403,
                            code="WORKSPACE_NOT_AUTHORIZED",
                            detail=f"项目 ID {pid} 不属于目标工作空间。",
                        )
                    await self.archive_project(project_id=pid, operator_id=operator_id, commit=False)
                    archived_ids.append(pid)
            elif entity_type == "page":
                for page_id in payload.ids:
                    page = await self.page_service.get(page_id, user_id=operator_id)
                    if page.workspace_id != workspace_id:
                        raise AppException(
                            status_code=403,
                            code="WORKSPACE_NOT_AUTHORIZED",
                            detail=f"页面 ID {page_id} 不属于目标工作空间。",
                        )
                    await self.page_service.delete(page_id=page_id, user_id=operator_id, commit=False)
                    archived_ids.append(page_id)
            elif entity_type == "component":
                for cid in payload.ids:
                    comp = await self.component_service.get(cid, user_id=operator_id)
                    if comp.workspace_id != workspace_id:
                        raise AppException(
                            status_code=403,
                            code="WORKSPACE_NOT_AUTHORIZED",
                            detail=f"组件 ID {cid} 不属于目标工作空间。",
                        )
                    await self.component_service.archive(component_id=cid, user_id=operator_id, commit=False)
                    archived_ids.append(cid)
            elif entity_type == "asset":
                for aid in payload.ids:
                    await self.asset_service.archive_asset(
                        workspace_id=workspace_id, asset_id=aid, archive_reason=payload.reason, commit=False
                    )
                    archived_ids.append(aid)
            elif entity_type == "theme":
                for tid in payload.ids:
                    await self.archive_theme(workspace_id=workspace_id, theme_id=tid, operator_id=operator_id, commit=False)
                    archived_ids.append(tid)
            elif entity_type == "style":
                for sid in payload.ids:
                    await self.archive_style(workspace_id=workspace_id, style_id=sid, operator_id=operator_id, commit=False)
                    archived_ids.append(sid)
            else:
                raise AppException(
                    status_code=400,
                    code="INVALID_ENTITY_TYPE",
                    detail=f"不支持批量归档实体类型: {entity_type}",
                )

            if commit:
                await self.session.commit()
            else:
                await self.session.flush()
        except Exception:
            await self.session.rollback()
            raise

        return ExternalBatchArchiveResponse(
            archived_ids=archived_ids,
            failed_ids=[],
            total=len(archived_ids),
        )
