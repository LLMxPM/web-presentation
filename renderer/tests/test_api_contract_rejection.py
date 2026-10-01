"""文件功能：验证 Renderer HTTP 边界对语义契约错误明确返回 400，并保留已接管请求的过期票据幂等。"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from test_slot_controller import _make_request
from wp_renderer.api import routes
from wp_renderer.control.slot import SlotController, SlotExecution
from wp_renderer.security.auth import require_service_token

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["contract_version", "viewport"])
async def test_semantic_contract_errors_return_400_without_acceptance(invalid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """版本/画布尺寸语义错误必须由真实 HTTP 路由转换为错误码，不能抛出 500 或改变占用。"""
    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    monkeypatch.setattr(routes, "_slot", slot)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_service_token] = lambda: "backend:renderer-local"
    payload = _make_request().to_dict()
    if invalid == "contract_version":
        payload[invalid] = "internal/render/v999"
    else:
        payload[invalid]["width"] = -1
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        response = await client.post("/internal/render/v1/executions", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "RENDER_CONTRACT_MISMATCH"
    assert not slot.busy and slot.slot_generation == 0


@pytest.mark.asyncio
async def test_existing_receipt_with_expired_ticket_still_returns_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """校验错误映射不能前移票据复核，否则已接管 attempt 的重试会被错误拒绝。"""
    slot = SlotController(worker_id="renderer-local", worker_epoch="epoch-1")
    original = _make_request()
    slot._receipts[original.attempt_id] = SlotExecution(request=original, accepted_at=datetime.now(UTC))
    expired = replace(original, admission_ticket=replace(
        original.admission_ticket, accept_before=(datetime.now(UTC)-timedelta(seconds=30)).isoformat(),
    ))
    monkeypatch.setattr(routes, "_slot", slot)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[require_service_token] = lambda: "backend:renderer-local"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/internal/render/v1/executions", json=expired.to_dict())
    assert response.status_code == 200
    assert response.json()["attempt_id"] == original.attempt_id
    assert slot.slot_generation == 0
