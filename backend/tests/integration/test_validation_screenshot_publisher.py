"""文件功能：验证校验附图发布、候选变化拒绝、跨空间及过期对象回收。"""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from app.core.exceptions import AppException
from app.core.time_utils import utc_now
from app.db.session import get_session_factory
from app.models.page import Page
from app.models.page_screenshot_artifact import PageScreenshotArtifact
from app.models.project_route import ProjectRoute
from app.schemas.page import PageCopyToProjectRequest, PageCreateRequest
from app.services.code_check_fingerprint import CodeCheckFingerprintBuilder
from app.services.code_check_result_cache import compute_check_fingerprint
from app.services.page_candidate_routes import candidate_runtime_routes
from app.services.page_screenshot_fingerprint_service import (
    PageScreenshotFingerprintService,
)
from app.services.page_service import PageService
from app.services.project_route_service import ProjectRouteService
from app.services.validation_screenshot_cleanup import cleanup_validation_screenshots
from app.services.validation_screenshot_publisher import (
    PreparedValidationScreenshot,
    publish_validation_screenshot,
)
from sqlalchemy import select


@pytest.mark.parametrize("drift", [None, "source", "title", "expired", "scope", "viewport"])
async def test_publish_only_matching_candidate(authenticated_client, drift):
    """原始候选可原子发布；源码/标题变化、跨空间或过期不得返回 ready。

    页面读取路由上下文，因此标题属于截图身份的一部分；纯内容页面的标题变化
    不再使旧图失效，由 API 层用例覆盖。
    """
    ws = (await authenticated_client.post("/api/workspaces", json={"name": "截图发布测试"})).json()["id"]
    project = (await authenticated_client.post("/api/projects", json={"workspace_id": ws, "name": "截图项目"})).json()["id"]
    page_source = (
        "<template><main>正式内容 {{ route.meta.title }}</main></template>\n"
        "<script setup>\n"
        "import { useRoute } from 'vue-router'\n"
        "const route = useRoute()\n"
        "</script>"
    )
    page_response = await authenticated_client.post("/api/pages", json={"workspace_id": ws, "project_id": project,
                "title": "正式标题", "page_content": page_source})
    assert page_response.status_code == 200, page_response.text
    page_id = page_response.json()["id"]
    async with get_session_factory()() as session:
        page = await session.get(Page, page_id)
        base = await CodeCheckFingerprintBuilder(session).build_page_fingerprint(workspace_id=ws, project_id=project,
            source=page.page_content, importer_module_path=f"src/views/{page.code}.vue",
            page_metadata={"code": page.code, "title": page.title, "speaker_notes": page.speaker_notes})
        identity = compute_check_fingerprint({"diagnostics": base, "capture_screenshot": True, "capture_policy": "page-static-capture.v1"})
        snapshot = await PageScreenshotFingerprintService(session).build_page_snapshot(page)
        expires = utc_now() + timedelta(minutes=-1 if drift == "expired" else 10)
        artifact = PageScreenshotArtifact(artifact_id="candidate", workspace_id=ws, sha256="a" * 64,
                                         storage_key="test/candidate.png", expires_at=expires)
        session.add(artifact)
        await session.flush()
        if drift == "source":
            page.page_content = "<template><main>变化的内容</main></template>"
        if drift == "title":
            page.title = "变更标题"
        prepared = PreparedValidationScreenshot("candidate", identity, ws + 1 if drift == "scope" else ws, "a" * 64,
                        1 if drift == "viewport" else snapshot.page_config.width, snapshot.page_config.height)
        result = await publish_validation_screenshot(session, page=page, validation={}, prepared=prepared)
        assert result["status"] == ("ready" if drift is None else "pending")
        assert (page.screenshot_storage_key is not None) == (drift is None)
        await session.commit()


async def test_cleanup_only_unpublished_expired_candidates(authenticated_client, monkeypatch):
    """取消/崩溃留下的临时对象过期后回收，已发布和未过期对象继续保留。"""
    ws = (await authenticated_client.post("/api/workspaces", json={"name": "截图回收测试"})).json()["id"]
    async with get_session_factory()() as session:
        for name, expires in (("expired", utc_now() - timedelta(seconds=1)), ("fresh", utc_now() + timedelta(minutes=1))):
            session.add(PageScreenshotArtifact(artifact_id=name, workspace_id=ws, sha256="a" * 64,
                                              storage_key=f"test/{name}.png", expires_at=expires))
        await session.commit()
    remove = AsyncMock()
    monkeypatch.setattr("app.services.validation_screenshot_cleanup.ObjectStorageService.delete_object", remove)
    assert await cleanup_validation_screenshots(get_session_factory()) == 1
    remove.assert_awaited_once_with("test/expired.png")
    async with get_session_factory()() as session:
        assert list(await session.scalars(select(PageScreenshotArtifact.artifact_id))) == ["fresh"]


