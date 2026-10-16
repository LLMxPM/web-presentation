"""文件功能：使用真实数据库、文件与 URL 生成器联通浏览器 P、Renderer P 和构建 Worker S 的读取链路。"""

from urllib.parse import parse_qs, urlsplit

from httpx import AsyncClient

from app.core.config import get_settings
from app.models.workspace import Project
from app.services.preview_service import PreviewService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService


async def test_real_generated_asset_urls_work_for_each_identity(authenticated_client, app_session, tmp_path, monkeypatch):
    """避免只 mock 文件端点：创建真实资产与快照，消费生产代码生成的 URL，并验证错误身份。"""
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()
    client = authenticated_client
    workspace = (await client.post("/api/workspaces", json={"name": "private-chain", "status": "active"})).json()
    project = (await client.post("/api/projects", json={"name": "private-chain", "workspace_id": workspace["id"], "status": "active"})).json()
    content = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
    uploaded = await client.post(
        f"/api/workspaces/{workspace['id']}/assets/upload",
        files={"file": ("private.svg", content, "image/svg+xml")}, data={"asset_type": "icon", "name": "private-logo"},
    )
    assert uploaded.status_code == 200, uploaded.text
    asset = uploaded.json()
    page = await client.post("/api/pages", json={
        "title": "private page", "page_content": "<template><div>private page</div></template>",
        "file_type": "vue", "status": "active", "workspace_id": workspace["id"], "project_id": project["id"],
    })
    assert page.status_code == 200, page.text
    routes = await client.put(f"/api/projects/{project['id']}/routes", json={"routes": [
        {"route_type": "page", "route": "home", "order": 0, "page_id": page.json()["id"]},
    ]})
    assert routes.status_code == 200, routes.text
    file_url = urlsplit(asset["url"])
    assert (await client.get(file_url.path + "?" + file_url.query)).content == content

    preview = await PreviewService(app_session).create_preview_artifact(
        project_id=project["id"], entry_descriptor=None, tenant_id="tenant_1", asset_delivery_mode="backend_cache",
    )
    token = parse_qs(urlsplit(preview.preview_url).query)["token"][0]
    manifest = await RuntimeArtifactStore().get_manifest(preview.artifact_id)
    assert "/preview/artifacts/" in manifest["asset_base_url"]
    assert "/internal/" not in manifest["asset_base_url"]
    path = urlsplit(manifest["asset_base_url"]).path + "/" + asset["file_hash"]

    # 构建快照使用数据库 Release ID，必须在分配 ID 后生成 Worker 素材入口。
    model = await app_session.get(Project, project["id"])
    model.build_extra_assets_json = {"asset_names": ["private-logo"]}
    await app_session.commit()
    created = await client.post(f"/api/projects/{project['id']}/build-jobs", json={"base_url": "./"})
    assert created.status_code == 200, created.text
    snapshot_id = str(created.json()["snapshot_release_id"])
    service_token = TokenService.generate_runtime_service_access_token(artifact_id=snapshot_id)
    service_headers = {"Authorization": f"Bearer {service_token}"}

    async with AsyncClient(transport=client._transport, base_url=client.base_url) as browser:
        assert (await browser.get(file_url.path)).status_code == 401
        assert (await browser.get(path)).status_code == 401
        allowed = await browser.get(path, params={"token": token})
        assert allowed.status_code == 200
        assert allowed.content == content
        assert (await browser.get(path, params={"token": token}, headers={"If-None-Match": allowed.headers["ETag"]})).status_code == 304
        ranged = await browser.get(path, params={"token": token}, headers={"Range": "bytes=0-3"})
        assert ranged.status_code == 206 and ranged.content == content[:4]
        assert (await browser.get(path, headers=service_headers)).status_code == 401
        snapshot = await browser.get(f"/internal/runtime/preview-artifacts/{snapshot_id}/manifest", headers=service_headers)
        assert snapshot.status_code == 200
        build_base = snapshot.json()["asset_base_url"]
        assert build_base.endswith(f"/internal/runtime/preview-artifacts/{snapshot_id}/assets")
        build_path = urlsplit(build_base).path + "/" + asset["file_hash"]
        downloaded = await browser.get(build_path, headers=service_headers)
        assert downloaded.status_code == 200 and downloaded.content == content
        assert (await browser.get(build_path, params={"token": token})).status_code == 401
