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
