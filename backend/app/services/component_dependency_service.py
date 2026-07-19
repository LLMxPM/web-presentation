"""文件功能：解析远程模块源码依赖、校验组件引用并维护页面/组件版本依赖索引。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.runtime_module_policy import (
    RUNTIME_REMOTE_COMPONENT_PREFIX,
    RuntimeKitImportDependency,
    get_runtime_kit_capability_by_import_path,
    is_runtime_page_module_path,
    is_runtime_public_local_module,
    is_runtime_public_local_module_path,
    normalize_relative_runtime_module_path,
    normalize_runtime_module_path,
    parse_workspace_component_module_path,
)
from app.models.enums import PageFileType
from app.models.page import Page
from app.models.page_version import PageVersion
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.repositories.module_dependency_repository import ModuleDependencyRepository, ResolvedComponentDependency
from app.repositories.workspace_component_repository import WorkspaceComponentRepository
from app.repositories.workspace_component_version_repository import WorkspaceComponentVersionRepository

_SCRIPT_BLOCK_PATTERN = re.compile(r"<script\b[^>]*>(.*?)</script>", flags=re.IGNORECASE | re.DOTALL)
_STATIC_IMPORT_PATTERN = re.compile(
    r"(?:^|\n)\s*import(?:\s+type)?(?:[\s\w*{},$]+?\s+from\s+)?[\"']([^\"']+)[\"']",
    flags=re.MULTILINE,
)
_DYNAMIC_IMPORT_PATTERN = re.compile(r"\bimport\s*\(", flags=re.MULTILINE)
_REMOTE_COMPONENT_IMPORT_PATTERN = re.compile(
    r"^@workspace-components/(?P<component_code>[A-Za-z0-9_-]+)/v/(?P<version_no>\d+)(?:\.vue)?$"
)
_STATIC_DEFAULT_IMPORT_BINDING_PATTERN = re.compile(
    r"(?:^|\n)[ \t]*import[ \t]+(?!type\b)"
    r"(?P<local_name>[A-Za-z_$][A-Za-z0-9_$]*)[ \t\r\n]+from[ \t\r\n]+"
    r"[\"'](?P<import_path>[^\"']+)[\"']",
    flags=re.MULTILINE,
)


@dataclass(frozen=True)
class ParsedDefaultImportBinding:
    """描述源码中无歧义的规范默认导入本地名与来源路径。"""

    local_name: str
    import_path: str


@dataclass(frozen=True)
class ParsedModuleDependencies:
    """源码解析后得到的远程组件依赖和 Runtime 本地公共模块依赖。"""

    component_imports: tuple[tuple[str, int], ...]
    runtime_local_imports: tuple[RuntimeKitImportDependency, ...]
    page_module_imports: tuple[str, ...]


class ComponentDependencyService:
    """源码依赖服务，负责解析 import、校验边界并维护依赖索引。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.component_repository = WorkspaceComponentRepository(session)
        self.component_version_repository = WorkspaceComponentVersionRepository(session)
        self.repository = ModuleDependencyRepository(session)

    async def rebuild_page_version_dependencies(
        self,
        *,
        page: Page,
        page_version: PageVersion,
        page_content: str,
        file_type: PageFileType | str,
    ) -> None:
        """按页面版本全量重建源码依赖索引。"""

        normalized_file_type = file_type.value if isinstance(file_type, PageFileType) else str(file_type)
        if normalized_file_type != PageFileType.VUE.value:
            await self.repository.replace_page_version_dependencies(
                page_id=page.id,
                page_version_id=page_version.id,
                component_dependencies=[],
                runtime_module_paths=[],
                page_module_paths=[],
            )
            return

        parsed = self.parse_dependencies(
            page_content,
            source_label=f"页面 {page.code}",
            importer_module_path=f"src/views/{page.code}.{normalized_file_type}",
            allow_page_module_imports=True,
        )
        component_dependencies = await self._resolve_component_dependencies(
            workspace_id=page.workspace_id,
            component_refs=parsed.component_imports,
            source_label=f"页面 {page.code}",
        )
        await self.repository.replace_page_version_dependencies(
            page_id=page.id,
            page_version_id=page_version.id,
            component_dependencies=component_dependencies,
            runtime_module_paths=parsed.runtime_local_imports,
            page_module_paths=parsed.page_module_imports,
        )

    async def rebuild_component_version_dependencies(
        self,
        *,
        component: WorkspaceComponent,
        component_version: WorkspaceComponentVersion,
        content: str,
        file_type: PageFileType | str,
    ) -> None:
        """按组件版本全量重建源码依赖索引，并校验无循环引用。"""

        normalized_file_type = file_type.value if isinstance(file_type, PageFileType) else str(file_type)
        if normalized_file_type != PageFileType.VUE.value:
            raise AppException(status_code=400, code="COMPONENT_FILE_TYPE_INVALID", detail="当前阶段仅支持 Vue 组件。")

        parsed = self.parse_dependencies(
            content,
            source_label=f"组件 {component.code}",
            importer_module_path=f"src/workspace-components/{component.code}/v/{component_version.version_no}.vue",
        )
        component_dependencies = await self._resolve_component_dependencies(
            workspace_id=component.workspace_id,
            component_refs=parsed.component_imports,
            source_label=f"组件 {component.code}",
        )
        await self.repository.replace_component_version_dependencies(
            component_id=component.id,
            component_version_id=component_version.id,
            component_dependencies=component_dependencies,
            runtime_module_paths=parsed.runtime_local_imports,
        )
        await self.assert_component_version_has_no_cycle(component_version.id)

    def parse_dependencies(
        self,
        source_text: str,
        *,
        source_label: str,
        importer_module_path: str | None = None,
        allow_page_module_imports: bool = False,
    ) -> ParsedModuleDependencies:
        """从 Vue 源码中解析静态 import 依赖，并校验 Runtime 本地公共模块边界。"""

        script_content = self._extract_script_content(source_text)
        if not script_content:
            return ParsedModuleDependencies(
                component_imports=tuple(),
                runtime_local_imports=tuple(),
                page_module_imports=tuple(),
            )

        if _DYNAMIC_IMPORT_PATTERN.search(script_content):
            raise AppException(
                status_code=400,
                code="REMOTE_MODULE_DYNAMIC_IMPORT_UNSUPPORTED",
                detail=f"{source_label} 暂不支持动态 import，请改为静态 import。",
            )

        component_imports: list[tuple[str, int]] = []
        runtime_local_imports: list[RuntimeKitImportDependency] = []
        page_module_imports: list[str] = []
        for import_source in _STATIC_IMPORT_PATTERN.findall(script_content):
            normalized_source = str(import_source or "").strip()
            if not normalized_source:
                continue

            remote_match = _REMOTE_COMPONENT_IMPORT_PATTERN.match(normalized_source)
            if remote_match:
                component_imports.append(
                    (
                        remote_match.group("component_code"),
                        int(remote_match.group("version_no")),
                    )
                )
                continue

            if normalized_source.startswith(RUNTIME_REMOTE_COMPONENT_PREFIX):
                raise AppException(
                    status_code=400,
                    code="REMOTE_COMPONENT_IMPORT_INVALID",
                    detail=(
                        f"{source_label} 中的组件引用格式不合法：{normalized_source}。"
                        "请使用 @workspace-components/<component_code>/v/<version_no>。"
                    ),
                )

            if normalized_source == "@runtime-kit" or normalized_source.startswith("@runtime-kit/"):
                runtime_dependency = get_runtime_kit_capability_by_import_path(normalized_source)
                if runtime_dependency is None or not is_runtime_public_local_module(normalized_source):
                    raise AppException(
                        status_code=400,
                        code="RUNTIME_LOCAL_IMPORT_FORBIDDEN",
                        detail=(
                            f"{source_label} 引用了未在 Runtime Kit manifest 中开放的模块：{normalized_source}。"
                            "请使用 @runtime-kit 清单中声明的版本化 import_path，例如 Name.v1。"
                        ),
                    )
                runtime_local_imports.append(runtime_dependency)
                continue

            normalized_module_path = normalize_runtime_module_path(normalized_source)
            relative_module_path = (
                normalize_relative_runtime_module_path(normalized_source, importer_module_path)
                if importer_module_path and (normalized_source.startswith("./") or normalized_source.startswith("../"))
                else ""
            )
            candidate_module_path = relative_module_path or normalized_module_path

            if normalized_source.startswith("@/"):
                if allow_page_module_imports and is_runtime_page_module_path(candidate_module_path):
                    page_module_imports.append(candidate_module_path)
                    continue
                if not is_runtime_public_local_module(normalized_source):
                    raise AppException(
                        status_code=400,
                        code="RUNTIME_LOCAL_IMPORT_FORBIDDEN",
                        detail=(
                            f"{source_label} 引用了未开放的 Runtime 本地模块：{normalized_source}。"
                            "当前仅允许使用 @runtime-kit 清单中的版本化基础能力，以及 @workspace-components 组件别名。"
                        ),
                    )
                runtime_dependency = get_runtime_kit_capability_by_import_path(normalized_source)
                if runtime_dependency is not None:
                    runtime_local_imports.append(runtime_dependency)
                continue

            if allow_page_module_imports and is_runtime_page_module_path(candidate_module_path):
                page_module_imports.append(candidate_module_path)
                continue

            component_module_ref = parse_workspace_component_module_path(candidate_module_path)
            if component_module_ref is not None:
                component_imports.append(component_module_ref)
                continue

            if relative_module_path and is_runtime_public_local_module_path(relative_module_path):
                raise AppException(
                    status_code=400,
                    code="RUNTIME_LOCAL_IMPORT_FORBIDDEN",
                    detail=(
                        f"{source_label} 通过相对路径引用了 Runtime Kit 模块：{normalized_source}。"
                        "请改用 manifest 中声明的版本化 @runtime-kit import_path。"
                    ),
                )

        return ParsedModuleDependencies(
            component_imports=tuple(self._deduplicate_pairs(component_imports)),
            runtime_local_imports=tuple(self._deduplicate_runtime_kit_dependencies(runtime_local_imports)),
            page_module_imports=tuple(self._deduplicate_strings(page_module_imports)),
        )

    def parse_default_import_bindings(
        self,
        source_text: str,
    ) -> tuple[ParsedDefaultImportBinding, ...]:
        """提取规范默认导入；同一本地名重复声明时整组忽略，禁止猜测组件身份。"""

        script_content = self._extract_script_content(source_text)
        if not script_content:
            return tuple()

        candidates = [
            ParsedDefaultImportBinding(
                local_name=match.group("local_name"),
                import_path=str(match.group("import_path") or "").strip(),
            )
            for match in _STATIC_DEFAULT_IMPORT_BINDING_PATTERN.finditer(script_content)
            if str(match.group("import_path") or "").strip()
        ]
        local_name_counts: dict[str, int] = {}
        for item in candidates:
            local_name_counts[item.local_name] = local_name_counts.get(item.local_name, 0) + 1
        return tuple(
            item for item in candidates if local_name_counts[item.local_name] == 1
        )

    async def get_page_dependencies(self, page_version_id: int) -> list[dict[str, object]]:
        """读取页面版本依赖并转为统一响应结构。"""

        items = await self.repository.list_page_version_dependencies(page_version_id)
        return [
            {
                "dependency_kind": item.dependency_kind,
                "component_code": item.component_code,
                "component_version_no": item.component_version_no,
                "runtime_module_path": item.runtime_module_path,
                "runtime_kit_name": item.runtime_kit_name,
                "runtime_kit_base_name": item.runtime_kit_base_name,
                "runtime_kit_version_no": item.runtime_kit_version_no,
                "runtime_kit_import_path": item.runtime_kit_import_path,
            }
            for item in items
        ]

    async def get_component_dependencies(self, component_version_id: int) -> list[dict[str, object]]:
        """读取组件版本依赖并转为统一响应结构。"""

        items = await self.repository.list_component_version_dependencies(component_version_id)
        return [
            {
                "dependency_kind": item.dependency_kind,
                "component_code": item.dependency_component_code,
                "component_version_no": item.dependency_component_version_no,
                "runtime_module_path": item.runtime_module_path,
                "runtime_kit_name": item.runtime_kit_name,
                "runtime_kit_base_name": item.runtime_kit_base_name,
                "runtime_kit_version_no": item.runtime_kit_version_no,
                "runtime_kit_import_path": item.runtime_kit_import_path,
            }
            for item in items
        ]

    async def resolve_component_dependencies(
        self,
        *,
        workspace_id: int | None,
        component_refs: tuple[tuple[str, int], ...],
        source_label: str,
    ) -> list[ResolvedComponentDependency]:
        """将源码中的组件别名依赖解析为具体组件版本记录。"""

        return await self._resolve_component_dependencies(
            workspace_id=workspace_id,
            component_refs=component_refs,
            source_label=source_label,
        )

    async def assert_component_version_has_no_cycle(self, component_version_id: int) -> None:
        """对组件版本执行 DFS 循环检测。"""

        visited: set[int] = set()
        stack: set[int] = set()

        async def dfs(current_version_id: int) -> None:
            if current_version_id in stack:
                raise AppException(
                    status_code=400,
                    code="COMPONENT_DEPENDENCY_CYCLE_DETECTED",
                    detail="检测到组件版本循环依赖，请调整组件引用关系。",
                )
            if current_version_id in visited:
                return

            visited.add(current_version_id)
            stack.add(current_version_id)
            for dependency_version_id in await self.repository.list_component_dependency_version_ids(current_version_id):
                await dfs(dependency_version_id)
            stack.remove(current_version_id)

        await dfs(component_version_id)

    async def assert_transient_component_dependencies_have_no_cycle(
        self,
        *,
        root_component_version_id: int | None,
        dependency_version_ids: list[int],
    ) -> None:
        """校验未落库草稿组件的依赖闭包不会回到当前组件版本。"""

        if root_component_version_id is None:
            return

        visited: set[int] = set()
        stack: set[int] = set()

        async def dfs(current_version_id: int) -> None:
            if current_version_id == root_component_version_id:
                raise AppException(
                    status_code=400,
                    code="COMPONENT_DEPENDENCY_CYCLE_DETECTED",
                    detail="检测到组件版本循环依赖，请调整组件引用关系。",
                )
            if current_version_id in stack or current_version_id in visited:
                return

            visited.add(current_version_id)
            stack.add(current_version_id)
            for dependency_version_id in await self.repository.list_component_dependency_version_ids(current_version_id):
                await dfs(dependency_version_id)
            stack.remove(current_version_id)

        for dependency_version_id in dependency_version_ids:
            await dfs(dependency_version_id)

    async def _resolve_component_dependencies(
        self,
        *,
        workspace_id: int | None,
        component_refs: tuple[tuple[str, int], ...],
        source_label: str,
    ) -> list[ResolvedComponentDependency]:
        """将源码中的组件别名依赖解析到具体组件版本记录。"""

        if not component_refs:
            return []

        if workspace_id is None:
            raise AppException(
                status_code=400,
                code="REMOTE_COMPONENT_WORKSPACE_REQUIRED",
                detail=f"{source_label} 所属工作空间不能为空，无法解析工作空间组件依赖。",
            )

        resolved_items: list[ResolvedComponentDependency] = []
        for component_code, version_no in component_refs:
            component = await self.component_repository.get_by_code(component_code)
            if component is None or component.workspace_id != workspace_id:
                raise AppException(
                    status_code=400,
                    code="REMOTE_COMPONENT_NOT_FOUND",
                    detail=f"{source_label} 引用了不存在的工作空间组件版本：{component_code} v{version_no}。",
                )

            component_version = await self.component_version_repository.get_by_component_and_version(component.id, version_no)
            if component_version is None:
                raise AppException(
                    status_code=400,
                    code="REMOTE_COMPONENT_VERSION_NOT_FOUND",
                    detail=f"{source_label} 引用了不存在的工作空间组件版本：{component_code} v{version_no}。",
                )

            resolved_items.append(
                ResolvedComponentDependency(
                    component_id=component.id,
                    component_version_id=component_version.id,
                    component_code=component.code,
                    component_version_no=component_version.version_no,
                )
            )
        return resolved_items

    @staticmethod
    def _extract_script_content(source_text: str) -> str:
        """提取 Vue 文件中的全部 script 块。"""

        blocks = _SCRIPT_BLOCK_PATTERN.findall(str(source_text or ""))
        return "\n".join(blocks) if blocks else ""

    @staticmethod
    def _deduplicate_pairs(items: list[tuple[str, int]]) -> list[tuple[str, int]]:
        """在保留顺序的前提下去重组件版本依赖。"""

        result: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    @staticmethod
    def _deduplicate_strings(items: list[str]) -> list[str]:
        """在保留顺序的前提下去重字符串依赖。"""

        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    @staticmethod
    def _deduplicate_runtime_kit_dependencies(
        items: list[RuntimeKitImportDependency],
    ) -> list[RuntimeKitImportDependency]:
        """在保留顺序的前提下按 import_path 去重 Runtime Kit 依赖。"""

        result: list[RuntimeKitImportDependency] = []
        seen: set[str] = set()
        for item in items:
            if item.import_path in seen:
                continue
            seen.add(item.import_path)
            result.append(item)
        return result
