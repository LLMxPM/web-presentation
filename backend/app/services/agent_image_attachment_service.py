"""文件功能：管理 Agent 会话图片附件的上传、校验、读取、转存资源与模型输入解析。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from pydantic_ai.messages import BinaryContent, ImageUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.ai.image_refs import (
    AGENT_IMAGE_SOURCE_TOOL_OUTPUT,
    AGENT_IMAGE_SOURCE_USER_UPLOAD,
    build_agent_image_ref,
)
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.models.ai_agent_attachment import AiAgentImageAttachment
from app.models.enums import AssetType, RecordStatus
from app.schemas.agent import AgentImageAttachmentItem, AgentMessageAttachmentItem
from app.services.agent_image_transport_resolver import AgentImageTransportResolver, ResolvedAgentImage
from app.services.asset_service import AssetService
from app.services.object_storage_service import ObjectStorageService

_ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_ALLOWED_IMAGE_SUFFIXES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_ATTACHMENT_STATUS_ACTIVE = RecordStatus.ACTIVE.value
_ATTACHMENT_STATUS_ARCHIVED = RecordStatus.ARCHIVED.value
_TOOL_IMAGE_PREFIX = "ai-agent-tool-images"


class AgentImageAttachmentService:
    """封装 Agent 图片附件全生命周期，确保会话、工作空间和用户边界一致。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        object_storage_service: ObjectStorageService | None = None,
        transport_resolver: AgentImageTransportResolver | None = None,
    ) -> None:
        self.session = session
        self.user_id = user_id
        self.settings = get_settings()
        self.object_storage_service = object_storage_service or ObjectStorageService()
        self.transport_resolver = transport_resolver or AgentImageTransportResolver(self.object_storage_service)
        self._hydrated_image_count = 0
        self._hydrated_image_bytes = 0

    async def upload_image_attachment(
        self,
        *,
        workspace_id: int,
        session_id: str,
        file: UploadFile,
        operator_id: int,
    ) -> AgentImageAttachmentItem:
        """保存一张用户上传图片，返回可用于 Composer 预览的附件信息。"""

        original_name = self._normalize_original_name(file.filename)
        content_type = self._resolve_content_type(original_name, file.content_type)
        content = await self._read_limited_file(file)
        if not content:
            raise AppException(status_code=400, code="AI_IMAGE_ATTACHMENT_EMPTY", detail="图片附件不能为空。")

        sha256 = hashlib.sha256(content).hexdigest()
        suffix = Path(original_name).suffix.lower() or _ALLOWED_IMAGE_CONTENT_TYPES[content_type]
        storage_key = await self.object_storage_service.put_object(
            f"ai-agent-attachments/{self.user_id}/{session_id}/{sha256}{suffix}",
            content,
            content_type,
        )
        attachment = AiAgentImageAttachment(
            user_id=self.user_id,
            workspace_id=workspace_id,
            session_id=session_id,
            source_kind=AGENT_IMAGE_SOURCE_USER_UPLOAD,
            storage_key=storage_key,
            original_name=original_name,
            content_type=content_type,
            file_size=len(content),
            sha256=sha256,
            owned_object=True,
            status=_ATTACHMENT_STATUS_ACTIVE,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(attachment)
        await self.session.commit()
        await self.session.refresh(attachment)
        return self._to_item(attachment)

    async def register_tool_image(
        self,
        *,
        workspace_id: int,
        session_id: str,
        run_id: str,
        content: bytes,
        content_type: str,
        original_name: str,
        tool_name: str | None,
        tool_call_id: str | None,
        source_payload: dict[str, object] | None,
        operator_id: int,
    ) -> AiAgentImageAttachment:
        """把工具返回图片复制为 AI 专用对象，并登记为可持久引用的视觉附件。"""

        normalized_name = self._normalize_original_name(original_name)
        normalized_type = self._resolve_content_type(normalized_name, content_type)
        if not content:
            raise AppException(status_code=400, code="AI_TOOL_IMAGE_EMPTY", detail="工具图片内容不能为空。")
        sha256 = hashlib.sha256(content).hexdigest()
        suffix = Path(normalized_name).suffix.lower() or _ALLOWED_IMAGE_CONTENT_TYPES[normalized_type]
        storage_key = await self.object_storage_service.put_object(
            f"{_TOOL_IMAGE_PREFIX}/{self.user_id}/{session_id}/{run_id}/{sha256}{suffix}",
            content,
            normalized_type,
        )
        attachment = AiAgentImageAttachment(
            user_id=self.user_id,
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            source_kind=AGENT_IMAGE_SOURCE_TOOL_OUTPUT,
            tool_name=(tool_name or "").strip() or None,
            tool_call_id=(tool_call_id or "").strip() or None,
            source_payload_json=dict(source_payload or {}),
            storage_key=storage_key,
            original_name=normalized_name,
            content_type=normalized_type,
            file_size=len(content),
            sha256=sha256,
            owned_object=True,
            status=_ATTACHMENT_STATUS_ACTIVE,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(attachment)
        await self.session.commit()
        await self.session.refresh(attachment)
        return attachment

    async def validate_attachments_for_run(
        self,
        *,
        workspace_id: int,
        session_id: str,
        attachment_ids: Iterable[int],
    ) -> list[AiAgentImageAttachment]:
        """校验 run 引用的附件均属于当前用户、工作空间与会话。"""

        normalized_ids = self._normalize_attachment_ids(attachment_ids)
        if not normalized_ids:
            return []
        statement = select(AiAgentImageAttachment).where(
            AiAgentImageAttachment.id.in_(normalized_ids),
            AiAgentImageAttachment.user_id == self.user_id,
            AiAgentImageAttachment.workspace_id == workspace_id,
            AiAgentImageAttachment.session_id == session_id,
            AiAgentImageAttachment.status == _ATTACHMENT_STATUS_ACTIVE,
        )
        items = list((await self.session.scalars(statement)).all())
        by_id = {item.id: item for item in items}
        missing_ids = [attachment_id for attachment_id in normalized_ids if attachment_id not in by_id]
        if missing_ids:
            raise AppException(
                status_code=403,
                code="AI_IMAGE_ATTACHMENT_SCOPE_DENIED",
                detail="图片附件不存在或不属于当前会话。",
            )
        return [by_id[attachment_id] for attachment_id in normalized_ids]

    async def build_images_for_run(self, attachments: list[AiAgentImageAttachment]) -> list[ResolvedAgentImage]:
        """把附件解析为 Pydantic AI 可接收的图片输入，并携带持久引用元数据。"""

        result: list[ResolvedAgentImage] = []
        for attachment in attachments:
            result.append(await self.resolve_attachment_for_model(attachment))
        return result

    async def resolve_attachment_id_for_model(
        self,
        *,
        attachment_id: int,
        session_id: str,
    ) -> ResolvedAgentImage:
        """按附件 ID 读取当前用户历史图片，并水合为模型输入。"""

        statement = select(AiAgentImageAttachment).where(
            AiAgentImageAttachment.id == attachment_id,
            AiAgentImageAttachment.user_id == self.user_id,
            AiAgentImageAttachment.session_id == session_id,
            AiAgentImageAttachment.status == _ATTACHMENT_STATUS_ACTIVE,
        )
        attachment = await self.session.scalar(statement)
        if attachment is None:
            raise AppException(status_code=404, code="AI_IMAGE_ATTACHMENT_NOT_FOUND", detail="图片附件不存在。")
        return await self.resolve_attachment_for_model(attachment)

    async def resolve_attachment_for_model(self, attachment: AiAgentImageAttachment) -> ResolvedAgentImage:
        """使用短时稳定 URL 或临时 bytes，把单个附件解析成模型图片输入。"""

        ref = build_agent_image_ref(attachment)
        model_url = await self._ensure_model_url(attachment)
        if model_url:
            return ResolvedAgentImage(
                image=ImageUrl(url=model_url, media_type=attachment.content_type, vendor_metadata=_image_vendor_metadata(ref)),
                transport="url",
                url=model_url,
                model_ref=ref,
            )
        content = await self.object_storage_service.read_object(attachment.storage_key)
        self._enforce_local_hydration_limit(content)
        resolved = await self.transport_resolver.resolve_image(
            storage_key=attachment.storage_key,
            content=content,
            mime_type=attachment.content_type,
            original_name=attachment.original_name,
        )
        return self._attach_model_ref(resolved, ref)

    async def mark_run_id(
        self,
        *,
        attachments: list[AiAgentImageAttachment],
        run_id: str,
        operator_id: int,
    ) -> None:
        """把附件绑定到本次 run，便于后续会话历史回显。"""

        if not attachments:
            return
        for attachment in attachments:
            attachment.run_id = run_id
            attachment.updated_by = operator_id
        await self.session.commit()

    async def list_message_attachments(
        self,
        *,
        workspace_id: int,
        session_id: str,
    ) -> dict[str, list[AgentMessageAttachmentItem]]:
        """按 run_id 返回当前会话中可展示的图片附件摘要。"""

        statement = (
            select(AiAgentImageAttachment)
            .where(
                AiAgentImageAttachment.user_id == self.user_id,
                AiAgentImageAttachment.workspace_id == workspace_id,
                AiAgentImageAttachment.session_id == session_id,
                AiAgentImageAttachment.run_id.is_not(None),
                AiAgentImageAttachment.status == _ATTACHMENT_STATUS_ACTIVE,
            )
            .order_by(AiAgentImageAttachment.id.asc())
        )
        result: dict[str, list[AgentMessageAttachmentItem]] = {}
        for attachment in (await self.session.scalars(statement)).all():
            run_id = str(attachment.run_id or "")
            if not run_id:
                continue
            result.setdefault(run_id, []).append(self._to_message_item(attachment))
        return result

    async def list_pending_attachments(
        self,
        *,
        workspace_id: int,
        session_id: str,
    ) -> list[AgentImageAttachmentItem]:
        """返回当前会话中尚未绑定到 run 的待发送图片附件。"""

        statement = (
            select(AiAgentImageAttachment)
            .where(
                AiAgentImageAttachment.user_id == self.user_id,
                AiAgentImageAttachment.workspace_id == workspace_id,
                AiAgentImageAttachment.session_id == session_id,
                AiAgentImageAttachment.run_id.is_(None),
                AiAgentImageAttachment.status == _ATTACHMENT_STATUS_ACTIVE,
            )
            .order_by(AiAgentImageAttachment.id.asc())
        )
        return [self._to_item(attachment) for attachment in (await self.session.scalars(statement)).all()]

    async def read_attachment_content(
        self,
        *,
        workspace_id: int,
        session_id: str,
        attachment_id: int,
    ) -> tuple[AiAgentImageAttachment, bytes]:
        """读取附件原始 bytes，供后端认证图片预览接口返回。"""

        attachment = await self._get_attachment_or_raise(
            workspace_id=workspace_id,
            session_id=session_id,
            attachment_id=attachment_id,
        )
        return attachment, await self.object_storage_service.read_object(attachment.storage_key)

    async def read_attachment_content_by_id(self, *, attachment_id: int) -> tuple[AiAgentImageAttachment, bytes]:
        """按当前用户和附件 ID 读取图片内容，供统一登录态预览入口使用。"""

        statement = select(AiAgentImageAttachment).where(
            AiAgentImageAttachment.id == attachment_id,
            AiAgentImageAttachment.user_id == self.user_id,
            AiAgentImageAttachment.status == _ATTACHMENT_STATUS_ACTIVE,
        )
        attachment = await self.session.scalar(statement)
        if attachment is None:
            raise AppException(status_code=404, code="AI_IMAGE_ATTACHMENT_NOT_FOUND", detail="图片附件不存在。")
        return attachment, await self.object_storage_service.read_object(attachment.storage_key)

    async def archive_attachment(
        self,
        *,
        workspace_id: int,
        session_id: str,
        attachment_id: int,
        operator_id: int,
    ) -> None:
        """软删除未发送或已发送的图片附件；不删除物理对象，避免历史消息失效。"""

        attachment = await self._get_attachment_or_raise(
            workspace_id=workspace_id,
            session_id=session_id,
            attachment_id=attachment_id,
        )
        attachment.status = _ATTACHMENT_STATUS_ARCHIVED
        attachment.updated_by = operator_id
        await self.session.commit()

    async def promote_attachment_to_asset(
        self,
        *,
        workspace_id: int,
        session_id: str,
        attachment_id: int,
        name: str | None,
        description: str | None,
        tags: list[str],
        overwrite: bool,
        operator_id: int,
    ) -> AgentImageAttachmentItem:
        """把图片附件保存为工作空间 image 资源，并回填 promoted_asset_id。"""

        attachment = await self._get_attachment_or_raise(
            workspace_id=workspace_id,
            session_id=session_id,
            attachment_id=attachment_id,
        )
        content = await self.object_storage_service.read_object(attachment.storage_key)
        upload_file = UploadFile(
            BytesIO(content),
            size=len(content),
            filename=attachment.original_name,
            headers=Headers({"content-type": attachment.content_type}),
        )
        asset = await AssetService(self.session).upload_asset(
            workspace_id,
            upload_file,
            AssetType.IMAGE,
            tags,
            name,
            description,
            overwrite=overwrite,
        )
        attachment.promoted_asset_id = asset.id
        attachment.updated_by = operator_id
        await self.session.commit()
        await self.session.refresh(attachment)
        return self._to_item(attachment)

    async def _get_attachment_or_raise(
        self,
        *,
        workspace_id: int,
        session_id: str,
        attachment_id: int,
    ) -> AiAgentImageAttachment:
        """按当前用户、工作空间和会话读取单个 active 附件。"""

        statement = select(AiAgentImageAttachment).where(
            AiAgentImageAttachment.id == attachment_id,
            AiAgentImageAttachment.user_id == self.user_id,
            AiAgentImageAttachment.workspace_id == workspace_id,
            AiAgentImageAttachment.session_id == session_id,
            AiAgentImageAttachment.status == _ATTACHMENT_STATUS_ACTIVE,
        )
        attachment = await self.session.scalar(statement)
        if attachment is None:
            raise AppException(status_code=404, code="AI_IMAGE_ATTACHMENT_NOT_FOUND", detail="图片附件不存在。")
        return attachment

    async def _ensure_model_url(self, attachment: AiAgentImageAttachment) -> str | None:
        """按短时连续会话窗口复用或刷新 S3 presigned URL；local 存储返回 None。"""

        if self.object_storage_service.driver != "s3":
            return None
        if self.settings.ai_image_transport_mode == "base64":
            return None
        now = _utc_now()
        if self._can_reuse_model_url(attachment, now=now):
            attachment.model_url_last_used_at = now
            attachment.updated_by = self.user_id
            await self.session.commit()
            return attachment.model_url

        expires_in = int(self.settings.ai_image_model_url_ttl_seconds)
        model_url = await self.object_storage_service.generate_presigned_url(
            attachment.storage_key,
            original_name=attachment.original_name,
            expires_in=expires_in,
        )
        if not self.transport_resolver._is_model_accessible_url(model_url):
            if self.settings.ai_image_transport_mode == "url":
                raise AppException(
                    status_code=409,
                    code="AI_IMAGE_URL_UNAVAILABLE",
                    detail="当前对象存储无法生成模型可访问的 HTTPS 图片 URL。",
                )
            return None
        attachment.model_url = model_url
        attachment.model_url_expires_at = now + timedelta(seconds=expires_in)
        attachment.model_url_last_used_at = now
        attachment.updated_by = self.user_id
        await self.session.commit()
        return model_url

    def _can_reuse_model_url(self, attachment: AiAgentImageAttachment, *, now: datetime) -> bool:
        """判断缓存的模型 URL 是否仍处于连续会话复用窗口内。"""

        if not attachment.model_url:
            return False
        last_used_at = _align_datetime(attachment.model_url_last_used_at, now)
        expires_at = _align_datetime(attachment.model_url_expires_at, now)
        if last_used_at is None or expires_at is None:
            return False
        if now - last_used_at > timedelta(seconds=int(self.settings.ai_image_model_url_reuse_window_seconds)):
            return False
        return expires_at - now > timedelta(seconds=int(self.settings.ai_image_model_url_expiry_safety_seconds))

    def _enforce_local_hydration_limit(self, content: bytes) -> None:
        """限制 local/base64 视觉历史水合规模，避免 JSON/请求体被历史图片放大。"""

        self._hydrated_image_count += 1
        self._hydrated_image_bytes += len(content)
        if self._hydrated_image_count > int(self.settings.ai_image_history_max_hydrated_images):
            raise AppException(
                status_code=413,
                code="AI_IMAGE_HISTORY_TOO_MANY",
                detail="当前会话历史图片数量过多，请新建会话或减少历史图片后重试。",
            )
        if self._hydrated_image_bytes > int(self.settings.ai_image_history_max_hydrated_bytes):
            raise AppException(
                status_code=413,
                code="AI_IMAGE_HISTORY_TOO_LARGE",
                detail="当前会话历史图片总大小过大，请新建会话或减少历史图片后重试。",
            )

    @staticmethod
    def _attach_model_ref(resolved: ResolvedAgentImage, ref: dict[str, object]) -> ResolvedAgentImage:
        """把持久图片引用写入 Pydantic AI media vendor_metadata，供保存前清洗使用。"""

        image = resolved.image
        if isinstance(image, ImageUrl):
            return ResolvedAgentImage(
                image=ImageUrl(
                    url=image.url,
                    media_type=getattr(image, "media_type", None),
                    vendor_metadata=_image_vendor_metadata(ref),
                ),
                transport=resolved.transport,
                url=resolved.url,
                model_ref=dict(ref),
            )
        if isinstance(image, BinaryContent):
            return ResolvedAgentImage(
                image=BinaryContent(
                    data=image.data,
                    media_type=image.media_type,
                    vendor_metadata=_image_vendor_metadata(ref),
                ),
                transport=resolved.transport,
                url=resolved.url,
                model_ref=dict(ref),
            )
        return ResolvedAgentImage(image=image, transport=resolved.transport, url=resolved.url, model_ref=dict(ref))

    async def _read_limited_file(self, file: UploadFile) -> bytes:
        """按配置大小上限读取上传文件，超过 10MB 立即拒绝。"""

        max_bytes = int(self.settings.ai_image_attachment_max_bytes)
        chunks: list[bytes] = []
        total_size = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_bytes:
                raise AppException(
                    status_code=413,
                    code="AI_IMAGE_ATTACHMENT_TOO_LARGE",
                    detail="单张图片附件不能超过 10MB。",
                )
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _normalize_attachment_ids(attachment_ids: Iterable[int]) -> list[int]:
        """清理附件 ID 列表，保持输入顺序且去重。"""

        result: list[int] = []
        for raw_id in attachment_ids:
            try:
                attachment_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if attachment_id > 0 and attachment_id not in result:
                result.append(attachment_id)
        return result

    @staticmethod
    def _normalize_original_name(file_name: str | None) -> str:
        """归一化上传文件名，避免空名和路径片段进入存储记录。"""

        name = Path(str(file_name or "image.png").replace("\\", "/")).name.strip() or "image.png"
        if Path(name).suffix.lower() not in _ALLOWED_IMAGE_SUFFIXES:
            raise AppException(
                status_code=400,
                code="AI_IMAGE_ATTACHMENT_TYPE_UNSUPPORTED",
                detail="图片附件仅支持 png、jpg、jpeg、webp。",
            )
        return name

    @staticmethod
    def _resolve_content_type(original_name: str, raw_content_type: str | None) -> str:
        """根据文件名和 Content-Type 校验并返回标准 MIME。"""

        suffix = Path(original_name).suffix.lower()
        expected_from_suffix = _ALLOWED_IMAGE_SUFFIXES.get(suffix)
        normalized_type = str(raw_content_type or "").split(";", 1)[0].strip().lower()
        if normalized_type and normalized_type not in _ALLOWED_IMAGE_CONTENT_TYPES:
            raise AppException(
                status_code=400,
                code="AI_IMAGE_ATTACHMENT_TYPE_UNSUPPORTED",
                detail="图片附件仅支持 png、jpg、jpeg、webp。",
            )
        return normalized_type or expected_from_suffix or "image/png"

    def _to_item(self, attachment: AiAgentImageAttachment) -> AgentImageAttachmentItem:
        """把附件模型转换为 Composer 可消费的响应结构。"""

        return AgentImageAttachmentItem(
            id=attachment.id,
            session_id=attachment.session_id,
            source_kind=attachment.source_kind,  # type: ignore[arg-type]
            original_name=attachment.original_name,
            content_type=attachment.content_type,
            file_size=attachment.file_size,
            sha256=attachment.sha256,
            url=self._build_attachment_url(attachment),
            preview_available=attachment.status == _ATTACHMENT_STATUS_ACTIVE,
            promoted_asset_id=attachment.promoted_asset_id,
            status=attachment.status,
            created_at=attachment.created_at.isoformat() if attachment.created_at is not None else None,
        )

    def _to_message_item(self, attachment: AiAgentImageAttachment) -> AgentMessageAttachmentItem:
        """把附件模型转换为会话消息中的展示摘要。"""

        return AgentMessageAttachmentItem(
            id=attachment.id,
            source_kind=attachment.source_kind,  # type: ignore[arg-type]
            original_name=attachment.original_name,
            content_type=attachment.content_type,
            file_size=attachment.file_size,
            url=self._build_attachment_url(attachment),
            preview_available=attachment.status == _ATTACHMENT_STATUS_ACTIVE,
            promoted_asset_id=attachment.promoted_asset_id,
        )

    @staticmethod
    def _build_attachment_url(attachment: AiAgentImageAttachment) -> str:
        """构造需要登录态访问的附件预览 URL。"""

        return f"/api/ai/attachments/images/{attachment.id}/content"


def _image_vendor_metadata(ref: dict[str, object]) -> dict[str, object]:
    """构造 Pydantic AI media vendor metadata，保存前据此还原轻量引用。"""

    return {"detail": "auto", "agent_image_ref": dict(ref)}


def _utc_now() -> datetime:
    """返回 UTC 当前时间。"""

    return datetime.now(tz=UTC)


def _align_datetime(value: datetime | None, reference: datetime) -> datetime | None:
    """对齐数据库返回的 aware/naive datetime，兼容 SQLite 测试环境。"""

    if value is None:
        return None
    if value.tzinfo is None and reference.tzinfo is not None:
        return value.replace(tzinfo=reference.tzinfo)
    if value.tzinfo is not None and reference.tzinfo is None:
        return value.replace(tzinfo=None)
    return value
