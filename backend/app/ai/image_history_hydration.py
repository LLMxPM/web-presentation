"""文件功能：在 Agent run 入模前把持久化图片引用临时水合为 Pydantic AI 可用图片内容。"""

from __future__ import annotations

import base64
import copy
import json
import re
from typing import Any

from pydantic_ai.messages import (
    BinaryContent,
    ImageUrl,
    ModelMessagesTypeAdapter,
    ModelRequest,
    SystemPromptPart,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.image_refs import AGENT_IMAGE_REF_KIND, normalize_agent_image_ref
from app.models.ai_agent_attachment import AiAgentImageAttachment
from app.models.asset import WorkspaceAsset
from app.services.agent_image_attachment_service import AgentImageAttachmentService


async def hydrate_agent_image_refs(
    *,
    session: AsyncSession,
    user_id: int,
    session_id: str,
    message_json: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """把历史 JSON 中的 agent-image-ref 替换成仅驻留内存的图片输入 JSON。"""

    reconciled = await reconcile_agent_image_asset_history(
        session=session,
        user_id=user_id,
        session_id=session_id,
        message_json=message_json,
    )
    attachment_ids = _collect_attachment_ids(reconciled)
    if not attachment_ids:
        return reconciled

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

    return replace(reconciled)


async def reconcile_agent_image_asset_history(
    *,
    session: AsyncSession,
    user_id: int,
    session_id: str,
    message_json: list[dict[str, Any]],
    correction_position: str = "end",
) -> list[dict[str, Any]]:
    """按附件实时状态校正图片工具历史，并追加已删除资源的权威提示。"""

    reconciled = copy.deepcopy(message_json)
    tool_attachment_ids = _collect_generate_image_attachment_ids(reconciled)
    serialized_history = json.dumps(message_json, ensure_ascii=False, default=str)
    result = await session.execute(
        select(AiAgentImageAttachment).where(
            AiAgentImageAttachment.user_id == user_id,
            AiAgentImageAttachment.session_id == session_id,
        )
    )
    attachments = list(result.scalars().all())
    relevant_attachments = [
        item
        for item in attachments
        if item.id in tool_attachment_ids
        or _history_mentions_promoted_asset(serialized_history, item)
    ]
    attachments_by_id = {item.id: item for item in relevant_attachments}
    current_asset_ids = {
        item.promoted_asset_id
        for item in relevant_attachments
        if item.promoted_asset_id is not None
    }
    assets_by_id: dict[int, WorkspaceAsset] = {}
    if current_asset_ids:
        assets = list(
            (
                await session.execute(
                    select(WorkspaceAsset).where(
                        WorkspaceAsset.id.in_(current_asset_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        assets_by_id = {item.id: item for item in assets}
    _rewrite_generate_image_results(reconciled, attachments_by_id, assets_by_id)
    deleted_attachments = [
        item
        for item in relevant_attachments
        if item.promoted_asset_id is None and item.last_promoted_asset_id is not None
    ]
    if deleted_attachments:
        marker = _deleted_asset_correction_marker(deleted_attachments)
        if correction_position == "start":
            reconciled[0:0] = marker
        else:
            reconciled.extend(marker)
    return reconciled


def _history_mentions_promoted_asset(
    serialized_history: str, attachment: AiAgentImageAttachment
) -> bool:
    """按资源名或带标签的资源 ID 判断压缩历史是否仍提到附件资源。"""

    if (
        attachment.last_promoted_asset_name
        and attachment.last_promoted_asset_name in serialized_history
    ):
        return True
    asset_id = attachment.last_promoted_asset_id
    if asset_id is None:
        return False
    return bool(
        re.search(
            rf"(?:resource_id|资源\s*ID|资源编号)[^0-9]{{0,8}}{asset_id}(?!\d)",
            serialized_history,
            flags=re.IGNORECASE,
        )
    )


def _collect_generate_image_attachment_ids(
    message_json: list[dict[str, Any]],
) -> set[int]:
    """收集 generate_image 工具返回中的附件 ID。"""

    result: set[int] = set()
    for message in message_json:
        for part in message.get("parts", []) if isinstance(message, dict) else []:
            if not isinstance(part, dict) or part.get("tool_name") != "generate_image":
                continue
            content = part.get("content")
            if not isinstance(content, dict):
                continue
            for item in content.get("attachments", []):
                if isinstance(item, dict) and isinstance(item.get("id"), int):
                    result.add(int(item["id"]))
    return result


def _rewrite_generate_image_results(
    message_json: list[dict[str, Any]],
    attachments_by_id: dict[int, AiAgentImageAttachment],
    assets_by_id: dict[int, WorkspaceAsset],
) -> None:
    """把图片生成工具返回改写为当前资源状态，保留原始附件引用。"""

    for message in message_json:
        for part in message.get("parts", []) if isinstance(message, dict) else []:
            if not isinstance(part, dict) or part.get("tool_name") != "generate_image":
                continue
            content = part.get("content")
            if not isinstance(content, dict):
                continue
            current_assets: list[dict[str, object]] = []
            deleted_assets: list[dict[str, object]] = []
            for item in content.get("attachments", []):
                if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                    continue
                attachment = attachments_by_id.get(int(item["id"]))
                if attachment is None:
                    continue
                item["promoted_asset_id"] = attachment.promoted_asset_id
                if attachment.promoted_asset_id is not None:
                    item["promotion_status"] = "promoted"
                    asset = assets_by_id.get(attachment.promoted_asset_id)
                    if asset is not None:
                        current_assets.append(
                            {
                                "id": asset.id,
                                "name": asset.name,
                                "original_name": asset.original_name,
                            }
                        )
                elif attachment.last_promoted_asset_id is not None:
                    item["promotion_status"] = "deleted"
                    deleted_assets.append(
                        {
                            "attachment_id": attachment.id,
                            "previous_asset_id": attachment.last_promoted_asset_id,
                            "previous_asset_name": attachment.last_promoted_asset_name,
                            "status": "deleted",
                            "message": "资源库副本已删除，会话原图仍可用并可重新保存。",
                        }
                    )
                else:
                    item["promotion_status"] = "never"
            content["assets"] = current_assets
            content["deleted_assets"] = deleted_assets


def _deleted_asset_correction_marker(
    attachments: list[AiAgentImageAttachment],
) -> list[dict[str, Any]]:
    """构造高优先级历史状态校正，覆盖摘要或助手文本中的旧资源描述。"""

    lines = [
        (
            f"attachment_id={item.id}；旧 resource_id={item.last_promoted_asset_id}；"
            f"旧 resource_name={item.last_promoted_asset_name or 'unknown'}；状态=deleted。"
        )
        for item in attachments
    ]
    marker = ModelRequest(
        parts=[
            SystemPromptPart(
                content=(
                    "资源状态校正（优先于此前工具结果、助手文本和压缩摘要）：\n"
                    + "\n".join(lines)
                    + "\n以上旧资源 ID 已失效，不得继续查询、更新或引用；会话原图仍可通过 attachment_id 使用。"
                    "如需工作空间资源，必须从对应附件重新保存。"
                )
            )
        ]
    )
    dumped = ModelMessagesTypeAdapter.dump_python([marker], mode="json")
    return dumped if isinstance(dumped, list) else []


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
