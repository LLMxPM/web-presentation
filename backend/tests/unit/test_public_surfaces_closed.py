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
@pytest.mark.asyncio
async def test_build_artifacts_protected_access_flow(monkeypatch):
    """测试私有构建授权 access 端点换取短 token，并携带该 token 成功浏览构建静态站。"""

    from app.api.dependencies import get_current_user
    from app.services.auth_service import AuthContext
    from app.models.user import User
    from app.models.project_build_job import ProjectBuildJob
    from app.services.project_service import ProjectService
    from app.services.project_build_service import ProjectBuildService
    from app.services.project_build_artifact_proxy_service import ProjectBuildArtifactProxyService, BuildArtifactProxyResult

    user = User(
        id=99,
        username="build_viewer",
        display_name="Build Viewer",
        password_hash="fake",
        preview_size_presets={},
    )
    mock_auth = AuthContext(user=user, session_token="s-token", backend_session_id="bs-1")

    job = ProjectBuildJob(
        id=2,
        project_id=1,
        snapshot_release_id=10,
        base_url="./",
        status="succeeded",
        artifact_storage_key="build-artifacts/1/2/attempts/1/dist.zip",
        artifact_sha256="fake-sha",
        artifact_size_bytes=100,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_auth

    try:
        monkeypatch.setattr(ProjectService, "get", AsyncMock(return_value=None))
        monkeypatch.setattr(ProjectBuildService, "get_job_by_project_and_id", AsyncMock(return_value=job))

        mock_proxy_result = BuildArtifactProxyResult(
            content=b"<!DOCTYPE html><html><body>SPA Index</body></html>",
            media_type="text/html",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
        monkeypatch.setattr(ProjectBuildArtifactProxyService, "get_artifact_file", AsyncMock(return_value=mock_proxy_result))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. 登录用户请求换取构建浏览短期授权
            access_resp = await client.post("/api/projects/1/build-jobs/2/access")
            assert access_resp.status_code == 200
            data = access_resp.json()
            assert "browse_url" in data
            assert "token" in data
            token = data["token"]

            # 2. 携带 token 请求私有构建站点根文件
            browse_resp = await client.get("/build-artifacts/1/2", params={"token": token})
            assert browse_resp.status_code == 200
            assert browse_resp.content == b"<!DOCTYPE html><html><body>SPA Index</body></html>"
            assert browse_resp.headers["Cache-Control"] == "no-store"
            # 验证返回了 wp_build_token Cookie
            assert "wp_build_token" in browse_resp.cookies

            # 3. 后续深层子资源请求自动带 Cookie 访问
            sub_result = BuildArtifactProxyResult(
                content=b"console.log('app.js');",
                media_type="application/javascript",
                headers={"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"},
            )
            monkeypatch.setattr(ProjectBuildArtifactProxyService, "get_artifact_file", AsyncMock(return_value=sub_result))

            cookie_resp = await client.get(
                "/build-artifacts/1/2/assets/app.js",
                cookies=browse_resp.cookies,
            )
            assert cookie_resp.status_code == 200
            assert cookie_resp.content == b"console.log('app.js');"
            assert cookie_resp.headers["Cache-Control"] == "private, no-cache"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_configs_anonymous_denied_and_authenticated_allowed(monkeypatch):
    """验证项目配置接口禁止匿名读取，严格要求登录鉴权并验证项目访问权 (W11)。"""

    from app.api.dependencies import get_current_user
    from app.services.auth_service import AuthContext
    from app.models.user import User
    from app.services.project_service import ProjectService
    from app.services.project_config_service import ProjectConfigService

    mock_session = AsyncMock()
    app.dependency_overrides[get_db_session] = lambda: mock_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. 匿名访问被拒绝 (401)
            anon_resp = await client.get("/api/runtime/projects/1/configs/app.config.yaml")
            assert anon_resp.status_code == 401

            # 2. 伪造登录态但无权访问该项目 (404/403)
            user = User(id=88, username="test_u", display_name="Test", password_hash="h", preview_size_presets={})
            auth_ctx = AuthContext(user=user, session_token="s-1", backend_session_id="bs-1")
            app.dependency_overrides[get_current_user] = lambda: auth_ctx

            from app.core.exceptions import AppException
            monkeypatch.setattr(ProjectService, "get", AsyncMock(side_effect=AppException(404, "PROJECT_NOT_FOUND", "项目不存在")))
            forbidden_resp = await client.get("/api/runtime/projects/1/configs/app.config.yaml")
            assert forbidden_resp.status_code == 404

            # 3. 合法登录用户成功读取并带 private, no-cache
            monkeypatch.setattr(ProjectService, "get", AsyncMock(return_value=None))
            monkeypatch.setattr(ProjectConfigService, "get_config_text", AsyncMock(return_value="name: demo\n"))
            ok_resp = await client.get("/api/runtime/projects/1/configs/app.config.yaml")
            assert ok_resp.status_code == 200
            assert "name: demo" in ok_resp.text
            assert ok_resp.headers["Cache-Control"] == "private, no-cache"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_backend_direct_public_routes_return_404():
    """验证 Backend 内部未挂载 /public 路由，直连任何 /public 端点均返回 404 (W11)。"""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_assets = await client.get("/public/assets/1/hash-123")
        assert resp_assets.status_code == 404

        resp_cached = await client.get("/public/cached-assets/1/hash-123")
        assert resp_cached.status_code == 404

        resp_screenshots = await client.get("/public/page-screenshots/1")
        assert resp_screenshots.status_code == 404


@pytest.mark.unit
def test_s3_storage_driver_no_font_public_bucket_split(monkeypatch):
    """验证 S3StorageDriver 上传字体不再分流至 public bucket，统一使用私有 bucket 且不返回公开直连 URL (W08,W11)。"""

    from app.services.asset_storage_drivers import S3StorageDriver
    from app.services.object_storage_service import ObjectStorageService
    from app.core.config import AppSettings

    custom_settings = AppSettings(
        s3_bucket="my-private-bucket",
        s3_public_bucket="my-public-bucket",
        s3_public_base_url="https://public.example.com",
    )
    monkeypatch.setattr(ObjectStorageService, "settings", property(lambda self: custom_settings))
    driver = S3StorageDriver()

    # 上传字体统一使用私有 bucket
    assert driver._resolve_bucket_name("custom-font.woff2") == "my-private-bucket"
    assert driver._resolve_bucket_name("custom-font.ttf") == "my-private-bucket"
    assert driver._resolve_bucket_name("image.png") == "my-private-bucket"

    # 不生成公开直连 URL
    assert driver._build_public_font_url(1, "custom-font.woff2") is None

