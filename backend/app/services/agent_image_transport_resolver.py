"""文件功能：解析 Agent 视觉输入图片的传输方式，在对象存储 URL 与 base64/bytes 之间切换。"""

from __future__ import annotations

import base64
import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from pydantic_ai.messages import BinaryContent, ImageUrl

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.object_storage_service import ObjectStorageService


@dataclass(slots=True)
class ResolvedAgentImage:
    """描述已经可传给 Pydantic AI 的图片对象与实际传输方式。"""

    image: ImageUrl | BinaryContent
    transport: str
    url: str | None = None
    model_ref: dict[str, Any] | None = None


class AgentImageTransportResolver:
    """按部署环境解析图片输入，优先使用可公网访问的 HTTPS URL。"""

    def __init__(self, object_storage_service: ObjectStorageService | None = None) -> None:
        self.settings = get_settings()
        self.object_storage_service = object_storage_service or ObjectStorageService()

    async def resolve_image(
        self,
        *,
        storage_key: str,
        content: bytes,
        mime_type: str,
        original_name: str | None = None,
        prefer_data_url: bool = False,
    ) -> ResolvedAgentImage:
        """根据配置把对象存储图片解析为 Pydantic AI 多模态内容。

        输入为对象 key、图片 bytes 与 MIME；输出包含模型输入对象和本次实际使用的 transport。
        `url` 模式不可生成公网 HTTPS URL 时会显式失败，避免把内网或 Cookie 鉴权地址传给模型。
        """

        mode = self.settings.ai_image_transport_mode
        if mode in {"auto", "url"}:
            presigned_url = await self.object_storage_service.generate_presigned_url(
                storage_key,
                original_name=original_name,
                expires_in=600,
            )
            if self._is_model_accessible_url(presigned_url):
                return ResolvedAgentImage(
                    image=ImageUrl(url=presigned_url, media_type=mime_type, vendor_metadata={"detail": "auto"}),
                    transport="url",
                    url=presigned_url,
                )
            if mode == "url":
                raise AppException(
                    status_code=409,
                    code="AI_IMAGE_URL_UNAVAILABLE",
                    detail="当前对象存储无法生成模型可访问的 HTTPS 图片 URL。",
                )

        if prefer_data_url:
            payload = base64.b64encode(content).decode("ascii")
            data_url = f"data:{mime_type};base64,{payload}"
            return ResolvedAgentImage(
                image=ImageUrl(url=data_url, media_type=mime_type, vendor_metadata={"detail": "auto"}),
                transport="base64-data-url",
            )
        return ResolvedAgentImage(
            image=BinaryContent(data=content, media_type=mime_type, vendor_metadata={"detail": "auto"}),
            transport="base64",
        )

    @staticmethod
    def _is_model_accessible_url(url: str | None) -> bool:
        """判断 URL 是否适合作为模型视觉输入地址。"""

        if not url:
            return False
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False
        host = (parsed.hostname or "").strip().lower()
        if not host or host in {"localhost"} or host.endswith(".local"):
            return False
        try:
            ip_address = ipaddress.ip_address(host)
        except ValueError:
            return True
        return not (
            ip_address.is_private
            or ip_address.is_loopback
            or ip_address.is_link_local
            or ip_address.is_reserved
            or ip_address.is_multicast
        )
