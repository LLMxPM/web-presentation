"""文件功能：验证新 run 模型覆盖与既有 run 模型快照恢复语义。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.session_facade_pydantic import AgentSessionFacade
from app.core.exceptions import AppException
from app.services.ai_llm_service import AiLlmService


def _llm_config(*, config_id: int = 7, model_id: str = "current-model") -> SimpleNamespace:
    """构造模型解析测试所需的最小配置对象。"""

    return SimpleNamespace(
        id=config_id,
        scope="personal",
        status="active",
        name="当前模型",
        provider_config_id=3,
        provider_config=SimpleNamespace(id=3, status="active", provider_key="openai"),
        model_id=model_id,
        model_type="chat",
        thinking_enabled=False,
        thinking_effort=None,
        supports_image_input=False,
        context_window_tokens=128_000,
        max_output_tokens=16_000,
        history_token_ratio=0.5,
        compression_target_ratio=0.1,
        advanced_config_json={},
    )


@pytest.mark.asyncio
async def test_new_run_should_prefer_requested_llm_config() -> None:
    """显式选择模型时不应继续读取会话默认模型。"""

    facade = object.__new__(AgentSessionFacade)
    requested_config = _llm_config(config_id=9)
    validated: list[tuple[str, int]] = []

    class FakeLlmService:
        async def get_selectable_active_config_or_raise(self, config_id: int) -> SimpleNamespace:
            assert config_id == 9
            return requested_config

        def _validate_slot_model_type(self, slot: str, config: SimpleNamespace) -> None:
            validated.append((slot, config.id))

    facade._llm_service = lambda: FakeLlmService()  # type: ignore[method-assign]
    resolved = await facade.resolve_new_run_llm_config(
        session_id="session-1",
        agent_id="agent-coordinator",
        slot="agent_coordinator",
        requested_llm_config_id=9,
    )

    assert resolved is requested_config
    assert validated == [("agent_coordinator", 9)]


@pytest.mark.asyncio
async def test_existing_run_should_restore_snapshot_parameters() -> None:
    """暂停续跑应固定启动时模型参数，而不是读取后来编辑后的值。"""

    facade = object.__new__(AgentSessionFacade)
    current_config = _llm_config(config_id=9, model_id="edited-model")

    class FakeLlmService:
        async def get_selectable_active_config_or_raise(self, config_id: int) -> SimpleNamespace:
            assert config_id == 9
            return current_config

        def _validate_slot_model_type(self, slot: str, config: SimpleNamespace) -> None:
            assert slot == "agent_coordinator"
            assert config.id == 9

    facade._llm_service = lambda: FakeLlmService()  # type: ignore[method-assign]
    run_model = SimpleNamespace(
        run_id="run-1",
        session_id="session-1",
        agent_id="agent-coordinator",
        llm_config_id=9,
        llm_config_snapshot_json={
            "model_id": "original-model",
            "max_output_tokens": 8_000,
            "advanced_config_json": {"temperature": 0.2},
        },
    )

    resolved = await facade.resolve_run_llm_config(
        run_model=run_model,
        slot="agent_coordinator",
    )

    assert resolved.model_id == "original-model"
    assert resolved.max_output_tokens == 8_000
    assert resolved.advanced_config_json == {"temperature": 0.2}
    assert resolved.provider_config is current_config.provider_config


@pytest.mark.asyncio
async def test_active_run_should_block_model_config_changes() -> None:
    """运行未终止时应保护其模型配置，避免暂停恢复发生协议漂移。"""

    class FakeSession:
        async def scalar(self, statement: object) -> str:
            _ = statement
            return "run-active"

    service = object.__new__(AiLlmService)
    service.session = FakeSession()  # type: ignore[assignment]

    with pytest.raises(AppException) as exc_info:
        await service._ensure_config_not_used_by_active_run(9)

    assert exc_info.value.code == "AI_LLM_CONFIG_ACTIVE_RUN_IN_USE"
