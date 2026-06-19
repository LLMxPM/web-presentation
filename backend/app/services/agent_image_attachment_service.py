"""文件功能：管理 Agent 会话图片附件的上传、校验、读取、转存资源与模型输入解析。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

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
            storage_key=storage_key,
            original_name=original_name,
            content_type=content_type,
            file_size=len(content),
            sha256=sha256,
            status=_ATTACHMENT_STATUS_ACTIVE,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(attachment)
        await self.session.commit()
        await self.session.refresh(attachment)
        return self._to_item(attachment)

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
        """读取附件对象并解析为 Pydantic AI 可接收的图片输入。"""

        result: list[ResolvedAgentImage] = []
        for attachment in attachments:
            content = await self.object_storage_service.read_object(attachment.storage_key)
            result.append(
                await self.transport_resolver.resolve_image(
                    storage_key=attachment.storage_key,
                    content=content,
                    mime_type=attachment.content_type,
                    original_name=attachment.original_name,
                )
            )
        return result

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
            original_name=attachment.original_name,
            content_type=attachment.content_type,
            file_size=attachment.file_size,
            sha256=attachment.sha256,
            url=self._build_attachment_url(attachment),
            promoted_asset_id=attachment.promoted_asset_id,
            status=attachment.status,
            created_at=attachment.created_at.isoformat() if attachment.created_at is not None else None,
        )

    def _to_message_item(self, attachment: AiAgentImageAttachment) -> AgentMessageAttachmentItem:
        """把附件模型转换为会话消息中的展示摘要。"""

        return AgentMessageAttachmentItem(
            id=attachment.id,
            original_name=attachment.original_name,
            content_type=attachment.content_type,
            file_size=attachment.file_size,
            url=self._build_attachment_url(attachment),
            promoted_asset_id=attachment.promoted_asset_id,
        )

    @staticmethod
    def _build_attachment_url(attachment: AiAgentImageAttachment) -> str:
        """构造需要登录态访问的附件预览 URL。"""

        session_id = quote(attachment.session_id)
        return (
            f"/api/ai/sessions/{session_id}/attachments/images/{attachment.id}/content"
            f"?workspace_id={attachment.workspace_id}&scope_type=workspace"
        )
