"""文件功能：定义 E2E mock 场景的类型契约，包括场景定义、状态快照、transition 规则与测试错误。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai.messages import ModelResponse

ModelRole = Literal["agent", "vision"]

AGENT_MODEL_ROLE: ModelRole = "agent"
VISION_MODEL_ROLE: ModelRole = "vision"


class MockScenarioError(RuntimeError):
    """mock 场景遇到未知输入或未知状态时抛出的明确测试错误；禁止回退真实模型。"""

    def __init__(
        self,
        *,
        scenario_id: str,
        model_role: ModelRole,
        detail: str,
        observed_tools: tuple[str, ...] = (),
        message_kinds: tuple[str, ...] = (),
    ) -> None:
        """构造带场景定位信息的错误；只携带脱敏后的种类摘要，不包含用户内容。"""

        self.scenario_id = scenario_id
        self.model_role = model_role
        self.observed_tools = observed_tools
        self.message_kinds = message_kinds
        super().__init__(
            f"[e2e-mock scenario={scenario_id} role={model_role}] {detail}"
            f"（observed_tools={list(observed_tools)}, message_kinds={list(message_kinds)}）"
        )


@dataclass(frozen=True, slots=True)
class ScenarioToolCall:
    """描述历史 ModelResponse 中观察到的一次工具调用。"""

    tool_name: str
    tool_call_id: str
    args: Any


@dataclass(frozen=True, slots=True)
class MockConversationState:
    """只从本次 FunctionModel 收到的 ModelMessage 推导的会话状态快照。

    禁止写入进程级可变状态：相同历史必须得到相同快照与相同响应，
    使 deferred 续跑具备幂等性。
    """

    initial_user_input: str
    attachment_ids: tuple[int, ...]
    tool_calls: tuple[ScenarioToolCall, ...]
    tool_returns: Mapping[str, tuple[Any, ...]]
    has_retry_prompt: bool

    def called_tool_names(self) -> tuple[str, ...]:
        """返回按顺序观察到的工具名。"""

        return tuple(item.tool_name for item in self.tool_calls)

    def has_called(self, tool_name: str) -> bool:
        """判断某工具是否已在历史中被调用。"""

        return tool_name in self.called_tool_names()

    def has_tool_return(self, tool_name: str) -> bool:
        """判断某工具是否已回灌真实执行结果（含 deferred result）。"""

        return bool(self.tool_returns.get(tool_name))

    def last_tool_return(self, tool_name: str) -> Any:
        """返回某工具最近一次回灌结果；不存在时返回 None。"""

        returns = self.tool_returns.get(tool_name) or ()
        return returns[-1] if returns else None


@dataclass(frozen=True, slots=True)
class ScenarioTransition:
    """场景状态机的一条迁移规则：匹配当前状态并构造下一次 ModelResponse。"""

    name: str
    match: Callable[[MockConversationState], bool]
    build_response: Callable[[MockConversationState], ModelResponse]


@dataclass(frozen=True, slots=True)
class MockScenario:
    """一个代码定义的有类型内容助手场景。

    - `initial_inputs`：规范化前的唯一自然语言输入候选；
    - `final_expectation`：最终用户可见期望，供 E2E 断言引用；
    - `transitions`：按声明顺序求值，首个匹配者生效。
    """

    scenario_id: str
    model_role: ModelRole
    initial_inputs: tuple[str, ...]
    final_expectation: str
    transitions: tuple[ScenarioTransition, ...]

    def next_response(self, state: MockConversationState) -> ModelResponse:
        """按状态匹配推进场景；无匹配 transition 时抛出明确测试错误。"""

        for transition in self.transitions:
            if transition.match(state):
                return transition.build_response(state)
        raise MockScenarioError(
            scenario_id=self.scenario_id,
            model_role=self.model_role,
            detail=f"场景没有匹配当前状态的 transition（状态包含工具 {list(state.called_tool_names())}）。",
            observed_tools=state.called_tool_names(),
        )
