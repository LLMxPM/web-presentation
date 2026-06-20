"""文件功能：验证 Agent 图片引用清洗与 S3 模型 URL 短时复用策略。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from pydantic_ai.messages import BinaryContent, ImageUrl, ModelMessagesTypeAdapter, ModelRequest, UserPromptPart

from app.ai.image_refs import contains_forbidden_image_payload, sanitize_message_history_image_refs
from app.models.ai_agent_attachment import AiAgentImageAttachment
from app.services.agent_image_attachment_service import AgentImageAttachmentService


def test_message_history_images_should_be_replaced_by_agent_image_refs() -> None:
    """保存 Pydantic AI 历史前，应把图片 bytes、data URL 和 presigned URL 都替换或清理掉。"""

    image_ref = {
        "kind": "agent-image-ref",
        "attachment_id": 7,
        "source_kind": "user_upload",
        "sha256": "abc",
        "content_type": "image/png",
        "original_name": "shot.png",
    }
    messages = [
        ModelRequest(
            parts=[
                UserPromptPart(
                    content=[
                        "看图",
                        BinaryContent(data=b"image-bytes", media_type="image/png", vendor_metadata={"agent_image_ref": image_ref}),
                        ImageUrl(url="data:image/png;base64,AAAA", media_type="image/png"),
                        ImageUrl(url="https://oss.example.com/a.png?X-Amz-Signature=secret", media_type="image/png"),
                    ]
                )
            ]
        )
    ]
    dumped = ModelMessagesTypeAdapter.dump_python(messages, mode="json")

    sanitized = sanitize_message_history_image_refs(dumped, image_refs=[image_ref])
    serialized = json.dumps(sanitized, ensure_ascii=False)

    assert '"kind": "agent-image-ref"' in serialized
    assert "aW1hZ2UtYnl0ZXM=" not in serialized
    assert "data:image" not in serialized
    assert "X-Amz-Signature" not in serialized
    assert not contains_forbidden_image_payload(sanitized)


async def test_s3_model_url_should_reuse_within_idle_window_and_refresh_after_gap() -> None:
    """S3 图片在连续窗口内复用同一个 model_url，超过空闲窗口后刷新。"""

    session = _FakeSession()
    storage = _FakeStorage()
    service = AgentImageAttachmentService(session, user_id=1, object_storage_service=storage)
    attachment = AiAgentImageAttachment(
        id=42,
        user_id=1,
        workspace_id=10,
        session_id="session-a",
        source_kind="user_upload",
        storage_key="images/a.png",
        original_name="a.png",
        content_type="image/png",
        file_size=10,
        sha256="abc",
        owned_object=True,
        status="active",
    )

    first = await service.resolve_attachment_for_model(attachment)
    second = await service.resolve_attachment_for_model(attachment)
    attachment.model_url_last_used_at = datetime.now(tz=UTC) - timedelta(hours=3)
    third = await service.resolve_attachment_for_model(attachment)

    assert first.url == second.url
    assert third.url != first.url
    assert storage.generated_count == 2


class _FakeSession:
    """提供 AgentImageAttachmentService 单测所需的最小异步 session 接口。"""

    async def commit(self) -> None:
        """模拟提交。"""


class _FakeStorage:
    """模拟 S3 对象存储并生成可区分的 presigned URL。"""

    driver = "s3"
    generated_count = 0

    async def generate_presigned_url(self, storage_key: str, **_: object) -> str:
        """返回 HTTPS 公网 URL，便于模型可访问性校验通过。"""

        self.generated_count += 1
        return f"https://oss.example.com/{storage_key}?X-Amz-Signature=sig-{self.generated_count}"

    async def read_object(self, storage_key: str) -> bytes:
        """S3 URL 可用时不应读取对象 bytes。"""

        raise AssertionError(f"unexpected read_object({storage_key})")
