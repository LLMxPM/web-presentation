"""文件功能：E2E mock 基础设施 API 契约测试，覆盖就绪指纹、seed 槽位绑定矩阵与业务防护。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.ai.testing.scenarios import SCENARIO_VERSION
from app.scripts.test_data import SEED_VERSION


async def _build_mock_client(
    database_template: Path,
    tmp_path: Path,
    *,
    database_name: str,
    ai_test_mode: str,
) -> AsyncClient:
    """按指定数据库名与 AI 测试模式构建应用客户端；调用方负责关闭后清理全局状态。"""

    from app.core.config import get_settings
    from app.db.session import reset_database_state
    from app.main import create_app
    from app.services.redis_runtime_client import reset_redis_runtime_client

    database_path = tmp_path / database_name
    shutil.copyfile(database_template, database_path)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    os.environ["AI_TEST_MODE"] = ai_test_mode
    os.environ["REDIS_URL"] = "memory://test"
    os.environ["REDIS_KEY_PREFIX"] = f"test_{database_path.stem}"

    get_settings.cache_clear()
    reset_redis_runtime_client()
    await reset_database_state()
    app = create_app()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _teardown_mock_client(client: AsyncClient) -> None:
    """关闭客户端并恢复全局数据库与配置状态，避免污染后续用例。"""

    import pydantic_ai.models as pydantic_ai_models

    from app.core.config import get_settings
    from app.db.session import reset_database_state
    from app.services.redis_runtime_client import reset_redis_runtime_client

    await client.aclose()
    await reset_database_state()
    get_settings.cache_clear()
    reset_redis_runtime_client()
    pydantic_ai_models.ALLOW_MODEL_REQUESTS = True


async def test_readiness_should_return_fingerprint_without_seed(
    client: AsyncClient,
) -> None:
    """mock 模式下就绪端点应返回环境指纹；未播种时 smoke_data_ready 为 false。"""

    response = await client.get("/api/testing/e2e-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["test_mode"] == "mock"
    assert payload["seed_version"] == SEED_VERSION
    assert payload["scenario_version"] == SCENARIO_VERSION
    assert payload["smoke_data_ready"] is False
    # 常规测试库不带 E2E 指纹，端点只暴露 unknown 而不泄露连接串。
    assert payload["database_profile"] == "unknown"
    assert payload["redis_profile"] == "unknown"


async def test_readiness_should_be_unreachable_in_disabled_mode(
    database_template: Path,
    tmp_path: Path,
) -> None:
    """非 mock 模式下就绪端点必须返回 404，避免生产环境暴露测试指纹。"""

    client = await _build_mock_client(
        database_template, tmp_path, database_name="disabled-mode.db", ai_test_mode="disabled"
    )
    try:
        response = await client.get("/api/testing/e2e-readiness")
        assert response.status_code == 404
        assert response.json()["code"] == "TESTING_READINESS_UNAVAILABLE"
    finally:
        await _teardown_mock_client(client)


async def test_seed_should_bind_three_mock_slots_and_report_ready(
    database_template: Path,
    tmp_path: Path,
) -> None:
    """E2E 库播种后，三个模型槽位应分别绑定 e2e-mock-* 配置且就绪指纹为 e2e。"""

    from app.scripts.test_data import ensure_smoke_data

    client = await _build_mock_client(
        database_template, tmp_path, database_name="web_presentation_e2e.db", ai_test_mode="mock"
    )
    try:
        await ensure_smoke_data()

        readiness = await client.get("/api/testing/e2e-readiness")
        assert readiness.status_code == 200
        payload = readiness.json()
        assert payload["smoke_data_ready"] is True
        assert payload["database_profile"] == "e2e"

        login = await client.post(
            "/api/auth/login", json={"username": "admin", "password": "Admin123456"}
        )
        assert login.status_code == 200

        slots = (await client.get("/api/ai/llm-slots")).json()
        expected_bindings = {
            "agent_coordinator": "e2e-mock-agent-chat",
            "image_understanding": "e2e-mock-vision-chat",
            "image_generation": "e2e-mock-image-gen",
        }
        for slot_name, expected_model_id in expected_bindings.items():
            target = next((item for item in slots if item["slot"] == slot_name), None)
            assert target is not None, f"槽位 {slot_name} 缺少绑定记录"
            assert target["model_id"] == expected_model_id
            assert target["binding_ready"] is True
    finally:
        await _teardown_mock_client(client)


async def test_create_config_should_reject_e2e_mock_model_outside_e2e_database(
    authenticated_client: AsyncClient,
) -> None:
    """非 E2E 数据库禁止通过业务 API 创建 e2e-mock-* 模型配置。"""

    provider = await authenticated_client.post(
        "/api/ai/llm-provider-configs",
        json={"name": "E2E 防护用例供应商", "provider_key": "openai", "api_key": "sk-test"},
    )
    assert provider.status_code == 201

    response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "E2E 防护用例模型",
            "provider_config_id": provider.json()["id"],
            "model_id": "e2e-mock-agent-chat",
            "model_type": "chat",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "AI_LLM_E2E_MOCK_ENVIRONMENT_REQUIRED"


async def test_update_config_should_reject_switching_to_e2e_mock_model(
    authenticated_client: AsyncClient,
) -> None:
    """非 E2E 数据库同样禁止把既有配置的模型切换为 e2e-mock-*。"""

    provider = await authenticated_client.post(
        "/api/ai/llm-provider-configs",
        json={"name": "E2E 防护用例供应商二", "provider_key": "openai", "api_key": "sk-test"},
    )
    assert provider.status_code == 201
    created = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "E2E 防护用例普通模型",
            "provider_config_id": provider.json()["id"],
            "model_id": "gpt-5-mini",
            "model_type": "chat",
        },
    )
    assert created.status_code == 201

    response = await authenticated_client.patch(
        f"/api/ai/llm-configs/{created.json()['id']}",
        json={"model_id": "e2e-mock-vision-chat"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "AI_LLM_E2E_MOCK_ENVIRONMENT_REQUIRED"
