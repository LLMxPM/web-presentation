"""文件功能：提供小米 MiMo OpenAI-compatible Agno 模型适配器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from os import getenv
from typing import Any, Dict, Optional

from agno.exceptions import ModelAuthenticationError
from agno.models.message import Message
from agno.models.openai.like import OpenAILike
from agno.utils.log import log_warning
from agno.utils.openai import _format_file_for_message, audio_to_message, images_to_message


@dataclass
class MiMo(OpenAILike):
    """适配 MiMo Chat Completions 接口，复用 OpenAI-compatible 请求链路。"""

    id: str = "not-provided"
    name: str = "MiMo"
    provider: str = "MiMo"

    api_key: Optional[str] = field(default_factory=lambda: getenv("MIMO_API_KEY"))
    base_url: str = "https://api.xiaomimimo.com/v1"

    supports_native_structured_outputs: bool = False

    def _get_client_params(self) -> Dict[str, Any]:
        """构造 OpenAI SDK client 参数，并优先读取 MIMO_API_KEY。"""

        if not self.api_key:
            self.api_key = getenv("MIMO_API_KEY")
            if not self.api_key:
                raise ModelAuthenticationError(
                    message="MIMO_API_KEY not set. Please set the MIMO_API_KEY environment variable.",
                    model_name=self.name,
                )

        base_params = {
            "api_key": self.api_key,
            "organization": self.organization,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "default_headers": self.default_headers,
            "default_query": self.default_query,
        }
        client_params = {key: value for key, value in base_params.items() if value is not None}
        if self.client_params:
            client_params.update(self.client_params)
        return client_params

    def _format_message(self, message: Message, compress_tool_results: bool = False) -> Dict[str, Any]:
        """把 Agno Message 转成 MiMo 兼容的 OpenAI Chat Completions 消息。"""

        tool_result = message.get_content(use_compressed_content=compress_tool_results)
        message_dict: Dict[str, Any] = {
            "role": self.role_map[message.role] if self.role_map else self.default_role_map[message.role],
            "content": tool_result,
            "name": message.name,
            "tool_call_id": message.tool_call_id,
            "tool_calls": message.tool_calls,
            "reasoning_content": message.reasoning_content,
        }
        message_dict = {key: value for key, value in message_dict.items() if value is not None}

        if (message.images is not None and len(message.images) > 0) or (
            message.audio is not None and len(message.audio) > 0
        ):
            if isinstance(message.content, str):
                message_dict["content"] = [{"type": "text", "text": message.content}]
                if message.images is not None:
                    message_dict["content"].extend(_images_to_mimo_message(message.images))
                if message.audio is not None:
                    message_dict["content"].extend(audio_to_message(audio=message.audio))

        if message.audio_output is not None:
            message_dict["content"] = ""
            message_dict["audio"] = {"id": message.audio_output.id}

        if message.videos is not None and len(message.videos) > 0:
            log_warning("Video input is currently unsupported.")

        if message.tool_calls is not None and len(message.tool_calls) == 0:
            message_dict["tool_calls"] = None

        if message.files is not None:
            content = message_dict.get("content")
            if isinstance(content, str):
                message_dict["content"] = [{"type": "text", "text": content}]
            elif content is None:
                message_dict["content"] = []
            for file in message.files:
                file_part = _format_file_for_message(file)
                if file_part:
                    message_dict["content"].insert(0, file_part)

        if message.content is None:
            message_dict["content"] = ""
        return message_dict


def _images_to_mimo_message(images: Any) -> list[dict[str, Any]]:
    """复用 Agno 图片编码，但移除 MiMo 文档未声明的 image_url.detail 字段。"""

    image_parts = images_to_message(images=images)
    for part in image_parts:
        image_url = part.get("image_url")
        if isinstance(image_url, dict):
            image_url.pop("detail", None)
    return image_parts
