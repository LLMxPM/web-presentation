"""文件功能：兼容旧导入路径，将用户模型配置解析为 Pydantic AI 模型实例。"""

from __future__ import annotations

from app.ai.pydantic_model_resolver import PydanticLlmModelResolver


class LlmModelResolver(PydanticLlmModelResolver):
    """保留历史类名，实际使用 Pydantic AI 模型解析逻辑。"""
