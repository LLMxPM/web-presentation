"""文件功能：验证 Models.dev 协议白名单、目录同步和保守能力策略。"""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.ai_model_catalog import AiChatModelCatalog
from app.services.ai_model_catalog_service import AiModelCatalogService, resolve_catalog_protocol


def test_protocol_mapping_should_reject_unimplemented_sdks() -> None:
    """目录只能映射到平台已经实现的协议，不接受 Anthropic/Bedrock。"""

    assert resolve_catalog_protocol("openai", "@ai-sdk/openai") == "openai_chat"
    assert resolve_catalog_protocol("community", "@ai-sdk/openai-compatible") == "openai_compatible_chat"
    assert resolve_catalog_protocol("anthropic", "@ai-sdk/anthropic") is None
    assert resolve_catalog_protocol("bedrock", "@ai-sdk/amazon-bedrock") is None


@pytest.mark.asyncio
async def test_catalog_sync_should_keep_only_supported_providers(tmp_path) -> None:
    """同步后仅保存白名单供应商，并正确投影模型限制与能力。"""

    path = tmp_path / "catalog.db"
    sync_engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    payload = {
        "demo": {"id": "demo", "name": "Demo", "api": "https://demo.test/v1", "npm": "@ai-sdk/openai-compatible", "models": {
            "demo-chat": {"id": "demo-chat", "name": "Demo Chat", "limit": {"context": 100000, "input": 90000, "output": 10000},
                "modalities": {"input": ["text", "image"], "output": ["text"]}, "tool_call": True, "reasoning": True,
                "reasoning_options": [{"type": "toggle"}, {"type": "effort", "values": ["none", "low", "high"]}]}
        }},
        "anthropic": {"id": "anthropic", "name": "Anthropic", "npm": "@ai-sdk/anthropic", "models": {}},
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=json.dumps(payload).encode(), headers={"etag": "v1"}))
    async with factory() as session, httpx.AsyncClient(transport=transport) as client:
        state = await AiModelCatalogService(session).sync(force=True, client=client)
        providers = await AiModelCatalogService(session).list_providers()
        model = await session.get(AiChatModelCatalog, 1)
        assert state.catalog_version
        assert [item.provider_key for item in providers] == ["demo"]
        assert model is not None
        assert model.input_tokens == 90000
        assert model.supports_tool_call is True
        assert model.input_modalities_json == ["text", "image"]
        assert model.reasoning_options_json == {
            "types": ["toggle", "effort"],
            "effort": ["none", "low", "high"],
        }
    await engine.dispose()
