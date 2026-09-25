"""文件功能：验证平台容器健康检查与就绪探针接口。"""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings


async def test_healthz_returns_ok(client: AsyncClient) -> None:
    """健康检查接口应无需登录即可返回可被容器探针识别的成功状态。"""

    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_reports_ready_with_reachable_database(client: AsyncClient) -> None:
    """数据库可连通且渲染 Worker 已配置时应返回 ready。"""

    response = await client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database_reachable"] is True
    assert body["checks"]["render_workers_configured"] is True


async def test_readyz_should_expose_static_runtime_state_metadata(client: AsyncClient) -> None:
    """就绪端点只报告运行态后端类型与临时性，不做连接探测。"""

    response = await client.get("/readyz")

    body = response.json()
    assert body["checks"]["runtime_state_backend"] == "memory"
    assert body["checks"]["runtime_state_ephemeral"] is True


async def test_runtime_state_metrics_should_report_aggregate_only(client: AsyncClient) -> None:
    """运行态指标只暴露聚合字节与计数，不返回 key 名称或 payload。"""

    response = await client.get("/metrics/runtime-state")

    assert response.status_code == 200
    body = response.json()
    assert body["backend_kind"] == "memory"
    assert body["ephemeral"] is True
    assert body["max_bytes"] > 0
    assert body["max_item_bytes"] > 0
    assert body["active_keys"] >= 0
    assert "runtime:" not in response.text


async def test_readyz_reports_not_ready_without_render_workers(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """渲染 Worker 未配置属于部署缺陷，必须 503 not_ready 而不是静默 ready。"""

    monkeypatch.setattr(get_settings(), "render_workers_config", [])

    response = await client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["render_workers_configured"] is False
    # 数据库本身仍然可连通，不能把配置缺陷误报成数据库故障。
    assert body["checks"]["database_reachable"] is True
