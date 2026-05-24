"""文件功能：读取 Runtime Kit 内建能力清单，并按规则生成只读组件预览 artifact。"""

from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.component_preview_schema import parse_component_preview_schema_text
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.runtime_module_policy import get_runtime_kit_capability, list_runtime_kit_capabilities, load_runtime_kit_manifest
from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.component_preview_options import ComponentPreviewOptions
from app.schemas.release import PreviewArtifactResponse
from app.schemas.runtime_kit import RuntimeKitCapabilityItem, RuntimeKitCapabilityKind, RuntimeKitCapabilityListResponse
from app.services.component_preview_service import ComponentPreviewService
from app.services.preview_service import PreviewService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService


class RuntimeKitComponentCapabilityService:
    """Runtime Kit 能力服务，负责目录查询与可预览能力的 artifact 创建。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.workspace_repository = WorkspaceRepository(session)
        self.component_preview_service = ComponentPreviewService(session)
        self.preview_service = PreviewService(session)

    def list_components(
        self,
        *,
        keyword: str | None = None,
        category: str | None = None,
        kind: RuntimeKitCapabilityKind | None = None,
        base_name: str | None = None,
        version_no: int | None = None,
        include_all_versions: bool = False,
        previewable: bool | None = None,
    ) -> RuntimeKitCapabilityListResponse:
        """查询 manifest 中可暴露给 Backend/Agent 的 Runtime Kit 能力目录。"""

        normalized_keyword = str(keyword or "").strip().lower()
        normalized_category = str(category or "").strip()
        normalized_kind = str(kind or "").strip() or None
        items = [
            self._to_capability_item(item)
            for item in list_runtime_kit_capabilities(
                base_name=base_name,
                version_no=version_no,
                include_all_versions=include_all_versions,
            )
            if self._matches_filter(
                item,
                keyword=normalized_keyword,
                category=normalized_category,
                kind=normalized_kind,
                previewable=previewable,
            )
        ]
        manifest_version = str(load_runtime_kit_manifest().get("version") or "").strip() or None
        return RuntimeKitCapabilityListResponse(items=items, total=len(items), manifest_version=manifest_version)

    def get_component(self, name: str) -> RuntimeKitCapabilityItem:
        """读取单个 Runtime Kit 能力详情。"""

        capability = get_runtime_kit_capability(name)
        if capability is None:
            raise AppException(status_code=404, code="RUNTIME_KIT_CAPABILITY_NOT_FOUND", detail="Runtime Kit 能力不存在。")
        return self._to_capability_item(capability)

    async def create_preview_artifact(
        self,
        *,
        name: str,
        workspace_id: int,
        preview_options: ComponentPreviewOptions | dict[str, object] | None,
        tenant_id: str,
    ) -> PreviewArtifactResponse:
        """为 Runtime Kit 可预览组件能力创建只读组件预览 artifact。"""

        settings = get_settings()
        capability = get_runtime_kit_capability(name)
        if capability is None:
            raise AppException(status_code=404, code="RUNTIME_KIT_CAPABILITY_NOT_FOUND", detail="Runtime Kit 能力不存在。")
        if capability["kind"] != "component" or capability["previewable"] is not True:
            raise AppException(
                status_code=400,
                code="RUNTIME_KIT_CAPABILITY_PREVIEW_NOT_ALLOWED",
                detail="当前 Runtime Kit 能力不支持预览 artifact。",
            )

        workspace = await self.workspace_repository.get_by_id(workspace_id)
        if workspace is None:
            raise AppException(status_code=404, code="WORKSPACE_NOT_FOUND", detail="所属工作空间不存在。")

        sandbox_project = await self.component_preview_service._ensure_workspace_preview_project(workspace_id)
        manifest_preview_options = capability.get("preview_options")
        resolved_preview_options = await self.component_preview_service.component_preview_options_service.resolve_options(
            workspace,
            manifest_preview_options if isinstance(manifest_preview_options, dict) else None,
            preview_options,
        )

        preview_schema = self._normalize_preview_schema(capability.get("preview_schema"), capability_name=capability["name"])
        preview_schema_text = json.dumps(preview_schema, ensure_ascii=False) if preview_schema is not None else None
        config_bundle = await self.component_preview_service._build_preview_config_bundle(
            workspace=workspace,
            preview_options=resolved_preview_options,
            component_display_name=str(capability["display_name"]),
            component_version_no=None,
            component_import_path=str(capability["import_path"]),
            component_code=str(capability["name"]),
            preview_schema=preview_schema_text,
            modules_data=[],
            component_source="runtime_kit",
            runtime_kit_component_name=str(capability["name"]),
            runtime_kit_manifest_version=str(capability["manifest_version"]),
        )
        await self.component_preview_service._commit_metadata_backfills()
        asset_mapping, asset_metadata = await self.preview_service._build_workspace_asset_mapping(workspace_id)
        asset_base_url = f"{settings.backend_public_base_url.rstrip('/')}/public/assets/{workspace_id}"
        entry_descriptor = self.component_preview_service._build_entry_descriptor()
        entry_descriptor_payload = entry_descriptor.model_dump(mode="python", exclude_none=True)

        manifest = {
            "artifact_kind": "preview_artifact",
            "tenant_id": tenant_id,
            "preview_kind": "component",
            "owner_scope": {
                "scope_type": "runtime_kit_component",
                "workspace_id": str(workspace_id),
                "runtime_kit_component_name": str(capability["name"]),
                "runtime_kit_manifest_version": str(capability["manifest_version"]),
            },
            "entry_descriptor": entry_descriptor_payload,
            "asset_base_url": asset_base_url,
            "component_preview_mode": "saved",
            "component_source": "runtime_kit",
            "runtime_kit_component_name": str(capability["name"]),
            "runtime_kit_manifest_version": str(capability["manifest_version"]),
            "modules": {},
            "assets": asset_mapping,
            "asset_metadata": asset_metadata,
        }
        artifact_id = await RuntimeArtifactStore().put_artifact(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            project_id=sandbox_project.id,
            artifact_kind="preview_artifact",
            manifest=manifest,
            config_bundle=config_bundle,
            modules_data=[],
        )
        preview_token = TokenService.generate_preview_context_token(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            preview_kind="component",
            scope_type="runtime_kit_component",
            workspace_id=workspace_id,
            entry_descriptor=entry_descriptor_payload,
            asset_base_url=asset_base_url,
            trace_id=f"req-{uuid.uuid4().hex[:8]}",
            component_preview_mode="saved",
            component_source="runtime_kit",
            runtime_kit_component_name=str(capability["name"]),
            runtime_kit_manifest_version=str(capability["manifest_version"]),
        )
        preview_url = (
            f"{settings.backend_public_base_url.rstrip('/')}/preview/artifacts/"
            f"{artifact_id}?{urlencode({'token': preview_token})}"
        )

        return PreviewArtifactResponse(
            preview_url=preview_url,
            artifact_id=artifact_id,
            preview_kind="component",
            entry_descriptor=entry_descriptor,
            viewport_width=resolved_preview_options.page.width,
            viewport_height=resolved_preview_options.page.height,
            workspace_id=workspace_id,
            component_preview_mode="saved",
            component_source="runtime_kit",
            runtime_kit_component_name=str(capability["name"]),
            runtime_kit_manifest_version=str(capability["manifest_version"]),
        )

    @classmethod
    def _matches_filter(
        cls,
        item: dict[str, Any],
        *,
        keyword: str,
        category: str,
        kind: str | None,
        previewable: bool | None,
    ) -> bool:
        """判断能力项是否命中列表筛选条件。"""

        if kind and str(item.get("kind") or "") != kind:
            return False
        if category and str(item.get("category") or "") != category:
            return False
        if previewable is not None and bool(item.get("previewable")) is not previewable:
            return False
        if not keyword:
            return True
        haystack = " ".join(
            [
                str(item.get("kind") or ""),
                str(item.get("base_name") or ""),
                str(item.get("version_no") or ""),
                str(item.get("name") or ""),
                str(item.get("display_name") or ""),
                str(item.get("summary") or ""),
                str(item.get("description") or ""),
                " ".join(str(tag) for tag in item.get("tags", []) or []),
                " ".join(str(line) for line in item.get("usage", []) or []),
                str(item.get("returns") or ""),
                " ".join(str(line) for line in item.get("return_example", []) or []),
                " ".join(str(line) for line in item.get("constraints", []) or []),
            ]
        ).lower()
        return keyword in haystack

    @classmethod
    def _to_capability_item(cls, item: dict[str, Any]) -> RuntimeKitCapabilityItem:
        """将 manifest 能力项归一化为接口响应模型。"""

        return RuntimeKitCapabilityItem.model_validate(
            {
                **item,
                "previewable": bool(item.get("previewable")),
                "preview_schema": cls._normalize_preview_schema(item.get("preview_schema"), capability_name=item["name"]),
                "preview_options": item.get("preview_options") if isinstance(item.get("preview_options"), dict) else None,
                "usage": [str(line).strip() for line in item.get("usage", []) or [] if str(line).strip()],
                "returns": str(item.get("returns") or "").strip() or None,
                "return_example": [
                    str(line).strip()
                    for line in item.get("return_example", []) or []
                    if str(line).strip()
                ],
                "constraints": [str(line).strip() for line in item.get("constraints", []) or [] if str(line).strip()],
                "audiences": [str(line).strip() for line in item.get("audiences", []) or [] if str(line).strip()],
            }
        )

    @staticmethod
    def _normalize_preview_schema(value: Any, *, capability_name: str) -> dict[str, Any] | None:
        """校验并返回 manifest 中的 preview_schema 对象。"""

        if value is None:
            return None
        if not isinstance(value, dict):
            raise AppException(
                status_code=500,
                code="RUNTIME_KIT_COMPONENT_CAPABILITY_INVALID",
                detail=f"Runtime Kit 能力 {capability_name} 的 preview_schema 必须是 JSON 对象。",
            )
        try:
            return parse_component_preview_schema_text(json.dumps(value, ensure_ascii=False))
        except AppException as exc:
            raise AppException(
                status_code=500,
                code="RUNTIME_KIT_COMPONENT_CAPABILITY_INVALID",
                detail=f"Runtime Kit 能力 {capability_name} 的 preview_schema 非法：{exc.detail}",
            ) from exc