async def test_create_uses_planned_code_and_rejects_conflict(authenticated_client):
    """正式创建必须沿用候选编码；冲突时拒绝保存，不改码复用旧图。"""
    identity = (await authenticated_client.get("/api/auth/me")).json()
    ws = (await authenticated_client.post("/api/workspaces", json={"name": "候选编码测试"})).json()["id"]
    project = (await authenticated_client.post("/api/projects", json={"workspace_id": ws, "name": "候选编码项目"})).json()["id"]
    async with get_session_factory()() as session:
        service = PageService(session)
        payload = PageCreateRequest(workspace_id=ws, project_id=project, title="正式标题", page_content="<template><main /></template>")
        created = await service.create(payload, identity["id"], candidate_code="PG20261019991")
        assert created.code == "PG20261019991"
        with pytest.raises(AppException) as caught:
            await service.create(payload, identity["id"], candidate_code=created.code)
        assert caught.value.code == "PAGE_CANDIDATE_CODE_CONFLICT"


@pytest.mark.parametrize("placement", ["root", "group"])
async def test_created_route_context_matches_candidate(authenticated_client, placement):
    """创建页读取目录/页码时，候选路由结构必须与正式保存结果完全一致。"""
    user = (await authenticated_client.get("/api/auth/me")).json()["id"]
    ws = (await authenticated_client.post("/api/workspaces", json={"name": "候选路由测试"})).json()["id"]
    project = (await authenticated_client.post("/api/projects", json={"workspace_id": ws, "name": "候选路由项目"})).json()["id"]
    async with get_session_factory()() as session:
        options = {"route_placement": placement, "route": "overview"}
        if placement == "group":
            parent = ProjectRoute(project_id=project, route="chapter", route_type="group", group_title="章节", order=10, hidden=False,
                                  created_by=user, updated_by=user)
            session.add(parent)
            await session.flush()
            options["parent_route_id"] = parent.id
        draft = Page(code="PG20261019992", project_id=project, workspace_id=ws, title="正式标题", speaker_notes="备注", file_type="vue")
        candidate = await candidate_runtime_routes(session, page=draft, options=options)
        await PageService(session).create(PageCreateRequest(workspace_id=ws, project_id=project, title=draft.title,
            speaker_notes=draft.speaker_notes, page_content="<template><main /></template>"), user, candidate_code=draft.code,
            route_options=PageCopyToProjectRequest(target_project_id=project, **options), commit=False)
        actual = await ProjectRouteService(session).build_runtime_route_config(project)
        assert candidate == actual


@pytest.mark.parametrize("placement", ["root", "group"])
async def test_candidate_capture_identity_matches_saved_page(authenticated_client, placement):
    """候选捕获身份必须等于保存后复算的身份，否则附图会被判为输入变化而丢弃。"""
    user = (await authenticated_client.get("/api/auth/me")).json()["id"]
    ws = (await authenticated_client.post("/api/workspaces", json={"name": "候选身份测试"})).json()["id"]
    project = (await authenticated_client.post("/api/projects", json={"workspace_id": ws, "name": "候选身份项目"})).json()["id"]
    page_source = (
        "<template><div>{{ catalog.length }}</div></template>\n"
        "<script setup>\n"
        "import { useRouteCatalog } from '@runtime-kit/public/composables/page/useRouteCatalog.v1'\n"
        "const catalog = useRouteCatalog().catalogItems.value\n"
        "</script>"
    )
    async with get_session_factory()() as session:
        options = {"route_placement": placement, "route": "overview"}
        if placement == "group":
            parent = ProjectRoute(project_id=project, route="chapter", route_type="group", group_title="章节", order=10,
                                  hidden=False, created_by=user, updated_by=user)
            session.add(parent)
            await session.flush()
            options["parent_route_id"] = parent.id
        draft = Page(code="PG20261019993", project_id=project, workspace_id=ws, title="候选身份标题",
                     speaker_notes="备注", file_type="vue")
        candidate = await candidate_runtime_routes(session, page=draft, options=options)
        created = await PageService(session).create(
            PageCreateRequest(workspace_id=ws, project_id=project, title=draft.title,
                              speaker_notes=draft.speaker_notes, page_content=page_source),
            user,
            candidate_code=draft.code,
            route_options=PageCopyToProjectRequest(target_project_id=project, **options),
            commit=False,
        )
        saved_page = await session.get(Page, created.id)
        assert saved_page is not None
        builder = CodeCheckFingerprintBuilder(session)
        candidate_identity = await builder.build_page_fingerprint(
            workspace_id=ws,
            project_id=project,
            source=page_source,
            importer_module_path=f"src/views/{draft.code}.vue",
            page_metadata={"code": draft.code, "title": draft.title, "speaker_notes": draft.speaker_notes},
            runtime_routes_override=candidate,
        )
        saved_identity = await builder.build_page_fingerprint(
            workspace_id=ws,
            project_id=project,
            source=saved_page.page_content,
            importer_module_path=f"src/views/{saved_page.code}.vue",
            page_metadata={"code": saved_page.code, "title": saved_page.title, "speaker_notes": saved_page.speaker_notes},
        )
        assert candidate_identity == saved_identity
