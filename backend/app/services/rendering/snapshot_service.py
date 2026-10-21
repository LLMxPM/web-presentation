"""文件功能：构建不可变渲染输入快照与预览访问授权。"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from render_contracts.constants import RUNTIME_RENDER_PROTOCOL_VERSION_V2
from render_contracts.tokens import PreviewAccess, canonical_json, sha256_hex
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.runtime_module_policy import load_runtime_kit_manifest
from app.core.time_utils import utc_now
from app.models.page import Page
from app.models.page_version import PageVersion
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.services.owner_resource_token_resolver import (
    OwnerResourceTokenResolver,
    OwnerResourceTokens,
)
from app.services.rendering.credentials import RenderCredentialService
from app.services.rendering.target_resolver import RenderTargetResolver
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)


class RenderSnapshotService:
    """授权后生成不可变输入快照，运行中不再次读取“当前页面配置”。"""

    def __init__(self, session: AsyncSession, *, target_resolver: RenderTargetResolver | None = None) -> None:
        self.session = session
        self.settings = get_settings()
        self.targets = target_resolver or RenderTargetResolver(self.settings)
        self.token_service = TokenService()

    async def build_page_snapshot(
        self,
        *,
        page_id: int,
        artifact_id: str,
        preview_token: str,
        viewport: dict[str, Any],
        operation_options: dict[str, Any],
        preview_url: str = "",
        extra_http_headers: Mapping[str, str] | None = None,
        source_override: str | None = None,
    ) -> dict[str, Any]:
        """固定页面源码版本与展示配置，生成快照 manifest。

        ``source_override`` 用于未落库候选源码。页面诊断必须让快照 digest
        与实际 Runtime artifact 的候选源码一致，不能只哈希数据库当前版本。
        """

        page = await self.session.get(Page, page_id)
        if page is None:
            raise ValueError("页面不存在，无法建立渲染快照。")
        version = await self.session.scalar(
            select(PageVersion)
            .where(PageVersion.page_id == page_id)
            .where(PageVersion.version_no == page.current_version_no)
            .limit(1)
        )
        source = version.content if version is not None else page.page_content
        snapshot_source = source if source_override is None else source_override
        version_no = version.version_no if version is not None else page.current_version_no
        input_material = {
            "page_code": page.code,
            "version_no": version_no,
            "source_sha256": sha256_hex(snapshot_source or ""),
            "source_origin": "candidate_override" if source_override is not None else "page_version",
            "viewport": viewport,
            "operation_options": operation_options,
            "runtime_build_id": artifact_id,
        }
        if source_override is not None:
            from app.services.runtime_artifact_store import RuntimeArtifactStore
            manifest = await RuntimeArtifactStore().get_manifest(artifact_id)
            # 候选的新资源引用已由 artifact builder 解析，不能套用旧版本的依赖索引。
            resource_identity = {"candidate_assets": (manifest or {}).get("asset_metadata") or {},
                                 "candidate_modules": (manifest or {}).get("modules") or {}}
        else:
            resource_identity = await self._resolve_page_resource_identity(
                workspace_id=page.workspace_id,
                page_version_id=version.id if version is not None else None,
            )
        if resource_identity:
            input_material["resource_identity"] = resource_identity
        input_digest = sha256_hex(canonical_json(input_material))
        now = utc_now()
        credentials = RenderCredentialService(self.settings).encrypt_sensitive_payload(
            {
                "preview_token": preview_token,
                "extra_http_headers": dict(extra_http_headers or {}),
                "preview_url": preview_url,
            }
        )
        return {
            "artifact_id": artifact_id,
            "input_digest": input_digest,
            "page_id": page_id,
            "page_code": page.code,
            "version_no": version_no,
            "workspace_id": page.workspace_id,
            "project_id": page.project_id,
            # 短期凭证只保存密文；明文 preview_token 不落库。
            "preview_credentials": credentials,
            "viewport": viewport,
            "operation_options": operation_options,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self.settings.runtime_preview_artifact_ttl_seconds)).isoformat(),
            "storage_kind": "runtime_artifact",
        }

    async def build_component_snapshot(
        self,
        *,
        component_id: str,
        artifact_id: str,
        preview_token: str,
        viewport: dict[str, Any],
        operation_options: dict[str, Any],
        preview_url: str = "",
        extra_http_headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """固定组件源码版本与场景参数。"""

        component = await self.session.get(WorkspaceComponent, component_id)
        if component is None:
            raise ValueError("组件不存在，无法建立渲染快照。")
        version = await self.session.scalar(
            select(WorkspaceComponentVersion)
            .where(WorkspaceComponentVersion.component_id == component_id)
            .where(WorkspaceComponentVersion.version_no == component.current_version_no)
            .limit(1)
        )
        source = (getattr(version, "source_code", None) or getattr(version, "component_source", "")) if version else ""
        version_no = int(getattr(component, "current_version_no", 1) or 1)
        scenarios = list(operation_options.get("scenarios") or [])
        input_material = {
            "component_key": component.key if hasattr(component, "key") else str(component_id),
            "version_no": version_no,
            "source_sha256": sha256_hex(str(source or "")),
            "scenarios": scenarios,
            "viewport": viewport,
            "operation_options": operation_options,
            "runtime_build_id": artifact_id,
        }
        resource_identity = await self._resolve_component_resource_identity(
            workspace_id=getattr(component, "workspace_id", None),
            component_version_id=version.id if version is not None else None,
        )
        if resource_identity:
            input_material["resource_identity"] = resource_identity
        input_digest = sha256_hex(canonical_json(input_material))
        now = utc_now()
        credentials = RenderCredentialService(self.settings).encrypt_sensitive_payload(
            {
                "preview_token": preview_token,
                "extra_http_headers": dict(extra_http_headers or {}),
                "preview_url": preview_url,
            }
        )
        return {
            "artifact_id": artifact_id,
            "input_digest": input_digest,
            "component_id": str(component_id),
            "version_no": version_no,
            "workspace_id": getattr(component, "workspace_id", None),
            "preview_credentials": credentials,
            "viewport": viewport,
            "operation_options": operation_options,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=self.settings.runtime_preview_artifact_ttl_seconds)).isoformat(),
            "storage_kind": "runtime_artifact",
        }

    async def _resolve_page_resource_identity(
        self,
        *,
        workspace_id: int | None,
        page_version_id: int | None,
    ) -> dict[str, Any]:
        """解析页面渲染输入关联资源的实时身份；无资源引用时返回空字典。"""

        if workspace_id is None or page_version_id is None:
            return {}
        resolved = await OwnerResourceTokenResolver(self.session).resolve_page_version_tokens(
            workspace_id=int(workspace_id),
            page_version_id=int(page_version_id),
        )
        return self._build_resource_identity(resolved)

    async def _resolve_component_resource_identity(
        self,
        *,
        workspace_id: int | None,
        component_version_id: int | None,
    ) -> dict[str, Any]:
        """解析组件渲染输入关联资源的实时身份；无资源引用时返回空字典。"""

        if workspace_id is None or component_version_id is None:
            return {}
        resolved = await OwnerResourceTokenResolver(self.session).resolve_component_version_tokens(
            workspace_id=int(workspace_id),
            component_version_id=int(component_version_id),
        )
        return self._build_resource_identity(resolved)

    @staticmethod
    def _build_resource_identity(resolved: OwnerResourceTokens) -> dict[str, Any]:
        """把资源身份结果组装为渲染输入摘要片段；三维引用附带引擎身份。

        资源替换后同一源码版本的渲染输入摘要随之变化，旧 digest 不会冒充当前输入。
        """

        if not resolved.tokens:
            return {}
        identity: dict[str, Any] = {"references": resolved.tokens}
        if resolved.has_model3d:
            identity["engine"] = load_runtime_kit_manifest().get("model3d_engine") or {}
        return identity

    def build_preview_access(self, snapshot: dict[str, Any]) -> PreviewAccess:
        """从快照生成 Renderer 使用的短期预览访问授权。"""

        artifact_id = str(snapshot.get("artifact_id") or "")
        credentials = RenderCredentialService(self.settings).decrypt_sensitive_payload(
            str(snapshot.get("preview_credentials") or "")
        )
        preview_token = str(credentials.get("preview_token") or "")
        extra_http_headers = credentials.get("extra_http_headers") if isinstance(credentials.get("extra_http_headers"), dict) else None
        preview_url = str(credentials.get("preview_url") or "").strip()
        navigation_base = self.targets.navigation_base_url()
        if preview_url:
            resolved_navigation = preview_url
        else:
            resolved_navigation = self.build_preview_navigation_url(
                navigation_base_url=navigation_base,
                artifact_id=artifact_id,
                preview_token=preview_token,
                input_digest=str(snapshot.get("input_digest") or "") or None,
            )
        return PreviewAccess(
            navigation_base_url=resolved_navigation,
            preview_token=preview_token,
            artifact_id=artifact_id,
            expires_at=str(snapshot.get("expires_at") or ""),
            runtime_protocol_version="render-ready.v1",
            asset_base_url=self.targets.asset_base_url(),
            platform_asset_base_url=self.targets.platform_asset_base_url(),
            extra_http_headers=(
                {str(k): str(v) for k, v in extra_http_headers.items()}
                if extra_http_headers
                else None
            ),
        )

    @staticmethod
    def build_preview_navigation_url(
        *,
        navigation_base_url: str,
        artifact_id: str,
        preview_token: str,
        input_digest: str | None = None,
        static_capture: bool = False,
        capture_protocol: str | None = None,
    ) -> str:
        """拼接受保护预览导航地址，并携带捕获标记供 Runtime 固定静态执行上下文。"""

        base = navigation_base_url.rstrip("/")
        params: dict[str, str] = {"artifact": artifact_id, "token": preview_token}
        if input_digest:
            params["input_digest"] = input_digest
        if static_capture:
            params["runtimeCapture"] = "1"
        if capture_protocol == RUNTIME_RENDER_PROTOCOL_VERSION_V2:
            params["runtimeCaptureProtocol"] = "2"
        query = urlencode(params)
        parts = urlsplit(f"{base}/preview")
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
