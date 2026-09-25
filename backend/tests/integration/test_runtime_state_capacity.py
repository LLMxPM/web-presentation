"""文件功能：验证进程内运行态容量预算在业务链路上的拒绝、回滚与无残留语义。"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.exceptions import AppException
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

    _apply_memory_budget(monkeypatch, max_bytes=32_000_000, max_item_bytes=4_096)
    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "容量模板预览空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = int(workspace_response.json()["id"])

    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/template-packages/preview-artifact",
        files={"archive": ("template.zip", _build_minimal_template_package(64 * 1024), "application/zip")},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "RUNTIME_STATE_CAPACITY_EXCEEDED"
    assert body["message"].startswith("运行时缓存容量已满")
    stats = get_redis_runtime_client().stats()
    assert stats.active_keys == 0
    assert stats.approx_bytes == 0


def _build_minimal_template_package(binary_size: int) -> bytes:
    """构造最小可解析模板包：只保留校验必需文件，并携带一个超限二进制资源。"""

    import io
    import json
    import zipfile
    from datetime import UTC, datetime

    exported_at = datetime.now(tz=UTC).isoformat()
    manifest = {
        "package_type": "web-presentation-project-template",
        "schema_version": 1,
        "exported_at": exported_at,
        "runtime_kit_manifest_version": "1.0.0",
        "template_path": "metadata/template.json",
        "screenshots_path": "metadata/screenshots.json",
        "project_path": "project/project.json",
        "routes_path": "project/routes.json",
        "page_count": 1,
        "component_count": 0,
        "asset_count": 0,
        "theme_count": 0,
        "font_count": 0,
        "pages": [{"source_page_code": "page_cover", "path": "pages/page_cover"}],
        "components": [],
        "assets": [],
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
    blob = b"\x89PNG\r\n\x1a\n" + bytes((index * 31 + 7) % 256 for index in range(binary_size))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("metadata/template.json", json.dumps(template, ensure_ascii=False))
        archive.writestr("metadata/screenshots.json", json.dumps(screenshots, ensure_ascii=False))
        archive.writestr("project/project.json", json.dumps(project, ensure_ascii=False))
        archive.writestr("project/routes.json", json.dumps(routes, ensure_ascii=False))
        archive.writestr("pages/page_cover/page.json", json.dumps(page, ensure_ascii=False))
        archive.writestr("pages/page_cover/index.vue", "<template><main>cover</main></template>")
        archive.writestr("screenshots/cover.png", blob)
        archive.writestr("screenshots/pages/page_cover.png", blob)
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