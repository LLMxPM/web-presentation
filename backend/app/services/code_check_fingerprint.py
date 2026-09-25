"""文件功能：计算代码检查完整输入指纹，覆盖源码、依赖版本、Runtime Kit、编译配置与主题样式。"""

from __future__ import annotations

import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.runtime_module_policy import (
    build_runtime_module_resolver_config,
    load_runtime_kit_manifest,
)
from app.core.text_normalizer import normalize_text_to_lf
from app.models.enums import RecordStatus
from app.models.font import WorkspaceFontConfig
from app.models.page import Page
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.repositories.module_dependency_repository import ModuleDependencyRepository
from app.services.code_check_result_cache import (
    CODE_CHECK_RULES_VERSION,
    compute_check_fingerprint,
)
from app.services.component_dependency_service import ComponentDependencyService
from app.services.component_validation_profile import (
    COMPONENT_VALIDATION_PROFILE_VERSION,
)
from app.services.page_screenshot_fingerprint_service import (
    PageScreenshotFingerprintService,
)

_PAGE_MODULE_PATH_PATTERN = re.compile(r"^src/views/(?P<code>[A-Za-z0-9_-]+)\.(?P<file_type>[A-Za-z0-9]+)$")


def _sha256_text(value: str) -> str:
    """计算 UTF-8 文本 SHA-256。"""

    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _hash_json_payload(payload: object) -> str:
    """把可 JSON 化载荷压缩为稳定 hash。"""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CodeCheckFingerprintBuilder:
    """按页面/组件代码检查真实输入组装完整指纹。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.dependency_service = ComponentDependencyService(session)
        self.module_dependency_repository = ModuleDependencyRepository(session)

    async def build_page_fingerprint(
        self,
        *,
        workspace_id: int,
        project_id: int,
        source: str,
        importer_module_path: str,
    ) -> str:
        """页面检查指纹：源码 + 依赖版本 + Kit + 编译配置 + 主题样式 + 规则版本。"""

        dependency_identity = await self._resolve_module_graph_identity(
            workspace_id=workspace_id,
            project_id=project_id,
            entry_content=source,
            importer_module_path=importer_module_path,
            allow_page_module_imports=True,
        )
        theme_style_hash = await self._build_theme_style_hash(workspace_id=workspace_id, project_id=project_id)
        payload = {
            "kind": "page",
            "source": normalize_text_to_lf(source),
            "workspace_id": int(workspace_id),
            "project_id": int(project_id),
            "module_path": importer_module_path or "",
            "dependency_identity": dependency_identity,
            "runtime_kit_version": str(load_runtime_kit_manifest().get("version") or ""),
            "compile_config": _hash_json_payload(build_runtime_module_resolver_config()),
            "theme_style": theme_style_hash,
            "check_rules_version": CODE_CHECK_RULES_VERSION,
            "component_validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
        }
        return compute_check_fingerprint(payload)

    async def build_component_fingerprint(
        self,
        *,
        workspace_id: int,
        source: str,
        preview_schema: str | None,
        component_type_value: str,
        profile_key: str,
    ) -> str:
        """组件检查指纹：源码/schema/类型 + 依赖版本 + Kit + 校验 profile + 规则版本。"""

        dependency_identity = await self._resolve_module_graph_identity(
            workspace_id=workspace_id,
            project_id=None,
            entry_content=source,
            importer_module_path=None,
            allow_page_module_imports=False,
        )
        payload = {
            "kind": "component",
            "source": normalize_text_to_lf(source),
            "preview_schema": preview_schema,
            "component_type": component_type_value,
            "profile_key": profile_key,
            "workspace_id": int(workspace_id),
            "dependency_identity": dependency_identity,
            "runtime_kit_version": str(load_runtime_kit_manifest().get("version") or ""),
            "compile_config": _hash_json_payload(build_runtime_module_resolver_config()),
            "theme_style": await self._build_theme_style_hash(workspace_id=workspace_id, project_id=None),
            "check_rules_version": CODE_CHECK_RULES_VERSION,
            "component_validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
        }
        return compute_check_fingerprint(payload)

    async def _resolve_module_graph_identity(
        self,
        *,
        workspace_id: int,
        project_id: int | None,
        entry_content: str,
        importer_module_path: str | None,
        allow_page_module_imports: bool,
    ) -> list[str]:
        """按 artifact 构建相同规则遍历模块图，输出稳定依赖身份 token。"""

        tokens: set[str] = set()
        visited_component_version_ids: set[int] = set()
        visited_page_paths: set[str] = set()
        queued_component_version_ids: list[int] = []
        queued_page_paths: list[str] = []

        parsed = self.dependency_service.parse_dependencies(
            entry_content,
            source_label="代码检查指纹",
            importer_module_path=importer_module_path,
            allow_page_module_imports=allow_page_module_imports,
        )
        for component_code, version_no in parsed.component_imports:
            tokens.add(f"import:{component_code}:v{version_no}")
        queued_page_paths.extend(parsed.page_module_imports)

        # 直接组件引用解析到具体版本后，再按版本依赖索引递归展开。
        resolved = await self.dependency_service.resolve_component_dependencies(
            workspace_id=workspace_id,
            component_refs=parsed.component_imports,
            source_label="代码检查指纹",
        )
        for item in resolved:
            queued_component_version_ids.append(int(item.component_version_id))

        def enqueue_parsed(content: str, importer_path: str | None) -> None:
            nested = self.dependency_service.parse_dependencies(
                content,
                source_label="代码检查指纹",
                importer_module_path=importer_path,
                allow_page_module_imports=allow_page_module_imports,
            )
            for component_code, version_no in nested.component_imports:
                tokens.add(f"import:{component_code}:v{version_no}")
            queued_page_paths.extend(nested.page_module_imports)

        while queued_component_version_ids:
            component_version_id = queued_component_version_ids.pop(0)
            if component_version_id in visited_component_version_ids:
                continue
            visited_component_version_ids.add(component_version_id)
            version = await self.session.get(WorkspaceComponentVersion, component_version_id)
            if version is None:
                tokens.add(f"cv:missing:{component_version_id}")
                continue
            component = await self.session.get(WorkspaceComponent, version.component_id)
            component_code = component.code if component is not None else f"id:{version.component_id}"
            content_hash = version.content_hash or _sha256_text(version.content or "")
            tokens.add(f"cv:{component_code}:v{version.version_no}:{content_hash}")
            for dependency_version_id in await self.module_dependency_repository.list_component_dependency_version_ids(
                component_version_id
            ):
                queued_component_version_ids.append(int(dependency_version_id))

        while queued_page_paths:
            page_path = queued_page_paths.pop(0)
            if page_path in visited_page_paths:
                continue
            visited_page_paths.add(page_path)
            page_identity = await self._resolve_page_module_identity(project_id=project_id, page_path=page_path)
            tokens.add(page_identity[0])
            if page_identity[1] is not None:
                enqueue_parsed(page_identity[1], page_path)

        return sorted(tokens)

    async def _resolve_page_module_identity(self, *, project_id: int | None, page_path: str) -> tuple[str, str | None]:
        """解析页面模块身份 token 与当前源码，供递归依赖展开。"""

        match = _PAGE_MODULE_PATH_PATTERN.match(page_path or "")
        if project_id is None or match is None:
            return f"page:{page_path}:unresolved", None
        page = await self.session.scalar(
            select(Page)
            .where(Page.project_id == project_id)
            .where(Page.code == match.group("code"))
            .where(Page.file_type == match.group("file_type"))
            .where(Page.deleted_at.is_(None))
        )
        if page is None:
            return f"page:{page_path}:missing", None
        content = page.page_content or ""
        return f"page:{page_path}:{_sha256_text(normalize_text_to_lf(content))}", content

    async def _build_theme_style_hash(self, *, workspace_id: int, project_id: int | None) -> str:
        """主题/样式输入 hash：项目主题与画布配置 + 工作空间字体签名。"""

        from app.models.workspace import Project

        fingerprint_service = PageScreenshotFingerprintService(self.session)
        project = await self.session.get(Project, project_id) if project_id is not None else None
        if project is not None:
            page_config_hash = (await fingerprint_service.build_project_snapshot(project)).config_hash
        else:
            page_config_hash = fingerprint_service.build_hash(
                page_config=_default_page_config(),
                theme_key=None,
                theme_config={},
            )

        font_rows = await self.session.execute(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.status == RecordStatus.ACTIVE.value)
            .order_by(WorkspaceFontConfig.asset_name.asc())
        )
        font_signatures = [
            {
                "asset_name": row.asset_name,
                "font_family": row.font_family,
                "font_format": row.font_format,
                "font_weight": row.font_weight,
                "font_style": row.font_style,
                "font_display": row.font_display,
            }
            for row in font_rows.scalars().all()
        ]
        return _hash_json_payload({"page_config": page_config_hash, "fonts": font_signatures})


def _default_page_config():
    """构造默认画布配置，用于无项目场景的主题样式 hash。"""

    from app.schemas.project_app_config import ProjectAppPageConfig

    return ProjectAppPageConfig()
