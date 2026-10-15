"""文件功能：单元测试 W11 公开面收口，验证匿名构建与旧公开端点的阻断、404 与 no-store 策略。"""

from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_db_session
from app.main import app
from unittest.mock import AsyncMock


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_artifacts_anonymous_disabled_get_and_head():
    """验证 Backend 内部已关闭旧 /build-artifacts 匿名站点代理入口。"""

    mock_session = AsyncMock()
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. GET 匿名访问构建产物根路径
            resp = await client.get("/build-artifacts/1/2")
            assert resp.status_code == 404
            assert resp.headers["Cache-Control"] == "no-store"
            data = resp.json()
            assert data["code"] == "BUILD_ARTIFACT_ANONYMOUS_DISABLED"

            # 2. GET 匿名访问构建产物子文件
            resp_sub = await client.get("/build-artifacts/1/2/index.html")
            assert resp_sub.status_code == 404
            assert resp_sub.headers["Cache-Control"] == "no-store"

            # 3. HEAD 匿名访问
            resp_head = await client.head("/build-artifacts/1/2")
            assert resp_head.status_code == 404
            assert resp_head.headers["Cache-Control"] == "no-store"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.unit
def test_gateway_nginx_conf_blocks_public_and_build_artifacts():
    """验证 Gateway Nginx 配置已收口 /public 与 /build-artifacts，禁止代理到上游或回退到 Editor SPA。"""

    conf_path = Path("deploy/docker/nginx/web-presentation.conf")
    assert conf_path.is_file(), "web-presentation.conf 不存在"
    content = conf_path.read_text(encoding="utf-8")

    # 1. 验证 /media 阻断
    assert "location = /media" in content
    assert "location ^~ /media/" in content

    # 2. 验证 /public 显式阻断
    assert "location = /public" in content
    assert "location ^~ /public/" in content

    # 3. 验证 /build-artifacts 显式阻断
    assert "location = /build-artifacts" in content
    assert "location ^~ /build-artifacts/" in content

    # 4. 验证 upstream 代理仅放行 api 与 preview，不再代理 public 与 build-artifacts
    assert "location ~ ^/(api|preview)(/|$)" in content
    assert "build-artifacts" not in content.split("location ~ ^/")[1].split(")(/|$)")[0]
    assert "public" not in content.split("location ~ ^/")[1].split(")(/|$)")[0]
