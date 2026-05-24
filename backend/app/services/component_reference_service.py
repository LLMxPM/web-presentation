"""文件功能：查询组件直接引用关系，并批量升级页面与组件草稿中的组件版本引用。"""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.text_normalizer import normalize_text_to_lf
from app.models.enums import PageFileType
from app.models.workspace_component import WorkspaceComponent
from app.repositories.module_dependency_repository import (
    ComponentComponentReferenceRow,
    ModuleDependencyRepository,
    PageComponentReferenceRow,
)
from app.repositories.page_repository import PageRepository
from app.repositories.workspace_component_repository import WorkspaceComponentRepository
from app.repositories.workspace_component_version_repository import WorkspaceComponentVersionRepository
from app.schemas.component import (
    WorkspaceComponentComponentReferenceItem,
    WorkspaceComponentPageReferenceItem,
    WorkspaceComponentReferenceUpgradeComponentItem,
    WorkspaceComponentReferenceUpgradeIssue,
    WorkspaceComponentReferenceUpgradePageItem,
    WorkspaceComponentReferenceUpgradeRequest,
    WorkspaceComponentReferenceUpgradeResponse,
    WorkspaceComponentReferences,
)
from app.services.page_version_service import PageVersionService
from app.services.workspace_component_version_service import WorkspaceComponentVersionService
from app.services.workspace_service import WorkspaceService


