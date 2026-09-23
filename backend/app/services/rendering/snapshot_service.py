"""文件功能：构建不可变渲染输入快照与预览访问授权。"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time_utils import utc_now
from app.models.page import Page
from app.models.page_version import PageVersion
from app.models.workspace_component import WorkspaceComponent
from app.models.workspace_component_version import WorkspaceComponentVersion
from app.services.rendering.credentials import RenderCredentialService
from app.services.rendering.target_resolver import RenderTargetResolver
from app.services.token_service import TokenService
from render_contracts.tokens import PreviewAccess, canonical_json, sha256_hex

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
        source = version.page_content if version is not None else page.page_content
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
    ) -> str:
        """拼接受保护预览导航地址，并携带 input_digest 供 render-ready 核对。"""

        base = navigation_base_url.rstrip("/")
        params: dict[str, str] = {"artifact": artifact_id, "token": preview_token}
        if input_digest:
            params["input_digest"] = input_digest
        query = urlencode(params)
        parts = urlsplit(f"{base}/preview")
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
