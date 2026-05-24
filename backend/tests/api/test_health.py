"""文件功能：验证平台容器健康检查接口。"""

from httpx import AsyncClient


async def test_healthz_returns_ok(client: AsyncClient) -> None:
    """健康检查接口应无需登录即可返回可被容器探针识别的成功状态。"""

    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
