"""文件功能：按 AI_TEST_MODE 与 model ID 前缀分派 E2E mock 模型与适配器，并提供真实模型请求熔断。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.config import get_settings

if TYPE_CHECKING:
    from app.services.image_generation.contracts import ImageGenerationAdapter


def is_mock_mode() -> bool:
    """判断当前进程是否启用了 AI mock 测试模式。"""

    return get_settings().ai_test_mode == "mock"


def resolve_mock_chat_model(config: Any) -> Any | None:
    """按 model ID 前缀分派 agent / vision FunctionModel；非命中或非 mock 返回 None。

    返回 None 表示不替换：普通 model ID 仍走真实解析路径，
    由 ALLOW_MODEL_REQUESTS 熔断阻止其发起真实请求。
    """

    if not is_mock_mode():
        return None
    from app.ai.testing.agent_function_model import build_agent_function_model
    from app.ai.testing.scenarios import AGENT_MOCK_MODEL_PREFIX, VISION_MOCK_MODEL_PREFIX
    from app.ai.testing.vision_function_model import build_vision_function_model

    model_id = str(getattr(config, "model_id", "") or "").strip()
    if model_id.startswith(AGENT_MOCK_MODEL_PREFIX):
        return build_agent_function_model(model_id)
    if model_id.startswith(VISION_MOCK_MODEL_PREFIX):
        return build_vision_function_model(model_id)
    return None


def resolve_mock_image_adapter(config: Any) -> "ImageGenerationAdapter | None":
    """按 model ID 前缀分派图片生成测试适配器；非命中或非 mock 返回 None。"""

    if not is_mock_mode():
        return None
    from app.ai.testing.image_adapter import E2eMockImageGenerationAdapter
    from app.ai.testing.scenarios import IMAGE_MOCK_MODEL_PREFIX

    model_id = str(getattr(config, "model_id", "") or "").strip()
    if model_id.startswith(IMAGE_MOCK_MODEL_PREFIX):
        return E2eMockImageGenerationAdapter()
    return None


def enforce_mock_model_request_fence() -> None:
    """mock 模式启动时关闭 Pydantic AI 全局模型请求开关。

    FunctionModel/TestModel 不受该开关影响；任何未被测试分派接管的
    模型请求会立即失败，防止错误配置意外访问真实供应商。
    """

    import pydantic_ai.models as pydantic_ai_models

    pydantic_ai_models.ALLOW_MODEL_REQUESTS = False
