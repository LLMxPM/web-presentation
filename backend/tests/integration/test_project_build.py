"""文件功能：验证项目整包构建任务的 base_url 校验、任务创建与后台执行链路。"""

from __future__ import annotations

import hashlib
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from httpx import AsyncClient

from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.project_build_job import ProjectBuildJob
from app.models.release import Release
from app.schemas.release import PreviewEntryDescriptor
from app.services.project_artifact_builder import ProjectArtifactSnapshot
from app.services.project_build_artifact_proxy_service import ProjectBuildArtifactProxyService
from app.services.project_build_service import normalize_project_build_base_url, run_project_build_job
from app.services.token_service import TokenService


async def create_active_project(authenticated_client: AsyncClient) -> tuple[int, int]:
    """创建启用中的工作空间与项目，供构建任务测试复用。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "构建工作空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "构建项目", "status": "active"},
    )
    assert project_response.status_code == 200
    return workspace_id, project_response.json()["id"]


async def upload_build_asset(
    authenticated_client: AsyncClient,
    workspace_id: int,
    name: str,
    *,
    asset_type: str = "image",
    file_name: str | None = None,
) -> dict:
    """上传构建测试使用的工作空间资源。"""

    resolved_file_name = file_name or f"{name}.png"
    content_type = "image/svg+xml" if asset_type == "icon" else "image/png"
    content = (
        f"<svg><path d='{name}' /></svg>".encode("utf-8")
        if asset_type == "icon"
        else f"fake-{name}".encode("utf-8")
    )
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (resolved_file_name, content, content_type)},
        data={"asset_type": asset_type, "tags": "[]", "name": name},
    )
    assert response.status_code == 200
    return response.json()


async def create_routed_build_page(
    authenticated_client: AsyncClient,
    workspace_id: int,
    project_id: int,
    page_content: str,
) -> dict:
    """创建并加入路由的构建测试页面。"""

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "构建资源页面",
            "page_content": page_content,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page["id"],
                }
            ]
        },
    )
    assert route_response.status_code == 200
    return page


def build_fake_snapshot(workspace_id: int) -> ProjectArtifactSnapshot:
    """构造最小可用的项目 artifact 快照，避免测试依赖真实模块组装。"""

    return ProjectArtifactSnapshot(
        project=SimpleNamespace(workspace_id=workspace_id),
        preview_kind="project",
        entry_descriptor=PreviewEntryDescriptor(entry_type="route", route="/"),
        page_config=None,
        config_bundle={"app": {"title": "构建测试应用"}},
        asset_base_url=f"http://testserver/public/assets/{workspace_id}",
        asset_mapping={"img/logo.svg": "hash-logo"},
        asset_metadata={
            "img/logo.svg": {
                "file_hash": "hash-logo",
                "original_name": "logo.svg",
            }
        },
        modules_metadata={
            "src/views/HomePage.vue": {
                "path": "src/views/HomePage.vue",
                "hash": "sha256:12345678",
            }
        },
        modules_data=[
            {
                "logical_path": "src/views/HomePage.vue",
                "content": "<template><div>build</div></template>",
                "content_hash": "1234567890abcdef",
            }
        ],
    )


def build_zip_bytes(files: dict[str, bytes]) -> bytes:
    """按给定文件集合构造测试用 ZIP 归档。"""

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for file_path, content in files.items():
            archive.writestr(file_path, content)
    return buffer.getvalue()


def test_normalize_project_build_base_url_should_accept_relative_or_root_paths() -> None:
    """base_url 仅允许 `./` 或以 `/` 开头的部署基路径。"""

    assert normalize_project_build_base_url(None) == "./"
    assert normalize_project_build_base_url("./") == "./"
    assert normalize_project_build_base_url("/demo") == "/demo/"
    assert normalize_project_build_base_url("/nested/path/") == "/nested/path/"


def test_normalize_project_build_base_url_should_reject_absolute_url() -> None:
    """完整 URL、双斜杠与普通相对路径都应被拒绝。"""

    with pytest.raises(AppException) as absolute_url_error:
        normalize_project_build_base_url("https://example.com/demo/")
    assert absolute_url_error.value.code == "PROJECT_BUILD_BASE_URL_INVALID"

    with pytest.raises(AppException):
        normalize_project_build_base_url("//cdn.example.com/demo/")

    with pytest.raises(AppException):
        normalize_project_build_base_url("demo")


@pytest.mark.asyncio
async def test_project_should_persist_normalized_build_extra_assets_json(
    authenticated_client: AsyncClient,
) -> None:
    """项目接口应读写并归一化构建额外资源 JSON。"""

    workspace_id, project_id = await create_active_project(authenticated_client)

    update_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={
            "build_extra_assets_json": {
                "asset_names": [" hero_bg ", "hero_bg", "./font/main.woff2", ""],
            }
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["build_extra_assets_json"] == {
        "asset_names": ["hero_bg", "font/main.woff2"]
    }

    invalid_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"build_extra_assets_json": {"asset_names": ["https://assets.example/logo.png"]}},
    )
    assert invalid_response.status_code == 422


@pytest.mark.asyncio
async def test_project_build_snapshot_should_only_include_referenced_and_extra_assets(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """构建快照应只包含静态引用资源和项目 JSON 中声明的额外资源。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    await upload_build_asset(authenticated_client, workspace_id, "slider", asset_type="icon", file_name="slider.svg")
    used_asset = await upload_build_asset(authenticated_client, workspace_id, "used_image")
    extra_asset = await upload_build_asset(authenticated_client, workspace_id, "manual_extra")
    await upload_build_asset(authenticated_client, workspace_id, "unused_large_image")
    await create_routed_build_page(
        authenticated_client,
        workspace_id,
        project_id,
        '<template><AssetImage name="used_image" /></template>',
    )
    update_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"build_extra_assets_json": {"asset_names": ["manual_extra"]}},
    )
    assert update_response.status_code == 200

    async def fake_run_project_build_job(job_id: int) -> None:  # pragma: no cover
        return None

    monkeypatch.setattr("app.api.routes.build_jobs.run_project_build_job", fake_run_project_build_job)
    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200

    async with get_session_factory()() as session:
        release = await session.get(Release, create_response.json()["snapshot_release_id"])

    assert release is not None
    assert release.manifest["assets"]["used_image"] == used_asset["file_hash"]
    assert release.manifest["assets"]["manual_extra"] == extra_asset["file_hash"]
    assert "unused_large_image" not in release.manifest["assets"]


