"""文件功能：E2E mock 测试基础设施包入口，导出场景协议、分派与适配器公共接口。

本包仅在 `AI_TEST_MODE=mock` 下被调用方启用；disabled 模式下入口不可达。
"""

from app.ai.testing.dispatch import (
    enforce_mock_model_request_fence,
    is_mock_mode,
    resolve_mock_chat_model,
    resolve_mock_image_adapter,
)
from app.ai.testing.image_adapter import E2eMockImageGenerationAdapter
from app.ai.testing.scenario_protocol import (
    MockConversationState,
    MockScenario,
    MockScenarioError,
    ScenarioToolCall,
    ScenarioTransition,
)
from app.ai.testing.scenarios import (
    AGENT_MOCK_MODEL_PREFIX,
    IMAGE_MOCK_MODEL_PREFIX,
    SCENARIO_VERSION,
    VISION_MOCK_MODEL_PREFIX,
    normalize_user_input,
    select_agent_scenario,
)

__all__ = [
    "AGENT_MOCK_MODEL_PREFIX",
    "E2eMockImageGenerationAdapter",
    "IMAGE_MOCK_MODEL_PREFIX",
    "MockConversationState",
    "MockScenario",
    "MockScenarioError",
    "SCENARIO_VERSION",
    "ScenarioToolCall",
    "ScenarioTransition",
    "VISION_MOCK_MODEL_PREFIX",
    "enforce_mock_model_request_fence",
    "is_mock_mode",
    "normalize_user_input",
    "resolve_mock_chat_model",
    "resolve_mock_image_adapter",
    "select_agent_scenario",
]
