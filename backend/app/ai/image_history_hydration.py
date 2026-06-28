"""文件功能：在 Agent run 入模前把持久化图片引用临时水合为 Pydantic AI 可用图片内容。"""

from __future__ import annotations

import base64
from typing import Any

from pydantic_ai.messages import BinaryContent, ImageUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.image_refs import AGENT_IMAGE_REF_KIND, normalize_agent_image_ref
from app.services.agent_image_attachment_service import AgentImageAttachmentService


async def hydrate_agent_image_refs(
    *,
    session: AsyncSession,
    user_id: int,
    session_id: str,
    message_json: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把历史 JSON 中的 agent-image-ref 替换成仅驻留内存的图片输入 JSON。"""

    attachment_ids = _collect_attachment_ids(message_json)
    if not attachment_ids:
        return [dict(item) for item in message_json]

    service = AgentImageAttachmentService(session, user_id=user_id)
    resolved_by_id: dict[int, dict[str, Any]] = {}
    for attachment_id in attachment_ids:
        resolved = await service.resolve_attachment_id_for_model(
            attachment_id=attachment_id,
            session_id=session_id,
        )
        resolved_by_id[attachment_id] = _resolved_image_to_model_json(resolved)

    def replace(item: Any) -> Any:
        """递归替换图片引用，保持其它历史 JSON 不变。"""

        if isinstance(item, dict):
            ref = normalize_agent_image_ref(item)
            if ref is not None:
                return dict(resolved_by_id.get(int(ref["attachment_id"]), item))
            return {str(key): replace(child) for key, child in item.items()}
        if isinstance(item, list):
            return [replace(child) for child in item]
        return item

    return replace(message_json)


def _collect_attachment_ids(value: Any) -> list[int]:
    """按出现顺序收集历史 JSON 中的图片附件 ID。"""

    result: list[int] = []

    def visit(item: Any) -> None:
        """递归遍历任意 JSON 结构并去重。"""

        if isinstance(item, dict):
            ref = normalize_agent_image_ref(item)
            if ref is not None:
                attachment_id = int(ref["attachment_id"])
                if attachment_id not in result:
                    result.append(attachment_id)
                return
            for child in item.values():
                visit(child)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return result


def _resolved_image_to_model_json(resolved: Any) -> dict[str, Any]:
    """把 ResolvedAgentImage 转换为 TypeAdapter 可校验的图片 JSON。"""

    ref = normalize_agent_image_ref(getattr(resolved, "model_ref", None))
    metadata = {"detail": "auto"}
    if ref is not None:
        metadata["agent_image_ref"] = ref
    image = getattr(resolved, "image", None)
    if isinstance(image, ImageUrl):
        return {
            "kind": "image-url",
            "url": image.url,
            "force_download": bool(getattr(image, "force_download", False)),
            "media_type": getattr(image, "media_type", None),
            "vendor_metadata": metadata,
        }
    if isinstance(image, BinaryContent):
        return {
            "kind": "binary",
            "data": base64.b64encode(image.data).decode("ascii"),
            "media_type": image.media_type,
            "vendor_metadata": metadata,
        }
    return {"kind": AGENT_IMAGE_REF_KIND, "attachment_id": int(ref["attachment_id"])} if ref else {}
