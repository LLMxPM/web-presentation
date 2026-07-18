"""文件功能：从页面规范源码的静态组件导入构建版本绑定的可视化 props 元数据。"""

from __future__ import annotations

import json

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.component_preview_schema import parse_component_preview_schema_text
from app.core.exceptions import AppException
from app.core.runtime_module_policy import (
    RUNTIME_REMOTE_COMPONENT_PREFIX,
    get_runtime_kit_capability_by_import_path,
    get_runtime_kit_component_capability,
    parse_workspace_component_import_path,
)
from app.models.page import Page
from app.repositories.module_dependency_repository import ResolvedComponentDependency
from app.repositories.workspace_component_version_repository import (
    WorkspaceComponentVersionRepository,
)
from app.schemas.page_visual_edit import (
    PageVisualEditComponentLocalName,
    PageVisualEditComponentPropField,
    PageVisualEditComponentPropName,
    PageVisualEditComponentSchema,
    PageVisualEditComponentSelectOption,
)
from app.services.component_dependency_service import (
    ComponentDependencyService,
    ParsedDefaultImportBinding,
)


_COMPONENT_LOCAL_NAME_ADAPTER = TypeAdapter(PageVisualEditComponentLocalName)
_COMPONENT_PROP_NAME_ADAPTER = TypeAdapter(PageVisualEditComponentPropName)
_SUPPORTED_PROP_FIELD_TYPES = {
    "string",
    "textarea",
    "number",
    "boolean",
    "select",
    "json",
}
_OPTIONAL_TEXT_FIELDS = ("label", "description", "placeholder")