@pytest.mark.asyncio
async def test_project_build_asset_summary_should_split_automatic_and_extra_assets(
    authenticated_client: AsyncClient,
) -> None:
    """构建资源摘要应区分后端自动包含资源和项目额外资源。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    await upload_build_asset(authenticated_client, workspace_id, "slider", asset_type="icon", file_name="slider.svg")
    await upload_build_asset(authenticated_client, workspace_id, "used_image")
    await upload_build_asset(authenticated_client, workspace_id, "manual_extra")
    await upload_build_asset(authenticated_client, workspace_id, "unused_large_image")
    await create_routed_build_page(
        authenticated_client,
        workspace_id,
        project_id,
        '<template><AssetImage name="used_image" /></template>',
    )
    update_response = await authenticated_client.patch(
        f"/api/projects/{project_id}",
        json={"build_extra_assets_json": {"asset_names": ["manual_extra"]}},
    )
    assert update_response.status_code == 200

    response = await authenticated_client.get(f"/api/projects/{project_id}/build-assets")

    assert response.status_code == 200
    payload = response.json()
    assert "used_image" in payload["automatic_asset_names"]
    assert payload["extra_asset_names"] == ["manual_extra"]
    assert "used_image" in payload["included_asset_names"]
    assert "manual_extra" in payload["included_asset_names"]
    assert "unused_large_image" not in payload["included_asset_names"]


@pytest.mark.asyncio
async def test_project_build_should_return_structured_dynamic_asset_error(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """动态资源无法静态解析且未配置额外资源时，应返回可展示的结构化错误。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    await upload_build_asset(authenticated_client, workspace_id, "slider", asset_type="icon", file_name="slider.svg")
    await upload_build_asset(authenticated_client, workspace_id, "candidate_image")
    await create_routed_build_page(
        authenticated_client,
        workspace_id,
        project_id,
        '<template><AssetImage :name="dynamicName" /></template>',
    )

    async def fake_run_project_build_job(job_id: int) -> None:  # pragma: no cover
        return None

    monkeypatch.setattr("app.api.routes.build_jobs.run_project_build_job", fake_run_project_build_job)
    response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "PROJECT_BUILD_DYNAMIC_ASSET_REFERENCE"
    assert payload["data"]["dynamic_module_paths"]
    assert "candidate_image" in payload["data"]["candidate_asset_names"]