class ComponentReferenceService:
    """组件引用服务，负责当前版本引用查询和源码 import 快速升级。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.component_repository = WorkspaceComponentRepository(session)
        self.component_version_repository = WorkspaceComponentVersionRepository(session)
        self.dependency_repository = ModuleDependencyRepository(session)
        self.page_repository = PageRepository(session)
        self.page_version_service = PageVersionService(session)
        self.component_version_service = WorkspaceComponentVersionService(session)
        self.workspace_service = WorkspaceService(session)

    async def get_references(self, component_id: int, *, user_id: int) -> WorkspaceComponentReferences:
        """读取目标组件被当前页面版本和当前组件发布版本直接引用的集合。"""

        component = await self._get_component_or_raise(component_id)
        await self.workspace_service.ensure_access(component.workspace_id, user_id=user_id)
        page_rows = await self.dependency_repository.list_current_page_references_to_component(component.id)
        component_rows = await self.dependency_repository.list_current_component_references_to_component(component.id)
        target_version_no = component.current_version_no

        return WorkspaceComponentReferences(
            component_id=component.id,
            component_code=component.code,
            current_version_no=target_version_no,
            page_references=[
                self._to_page_reference_item(row, target_version_no)
                for row in self._deduplicate_page_reference_rows(page_rows, target_version_no)
            ],
            component_references=[
                await self._to_component_reference_item(row, component.code, target_version_no)
                for row in self._deduplicate_component_reference_rows(component_rows, target_version_no)
            ],
        )

    async def upgrade_references(
        self,
        component_id: int,
        payload: WorkspaceComponentReferenceUpgradeRequest,
        *,
        user_id: int,
    ) -> WorkspaceComponentReferenceUpgradeResponse:
        """将选中的直接引用升级到目标组件当前发布版本。"""

        component = await self._get_component_or_raise(component_id)
        await self.workspace_service.ensure_access(component.workspace_id, user_id=user_id)
        if component.current_version_no <= 0:
            raise AppException(
                status_code=409,
                code="COMPONENT_NOT_PUBLISHED",
                detail="组件尚未发布正式版本，不能升级引用页面或组件。",
            )
        target_component_id = component.id
        target_component_code = component.code
        target_version_no = component.current_version_no

        page_rows = self._build_page_reference_map(
            await self.dependency_repository.list_current_page_references_to_component(target_component_id),
            target_version_no,
        )
        component_rows = self._build_component_reference_map(
            await self.dependency_repository.list_current_component_references_to_component(target_component_id),
            target_version_no,
        )
        response = WorkspaceComponentReferenceUpgradeResponse()

        for page_id in self._unique_positive_ids(payload.page_ids):
            await self._upgrade_page_reference(
                target_component_code=target_component_code,
                target_version_no=target_version_no,
                page_id=page_id,
                reference_rows=page_rows,
                operator_id=user_id,
                response=response,
            )

        for referencing_component_id in self._unique_positive_ids(payload.component_ids):
            await self._upgrade_component_reference(
                target_component_code=target_component_code,
                target_version_no=target_version_no,
                referencing_component_id=referencing_component_id,
                reference_rows=component_rows,
                operator_id=user_id,
                response=response,
            )

        return response

    async def _upgrade_page_reference(
        self,
        *,
        target_component_code: str,
        target_version_no: int,
        page_id: int,
        reference_rows: dict[int, PageComponentReferenceRow],
        operator_id: int,
        response: WorkspaceComponentReferenceUpgradeResponse,
    ) -> None:
        """升级单个页面中的目标组件 import 版本，并生成页面新版本。"""

        row = reference_rows.get(page_id)
        if row is None:
            response.skipped.append(self._build_issue("page", page_id, "REFERENCE_NOT_FOUND", "当前页面未引用该组件。"))
            return
        if row.referenced_component_version_no == target_version_no:
            response.skipped.append(self._build_issue("page", page_id, "ALREADY_CURRENT", "当前页面已引用组件最新版本。"))
            return

        page = await self.page_repository.get_by_id(page_id)
        if page is None:
            response.skipped.append(self._build_issue("page", page_id, "PAGE_NOT_FOUND", "页面不存在或已删除。"))
            return

        updated_content, replacement_count = self._replace_component_import_versions(
            page.page_content,
            component_code=target_component_code,
            target_version_no=target_version_no,
        )
        if replacement_count == 0 or normalize_text_to_lf(updated_content) == normalize_text_to_lf(page.page_content):
            response.skipped.append(self._build_issue("page", page_id, "SOURCE_NOT_CHANGED", "页面源码中未找到可升级的旧版 import。"))
            return

        previous_version_no = page.current_version_no
        try:
            await self.page_version_service.save_new_version(
                page=page,
                page_content=updated_content,
                file_type=PageFileType(page.file_type),
                operator_id=operator_id,
                change_note=f"升级组件 {target_component_code} 到 v{target_version_no}",
            )
            page.updated_by = operator_id
            await self.session.commit()
            response.updated_pages.append(
                WorkspaceComponentReferenceUpgradePageItem(
                    page_id=page.id,
                    page_code=page.code,
                    page_title=page.title,
                    previous_version_no=previous_version_no,
                    current_version_no=page.current_version_no,
                )
            )
        except AppException as error:
            await self.session.rollback()
            response.failures.append(self._build_issue("page", page_id, error.code, error.detail))
        except Exception as error:
            await self.session.rollback()
            response.failures.append(self._build_issue("page", page_id, "PAGE_REFERENCE_UPGRADE_FAILED", str(error)))

    async def _upgrade_component_reference(
        self,
        *,
        target_component_code: str,
        target_version_no: int,
        referencing_component_id: int,
        reference_rows: dict[int, ComponentComponentReferenceRow],
        operator_id: int,
        response: WorkspaceComponentReferenceUpgradeResponse,
    ) -> None:
        """升级引用方组件草稿中的目标组件 import 版本，不自动发布。"""

        row = reference_rows.get(referencing_component_id)
        if row is None:
            response.skipped.append(
                self._build_issue("component", referencing_component_id, "REFERENCE_NOT_FOUND", "当前组件发布版本未引用该组件。")
            )
            return
        if row.referenced_component_version_no == target_version_no:
            response.skipped.append(
                self._build_issue("component", referencing_component_id, "ALREADY_CURRENT", "当前组件已引用组件最新版本。")
            )
            return

        component = await self.component_repository.get_by_id(referencing_component_id)
        if component is None:
            response.skipped.append(
                self._build_issue("component", referencing_component_id, "COMPONENT_NOT_FOUND", "组件不存在或已删除。")
            )
            return

        updated_content, replacement_count = self._replace_component_import_versions(
            component.content,
            component_code=target_component_code,
            target_version_no=target_version_no,
        )
        if replacement_count == 0 or normalize_text_to_lf(updated_content) == normalize_text_to_lf(component.content):
            response.skipped.append(
                self._build_issue("component", referencing_component_id, "SOURCE_NOT_CHANGED", "组件草稿中未找到可升级的旧版 import。")
            )
            return

        try:
            await self.component_version_service.validate_draft_dependencies(
                component=component,
                content=updated_content,
                file_type=component.file_type,
            )
            component.content = normalize_text_to_lf(updated_content)
            component.updated_by = operator_id
            await self.session.commit()
            response.updated_components.append(
                WorkspaceComponentReferenceUpgradeComponentItem(
                    component_id=component.id,
                    component_code=component.code,
                    component_name=component.name,
                    current_version_no=component.current_version_no,
                    draft_referenced_component_version_no=target_version_no,
                )
            )
        except AppException as error:
            await self.session.rollback()
            response.failures.append(self._build_issue("component", referencing_component_id, error.code, error.detail))
        except Exception as error:
            await self.session.rollback()
            response.failures.append(
                self._build_issue("component", referencing_component_id, "COMPONENT_REFERENCE_UPGRADE_FAILED", str(error))
            )

    async def _to_component_reference_item(
        self,
        row: ComponentComponentReferenceRow,
        target_component_code: str,
        target_version_no: int,
    ) -> WorkspaceComponentComponentReferenceItem:
        """将组件引用行补齐草稿状态后转为响应项。"""

        component = await self.component_repository.get_by_id(row.component_id)
        draft_version_no = self._resolve_draft_referenced_version_no(
            component.content if component is not None else "",
            component_code=target_component_code,
            target_version_no=target_version_no,
        )
        has_unpublished_changes = await self._component_has_unpublished_changes(component) if component is not None else False
        is_current_version = row.referenced_component_version_no == target_version_no
        draft_is_current_version = draft_version_no == target_version_no
        return WorkspaceComponentComponentReferenceItem(
            component_id=row.component_id,
            component_code=row.component_code,
            component_name=row.component_name,
            current_version_no=row.current_version_no,
            component_version_id=row.component_version_id,
            referenced_component_version_no=row.referenced_component_version_no,
            has_unpublished_changes=has_unpublished_changes,
            draft_referenced_component_version_no=draft_version_no,
            draft_is_current_version=draft_is_current_version,
            is_current_version=is_current_version,
            can_upgrade=not is_current_version and not draft_is_current_version,
        )

    async def _component_has_unpublished_changes(self, component: WorkspaceComponent | None) -> bool:
        """判断组件草稿相对当前发布版本是否存在未发布变化。"""

        if component is None or component.current_version_no <= 0:
            return True
        latest_version = await self.component_version_repository.get_by_component_and_version(
            component.id,
            component.current_version_no,
        )
        if latest_version is None:
            return True
        return (
            component.draft_base_version_no != component.current_version_no
            or normalize_text_to_lf(component.content) != normalize_text_to_lf(latest_version.content)
            or component.preview_schema != latest_version.preview_schema
            or component.file_type != latest_version.file_type
        )

    async def _get_component_or_raise(self, component_id: int) -> WorkspaceComponent:
        """读取目标组件，不存在时抛出标准错误。"""

        component = await self.component_repository.get_by_id(component_id)
        if component is None:
            raise AppException(status_code=404, code="COMPONENT_NOT_FOUND", detail="组件不存在。")
        return component

    @staticmethod
    def _to_page_reference_item(
        row: PageComponentReferenceRow,
        target_version_no: int,
    ) -> WorkspaceComponentPageReferenceItem:
        """将页面引用行转为接口响应项。"""

        is_current_version = row.referenced_component_version_no == target_version_no
        return WorkspaceComponentPageReferenceItem(
            page_id=row.page_id,
            page_code=row.page_code,
            page_title=row.page_title,
            project_id=row.project_id,
            project_name=row.project_name,
            current_version_no=row.current_version_no,
            page_version_id=row.page_version_id,
            referenced_component_version_no=row.referenced_component_version_no,
            is_current_version=is_current_version,
            can_upgrade=not is_current_version,
        )

    @staticmethod
    def _build_page_reference_map(
        rows: list[PageComponentReferenceRow],
        target_version_no: int,
    ) -> dict[int, PageComponentReferenceRow]:
        """按页面主键整理引用行，优先保留可升级的旧版本引用。"""

        return {
            row.page_id: row
            for row in ComponentReferenceService._deduplicate_page_reference_rows(rows, target_version_no)
        }

    @staticmethod
    def _build_component_reference_map(
        rows: list[ComponentComponentReferenceRow],
        target_version_no: int,
    ) -> dict[int, ComponentComponentReferenceRow]:
        """按组件主键整理引用行，优先保留可升级的旧版本引用。"""

        return {
            row.component_id: row
            for row in ComponentReferenceService._deduplicate_component_reference_rows(rows, target_version_no)
        }

    @staticmethod
    def _deduplicate_page_reference_rows(
        rows: list[PageComponentReferenceRow],
        target_version_no: int,
    ) -> list[PageComponentReferenceRow]:
        """同一页面多次引用目标组件时，优先展示旧版本引用。"""

        selected: dict[int, PageComponentReferenceRow] = {}
        for row in rows:
            current = selected.get(row.page_id)
            if current is None or ComponentReferenceService._prefer_reference_row(
                row.referenced_component_version_no,
                current.referenced_component_version_no,
                target_version_no,
            ):
                selected[row.page_id] = row
        return list(selected.values())

    @staticmethod
    def _deduplicate_component_reference_rows(
        rows: list[ComponentComponentReferenceRow],
        target_version_no: int,
    ) -> list[ComponentComponentReferenceRow]:
        """同一组件多次引用目标组件时，优先展示旧版本引用。"""

        selected: dict[int, ComponentComponentReferenceRow] = {}
        for row in rows:
            current = selected.get(row.component_id)
            if current is None or ComponentReferenceService._prefer_reference_row(
                row.referenced_component_version_no,
                current.referenced_component_version_no,
                target_version_no,
            ):
                selected[row.component_id] = row
        return list(selected.values())

    @staticmethod
    def _prefer_reference_row(candidate_version_no: int, current_version_no: int, target_version_no: int) -> bool:
        """旧版本引用优先；同为旧版本时选更小版本号，便于提示需要升级。"""

        candidate_is_old = candidate_version_no != target_version_no
        current_is_old = current_version_no != target_version_no
        if candidate_is_old != current_is_old:
            return candidate_is_old
        return candidate_version_no < current_version_no

    @staticmethod
    def _replace_component_import_versions(
        source_text: str,
        *,
        component_code: str,
        target_version_no: int,
    ) -> tuple[str, int]:
        """替换源码中目标工作空间组件 import 路径的版本号。"""

        pattern = re.compile(
            rf"(?P<prefix>@workspace-components/{re.escape(component_code)}/v/)"
            r"(?P<version_no>\d+)(?P<suffix>\.vue)?"
        )
        replacement_count = 0

        def replace_match(match: re.Match[str]) -> str:
            nonlocal replacement_count
            version_no = int(match.group("version_no"))
            if version_no == target_version_no:
                return match.group(0)
            replacement_count += 1
            return f"{match.group('prefix')}{target_version_no}{match.group('suffix') or ''}"

        return pattern.sub(replace_match, str(source_text or "")), replacement_count

    @staticmethod
    def _resolve_draft_referenced_version_no(
        source_text: str,
        *,
        component_code: str,
        target_version_no: int,
    ) -> int | None:
        """读取草稿源码中目标组件 import 的版本号，存在当前版本时优先返回当前版本。"""

        pattern = re.compile(
            rf"@workspace-components/{re.escape(component_code)}/v/(?P<version_no>\d+)(?:\.vue)?"
        )
        version_numbers = sorted({int(match.group("version_no")) for match in pattern.finditer(str(source_text or ""))})
        if not version_numbers:
            return None
        if target_version_no in version_numbers:
            return target_version_no
        return version_numbers[-1]

    @staticmethod
    def _unique_positive_ids(values: list[int]) -> list[int]:
        """清理批量入参中的重复或非法主键。"""

        result: list[int] = []
        seen: set[int] = set()
        for value in values:
            normalized = int(value)
            if normalized <= 0 or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def _build_issue(kind: str, item_id: int, code: str, detail: str) -> WorkspaceComponentReferenceUpgradeIssue:
        """构造批量升级跳过或失败明细。"""

        return WorkspaceComponentReferenceUpgradeIssue(kind=kind, id=item_id, code=code, detail=detail)
