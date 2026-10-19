"""文件功能：对固定页面集实测关闭/开启附图、连续保存与缓存命中，不用 Mock 推断浏览器收益。"""

import json
import time

from app.db.session import get_session_factory
from app.models.page import Page
from app.schemas.page import PageUpdateRequest
from app.services.capture_viewport_resolver import CaptureViewport
from app.services.code_check_service import CodeCheckService
from app.services.object_storage_service import ObjectStorageService
from app.services.page_screenshot_fingerprint_service import (
    PageScreenshotFingerprintService,
)
from app.services.page_screenshot_service import PageScreenshotService
from app.services.page_service import PageService
from app.services.validation_result import is_validation_passed
from app.services.validation_screenshot_publisher import (
    prepare_validation_screenshot,
    publish_validation_screenshot,
)
from validation_screenshot_fixtures import create_fixed_pages


async def run_benchmark(client, *, ws: int, project_id: int, user_id: int, token: str, root, out, report,
                        request_json, metrics, verify_png, cli_call, context_source: str) -> None:
    """基线走相同 CodeCheck 与 PageService，分别关闭/开启图片阶段，再按真实公开接口取图。"""
    empty = await cli_call(token, ws, "asset", "list", "--type", "icon", "--page", "1", "--page-size", "50")
    assert empty["total"] == 0
    sources = await create_fixed_pages(client, ws, request_json=request_json, root=root, context_source=context_source)
    icons = await cli_call(token, ws, "asset", "list", "--type", "icon", "--page", "1", "--page-size", "50")
    assert icons["total"] == 1 and icons["items"][0]["name"] == "drill-icon"
    contract = await cli_call(token, ws, "runtime-kit", "get", "Icon.v1")
    capability = contract.get("capability") or contract
    assert contract.get("import_path") and all(name in capability for name in ("usage", "constraints", "preview_schema"))
    report["resource_discovery"] = {"empty_total": empty["total"], "created_icon": icons["items"][0]["name"], "total": icons["total"]}
    report["benchmark"] = []
    for kind, source in sources.items():
        page = await request_json(client, "POST", "/api/pages", json={"workspace_id": ws, "project_id": project_id,
                    "title": f"正式标题 {kind}", "page_content": "<template><main /></template>"})
        page_id = page["id"]
        for capture in (False, True):
            before = await metrics(project_id)
            started = time.perf_counter()
            async with get_session_factory()() as session:
                checker = CodeCheckService(session)
                validation = await checker.check_page_code(page_id=page_id, workspace_id=ws, user_id=user_id,
                                                           content=source, capture_screenshot=capture)
                assert is_validation_passed(validation), validation
                check_ms = round((time.perf_counter()-started)*1000,2)
                if capture:
                    cached = await checker.check_page_code(page_id=page_id, workspace_id=ws, user_id=user_id,
                                                            content=source, capture_screenshot=True)
                    assert cached["_code_check_cache"] == "hit", cached.get("_code_check_cache")
            prepared = await prepare_validation_screenshot(validation, workspace_id=ws) if capture else None
            async with get_session_factory()() as session:
                await PageService(session).update(page_id, PageUpdateRequest(page_content=source), user_id, commit=False)
                model = await session.get(Page, page_id)
                if capture:
                    screenshot = await publish_validation_screenshot(session, page=model, validation=validation, prepared=prepared)
                    assert screenshot["status"] == "ready", screenshot
                await session.commit()
            write_ms = round((time.perf_counter()-started)*1000,2)
            png = await client.get(f"/api/v1/pages/{page_id}/screenshot", headers={"Authorization": f"Bearer {token}"})
            assert png.is_success, png.text[:500] if not png.is_success else ""
            verify_png(png.content)
            (out / f"{kind}-{'joint' if capture else 'baseline'}.png").write_bytes(png.content)
            after = await metrics(project_id)
            delta = {key: after[key] - before[key] for key in ("attempts", "successful_attempts", "launches", "navigations", "physical_launches", "physical_navigations", "png_bytes", "screenshot_ms", "diagnose_ms")}
            assert delta["successful_attempts"] == (1 if capture else 2), delta
            assert delta["launches"] == delta["navigations"] == delta["successful_attempts"]
            assert delta["physical_launches"] == delta["physical_navigations"] == delta["successful_attempts"]
            row = {"fixture": kind, "capture_screenshot": capture, "check_ms": check_ms, "write_ms": write_ms,
                    "total_ms": round((time.perf_counter()-started)*1000,2), "cache_hit_without_attempt": capture, **delta}
            report["benchmark"].append(row)
            (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if kind == "context" and capture:
                async with get_session_factory()() as session:
                    model = await session.get(Page, page_id)
                    snapshot = await PageScreenshotFingerprintService(session).build_page_snapshot(model)
                    artifact = await PageScreenshotService(session).capture_page_screenshot_artifact(page=model, operator_id=user_id,
                        target_page_version_no=model.current_version_no, config_hash=snapshot.config_hash,
                        viewport=CaptureViewport(width=snapshot.page_config.width, height=snapshot.page_config.height))
                formal = await ObjectStorageService().read_object(artifact.storage_key)
                assert formal == png.content, "保存后的正式上下文与候选截图不一致"
                report["context_parity"] = "候选与正式截图 PNG 字节一致"
