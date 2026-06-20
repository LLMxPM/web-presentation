"""文件功能：定义 Agent 图片引用 JSON 结构，并提供模型历史保存前的图片载荷清洗能力。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from pydantic_ai.messages import BinaryContent, ImageUrl

AGENT_IMAGE_REF_KIND = "agent-image-ref"
AGENT_IMAGE_SOURCE_USER_UPLOAD = "user_upload"
AGENT_IMAGE_SOURCE_TOOL_OUTPUT = "tool_output"

_MODEL_IMAGE_KINDS = {"binary", "image-url"}
_SIGNED_URL_PATTERN = re.compile(
    r"https://[^\s\"'<>]*(?:X-Amz-Signature|X-Amz-Credential|AWSAccessKeyId|Signature=)[^\s\"'<>]*",
    flags=re.IGNORECASE,
)
_DATA_IMAGE_PATTERN = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=_-]+")


def build_agent_image_ref(attachment: Any) -> dict[str, Any]:
    """从附件 ORM 或同形对象构造可持久化的轻量图片引用。"""

    return normalize_agent_image_ref(
        {
            "kind": AGENT_IMAGE_REF_KIND,
            "attachment_id": getattr(attachment, "id", None),
            "source_kind": getattr(attachment, "source_kind", None) or AGENT_IMAGE_SOURCE_USER_UPLOAD,
            "tool_name": getattr(attachment, "tool_name", None),
            "sha256": getattr(attachment, "sha256", None),
            "content_type": getattr(attachment, "content_type", None),
            "original_name": getattr(attachment, "original_name", None),
        }
    )


def normalize_agent_image_ref(value: Any) -> dict[str, Any] | None:
    """校验并规整 agent-image-ref；无效输入返回 None。"""

    if not isinstance(value, dict) or value.get("kind") != AGENT_IMAGE_REF_KIND:
        return None
    try:
        attachment_id = int(value.get("attachment_id"))
    except (TypeError, ValueError):
        return None
    if attachment_id <= 0:
        return None
    source_kind = str(value.get("source_kind") or AGENT_IMAGE_SOURCE_USER_UPLOAD).strip()
    if source_kind not in {AGENT_IMAGE_SOURCE_USER_UPLOAD, AGENT_IMAGE_SOURCE_TOOL_OUTPUT}:
        source_kind = AGENT_IMAGE_SOURCE_USER_UPLOAD
    return {
        "kind": AGENT_IMAGE_REF_KIND,
        "attachment_id": attachment_id,
        "source_kind": source_kind,
        "tool_name": _optional_str(value.get("tool_name")),
        "sha256": _optional_str(value.get("sha256")),
        "content_type": _optional_str(value.get("content_type")),
        "original_name": _optional_str(value.get("original_name")),
    }


def image_refs_from_resolved_images(resolved_images: Iterable[Any]) -> list[dict[str, Any]]:
    """从本轮已解析图片中提取保存历史时使用的引用列表。"""

    refs: list[dict[str, Any]] = []
    for resolved in resolved_images:
        ref = normalize_agent_image_ref(getattr(resolved, "model_ref", None))
        if ref is not None:
            refs.append(ref)
    return refs


def sanitize_message_history_image_refs(
    value: Any,
    *,
    image_refs: Iterable[dict[str, Any]] | None = None,
) -> Any:
    """把 Pydantic AI 消息中的图片 bytes、data URL 和模型 URL 替换为 agent-image-ref。"""

    pending_refs = [ref for ref in (normalize_agent_image_ref(item) for item in image_refs or []) if ref is not None]
    ref_index = 0

    def next_ref() -> dict[str, Any] | None:
        """按出现顺序消费本轮用户图片引用。"""

        nonlocal ref_index
        if ref_index >= len(pending_refs):
            return None
        ref = pending_refs[ref_index]
        ref_index += 1
        return dict(ref)

    def visit(item: Any) -> Any:
        """递归清理任意 JSON 形态中的模型图片载荷。"""

        if isinstance(item, (BinaryContent, ImageUrl)):
            vendor_ref = _image_ref_from_vendor_metadata(getattr(item, "vendor_metadata", None))
            return vendor_ref or next_ref() or "[图片内容已移除：缺少智能体图片引用]"
        if isinstance(item, dict):
            ref = normalize_agent_image_ref(item)
            if ref is not None:
                return ref
            if item.get("kind") in _MODEL_IMAGE_KINDS:
                vendor_metadata = item.get("vendor_metadata")
                vendor_ref = _image_ref_from_vendor_metadata(vendor_metadata)
                return vendor_ref or next_ref() or "[图片内容已移除：缺少智能体图片引用]"
            return {str(key): visit(child) for key, child in item.items()}
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, str):
            return _redact_sensitive_image_payloads(item)
        return item

    return visit(value)


def contains_forbidden_image_payload(value: Any) -> bool:
    """检查 JSON 结构中是否仍包含 base64 图片、data URL 或典型预签名 URL。"""

    if isinstance(value, dict):
        if value.get("kind") == "binary" and value.get("data"):
            return True
        if value.get("kind") == "image-url" and _looks_sensitive_url(value.get("url")):
            return True
        return any(contains_forbidden_image_payload(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_forbidden_image_payload(child) for child in value)
    if isinstance(value, str):
        return bool(_DATA_IMAGE_PATTERN.search(value) or _SIGNED_URL_PATTERN.search(value))
    return False


def _redact_sensitive_image_payloads(value: str) -> str:
    """清理字符串中的 data URL 与典型预签名 URL，避免嵌套 JSON 字符串泄漏。"""

    if "data:image/" in value:
        value = _DATA_IMAGE_PATTERN.sub("[已移除的图片 data URL]", value)
    if "X-Amz-" in value or "AWSAccessKeyId" in value or "Signature=" in value:
        value = _SIGNED_URL_PATTERN.sub("[已移除的模型图片 URL]", value)
    return value


def _looks_sensitive_url(value: Any) -> bool:
    """识别不应写入模型历史 JSON 的 bearer URL。"""

    text = str(value or "")
    return bool(_SIGNED_URL_PATTERN.search(text) or text.startswith("data:image/"))


def _image_ref_from_vendor_metadata(value: Any) -> dict[str, Any] | None:
    """从 media vendor_metadata 中读取标准图片引用。"""

    if not isinstance(value, dict):
        return None
    return normalize_agent_image_ref(value.get("agent_image_ref"))


def _optional_str(value: Any) -> str | None:
    """把可选字段规整为非空字符串。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None
