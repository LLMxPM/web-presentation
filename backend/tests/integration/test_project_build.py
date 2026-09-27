"""文件功能：验证项目整包构建任务的 base_url 校验、任务创建与后台执行链路。"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.project_build_job import ProjectBuildJob
from app.models.release import Release
from app.schemas.release import PreviewEntryDescriptor
from app.services.project_artifact_builder import ProjectArtifactSnapshot
from app.services.project_build_artifact_proxy_service import ProjectBuildArtifactProxyService
from app.services.project_build_service import (
    ProjectBuildService,
    normalize_project_build_base_url,
)
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


async def aiter_chunks(chunks: list[bytes]) -> AsyncIterator[bytes]:
    """把分片列表包成异步迭代器，匹配构建归档的流式接收接口。"""

    for chunk in chunks:
        yield chunk


async def upload_build_archive_stream(
    client: AsyncClient,
    *,
    job_id: int,
    build_token: str,
    archive_content: bytes,
    entry_file: str = "index.html",
    sha256: str | None = None,
    declared_size_bytes: int | None = None,
):
    """按流式归档契约上传构建产物。

    归档正文直接作为请求体发送，入口文件与校验声明通过 `x-runtime-build-archive-*`
    头声明：`sha256` 为 None 时省略该头，大小默认声明为正文实际长度，
    传 `declared_size_bytes` 可模拟声明与实际不一致。
    正文用分块迭代器发送，请求因此没有 Content-Length，贴近 Runtime 的真实上传形态。
    """

    headers = {
        "Authorization": f"Bearer {build_token}",
        "content-type": "application/zip",
        "x-runtime-build-archive-entry-file": entry_file,
        "x-runtime-build-archive-size-bytes": str(
            len(archive_content) if declared_size_bytes is None else declared_size_bytes
        ),
    }
    if sha256 is not None:
        headers["x-runtime-build-archive-sha256"] = sha256
    chunks = [archive_content[offset : offset + 1024] for offset in range(0, len(archive_content), 1024)]
    return await client.post(
        f"/internal/runtime/build-jobs/{job_id}/artifact",
        headers=headers,
        content=aiter_chunks(chunks),
    )


async def create_claimed_build_job(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[int, int, int, str]:
    """创建并以 `test-worker` 领取一个构建任务，返回工作空间、项目、任务 ID 和 attempt 令牌。

    令牌按领取到的 `attempt_id` 与租约持有者签发，贴近 Worker 上传产物的真实前置状态。
    """

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

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )
    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200
    build_job = create_response.json()
    async with get_session_factory()() as session:
        claimed_job = await ProjectBuildService(session, lease_owner="test-worker").claim_job(
            job_id=build_job["id"]
        )
        assert claimed_job is not None
        attempt_id = claimed_job.attempt_id
    build_token = TokenService.generate_runtime_build_command_token(
        job_id=build_job["id"],
        artifact_id=str(build_job["snapshot_release_id"]),
        project_id=project_id,
        workspace_id=workspace_id,
        base_url="./",
        attempt_id=attempt_id,
        lease_owner="test-worker",
    )
    return workspace_id, project_id, int(build_job["id"]), build_token


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
async def test_project_build_snapshot_should_not_include_suggested_reference_assets(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """项目建议引用资源只服务 AI 上下文，不应自动进入整包构建资源。"""

    workspace_id, project_id = await create_active_project(authenticated_client)
    await upload_build_asset(authenticated_client, workspace_id, "slider", asset_type="icon", file_name="slider.svg")
    used_asset = await upload_build_asset(authenticated_client, workspace_id, "used_image")
    suggested_asset = await upload_build_asset(authenticated_client, workspace_id, "suggested_only")
    await create_routed_build_page(
        authenticated_client,
        workspace_id,
        project_id,
        '<template><AssetImage name="used_image" /></template>',
    )
    suggested_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": [suggested_asset["id"]]},
    )
    assert suggested_response.status_code == 200

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200

    async with get_session_factory()() as session:
        release = await session.get(Release, create_response.json()["snapshot_release_id"])

    assert release is not None
    assert release.manifest["assets"]["used_image"] == used_asset["file_hash"]
    assert "suggested_only" not in release.manifest["assets"]


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

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

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
    # 创建后不再同步派发：任务保持 pending，等待 Runtime Build Worker 领取。
    assert build_job["status"] == "pending"

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

    async def fake_build_snapshot(  # noqa: ANN001
        self,
        *,
        project_id: int,
        entry_descriptor=None,
        asset_delivery_mode="public",
        asset_snapshot_mode="all",
    ) -> ProjectArtifactSnapshot:
        return build_fake_snapshot(workspace_id)

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

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


@pytest.mark.asyncio
async def test_run_project_build_job_should_update_status_for_success_and_failure(
    authenticated_client: AsyncClient,
    monkeypatch,
    build_worker_credential: str,
) -> None:
    """Runtime Build Worker 通过 claim/complete API 执行后，应更新 succeeded 或 failed 状态。"""

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

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

    success_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert success_response.status_code == 200
    success_job_id = success_response.json()["id"]

    claim_response = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": "Bearer test-build-worker-credential"},
    )
    assert claim_response.status_code == 200
    claim = claim_response.json()
    assert claim["job_id"] == success_job_id
    build_token = claim["build_token"]

    async with get_session_factory()() as upload_session:
        service = ProjectBuildService(upload_session)
        job = await service.get_job_by_id(success_job_id)
        await service.persist_uploaded_artifact(
            job=job,
            archive_chunks=aiter_chunks([build_zip_bytes({"index.html": b"<html>ok</html>"})]),
            entry_file="index.html",
            sha256=None,
            size_bytes=None,
            attempt_id=job.attempt_id,
            lease_owner=job.lease_owner,
        )

    complete_ok = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{success_job_id}/complete",
        json={"success": True},
        headers={"Authorization": f"Bearer {build_token}"},
    )
    assert complete_ok.status_code == 200

    session_factory = get_session_factory()
    async with session_factory() as session:
        success_job = await session.get(ProjectBuildJob, success_job_id)

    assert success_job is not None
    assert success_job.status == "succeeded"
    assert success_job.error_message is None
    assert success_job.started_at is not None
    assert success_job.finished_at is not None
    assert success_job.attempt_count == 1

    failed_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "/prod"},
    )
    assert failed_response.status_code == 200
    failed_job_id = failed_response.json()["id"]

    async with session_factory() as session:
        failed_job_row = await session.get(ProjectBuildJob, failed_job_id)
        assert failed_job_row is not None
        failed_job_row.max_attempts = 1
        await session.commit()

    claim_failed = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": "Bearer test-build-worker-credential"},
    )
    assert claim_failed.status_code == 200
    failed_claim = claim_failed.json()
    assert failed_claim["job_id"] == failed_job_id

    complete_fail = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{failed_job_id}/complete",
        json={"success": False, "error_message": "Runtime 服务暂不可用。"},
        headers={"Authorization": f"Bearer {failed_claim['build_token']}"},
    )
    assert complete_fail.status_code == 200

    async with session_factory() as session:
        failed_job = await session.get(ProjectBuildJob, failed_job_id)

    assert failed_job is not None
    assert failed_job.status == "failed"
    assert failed_job.error_message == "Runtime 服务暂不可用。"
    assert failed_job.started_at is not None
    assert failed_job.finished_at is not None


@pytest.mark.asyncio
async def test_project_build_artifact_upload_download_and_delete_should_persist_metadata(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """Runtime 上传构建产物后，应支持下载、公开代理和保留历史的产物删除。"""

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

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

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
    async with get_session_factory()() as session:
        created_job = await session.get(ProjectBuildJob, build_job["id"])
        assert created_job is not None
        # 生产路径先领取再上传：围栏要求有效租约，pending 创建态不得直接提升产物。
        claimed_job = await ProjectBuildService(session, lease_owner="test-worker").claim_job(
            job_id=build_job["id"]
        )
        assert claimed_job is not None
        job_attempt_id = claimed_job.attempt_id
        expected_storage_key = (
            f"build-artifacts/{project_id}/{build_job['id']}/attempts/{job_attempt_id}/dist.zip"
        )
    build_token = TokenService.generate_runtime_build_command_token(
        job_id=build_job["id"],
        artifact_id=str(build_job["snapshot_release_id"]),
        project_id=project_id,
        workspace_id=workspace_id,
        base_url="/deploy/",
        attempt_id=job_attempt_id,
        lease_owner="test-worker",
    )

    upload_response = await upload_build_archive_stream(
        authenticated_client,
        job_id=build_job["id"],
        build_token=build_token,
        archive_content=archive_content,
        sha256=archive_sha256,
    )
    assert upload_response.status_code == 200
    upload_payload = upload_response.json()

    assert upload_payload["artifact_entry_file"] == "index.html"
    assert upload_payload["artifact_sha256"] == archive_sha256
    assert upload_payload["artifact_size_bytes"] == len(archive_content)
    assert upload_payload["artifact_storage_key"] == expected_storage_key
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
    assert detail_payload["artifact_storage_key"] == expected_storage_key
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
    assert persisted_job.artifact_storage_key == expected_storage_key
    assert persisted_job.artifact_download_url

    active_delete_response = await authenticated_client.delete(
        f"/api/projects/{project_id}/build-jobs/{build_job['id']}/artifact"
    )
    assert active_delete_response.status_code == 409
    assert active_delete_response.json()["code"] == "BUILD_ARTIFACT_DELETE_CONFLICT"

    async with session_factory() as session:
        completed_job = await session.get(ProjectBuildJob, build_job["id"])
        assert completed_job is not None
        completed_job.status = "succeeded"
        await session.commit()

    delete_response = await authenticated_client.delete(
        f"/api/projects/{project_id}/build-jobs/{build_job['id']}/artifact"
    )
    assert delete_response.status_code == 204

    deleted_detail_response = await authenticated_client.get(f"/api/build-jobs/{build_job['id']}")
    assert deleted_detail_response.status_code == 200
    deleted_detail = deleted_detail_response.json()
    assert deleted_detail["status"] == "succeeded"
    assert deleted_detail["artifact_storage_key"] is None
    assert deleted_detail["artifact_download_url"] is None
    assert deleted_detail["artifact_proxy_url"] is None
    assert deleted_detail["artifact_entry_file"] is None
    assert deleted_detail["artifact_sha256"] is None
    assert deleted_detail["artifact_size_bytes"] is None

    deleted_download_response = await authenticated_client.get(
        f"/api/projects/{project_id}/build-jobs/{build_job['id']}/artifact"
    )
    assert deleted_download_response.status_code == 404
    assert deleted_download_response.json()["code"] == "BUILD_ARTIFACT_NOT_FOUND"

    deleted_proxy_response = await authenticated_client.get(
        f"/build-artifacts/{project_id}/{build_job['id']}/"
    )
    assert deleted_proxy_response.status_code == 404
    assert deleted_proxy_response.json()["code"] == "BUILD_ARTIFACT_NOT_FOUND"

    repeated_delete_response = await authenticated_client.delete(
        f"/api/projects/{project_id}/build-jobs/{build_job['id']}/artifact"
    )
    assert repeated_delete_response.status_code == 404
    assert repeated_delete_response.json()["code"] == "BUILD_ARTIFACT_NOT_FOUND"


@pytest.mark.asyncio
async def test_project_build_artifact_upload_should_reject_oversized_declared_size_early(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """声明长度越界的归档应在读取请求体前被拒，不开始接收一个必然失败的归档。"""

    settings = get_settings()
    monkeypatch.setattr(settings, "project_build_artifact_max_bytes", 128)

    response = await authenticated_client.post(
        "/internal/runtime/build-jobs/1/artifact",
        headers={
            "Authorization": "Bearer invalid-build-token",
            "x-runtime-build-archive-entry-file": "index.html",
            "x-runtime-build-archive-size-bytes": "4096",
        },
        content=aiter_chunks([b"x" * 1024] * 4),
    )

    assert response.status_code == 413
    assert response.json()["code"] == "BUILD_ARTIFACT_TOO_LARGE"


@pytest.mark.asyncio
async def test_project_build_artifact_upload_should_require_entry_file_header(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """流式归档必须声明入口文件头，缺失时在读取正文前拒绝。"""

    _, _, job_id, build_token = await create_claimed_build_job(authenticated_client, monkeypatch)

    response = await authenticated_client.post(
        f"/internal/runtime/build-jobs/{job_id}/artifact",
        headers={
            "Authorization": f"Bearer {build_token}",
            "x-runtime-build-archive-size-bytes": "8",
        },
        content=aiter_chunks([b"12345678"]),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "BUILD_ARTIFACT_ENTRY_FILE_INVALID"


@pytest.mark.asyncio
async def test_project_build_artifact_upload_should_reject_mismatched_declared_size(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """声明大小只是预筛依据：与实际归档不一致时不得提升产物。"""

    _, _, job_id, build_token = await create_claimed_build_job(authenticated_client, monkeypatch)
    archive_content = build_zip_bytes({"index.html": b"<html>ok</html>"})

    response = await upload_build_archive_stream(
        authenticated_client,
        job_id=job_id,
        build_token=build_token,
        archive_content=archive_content,
        sha256=hashlib.sha256(archive_content).hexdigest(),
        declared_size_bytes=len(archive_content) + 1,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "BUILD_ARTIFACT_SIZE_MISMATCH"


@pytest.mark.asyncio
async def test_persist_uploaded_artifact_should_abort_when_stream_exceeds_limit(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    build_worker_credential: str,
) -> None:
    """逐块写入应在越界处立即中止：不提升产物，也不留下半成品对象。"""

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

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "project_build_artifact_max_bytes", 64)

    create_response = await authenticated_client.post(
        f"/api/projects/{project_id}/build-jobs",
        json={"base_url": "./"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]
    claim_response = await authenticated_client.post(
        "/internal/runtime/build-jobs/claim",
        json={"worker_id": "runtime-build-test"},
        headers={"Authorization": f"Bearer {build_worker_credential}"},
    )
    assert claim_response.status_code == 200

    async with get_session_factory()() as upload_session:
        service = ProjectBuildService(upload_session)
        job = await service.get_job_by_id(job_id)
        with pytest.raises(AppException) as exc_info:
            await service.persist_uploaded_artifact(
                job=job,
                archive_chunks=aiter_chunks([b"a" * 32, b"b" * 32, b"c" * 32]),
                entry_file="index.html",
                sha256=None,
                size_bytes=None,
                attempt_id=job.attempt_id,
                lease_owner=job.lease_owner,
            )

        assert exc_info.value.code == "OBJECT_TOO_LARGE"
        aborted_job = await service.get_job_by_id(job_id)
        assert aborted_job.artifact_storage_key is None
        assert aborted_job.artifact_size_bytes is None


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

    monkeypatch.setattr(
        "app.services.project_build_service.ProjectArtifactBuilder.build_snapshot",
        fake_build_snapshot,
    )

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