class PageVisualEditComponentSchemaService:
    """解析无歧义本地组件导入，并只读取其真实钉住版本的 previewSchema。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        dependency_service: ComponentDependencyService | None = None,
        component_version_repository: WorkspaceComponentVersionRepository | None = None,
    ) -> None:
        self.dependency_service = dependency_service or ComponentDependencyService(
            session
        )
        self.component_version_repository = (
            component_version_repository or WorkspaceComponentVersionRepository(session)
        )

    async def build_for_page(
        self,
        *,
        page: Page,
    ) -> dict[str, PageVisualEditComponentSchema]:
        """返回以页面源码本地标签名为 key 的严格 props 元数据映射。"""

        source_label = f"页面 {page.code}"
        module_path = f"src/views/{page.code}.{page.file_type}"
        parsed_dependencies = self.dependency_service.parse_dependencies(
            page.page_content,
            source_label=source_label,
            importer_module_path=module_path,
            allow_page_module_imports=True,
        )
        resolved_components = (
            await self.dependency_service.resolve_component_dependencies(
                workspace_id=page.workspace_id,
                component_refs=parsed_dependencies.component_imports,
                source_label=source_label,
            )
        )
        resolved_by_ref = {
            (item.component_code, item.component_version_no): item
            for item in resolved_components
        }
        bindings = self.dependency_service.parse_default_import_bindings(
            page.page_content
        )

        result: dict[str, PageVisualEditComponentSchema] = {}
        for binding in bindings:
            schema = await self._build_binding_schema(binding, resolved_by_ref)
            if schema is None:
                continue
            local_name = self._validate_local_name(binding.local_name)
            if local_name is not None:
                result[local_name] = schema
        return result

    async def _build_binding_schema(
        self,
        binding: ParsedDefaultImportBinding,
        resolved_by_ref: dict[tuple[str, int], ResolvedComponentDependency],
    ) -> PageVisualEditComponentSchema | None:
        """按导入来源构建工作空间组件或 Runtime Kit 组件的版本身份。"""

        if binding.import_path.startswith(RUNTIME_REMOTE_COMPONENT_PREFIX):
            return await self._build_workspace_component_schema(
                binding, resolved_by_ref
            )
        return self._build_runtime_kit_component_schema(binding)

    async def _build_workspace_component_schema(
        self,
        binding: ParsedDefaultImportBinding,
        resolved_by_ref: dict[tuple[str, int], ResolvedComponentDependency],
    ) -> PageVisualEditComponentSchema | None:
        """读取 import 精确指定的不可变 WorkspaceComponentVersion，禁止回退最新草稿。"""

        component_ref = parse_workspace_component_import_path(binding.import_path)
        if component_ref is None:
            return None
        component_code, version_no = component_ref
        canonical_path = f"@workspace-components/{component_code}/v/{version_no}"
        if binding.import_path not in {canonical_path, f"{canonical_path}.vue"}:
            return None

        resolved = resolved_by_ref.get(component_ref)
        if resolved is None:
            return None
        component_version = await self.component_version_repository.get_by_id(
            resolved.component_version_id
        )
        if (
            component_version is None
            or component_version.component_id != resolved.component_id
            or component_version.version_no != version_no
        ):
            raise AppException(
                status_code=400,
                code="REMOTE_COMPONENT_VERSION_NOT_FOUND",
                detail=f"页面引用了不存在的工作空间组件版本：{component_code} v{version_no}。",
            )

        return PageVisualEditComponentSchema(
            source="workspace_component",
            import_path=binding.import_path,
            component_code=component_code,
            version_no=version_no,
            props=self._parse_props(component_version.preview_schema),
        )

    def _build_runtime_kit_component_schema(
        self,
        binding: ParsedDefaultImportBinding,
    ) -> PageVisualEditComponentSchema | None:
        """从 Runtime Kit manifest 单一事实源读取可预览组件的 props 元数据。"""

        dependency = get_runtime_kit_capability_by_import_path(binding.import_path)
        if dependency is None:
            return None
        capability = get_runtime_kit_component_capability(dependency.name)
        if capability is None or capability.get("import_path") != binding.import_path:
            return None
        raw_preview_schema = capability.get("preview_schema")
        preview_schema_text = (
            json.dumps(raw_preview_schema, ensure_ascii=False, allow_nan=False)
            if isinstance(raw_preview_schema, dict)
            else None
        )
        return PageVisualEditComponentSchema(
            source="runtime_kit",
            import_path=binding.import_path,
            component_code=dependency.base_name,
            version_no=dependency.version_no,
            props=self._parse_props(preview_schema_text),
        )

    @classmethod
    def _parse_props(
        cls,
        preview_schema_text: str | None,
    ) -> dict[str, PageVisualEditComponentPropField] | None:
        """复用现有 previewSchema 校验，并仅提取可安全展示的 props UI 字段。"""

        parsed_schema = parse_component_preview_schema_text(preview_schema_text)
        if parsed_schema is None:
            return None
        raw_props = parsed_schema.get("props")
        if not isinstance(raw_props, dict):
            return {}

        result: dict[str, PageVisualEditComponentPropField] = {}
        for raw_name, raw_field in raw_props.items():
            prop_name = cls._validate_prop_name(raw_name)
            prop_field = cls._parse_prop_field(raw_field)
            if prop_name is not None and prop_field is not None:
                result[prop_name] = prop_field
        return result

    @staticmethod
    def _parse_prop_field(raw_field: object) -> PageVisualEditComponentPropField | None:
        """过滤非 props UI 字段；不完整或不支持的控件保持不下发。"""

        if (
            not isinstance(raw_field, dict)
            or raw_field.get("type") not in _SUPPORTED_PROP_FIELD_TYPES
        ):
            return None
        payload: dict[str, object] = {"type": raw_field["type"]}
        for key in _OPTIONAL_TEXT_FIELDS:
            value = raw_field.get(key)
            if isinstance(value, str) and (key == "placeholder" or value.strip()):
                payload[key] = value
        if isinstance(raw_field.get("required"), bool):
            payload["required"] = raw_field["required"]
        if "default" in raw_field:
            payload["default"] = raw_field["default"]
        if isinstance(raw_field.get("options"), list):
            payload["options"] = (
                PageVisualEditComponentSchemaService._parse_select_options(
                    raw_field["options"]
                )
            )
        try:
            return PageVisualEditComponentPropField.model_validate(payload)
        except ValidationError:
            return None

    @staticmethod
    def _parse_select_options(
        raw_options: list[object],
    ) -> list[PageVisualEditComponentSelectOption]:
        """过滤 select 中结构不完整的选项，保留有限 JSON 标量值。"""

        result: list[PageVisualEditComponentSelectOption] = []
        for raw_option in raw_options:
            if not isinstance(raw_option, dict):
                continue
            try:
                result.append(
                    PageVisualEditComponentSelectOption.model_validate(
                        {
                            "label": raw_option.get("label"),
                            "value": raw_option.get("value"),
                        }
                    )
                )
            except ValidationError:
                continue
        return result

    @staticmethod
    def _validate_local_name(value: object) -> str | None:
        """校验默认导入本地名可以安全作为 component_schemas key。"""

        try:
            return _COMPONENT_LOCAL_NAME_ADAPTER.validate_python(value, strict=True)
        except ValidationError:
            return None

    @staticmethod
    def _validate_prop_name(value: object) -> str | None:
        """校验 previewSchema prop 名，非法名称不进入公开映射。"""

        try:
            return _COMPONENT_PROP_NAME_ADAPTER.validate_python(value, strict=True)
        except ValidationError:
            return None


__all__ = ["PageVisualEditComponentSchemaService"]
