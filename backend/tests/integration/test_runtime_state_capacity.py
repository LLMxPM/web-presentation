"""文件功能：验证进程内运行态容量预算在业务链路上的拒绝、回滚与无残留语义。"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.core.audio_defaults import default_audio_volume_payload
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.schemas.project_template import PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION
from app.schemas.slideshow import default_slideshow_settings
from app.services.redis_runtime_client import (
    get_redis_runtime_client,
    reset_redis_runtime_client,
)
from app.services.runtime_artifact_store import RuntimeArtifactStore


def _apply_memory_budget(monkeypatch: pytest.MonkeyPatch, *, max_bytes: int, max_item_bytes: int) -> None:
    """以更小的预算重建进程内运行态，模拟容量临界场景。"""

    settings = get_settings()
    monkeypatch.setattr(settings, "runtime_state_memory_max_bytes", max_bytes)
    monkeypatch.setattr(settings, "runtime_state_memory_max_item_bytes", max_item_bytes)
    reset_redis_runtime_client()


@pytest.mark.asyncio
async def test_put_artifact_should_not_leave_partial_state_when_item_exceeds_limit(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单项超限时必须整批拒绝，且不留下可访问的半成品 artifact。"""

    _ = client
    _apply_memory_budget(monkeypatch, max_bytes=10_000_000, max_item_bytes=2_048)
    store = RuntimeArtifactStore()

    with pytest.raises(AppException) as exc_info:
        await store.put_artifact(
            tenant_id="tenant_capacity",
            workspace_id=1,
            project_id=1,
            artifact_kind="page-preview",
            manifest={"preview_kind": "page"},
            config_bundle={},
            modules_data=[{"logical_path": "src/views/big.vue", "content": "x" * 8_000}],
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "RUNTIME_STATE_CAPACITY_EXCEEDED"
    stats = get_redis_runtime_client().stats()
    assert stats.active_keys == 0
    assert stats.approx_bytes == 0
    assert stats.capacity_rejections >= 1


@pytest.mark.asyncio
async def test_put_artifact_should_reject_write_before_budget_is_exceeded(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """累计超预算时拒绝新 artifact，但已写入的 artifact 仍然完整可用。"""

    _ = client
    _apply_memory_budget(monkeypatch, max_bytes=6_000, max_item_bytes=4_000)
    store = RuntimeArtifactStore()
    first_id = await store.put_artifact(
        tenant_id="tenant_capacity",
        workspace_id=1,
        project_id=1,
        artifact_kind="page-preview",
        manifest={"preview_kind": "page"},
        config_bundle={},
        modules_data=[{"logical_path": "src/views/ok.vue", "content": "y" * 2_000}],
    )

    with pytest.raises(AppException) as exc_info:
        await store.put_artifact(
            tenant_id="tenant_capacity",
            workspace_id=1,
            project_id=1,
            artifact_kind="page-preview",
            manifest={"preview_kind": "page"},
            config_bundle={},
            modules_data=[{"logical_path": "src/views/big.vue", "content": "z" * 3_000}],
        )

    assert exc_info.value.code == "RUNTIME_STATE_CAPACITY_EXCEEDED"
    assert await store.get_manifest(first_id) is not None
    assert await store.get_module(first_id, "src/views/ok.vue") == "y" * 2_000
    assert await store.delete_artifact(first_id) == 4


@pytest.mark.asyncio
async def test_template_preview_should_not_leave_artifact_when_capacity_rejected(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模板预览的资源 blob 被容量拒绝时，接口不得签发可用 URL，也不得残留 artifact。"""

    # 基础配置包需能落库；大资源在后续 blob 阶段超过单项预算，才能覆盖半成品清理。
    max_item_bytes = 256 * 1024
    _apply_memory_budget(monkeypatch, max_bytes=32_000_000, max_item_bytes=max_item_bytes)
    original_put_asset_blobs = RuntimeArtifactStore.put_asset_blobs
    blob_write_attempted = False

    async def put_asset_blobs_after_artifact(self, *, artifact_id, assets) -> None:
        """复核 blob 写入前已有完整 artifact，避免测试误落在基础包的容量拒绝分支。"""

        nonlocal blob_write_attempted
        assert await self.get_manifest(artifact_id) is not None
        assert assets
        blob_write_attempted = True
        await original_put_asset_blobs(self, artifact_id=artifact_id, assets=assets)

    monkeypatch.setattr(RuntimeArtifactStore, "put_asset_blobs", put_asset_blobs_after_artifact)
    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "容量模板预览空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = int(workspace_response.json()["id"])

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/template-packages/preview-artifact",
        # SVG 小于文本资源上限，Base64 编码后的 blob 则超出单项缓存预算。
        files={"archive": ("template.zip", _build_minimal_template_package(max_item_bytes * 3 // 2), "application/zip")},
    )

    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "RUNTIME_STATE_CAPACITY_EXCEEDED"
    assert body["message"].startswith("运行时缓存容量已满")
    assert blob_write_attempted
    stats = get_redis_runtime_client().stats()
    assert stats.active_keys == 0
    assert stats.approx_bytes == 0


def _build_minimal_template_package(binary_size: int) -> bytes:
    """按当前协议构造合法模板包，使用大 SVG 资源触发 blob 预算，截图保持有效。"""

    import hashlib
    import io
    import json
    import zipfile
    from datetime import UTC, datetime

    from app.services.project_template_package_service import ProjectTemplatePackageService

    exported_at = datetime.now(tz=UTC).isoformat()
    blob = b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><!--' + b'x' * binary_size + b'--></svg>'
    file_hash = hashlib.sha256(blob).hexdigest()
    asset = {
        "name": "capacity-payload",
        "original_name": "capacity-payload.svg",
        "asset_type": "image",
        "content_type": "image/svg+xml",
        "file_hash": file_hash,
    }
    manifest = {
        "package_type": "web-presentation-project-template",
        "schema_version": PROJECT_TEMPLATE_PACKAGE_SCHEMA_VERSION,
        "exported_at": exported_at,
        "runtime_kit_manifest_version": "1.0.0",
        "template_path": "metadata/template.json",
        "screenshots_path": "metadata/screenshots.json",
        "project_path": "project/project.json",
        "routes_path": "project/routes.json",
        "page_count": 1,
        "component_count": 0,
        "asset_count": 1,
        "theme_count": 0,
        "font_count": 0,
        "pages": [{"source_page_code": "page_cover", "path": "pages/page_cover"}],
        "components": [],
        "assets": [{"file_hash": file_hash}],
        "themes": [],
        "fonts": [],
    }
    template = {
        "slug": "capacity-case",
        "name": "容量用例模板",
        "summary": "容量用例模板。",
        "description": "容量用例模板。",
        "author": "admin",
        "page_count": 1,
        "page_width": 1920,
        "page_height": 1080,
        "aspect_ratio": "16:9",
        "runtime_kit_manifest_version": "1.0.0",
        "created_at": exported_at,
        "updated_at": exported_at,
    }
    screenshots = {
        "cover": {"path": "screenshots/cover.png", "width": 1920, "height": 1080},
        "pages": [
            {
                "source_page_code": "page_cover",
                "title": "封面",
                "path": "screenshots/pages/page_cover.png",
                "order": 1,
                "width": 1920,
                "height": 1080,
            }
        ],
    }
    project = {
        "source_project_code": "PRJ_CAPACITY",
        "name": "容量用例项目",
        "description": "容量用例项目。",
        "page_width": 1920,
        "page_height": 1080,
        "base_font_size": "16px",
        "icon_default_stroke_width": 2,
        "show_pdf_export_button": True,
        "menu_mode": "preview",
        "slideshow": default_slideshow_settings().model_dump(mode="json"),
        "audio_settings": {**default_audio_volume_payload(), "cue_bindings": []},
        "theme_key": None,
        "theme_config_yaml": "themes: {}\n",
        "style_spec_markdown": "",
        "build_extra_assets_json": {"asset_names": []},
        "suggested_reference_asset_names": [],
        "suggested_components": [],
    }
    page = {
        "source_page_code": "page_cover",
        "title": "封面",
        "summary": None,
        "speaker_notes": None,
        "file_type": "vue",
    }
    routes = {
        "routes": [
            {
                "route_type": "page",
                "route": "cover",
                "order": 1,
                "hidden": False,
                "group_title": None,
                "source_page_code": "page_cover",
                "children": [],
            }
        ]
    }
    screenshot = ProjectTemplatePackageService._build_placeholder_png(1920, 1080)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("metadata/template.json", json.dumps(template, ensure_ascii=False))
        archive.writestr("metadata/screenshots.json", json.dumps(screenshots, ensure_ascii=False))
        archive.writestr("project/project.json", json.dumps(project, ensure_ascii=False))
        archive.writestr("project/routes.json", json.dumps(routes, ensure_ascii=False))
        archive.writestr("pages/page_cover/page.json", json.dumps(page, ensure_ascii=False))
        archive.writestr("pages/page_cover/index.vue", "<template><main>cover</main></template>")
        archive.writestr(f"assets/{file_hash}/asset.json", json.dumps(asset))
        archive.writestr(f"assets/{file_hash}/capacity-payload.svg", blob)
        archive.writestr("screenshots/cover.png", screenshot)
        archive.writestr("screenshots/pages/page_cover.png", screenshot)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_concurrent_writes_should_never_exceed_budget(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """临界并发写入不能突破预算：拒绝发生在锁内，超限写入不会生效。"""

    _ = client
    _apply_memory_budget(monkeypatch, max_bytes=20_000, max_item_bytes=20_000)
    client_handle = get_redis_runtime_client()

    async def _write(index: int) -> bool:
        try:
            return bool(
                await asyncio.to_thread(
                    client_handle.set,
                    client_handle.key(f"concurrent:{index}"),
                    "p" * 2_000,
                    ex=60,
                )
            )
        except AppException:
            return False
        except Exception:  # noqa: BLE001
            return False

    results = await asyncio.gather(*(_write(index) for index in range(16)))

    stats = client_handle.stats()
    assert stats.approx_bytes is not None and stats.approx_bytes <= 20_000
    assert stats.active_keys is not None and stats.active_keys < 16
    assert any(results)


@pytest.mark.asyncio
async def test_repeated_preview_creation_capacity_accounting_and_sweep_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """定向验证 M03-F1：同项目多次新建预览累积达到总量预算时被拒（503），过期清扫后容量完全恢复。"""

    _apply_memory_budget(monkeypatch, max_bytes=6_000, max_item_bytes=4_000)
    store = RuntimeArtifactStore()

    # 1. 循环创建短 TTL artifact (每个约 2KB) 直至累计突破 6,000 字节总预算被拒 (M03-F1 根本成因)
    created_ids: list[str] = []
    with pytest.raises(AppException) as exc_info:
        for idx in range(10):
            art = await store.put_artifact(
                tenant_id="tenant_cap",
                workspace_id=1,
                project_id=1,
                artifact_kind="page-preview",
                manifest={"preview_kind": "page"},
                config_bundle={},
                modules_data=[{"logical_path": f"src/views/p{idx}.vue", "content": "x" * 1_500}],
                ttl_seconds=1,
            )
            created_ids.append(art)

    assert len(created_ids) >= 1  # 至少第一个成功创建
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "RUNTIME_STATE_CAPACITY_EXCEEDED"
    assert "超过进程内预算" in exc_info.value.detail or "容量已满" in exc_info.value.detail

    # 2. 等待 TTL 过期并执行主动清扫
    await asyncio.sleep(1.2)
    purged_count = await store.sweep_expired()
    assert purged_count >= len(created_ids) * 4

    # 3. 容量已恢复，再次创建应立即成功
    art_after = await store.put_artifact(
        tenant_id="tenant_cap",
        workspace_id=1,
        project_id=1,
        artifact_kind="page-preview",
        manifest={"preview_kind": "page"},
        config_bundle={},
        modules_data=[{"logical_path": "src/views/new.vue", "content": "e" * 1_500}],
        ttl_seconds=60,
    )
    assert art_after is not None
    assert await store.get_manifest(art_after) is not None