@pytest.mark.asyncio
async def test_project_build_should_return_structured_missing_asset_error(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """构建引用不存在资源时，应返回缺失资源名列表。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    await upload_build_asset(authenticated_client, workspace_id, "slider", asset_type="icon", file_name="slider.svg")
    await create_routed_build_page(
        authenticated_client,
        workspace_id,
        project_id,
        '<template><AssetImage name="missing_image" /></template>',
    )

    async def fake_run_project_build_job(job_id: int) -> None:  # pragma: no cover
        return None

    monkeypatch.setattr("app.api.routes.build_jobs.run_project_build_job", fake_run_project_build_job)
    response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "PROJECT_BUILD_ASSET_MISSING"
    assert "missing_image" in payload["data"]["missing_asset_names"]


@pytest.mark.asyncio
async def test_project_build_job_routes_should_create_and_query_latest_job(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """创建构建任务后，应能通过 latest、history 和 by-id 接口读取任务。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    background_job_ids: list[int] = []

    captured_snapshot: dict[str, object] = {}

    async def fake_build_snapshot(  # noqa: ANN001
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ) -> ProjectArtifactSnapshot:
        captured_snapshot["asset_delivery_mode"] = asset_delivery_mode
        captured_snapshot["asset_snapshot_mode"] = asset_snapshot_mode
        return build_fake_snapshot(workspace_id)

    async def fake_run_project_build_job(job_id: int) -> None:
        background_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )
    monkeypatch.setattr("app.api.routes.build_jobs.run_project_build_job", fake_run_project_build_job)

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "/demo"},
    )
    assert create_response.status_code == 200

    build_job = create_response.json()
    assert build_job["project_id"] == project_id
    assert build_job["base_url"] == "/demo/"
    assert build_job["status"] == "pending"
    assert build_job["snapshot_release_id"] > 0
    assert background_job_ids == [build_job["id"]]

    latest_response = await authenticated_client.get(f"/api/projects/{project_id}/build-jobs/latest")
    assert latest_response.status_code == 200
    assert latest_response.json()["id"] == build_job["id"]

    detail_response = await authenticated_client.get(f"/api/build-jobs/{build_job['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == build_job["id"]

    session_factory = get_session_factory()
    async with session_factory() as session:
        first_job = await session.get(ProjectBuildJob, build_job["id"])
        assert first_job is not None
        first_job.status = "succeeded"
        await session.commit()

    second_create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert second_create_response.status_code == 200
    second_job = second_create_response.json()

    history_response = await authenticated_client.get(f"/api/projects/{project_id}/build-jobs")
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert [item["id"] for item in history_payload] == [second_job["id"], build_job["id"]]
    assert history_payload[0]["base_url"] == "./"
    assert history_payload[1]["base_url"] == "/demo/"

    async with session_factory() as session:
        release = await session.get(Release, build_job["snapshot_release_id"])

    assert release is not None
    assert release.version == "build-snapshot"
    assert release.is_draft is True
    assert release.manifest["artifact_kind"] == "build_snapshot"
    assert release.manifest["asset_metadata"]["img/logo.svg"]["original_name"] == "logo.svg"
    assert captured_snapshot["asset_delivery_mode"] == "backend_cache"
    assert captured_snapshot["asset_snapshot_mode"] == "referenced"


@pytest.mark.asyncio
async def test_create_project_build_job_should_reject_when_active_job_exists(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """已有排队或运行中的构建任务时，应拒绝重复创建新任务。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    background_job_ids: list[int] = []

    async def fake_build_snapshot(  # noqa: ANN001
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ) -> ProjectArtifactSnapshot:
        return build_fake_snapshot(workspace_id)

    async def fake_run_project_build_job(job_id: int) -> None:
        background_job_ids.append(job_id)

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )
    monkeypatch.setattr("app.api.routes.build_jobs.run_project_build_job", fake_run_project_build_job)

    first_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert first_response.status_code == 200
    first_job = first_response.json()

    second_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert second_response.status_code == 409
    payload = second_response.json()
    assert payload["code"] == "PROJECT_BUILD_ALREADY_RUNNING"
    assert payload["data"] == {
        "active_job_id": first_job["id"],
        "active_job_status": "pending",
    }
    assert background_job_ids == [first_job["id"]]


@pytest.mark.asyncio
async def test_run_project_build_job_should_update_status_for_success_and_failure(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """后台任务执行后，应根据 Runtime 返回结果更新 succeeded 或 failed 状态。"""

    workspace_id, project_id = await create_active_project(authenticated_client)

    async def fake_build_snapshot(  # noqa: ANN001
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ) -> ProjectArtifactSnapshot:
        return build_fake_snapshot(workspace_id)

    async def fake_background_job(job_id: int) -> None:  # pragma: no cover
        return None

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )
    monkeypatch.setattr("app.api.routes.build_jobs.run_project_build_job", fake_background_job)
    monkeypatch.setattr(
        "app.services.project_build_service.TokenService.generate_runtime_build_command_token",
        lambda **kwargs: "runtime-build-token",
    )

    success_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert success_response.status_code == 200
    success_job_id = success_response.json()["id"]
    success_job_snapshot_release_id = success_response.json()["snapshot_release_id"]
    captured_dispatch: dict[str, str] = {}

    async def fake_dispatch_success(self, *, artifact_id: str, base_url: str, build_token: str):  # noqa: ANN001
        captured_dispatch["artifact_id"] = artifact_id
        captured_dispatch["base_url"] = base_url
        captured_dispatch["build_token"] = build_token

    monkeypatch.setattr(
        "app.services.project_build_service.RuntimeBuildClient.dispatch_project_build",
        fake_dispatch_success,
    )

    await run_project_build_job(success_job_id)

    session_factory = get_session_factory()
    async with session_factory() as session:
        success_job = await session.get(ProjectBuildJob, success_job_id)

    assert success_job is not None
    assert success_job.status == "succeeded"
    assert success_job.error_message is None
    assert success_job.started_at is not None
    assert success_job.finished_at is not None
    assert captured_dispatch == {
        "artifact_id": str(success_job_snapshot_release_id),
        "base_url": "./",
        "build_token": "runtime-build-token",
    }

    failed_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "/prod"},
    )
    assert failed_response.status_code == 200
    failed_job_id = failed_response.json()["id"]

    async def fake_dispatch_failure(self, *, artifact_id: str, base_url: str, build_token: str):  # noqa: ANN001, ARG001
        raise AppException(status_code=502, code="RUNTIME_BUILD_FAILED", detail="Runtime 服务暂不可用。")

    monkeypatch.setattr(
        "app.services.project_build_service.RuntimeBuildClient.dispatch_project_build",
        fake_dispatch_failure,
    )

    await run_project_build_job(failed_job_id)

    async with session_factory() as session:
        failed_job = await session.get(ProjectBuildJob, failed_job_id)

    assert failed_job is not None
    assert failed_job.status == "failed"
    assert failed_job.error_message == "Runtime 服务暂不可用。"
    assert failed_job.started_at is not None
    assert failed_job.finished_at is not None


@pytest.mark.asyncio
async def test_project_build_artifact_upload_and_download_should_persist_metadata(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """Runtime 上传构建产物后，应能持久化元数据，并通过下载和公开代理访问。"""

    workspace_id, project_id = await create_active_project(authenticated_client)

    async def fake_build_snapshot(  # noqa: ANN001
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ) -> ProjectArtifactSnapshot:
        return build_fake_snapshot(workspace_id)

    async def fake_background_job(job_id: int) -> None:  # pragma: no cover
        return None

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )
    monkeypatch.setattr("app.api.routes.build_jobs.run_project_build_job", fake_background_job)

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "/deploy"},
    )
    assert create_response.status_code == 200
    build_job = create_response.json()

    index_html = b"<!doctype html><html><body><div id='app'>Build Artifact</div></body></html>"
    app_js = b"console.log('build artifact')"
    archive_content = build_zip_bytes(
        {
            "index.html": index_html,
            "assets/app.js": app_js,
        }
    )
    archive_sha256 = hashlib.sha256(archive_content).hexdigest()
    build_token = TokenService.generate_runtime_build_command_token(
        job_id=build_job["id"],
        artifact_id=str(build_job["snapshot_release_id"]),
        project_id=project_id,
        workspace_id=workspace_id,
        base_url="/deploy/",
    )

    upload_response = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{build_job['id']}/artifact",
        headers={"Authorization": f"Bearer {build_token}"},
        files={"archive": ("dist.zip", archive_content, "application/zip")},
        data={
            "entry_file": "index.html",
            "sha256": archive_sha256,
            "size_bytes": str(len(archive_content)),
        },
    )
    assert upload_response.status_code == 200
    upload_payload = upload_response.json()

    assert upload_payload["artifact_entry_file"] == "index.html"
    assert upload_payload["artifact_sha256"] == archive_sha256
    assert upload_payload["artifact_size_bytes"] == len(archive_content)
    assert upload_payload["artifact_storage_key"] == f"build-artifacts/{project_id}/{build_job['id']}/dist.zip"
    assert upload_payload["artifact_download_url"].endswith(
        f"/api/projects/{project_id}/build-jobs/{build_job['id']}/artifact"
    )
    assert upload_payload["artifact_proxy_url"].endswith(
        f"/build-artifacts/{project_id}/{build_job['id']}/"
    )

    detail_response = await authenticated_client.get(f"/api/build-jobs/{build_job['id']}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["artifact_entry_file"] == "index.html"
    assert detail_payload["artifact_sha256"] == archive_sha256
    assert detail_payload["artifact_size_bytes"] == len(archive_content)
    assert detail_payload["artifact_storage_key"] == f"build-artifacts/{project_id}/{build_job['id']}/dist.zip"
    assert detail_payload["artifact_download_url"]
    assert detail_payload["artifact_proxy_url"].endswith(
        f"/build-artifacts/{project_id}/{build_job['id']}/"
    )

    download_response = await authenticated_client.get(
        f"/api/projects/{project_id}/build-jobs/{build_job['id']}/artifact"
    )
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/zip"
    assert download_response.content == archive_content

    root_proxy_response = await authenticated_client.get(
        f"/build-artifacts/{project_id}/{build_job['id']}/"
    )
    assert root_proxy_response.status_code == 200
    assert root_proxy_response.headers["content-type"].startswith("text/html")
    assert root_proxy_response.headers["cache-control"] == "no-cache"
    assert root_proxy_response.content == index_html

    asset_proxy_response = await authenticated_client.get(
        f"/build-artifacts/{project_id}/{build_job['id']}/assets/app.js"
    )
    assert asset_proxy_response.status_code == 200
    assert "javascript" in asset_proxy_response.headers["content-type"]
    assert asset_proxy_response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert asset_proxy_response.content == app_js

    spa_route_response = await authenticated_client.get(
        f"/build-artifacts/{project_id}/{build_job['id']}/slides/intro"
    )
    assert spa_route_response.status_code == 200
    assert spa_route_response.headers["content-type"].startswith("text/html")
    assert spa_route_response.content == index_html

    missing_asset_response = await authenticated_client.get(
        f"/build-artifacts/{project_id}/{build_job['id']}/assets/missing.js"
    )
    assert missing_asset_response.status_code == 404
    assert missing_asset_response.json()["code"] == "BUILD_ARTIFACT_FILE_NOT_FOUND"

    _, other_project_id = await create_active_project(authenticated_client)
    cross_project_response = await authenticated_client.get(
        f"/build-artifacts/{other_project_id}/{build_job['id']}/"
    )
    assert cross_project_response.status_code == 404
    assert cross_project_response.json()["code"] == "BUILD_JOB_NOT_FOUND"

    session_factory = get_session_factory()
    async with session_factory() as session:
        persisted_job = await session.get(ProjectBuildJob, build_job["id"])

    assert persisted_job is not None
    assert persisted_job.artifact_entry_file == "index.html"
    assert persisted_job.artifact_sha256 == archive_sha256
    assert persisted_job.artifact_size_bytes == len(archive_content)
    assert persisted_job.artifact_storage_key == f"build-artifacts/{project_id}/{build_job['id']}/dist.zip"
    assert persisted_job.artifact_download_url


@pytest.mark.asyncio
async def test_project_build_artifact_proxy_should_report_missing_archive(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """构建任务未上传归档时，公开代理入口应返回产物不存在。"""

    workspace_id, project_id = await create_active_project(authenticated_client)

    async def fake_build_snapshot(  # noqa: ANN001
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ) -> ProjectArtifactSnapshot:
        return build_fake_snapshot(workspace_id)

    async def fake_background_job(job_id: int) -> None:  # pragma: no cover
        return None

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )
    monkeypatch.setattr("app.api.routes.build_jobs.run_project_build_job", fake_background_job)

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200
    build_job = create_response.json()

    proxy_response = await authenticated_client.get(
        f"/build-artifacts/{project_id}/{build_job['id']}/"
    )
    assert proxy_response.status_code == 404
    assert proxy_response.json()["code"] == "BUILD_ARTIFACT_NOT_FOUND"


def test_project_build_artifact_proxy_should_reject_unsafe_paths() -> None:
    """构建产物代理路径不允许目录跳转、绝对路径和反斜杠。"""

    unsafe_paths = ["../secret", "/absolute/path", r"assets\app.js", "assets/../secret"]
    for unsafe_path in unsafe_paths:
        with pytest.raises(AppException) as error:
            ProjectBuildArtifactProxyService.normalize_request_path(unsafe_path)
        assert error.value.code == "BUILD_ARTIFACT_PATH_INVALID"
