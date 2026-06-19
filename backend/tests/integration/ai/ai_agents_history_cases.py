"""文件功能：承载 AI history 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.ai.ai_agents_cases import *  # noqa: F403


async def test_ai_continue_stream_should_not_reinject_current_run_history() -> None:
    """继续 paused run 时不应重复注入当前 run 历史，避免 DeepSeek 工具链顺序校验失败。"""

    class EmptyAsyncIterator:
        """提供空的 Agno 事件流。"""

        def __aiter__(self) -> "EmptyAsyncIterator":
            return self

        async def __anext__(self) -> object:
            raise StopAsyncIteration

    class FakeAgent:
        """记录 continue_run 前的历史注入配置。"""

        def __init__(self) -> None:
            self.add_history_to_context = True
            self.add_history_value_when_continued: bool | None = None
            self.continue_kwargs: dict[str, object] = {}

        def acontinue_run(self, **kwargs: object) -> EmptyAsyncIterator:
            self.add_history_value_when_continued = self.add_history_to_context
            self.continue_kwargs = kwargs
            return EmptyAsyncIterator()

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    facade._registry = SimpleNamespace(
        get_descriptor=lambda agent_id: SimpleNamespace(id=agent_id, llm_slot="component_manager")
    )
    facade._agent_config_service = SimpleNamespace(
        get_effective_runtime_config=lambda agent_id: _async_value(SimpleNamespace())
    )
    facade._llm_service = SimpleNamespace(
        get_bound_config_or_raise=lambda slot: _async_value(SimpleNamespace(supports_image_input=False))
    )
    session_detail = AgentSession(
        session_id="continue-session-1",
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        user_id="1",
        metadata={"workspace_id": 1, "source": "editor-agent-sidebar"},
        runs=[
            RunOutput(
                run_id="continue-run-1",
                session_id="continue-session-1",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.paused,
                messages=[
                    Message(role="user", content="创建组件"),
                    Message(
                        role="assistant",
                        content="准备创建组件",
                        reasoning_content="先整理组件参数",
                        tool_calls=[
                            {
                                "id": "call-create-1",
                                "type": "function",
                                "function": {"name": "create_component", "arguments": "{}"},
                            }
                        ],
                    ),
                ],
            )
        ],
    )
    fake_agent = FakeAgent()

    async def fake_ensure_session_access(**_: object) -> AgentSession:
        return session_detail

    async def fake_build_agent_for_descriptor(*_: object, **__: object) -> tuple[FakeAgent, dict[str, object]]:
        return fake_agent, {}

    async def fake_set_existing_run_status(**_: object) -> None:
        return None

    async def fake_sync_requirement_decision(**_: object) -> None:
        return None

    facade.ensure_session_access = fake_ensure_session_access
    facade._resolve_run_session_metadata = lambda **kwargs: dict(kwargs["metadata"])
    facade._build_agent_for_descriptor = fake_build_agent_for_descriptor
    facade._build_tool_dependencies = lambda **_: {}
    facade._set_existing_run_status = fake_set_existing_run_status
    facade._sync_agno_requirement_decision_before_continue = fake_sync_requirement_decision

    builder = facade._build_continue_stream(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        session_id="continue-session-1",
        scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
        run_id="continue-run-1",
        updated_tool_execution={
            "tool_call_id": "call-create-1",
            "tool_name": "create_component",
            "confirmed": True,
        },
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-agent-sidebar",
        ),
    )

    active_stream = await builder()

    assert active_stream.agent is fake_agent
    assert fake_agent.add_history_value_when_continued is False
    assert "updated_tools" not in fake_agent.continue_kwargs
    requirements = fake_agent.continue_kwargs["requirements"]
    assert len(requirements) == 1
    assert requirements[0].tool_execution.tool_call_id == "call-create-1"

async def test_ai_new_run_should_inject_cancelled_history_to_model_context() -> None:
    """新 run 构造模型上下文时应包含已补偿的 cancelled 历史，且不重复启用 Agno 默认历史。"""

    class EmptyAsyncIterator:
        """提供空的 Agno 事件流。"""

        def __aiter__(self) -> "EmptyAsyncIterator":
            return self

        async def __anext__(self) -> object:
            raise StopAsyncIteration

    class FakeAgent:
        """记录 arun 收到的历史注入参数。"""

        def __init__(self) -> None:
            self.add_history_to_context = True
            self.additional_input: list[Message] | None = None
            self.num_history_runs = None
            self.num_history_messages = 20
            self.max_tool_calls_from_history = 4
            self.system_message_role = "system"
            self.run_kwargs: dict[str, object] = {}

        def arun(self, *_: object, **kwargs: object) -> EmptyAsyncIterator:
            self.run_kwargs = kwargs
            return EmptyAsyncIterator()

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = SimpleNamespace(user=SimpleNamespace(id=1))
    facade._session = None
    facade._registry = SimpleNamespace(
        get_descriptor=lambda agent_id: SimpleNamespace(id=agent_id, llm_slot="component_manager")
    )
    facade._agent_config_service = SimpleNamespace(
        get_effective_runtime_config=lambda agent_id: _async_value(SimpleNamespace())
    )
    facade._llm_service = SimpleNamespace(
        get_bound_config_or_raise=lambda slot: _async_value(SimpleNamespace(supports_image_input=False))
    )
    session_detail = AgentSession(
        session_id="cancelled-history-session",
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        user_id="1",
        metadata={"workspace_id": 1, "source": "editor-agent-sidebar"},
        runs=[
            RunOutput(
                run_id="run-completed-history",
                session_id="cancelled-history-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.completed,
                messages=[
                    Message(role="user", content="上一轮完整问题"),
                    Message(role="assistant", content="上一轮完整回答"),
                ],
            ),
            RunOutput(
                run_id="run-cancelled-history",
                session_id="cancelled-history-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.cancelled,
                messages=[
                    Message(role="user", content="被停止的用户问题"),
                    Message(role="assistant", content="被停止前的局部回答", reasoning_content="已暴露思考"),
                ],
            ),
            RunOutput(
                run_id="run-cancelled-empty-messages",
                session_id="cancelled-history-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.cancelled,
                input=RunInput(input_content="被停止但未写 messages 的问题"),
                content="被停止前已输出的回答",
                reasoning_content="被停止前已输出的思考",
                messages=[],
            ),
            RunOutput(
                run_id="run-error-history",
                session_id="cancelled-history-session",
                agent_id=COMPONENT_MANAGER_AGENT_ID,
                status=RunStatus.error,
                messages=[Message(role="user", content="错误 run 不应进入模型历史")],
            ),
        ],
    )
    fake_agent = FakeAgent()

    async def fake_ensure_session_access(**_: object) -> AgentSession:
        return session_detail

    async def fake_build_agent_for_descriptor(*_: object, **__: object) -> tuple[FakeAgent, dict[str, object]]:
        return fake_agent, {}

    async def fake_upsert_run_marker(**_: object) -> None:
        return None

    facade.ensure_session_access = fake_ensure_session_access
    facade._resolve_run_session_metadata = lambda **kwargs: dict(kwargs["metadata"])
    facade._build_agent_for_descriptor = fake_build_agent_for_descriptor
    facade._build_tool_dependencies = lambda **_: {}
    facade._upsert_run_marker = fake_upsert_run_marker
    facade._ai_db = SimpleNamespace(upsert_session=lambda detail: None)

    builder = facade._build_run_stream(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        session_id="cancelled-history-session",
        scope=AgentScopeContext(scope_type="workspace", workspace_id=1, source="editor-agent-sidebar"),
        message="继续处理",
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-agent-sidebar",
        ),
        run_id="run-next",
    )

    active_stream = await builder()

    assert active_stream.agent is fake_agent
    assert fake_agent.add_history_to_context is False
    assert fake_agent.run_kwargs["add_history_to_context"] is False
    assert fake_agent.additional_input is not None
    assert [message.content for message in fake_agent.additional_input] == [
        "上一轮完整问题",
        "上一轮完整回答",
        "被停止的用户问题",
        "被停止前的局部回答",
        "被停止但未写 messages 的问题",
        "被停止前已输出的回答",
    ]
    assert all(message.from_history for message in fake_agent.additional_input)
    assert fake_agent.additional_input[-3].reasoning_content == "已暴露思考"
    assert fake_agent.additional_input[-1].reasoning_content == "被停止前已输出的思考"

def test_ai_history_policy_should_scale_with_model_context_window() -> None:
    """动态历史策略应随模型上下文变化，不再固定为 20 条 run。"""

    class Config:
        def __init__(self, *, context_window_tokens: int) -> None:
            self.context_window_tokens = context_window_tokens
            self.max_output_tokens = 1024
            self.history_token_ratio = 0.5

    small_policy = build_history_policy(Config(context_window_tokens=4096), current_input="请改写页面")
    large_policy = build_history_policy(Config(context_window_tokens=128000), current_input="请改写页面")

    assert small_policy.num_history_messages < large_policy.num_history_messages
    assert small_policy.num_history_messages != 20

def test_ai_history_policy_should_trigger_compression_by_token_budget() -> None:
    """历史 token 超过预算时应触发压缩，并按压缩目标保留最近原文。"""

    class Config:
        context_window_tokens = 4096
        max_output_tokens = 1024
        history_token_ratio = 0.4
        compression_target_ratio = 0.1

    messages = [
        Message(role="user", content=f"第 {index} 条历史 " + "长文本" * 240)
        for index in range(24)
    ]

    policy = build_history_policy(Config(), current_input="继续", history_messages=messages)

    assert policy.compression_required is True
    assert policy.history_budget_tokens > policy.compression_target_tokens
    assert policy.estimated_history_tokens > policy.history_budget_tokens
    assert policy.retained_recent_history_tokens <= policy.compression_target_tokens
    assert 0 < policy.num_history_messages < len(messages)

def test_ai_history_policy_should_expand_budget_with_history_ratio() -> None:
    """提高历史上下文比例应增加历史预算，但压缩目标由独立比例控制。"""

    class Config:
        context_window_tokens = 32_000
        max_output_tokens = 4096
        compression_target_ratio = 0.2

        def __init__(self, history_token_ratio: float) -> None:
            self.history_token_ratio = history_token_ratio

    small_budget = build_history_policy(Config(0.2), current_input="继续")
    large_budget = build_history_policy(Config(0.7), current_input="继续")

    assert small_budget.history_budget_tokens < large_budget.history_budget_tokens
    assert large_budget.compression_target_tokens == 6400
