"""文件功能：验证资源渲染提示回填任务接口、队列执行和任务组聚合行为。"""

from __future__ import annotations

import struct
from typing import Any

from httpx import AsyncClient

from app.core.exceptions import AppException
from app.db.session import get_session_factory
from app.models.asset import WorkspaceAsset
from app.models.enums import AssetType
from app.services.asset_render_hint_backfill_job_service import (
    AssetRenderHintBackfillJobService,
    run_asset_render_hint_backfill_job,
)
from app.services.asset_render_metadata_service import AssetRenderMetadataService


def _build_png_header(width: int, height: int) -> bytes:
    """构造最小 PNG 头用于资源比例解析。"""

    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", width, height)


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return int(response.json()["id"])


async def _create_content_asset(
    authenticated_client: AsyncClient,
    workspace_id: int,
    *,
    asset_type: str = "formula",
    name: str,
    content: str,
    approx_aspect_ratio: str | None = None,
) -> dict[str, Any]:
    """创建文本内容资源并返回响应。"""

    extension_map = {
        "drawio": "drawio",
        "formula": "tex",
        "mermaid": "mmd",
    }
    extension = extension_map.get(asset_type, "txt")
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": asset_type,
            "name": name,
            "original_name": f"{name}.{extension}",
            "content": content,
            "tags": [],
            "approx_aspect_ratio": approx_aspect_ratio,
        },
    )
    assert response.status_code == 200
    return dict(response.json())


