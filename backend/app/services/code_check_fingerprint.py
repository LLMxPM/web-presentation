"""文件功能：计算代码检查完整输入指纹，覆盖源码、依赖版本、资源、Runtime Kit、编译配置与主题样式。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from render_contracts.screenshot import CAPTURE_POLICY_VERSION
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.runtime_module_policy import (
    build_runtime_module_resolver_config,
    load_runtime_kit_manifest,
)
from app.core.text_normalizer import normalize_text_to_lf
from app.models.asset import WorkspaceAsset
from app.models.enums import RecordStatus
from app.models.font import WorkspaceFontConfig
from app.models.page import Page
from app.models.workspace import Workspace
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.repositories.module_dependency_repository import ModuleDependencyRepository
from app.services.audio_capability_gate import open_audio_capabilities
from app.services.code_check_result_cache import (
    CODE_CHECK_RULES_VERSION,
    compute_check_fingerprint,
)
from app.services.component_dependency_service import ComponentDependencyService
from app.services.component_validation_profile import (
    COMPONENT_VALIDATION_PROFILE_VERSION,
)
from app.services.model3d_acceptance_policy import build_model3d_support_matrix
from app.services.page_render_identity import (
    project_route_catalog,
    routes_need_screenshot_identity,
)
from app.services.page_screenshot_fingerprint_service import (
    PageScreenshotFingerprintService,
)
from app.services.resource_reference_parser import ResourceReferenceParser
from app.services.workspace_theme_service import WorkspaceThemeService
from app.services.theme_asset_fingerprint import collect_theme_asset_identity

_PAGE_MODULE_PATH_PATTERN = re.compile(r"^src/views/(?P<code>[A-Za-z0-9_-]+)\.(?P<file_type>[A-Za-z0-9]+)$")


@dataclass(frozen=True, slots=True)
class ModuleGraphIdentity:
    """源码闭包身份：依赖 token、引用资源名，以及闭包是否能读到路由上下文。"""

    dependency_tokens: list[str]
    asset_names: list[str]
    reads_route_context: bool


@dataclass(frozen=True, slots=True)
class ProjectRenderIdentity:
    """项目级渲染身份快照：同一项目内所有页面共用，避免逐页重复解析路由与配置。

    只覆盖「页面在静态截图里真正能读到」的项目级输入：
    - ``app_title``：项目名会被写成 ``document.title``，页面无需任何导入即可读取；
    - ``route_catalog``：页码目录投影，仅在页面闭包可读路由上下文时进入身份；
    - ``renderer_profile`` / ``capture_policy``：捕获环境与策略版本。
    """

    app_title: str
    route_catalog: dict[str, object] | None
    renderer_profile: str
    capture_policy: str

    def build_render_context(self, *, reads_route_context: bool) -> dict[str, object]:
        """按页面可达性输出渲染上下文身份片段。"""

        context: dict[str, object] = {
            "app_title": self.app_title,
            "renderer_profile": self.renderer_profile,
            "capture_policy": self.capture_policy,
        }
        if reads_route_context and self.route_catalog is not None:
            context["routes"] = self.route_catalog
        return context


def capture_check_fingerprint(diagnostic_fingerprint: str) -> str:
    """有图与无图检查不合并，捕获策略升级必须使结果缓存与发布身份一并失效。"""
    return compute_check_fingerprint({"diagnostics": diagnostic_fingerprint, "capture_screenshot": True,
                                      "capture_policy": CAPTURE_POLICY_VERSION})


def _sha256_text(value: str) -> str:
    """计算 UTF-8 文本 SHA-256。"""

    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _hash_json_payload(payload: object) -> str:
    """把可 JSON 化载荷压缩为稳定 hash。"""

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def audio_capability_identity() -> list[str]:
    """返回当前开放音频能力集合，能力开关变化必须使检查缓存失效。"""

    return sorted(open_audio_capabilities())


def _collect_source_asset_names(*sources: str | None) -> list[str]:
    """从源码与 preview_schema 收集静态资源名。"""

    names: list[str] = []
    for source in sources:
        text = source or ""
        if not text.strip():
            continue
        names.extend(ResourceReferenceParser.collect_static_asset_call_names([text]))
        references = ResourceReferenceParser.collect_vue_asset_references(text)
        names.extend(references.asset_names)
        schema_refs = ResourceReferenceParser.collect_preview_schema_asset_references(text)
        names.extend(schema_refs.asset_names)
    return sorted({name for name in names if name and name != "__DYNAMIC__"})


class CodeCheckFingerprintBuilder:
    """按页面/组件代码检查真实输入组装完整指纹。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.dependency_service = ComponentDependencyService(session)
        self.module_dependency_repository = ModuleDependencyRepository(session)
        self.theme_service = WorkspaceThemeService(session)

    async def build_page_fingerprint(
        self,
        *,
        workspace_id: int,
        project_id: int,
        source: str,
        importer_module_path: str,
        page_metadata: dict[str, object] | None = None,
        runtime_routes_override: dict[str, object] | None = None,
        render_identity: ProjectRenderIdentity | None = None,
    ) -> str:
        """页面检查指纹：源码 + 依赖版本 + 引用资源 + Kit/编译器 + 主题样式 + 规则版本。

        ``render_identity`` 允许调用方按项目预算一次并逐页复用；为空时本方法自行解析。
        """

        graph = await self._resolve_module_graph_identity(
            workspace_id=workspace_id,
            project_id=project_id,
            entry_content=source,
            importer_module_path=importer_module_path,
            allow_page_module_imports=True,
            extra_asset_sources=[source],
        )
        theme_style_hash = await self._build_theme_style_hash(
            workspace_id=workspace_id,
            project_id=project_id,
            for_component=False,
        )
        referenced_assets = await self._resolve_workspace_asset_tokens(
            workspace_id=workspace_id,
            asset_names=graph.asset_names,
        )
        resolved_identity = render_identity or await self.build_project_render_identity(
            project_id,
            runtime_routes_override,
        )
        payload = {
            "kind": "page",
            "source": normalize_text_to_lf(source),
            "workspace_id": int(workspace_id),
            "project_id": int(project_id),
            "module_path": importer_module_path or "",
            # 页面标题与备注只经 vue-router 的 route.meta 或 useCurrentPage 暴露；
            # 不读取路由上下文的页面拿不到它们，变化不应让旧截图过期。
            **({"page_metadata": page_metadata} if graph.reads_route_context and page_metadata else {}),
            "render_context": resolved_identity.build_render_context(
                reads_route_context=graph.reads_route_context,
            ),
            "dependency_identity": graph.dependency_tokens,
            "referenced_assets": referenced_assets,
            "compiler_identity": _compiler_identity(),
            "theme_style": theme_style_hash,
            "check_rules_version": CODE_CHECK_RULES_VERSION,
            "component_validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
            # 能力集合变化必须使旧的 valid 结果失效，避免复用关闭能力期间的缓存。
            "audio_capabilities": audio_capability_identity(),
        }
        return compute_check_fingerprint(payload)

    async def build_project_render_identity(
        self,
        project_id: int,
        runtime_routes_override: dict[str, object] | None = None,
    ) -> ProjectRenderIdentity:
        """按项目解析渲染身份，供同项目多页面批量复用以避免逐页重复查询。

        只纳入静态截图真正能读到的项目级输入：项目名（写入 ``document.title``）、
        页码目录投影（仅对可读路由上下文的页面生效）、渲染档案与捕获策略。
        画布尺寸、字号、描边与主题已由主题样式 hash 覆盖，不再重复计入。
        """
        from app.core.config import get_settings
        from app.models.workspace import Project
        from app.services.project_route_service import ProjectRouteService

        settings = get_settings()
        project = await self.session.get(Project, project_id)
        if project is None:
            return ProjectRenderIdentity(
                app_title="",
                route_catalog=None,
                renderer_profile=settings.render_profile_digest,
                capture_policy=CAPTURE_POLICY_VERSION,
            )
        raw_routes = (
            runtime_routes_override
            if runtime_routes_override is not None
            else await ProjectRouteService(self.session).build_runtime_route_config(project_id)
        )
        return ProjectRenderIdentity(
            app_title=str(project.name or ""),
            route_catalog=project_route_catalog(raw_routes).to_identity_payload(),
            renderer_profile=settings.render_profile_digest,
            capture_policy=CAPTURE_POLICY_VERSION,
        )

    async def build_component_fingerprint(
        self,
        *,
        workspace_id: int,
        source: str,
        preview_schema: str | None,
        component_type_value: str,
        profile_key: str,
    ) -> str:
        """组件检查指纹：源码/schema/类型 + 依赖版本 + 引用资源 + Kit/编译器 + 主题 + 规则版本。"""

        graph = await self._resolve_module_graph_identity(
            workspace_id=workspace_id,
            project_id=None,
            entry_content=source,
            importer_module_path=None,
            allow_page_module_imports=False,
            extra_asset_sources=[source, preview_schema],
        )
        referenced_assets = await self._resolve_workspace_asset_tokens(
            workspace_id=workspace_id,
            asset_names=graph.asset_names,
        )
        payload = {
            "kind": "component",
            "source": normalize_text_to_lf(source),
            "preview_schema": preview_schema,
            "component_type": component_type_value,
            "profile_key": profile_key,
            "workspace_id": int(workspace_id),
            "dependency_identity": graph.dependency_tokens,
            "referenced_assets": referenced_assets,
            "compiler_identity": _compiler_identity(),
            "theme_style": await self._build_theme_style_hash(
                workspace_id=workspace_id,
                project_id=None,
                for_component=True,
            ),
            "check_rules_version": CODE_CHECK_RULES_VERSION,
            "component_validation_profile_version": COMPONENT_VALIDATION_PROFILE_VERSION,
            "audio_capabilities": audio_capability_identity(),
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
        extra_asset_sources: list[str | None],
    ) -> ModuleGraphIdentity:
        """按 artifact 构建相同规则遍历模块图，输出依赖身份 token、引用资源名与路由可达性。

        路由可达性来自整个闭包（入口源码 + 递归组件 + 递归页面模块）的 import：
        只要其中任一处引用 ``vue-router`` 或路由类 Runtime Kit 能力，页面就可能读取
        当前路由、页码或路由目录，此时页码目录投影必须进入截图身份。
        """

        tokens: set[str] = set()
        asset_names: set[str] = set()
        kit_capability_names: set[str] = set()
        bare_import_specifiers: set[str] = set()
        visited_component_version_ids: set[int] = set()
        visited_page_paths: set[str] = set()
        queued_component_version_ids: list[int] = []
        queued_page_paths: list[str] = []

        for name in _collect_source_asset_names(*extra_asset_sources):
            asset_names.add(name)

        def record_parsed(parsed: object) -> None:
            """把一次解析结果并入闭包身份：组件、页面模块、Kit 能力与裸导入。"""

            for component_code, version_no in parsed.component_imports:
                tokens.add(f"import:{component_code}:v{version_no}")
            for runtime_dependency in parsed.runtime_local_imports:
                kit_capability_names.add(runtime_dependency.name)
                tokens.add(f"kit:{runtime_dependency.import_path}")
            for bare_specifier in parsed.bare_imports:
                bare_import_specifiers.add(bare_specifier)
                tokens.add(f"bare:{bare_specifier}")
            queued_page_paths.extend(parsed.page_module_imports)

        parsed = self.dependency_service.parse_dependencies(
            entry_content,
            source_label="代码检查指纹",
            importer_module_path=importer_module_path,
            allow_page_module_imports=allow_page_module_imports,
        )
        record_parsed(parsed)

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
            record_parsed(nested)

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
            # 依赖组件自身引用的资源也进入指纹，替换资源不得复用旧检查结果。
            for name in _collect_source_asset_names(version.content, version.preview_schema):
                asset_names.add(name)
            # 组件的 import 同样决定页面闭包能读到什么，必须参与路由可达性判定。
            enqueue_parsed(version.content or "", None)
            for dependency_version_id in await self.module_dependency_repository.list_component_dependency_version_ids(
                component_version_id
            ):
                queued_component_version_ids.append(int(dependency_version_id))

        while queued_page_paths:
            page_path = queued_page_paths.pop(0)
            if page_path in visited_page_paths:
                continue
            visited_page_paths.add(page_path)
            page_identity, page_content = await self._resolve_page_module_identity(
                project_id=project_id,
                page_path=page_path,
            )
            tokens.add(page_identity)
            if page_content is not None:
                for name in _collect_source_asset_names(page_content):
                    asset_names.add(name)
                enqueue_parsed(page_content, page_path)

        return ModuleGraphIdentity(
            dependency_tokens=sorted(tokens),
            asset_names=sorted(asset_names),
            reads_route_context=routes_need_screenshot_identity(
                kit_capability_names=kit_capability_names,
                bare_import_specifiers=bare_import_specifiers,
            ),
        )

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

    async def _resolve_workspace_asset_tokens(
        self,
        *,
        workspace_id: int,
        asset_names: list[str],
    ) -> list[str]:
        """把引用资源解析为 name:file_hash 身份 token；缺失资源显式记入指纹。"""

        names = sorted({str(name or "").strip() for name in asset_names if str(name or "").strip()})
        if not names:
            return []
        rows = await self.session.execute(
            select(WorkspaceAsset.name, WorkspaceAsset.file_hash)
            .where(WorkspaceAsset.workspace_id == workspace_id)
            .where(WorkspaceAsset.name.in_(names))
            .where(WorkspaceAsset.status == RecordStatus.ACTIVE.value)
        )
        by_name = {str(name): str(file_hash or "") for name, file_hash in rows.all()}
        tokens: list[str] = []
        for name in names:
            file_hash = by_name.get(name)
            if file_hash is None:
                tokens.append(f"asset:{name}:missing")
            else:
                tokens.append(f"asset:{name}:{file_hash}")
        return tokens

    async def _build_theme_style_hash(
        self,
        *,
        workspace_id: int,
        project_id: int | None,
        for_component: bool,
    ) -> str:
        """主题/样式输入 hash：项目主题或工作空间默认主题 + 画布配置 + 字体签名。"""

        from app.models.workspace import Project

        fingerprint_service = PageScreenshotFingerprintService(self.session)
        project = await self.session.get(Project, project_id) if project_id is not None else None
        if project is not None:
            snapshot = await fingerprint_service.build_project_snapshot(project)
            page_config_hash = snapshot.config_hash
            theme_config = snapshot.theme_config
            theme_identity: dict[str, object] = {
                "mode": "project",
                "theme_key": project.theme_key,
            }
        elif for_component:
            # 组件预览基线是工作空间默认主题，不得用空主题导致色板变更不失效。
            workspace = await self.session.get(Workspace, workspace_id)
            theme_key = (workspace.default_theme_key if workspace is not None else None) or None
            theme_config: dict[str, object] = {}
            if theme_key:
                try:
                    theme_config = await self.theme_service.build_theme_config_document_by_key(
                        workspace_id,
                        theme_key,
                    )
                except Exception:  # noqa: BLE001 - 主题缺失时显式记入指纹
                    theme_config = {"__missing_theme__": theme_key}
            page_config_hash = fingerprint_service.build_hash(
                page_config=_default_page_config(),
                theme_key=theme_key,
                theme_config=theme_config,
            )
            theme_identity = {
                "mode": "workspace_default",
                "theme_key": theme_key,
                "theme_config": theme_config,
            }
        else:
            theme_config = {}
            page_config_hash = fingerprint_service.build_hash(
                page_config=_default_page_config(),
                theme_key=None,
                theme_config={},
            )
            theme_identity = {"mode": "none"}

        font_rows = await self.session.execute(
            select(WorkspaceFontConfig)
            .where(WorkspaceFontConfig.workspace_id == workspace_id)
            .where(WorkspaceFontConfig.status == RecordStatus.ACTIVE.value)
            .order_by(WorkspaceFontConfig.asset_name.asc())
        )
        font_configs = font_rows.scalars().all()
        font_signatures = [
            {
                "asset_name": row.asset_name,
                "font_family": row.font_family,
                "font_format": row.font_format,
                "font_weight": row.font_weight,
                "font_style": row.font_style,
                "font_display": row.font_display,
            }
            for row in font_configs
        ]
        return _hash_json_payload({
            "page_config": page_config_hash,
            "theme_identity": theme_identity,
            "fonts": font_signatures,
            "theme_assets": await collect_theme_asset_identity(
                self.session, workspace_id=workspace_id, theme_config=theme_config, fonts=font_configs,
            ),
        })


def _compiler_identity() -> dict[str, object]:
    """编译器/规则身份：Kit 清单内容 hash + 三维规则与引擎身份 + 解析器配置，避免只依赖进程级版本字符串。"""

    manifest = load_runtime_kit_manifest()
    from app.services.runtime_release_identity import current_runtime_release_identity
    # 清单全文入指纹：即使 version 字段未变，exports 结构变化也必须失效缓存。
    manifest_hash = _hash_json_payload(manifest)
    return {
        "runtime_kit_version": str(manifest.get("version") or ""),
        "runtime_kit_manifest_hash": manifest_hash,
        "compile_config": _hash_json_payload(build_runtime_module_resolver_config()),
        "runtime_build": current_runtime_release_identity(),
        # 三维接受规则与运行时引擎策略同源入指纹：规则或引擎策略变化必须使检查缓存失效。
        "model3d_rules_identity": _hash_json_payload(build_model3d_support_matrix()),
        "model3d_engine_identity": _hash_json_payload(manifest.get("model3d_engine") or {}),
    }


def _default_page_config():
    """构造默认画布配置，用于无项目场景的主题样式 hash。"""

    from app.schemas.project_app_config import ProjectAppPageConfig

    return ProjectAppPageConfig()
