"""文件功能：验证开发环境 LLM HTTP trace 的记录、脱敏和 resolver 注入行为。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.ai.llm_http_trace import (
    build_llm_http_trace_client,
    build_llm_http_trace_hooks,
    clear_llm_http_trace_client_cache,
)
from app.ai.pydantic_model_resolver import PydanticLlmModelResolver
from app.core.config import AppSettings, get_settings
from app.models.ai_llm import AiLlmConfig, AiLlmProviderConfig
from app.models.enums import RecordStatus


async def test_llm_http_trace_hooks_should_write_redacted_jsonl(tmp_path: Path) -> None:
    """trace hook 应记录请求与响应摘要，并脱敏 headers、token 字段和 URL 密钥参数。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        """模拟供应商响应，并确认 request hook 读取请求体后不影响后续发送。"""

        assert b"hello" in request.content
        return httpx.Response(
            200,
            headers={"set-cookie": "session=secret", "x-request-id": "req-test"},
            json={"ok": True},
        )

    hooks = build_llm_http_trace_hooks(
        trace_dir=tmp_path,
        body_max_bytes=20_000,
        metadata={"llm_config_id": 7, "provider_key": "openai", "model_id": "gpt-test"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), event_hooks=hooks) as client:
        response = await client.post(
            "https://api.example.com/v1/chat/completions?api_key=url-secret&x=1",
            headers={"Authorization": "Bearer sk-test-token-value", "X-Api-Key": "sk-header"},
            json={
                "model": "gpt-test",
                "max_tokens": 123,
                "api_key": "sk-body",
                "messages": [{"role": "user", "content": "hello"}],
                "metadata": {"token": "secret-token"},
            },
        )

    assert response.status_code == 200
    records = _read_trace_records(tmp_path)
    assert [item["event"] for item in records] == ["llm.http.request", "llm.http.response"]

    request_record = records[0]
    assert request_record["provider_key"] == "openai"
    assert request_record["url"] == "https://api.example.com/v1/chat/completions?api_key=[redacted]&x=1"
    assert request_record["headers"]["authorization"] == "[redacted]"
    assert request_record["headers"]["x-api-key"] == "[redacted]"
    assert "\"content\":\"hello\"" in request_record["body"]["content"]
    assert "\"max_tokens\":123" in request_record["body"]["content"]
    assert "sk-body" not in request_record["body"]["content"]
    assert "secret-token" not in request_record["body"]["content"]

    response_record = records[1]
    assert response_record["status_code"] == 200
    assert response_record["headers"]["set-cookie"] == "[redacted]"
    assert response_record["headers"]["x-request-id"] == "req-test"
    assert response_record["duration_ms"] is not None


def test_llm_http_trace_settings_should_validate_defaults() -> None:
    """配置应保留稳定默认值，并拒绝无效的请求体大小上限。"""

    settings = AppSettings(_env_file=None)

    assert settings.ai_llm_http_trace_body_max_bytes == 200_000
    assert settings.ai_llm_http_trace_dir_path.name == "llm-http-trace"
    with pytest.raises(ValueError, match="AI_LLM_HTTP_TRACE_BODY_MAX_BYTES"):
        AppSettings(_env_file=None, ai_llm_http_trace_body_max_bytes=0)


async def test_model_resolver_should_inject_trace_client_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """开启 trace 后，模型 resolver 应把 trace client 注入 Pydantic AI provider。"""

    monkeypatch.setenv("AI_LLM_HTTP_TRACE_ENABLED", "true")
    monkeypatch.setenv("AI_LLM_HTTP_TRACE_DIR", str(tmp_path))
    get_settings.cache_clear()
    clear_llm_http_trace_client_cache()

    provider_config = AiLlmProviderConfig(
        id=199,
        user_id=1,
        scope="personal",
        name="trace-openai-provider",
        provider_key="openai",
        base_url="https://api.example.com/v1",
        api_key_ciphertext=None,
        status=RecordStatus.ACTIVE.value,
    )
    config = AiLlmConfig(
        id=99,
        user_id=1,
        scope="personal",
        name="trace-openai",
        provider_config_id=provider_config.id,
        provider_config=provider_config,
        model_id="gpt-test",
        advanced_config_json={},
        status=RecordStatus.ACTIVE.value,
    )

    expected_client: httpx.AsyncClient | None = None
    try:
        model = PydanticLlmModelResolver().resolve_model(config)
        expected_client = build_llm_http_trace_client(config)
        assert model.client._client is expected_client
        assert expected_client is not None
        assert len(expected_client.event_hooks["request"]) == 1
        assert len(expected_client.event_hooks["response"]) == 1
    finally:
        if expected_client is not None:
            await expected_client.aclose()
        clear_llm_http_trace_client_cache()
        get_settings.cache_clear()


def _read_trace_records(trace_dir: Path) -> list[dict]:
    """读取 trace 目录中的 JSONL 记录，测试只生成一个文件。"""

    trace_files = list(trace_dir.glob("llm-http-*.jsonl"))
    assert len(trace_files) == 1
    return [json.loads(line) for line in trace_files[0].read_text(encoding="utf-8").splitlines()]