async def _run_group_jobs(group: dict[str, Any]) -> None:
    """领取并执行任务组里的所有 pending 任务。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        claimed_jobs = await AssetRenderHintBackfillJobService(session).claim_pending_jobs(
            limit=max(1, int(group["requested_count"])),
        )
    for job in claimed_jobs:
        await run_asset_render_hint_backfill_job(job.id, session_factory=session_factory)


async def test_preview_asset_render_hint_backfill_should_not_write_asset(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """预览模式应保存任务候选结果，但不写入资源 render_metadata。"""

    workspace_id = await _create_workspace(authenticated_client, "资源比例预览空间")
    asset = await _create_content_asset(
        authenticated_client,
        workspace_id,
        name="preview_formula",
        content="E = mc^2",
    )
    next_metadata = AssetRenderMetadataService.build_metadata_from_ratio(2.0, source="auto")

    async def fake_measure_metadata(self, *, asset: WorkspaceAsset, content: bytes) -> dict[str, Any]:  # noqa: ARG001
        """返回固定测量结果，避免测试依赖 Runtime。"""

        return next_metadata

    monkeypatch.setattr(
        "app.services.asset_render_hint_measurement_service.AssetRenderHintMeasurementService.measure_metadata",
        fake_measure_metadata,
    )

    create_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/render-hint-backfill-jobs",
        json={"asset_types": ["formula"], "asset_ids": [asset["id"]], "mode": "preview"},
    )
    assert create_response.status_code == 200
    group = create_response.json()
    assert group["requested_count"] == 1
    assert group["status"] == "pending"

    await _run_group_jobs(group)

    group_response = await authenticated_client.get(
        f"/api/asset-render-hint-backfill-job-groups/{group['job_group_id']}",
    )
    assert group_response.status_code == 200
    completed = group_response.json()
    assert completed["status"] == "succeeded"
    assert completed["succeeded_count"] == 1
    assert completed["jobs"][0]["next_render_metadata"] == next_metadata
    assert completed["jobs"][0]["next_approx_aspect_ratio"] == "2:1"

    asset_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/content",
    )
    assert asset_response.status_code == 200
    assert asset_response.json()["asset"]["render_metadata"] is None


async def test_apply_asset_render_hint_backfill_should_write_asset(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """写回模式应把 Runtime 测量结果写入资源 render_metadata。"""

    workspace_id = await _create_workspace(authenticated_client, "资源比例写回空间")
    asset = await _create_content_asset(
        authenticated_client,
        workspace_id,
        asset_type="mermaid",
        name="apply_mermaid",
        content="flowchart TD\n  A --> B",
    )
    next_metadata = AssetRenderMetadataService.build_metadata_from_ratio(16 / 9, source="auto")

    async def fake_measure_metadata(self, *, asset: WorkspaceAsset, content: bytes) -> dict[str, Any]:  # noqa: ARG001
        """返回固定测量结果，避免测试依赖 Runtime。"""

        return next_metadata

    monkeypatch.setattr(
        "app.services.asset_render_hint_measurement_service.AssetRenderHintMeasurementService.measure_metadata",
        fake_measure_metadata,
    )

    create_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/render-hint-backfill-jobs",
        json={"asset_types": ["mermaid"], "asset_ids": [asset["id"]], "mode": "apply"},
    )
    assert create_response.status_code == 200

    await _run_group_jobs(create_response.json())

    asset_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/content",
    )
    assert asset_response.status_code == 200
    assert asset_response.json()["asset"]["render_metadata"] == next_metadata
    assert asset_response.json()["asset"]["approx_aspect_ratio"] == "16:9"
    assert asset_response.json()["asset"]["aspect_ratio_source"] == "auto"


async def test_static_asset_render_hint_backfill_should_support_image_and_drawio(
    authenticated_client: AsyncClient,
) -> None:
    """静态图片和 Draw.io 资源应能进入比例回填任务并写回自动比例。"""

    workspace_id = await _create_workspace(authenticated_client, "静态资源比例写回空间")
    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", _build_png_header(800, 600), "image/png")},
        data={"asset_type": "image", "tags": "[]", "name": "cover_image"},
    )
    assert upload_response.status_code == 200
    image_asset = upload_response.json()
    drawio_asset = await _create_content_asset(
        authenticated_client,
        workspace_id,
        asset_type="drawio",
        name="flow_drawio",
        content='<mxfile><diagram><mxGraphModel pageWidth="960" pageHeight="540" /></diagram></mxfile>',
    )
    async with get_session_factory()() as session:
        for asset_id in [image_asset["id"], drawio_asset["id"]]:
            asset_model = await session.get(WorkspaceAsset, asset_id)
            assert asset_model is not None
            asset_model.render_metadata = None
        await session.commit()

    create_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/render-hint-backfill-jobs",
        json={"asset_types": ["image", "drawio"], "asset_ids": [image_asset["id"], drawio_asset["id"]], "mode": "apply"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["requested_count"] == 2

    await _run_group_jobs(create_response.json())

    list_response = await authenticated_client.get(f"/api/workspaces/{workspace_id}/assets")
    assert list_response.status_code == 200
    assets_by_name = {item["name"]: item for item in list_response.json()["items"]}
    assert assets_by_name["cover_image"]["approx_aspect_ratio"] == "4:3"
    assert assets_by_name["flow_drawio"]["approx_aspect_ratio"] == "16:9"
    assert assets_by_name["cover_image"]["aspect_ratio_source"] == "auto"


async def test_manual_asset_render_hint_backfill_should_skip_by_default(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """默认不覆盖人工或 Agent 维护的比例。"""

    workspace_id = await _create_workspace(authenticated_client, "资源比例人工跳过空间")
    asset = await _create_content_asset(
        authenticated_client,
        workspace_id,
        name="manual_formula",
        content="a^2 + b^2 = c^2",
        approx_aspect_ratio="4:3",
    )
    next_metadata = AssetRenderMetadataService.build_metadata_from_ratio(2.0, source="auto")

    async def fake_measure_metadata(self, *, asset: WorkspaceAsset, content: bytes) -> dict[str, Any]:  # noqa: ARG001
        """如果被调用则返回固定结果，用于暴露跳过逻辑失效。"""

        return next_metadata

    monkeypatch.setattr(
        "app.services.asset_render_hint_measurement_service.AssetRenderHintMeasurementService.measure_metadata",
        fake_measure_metadata,
    )

    create_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/render-hint-backfill-jobs",
        json={"asset_ids": [asset["id"]], "mode": "apply"},
    )
    assert create_response.status_code == 200

    await _run_group_jobs(create_response.json())

    group_response = await authenticated_client.get(
        f"/api/asset-render-hint-backfill-job-groups/{create_response.json()['job_group_id']}",
    )
    assert group_response.status_code == 200
    completed = group_response.json()
    assert completed["status"] == "succeeded"
    assert completed["skipped_count"] == 1
    assert completed["jobs"][0]["status"] == "skipped"

    asset_response = await authenticated_client.get(
        f"/api/workspaces/{workspace_id}/assets/{asset['id']}/content",
    )
    assert asset_response.status_code == 200
    assert asset_response.json()["asset"]["approx_aspect_ratio"] == "4:3"
    assert asset_response.json()["asset"]["aspect_ratio_source"] == "manual"


async def test_asset_render_hint_backfill_group_should_aggregate_failures(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """任务组应聚合成功和失败数量，并返回失败原因摘要。"""

    workspace_id = await _create_workspace(authenticated_client, "资源比例失败聚合空间")
    good_asset = await _create_content_asset(
        authenticated_client,
        workspace_id,
        name="good_formula",
        content="x",
    )
    bad_asset = await _create_content_asset(
        authenticated_client,
        workspace_id,
        name="bad_formula",
        content="y",
    )
    next_metadata = AssetRenderMetadataService.build_metadata_from_ratio(2.0, source="auto")

    async def fake_measure_metadata(self, *, asset: WorkspaceAsset, content: bytes) -> dict[str, Any]:  # noqa: ARG001
        """按资源名称模拟单项失败。"""

        if asset.name == "bad_formula":
            raise AppException(status_code=422, code="RUNTIME_RENDER_FAILED", detail="公式渲染失败。")
        return next_metadata

    monkeypatch.setattr(
        "app.services.asset_render_hint_measurement_service.AssetRenderHintMeasurementService.measure_metadata",
        fake_measure_metadata,
    )

    create_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/render-hint-backfill-jobs",
        json={"asset_ids": [good_asset["id"], bad_asset["id"]], "mode": "preview"},
    )
    assert create_response.status_code == 200

    await _run_group_jobs(create_response.json())

    group_response = await authenticated_client.get(
        f"/api/asset-render-hint-backfill-job-groups/{create_response.json()['job_group_id']}",
    )
    assert group_response.status_code == 200
    completed = group_response.json()
    assert completed["status"] == "partial"
    assert completed["succeeded_count"] == 1
    assert completed["failed_count"] == 1
    assert completed["failures"] == [
        {
            "asset_id": bad_asset["id"],
            "asset_name": "bad_formula",
            "code": "RUNTIME_RENDER_FAILED",
            "detail": "公式渲染失败。",
        },
    ]


async def test_create_asset_render_hint_backfill_jobs_should_require_workspace_access(
    client: AsyncClient,
) -> None:
    """创建回填任务需要登录并具备工作空间访问权。"""

    response = await client.post(
        "/api/workspaces/1/assets/render-hint-backfill-jobs",
        json={"asset_types": ["formula"], "mode": "preview"},
    )

    assert response.status_code == 401
