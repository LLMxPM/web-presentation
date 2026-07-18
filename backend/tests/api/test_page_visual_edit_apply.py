"""文件功能：验证页面可视化编辑 apply API 的成功保存、冲突和失败不落库语义。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.core.exceptions import AppException
from app.schemas.page_visual_edit_manifest import (
    PageVisualEditManifest,
    PageVisualEditNode,
    PageVisualEditSourceRange,
    build_page_visual_edit_source_hash,
)
from app.schemas.runtime_page_visual_edit import (
    RuntimePageVisualEditAnalyzeRequest,
    RuntimePageVisualEditAnalyzeResponse,
    RuntimePageVisualEditApplyRequest,
    RuntimePageVisualEditApplyResponse,
)
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.runtime_visual_edit_client import RuntimeVisualEditClient


SOURCE = "<template><main>旧标题</main></template>"
NEXT_SOURCE = "<template><main>新标题</main></template>"


async def _create_page(authenticated_client: AsyncClient) -> dict[str, Any]:
    """创建可用于 apply 集成测试的工作空间、项目和 Vue 页面。"""

    workspace = await authenticated_client.post(
        "/api/workspaces",
        json={"name": "Apply 测试空间", "status": "active"},
    )
    assert workspace.status_code == 200
    project = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace.json()["id"],
            "name": "Apply 测试项目",
            "status": "active",
        },
    )
    assert project.status_code == 200
    page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": SOURCE,
            "file_type": "vue",
            "title": "Apply 测试页面",
            "status": "active",
            "workspace_id": workspace.json()["id"],
            "project_id": project.json()["id"],
        },
    )
    assert page.status_code == 200
    return page.json()


def _patch_analyze(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 create artifact 使用与请求源码严格绑定的 Runtime 分析结果。"""

    async def analyze(
        _self: RuntimeVisualEditClient,
        request: RuntimePageVisualEditAnalyzeRequest,
    ) -> RuntimePageVisualEditAnalyzeResponse:
        """返回包含最小节点树和空 Tailwind Catalog 的 canonical Manifest。"""

        return RuntimePageVisualEditAnalyzeResponse(
            protocol_version=1,
            manifest=PageVisualEditManifest(
                protocol_version=1,
                module_path=request.module_path,
                source_hash=request.source_hash,
                root=PageVisualEditNode(
                    node_id="node_root",
                    kind="root",
                    tag="#document",
                    source_range=PageVisualEditSourceRange(
                        start=0, end=len(request.source)
                    ),
                ),
                diagnostics=[],
                tailwind_catalog={"version": 1, "groups": []},
            ),
            instrumented_source=f"{request.source}\n<!-- instrumented-only -->",
        )

    monkeypatch.setattr(RuntimeVisualEditClient, "analyze", analyze)


async def _create_artifact(
    authenticated_client: AsyncClient,
    page: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """创建绑定页面 v1 的可视化编辑 artifact。"""

    _patch_analyze(monkeypatch)
    response = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/preview-artifacts",
        json={"protocol_version": 1, "base_version_no": 1},
    )
    assert response.status_code == 200
    return response.json()


def _build_apply_payload(
    artifact: dict[str, Any], *, source_hash: str | None = None
) -> dict[str, Any]:
    """构造包含两个不同绑定目标的完整批量编辑请求。"""

    return {
        "protocol_version": 1,
        "artifact_id": artifact["artifact_id"],
        "base_version_no": 1,
        "source_hash": source_hash or artifact["visual_edit"]["source_hash"],
        "operations": [
            {
                "type": "set_value",
                "node_id": "node_title",
                "binding_id": "binding_title",
                "instance_path": [],
                "value": "新标题",
            },
            {
                "type": "set_value",
                "node_id": "node_subtitle",
                "binding_id": "binding_subtitle",
                "instance_path": [],
                "value": "新副标题",
            },
        ],
        "change_note": "可视化批量编辑",
    }


def _patch_apply(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candidate_source: str = NEXT_SOURCE,
    failure: AppException | None = None,
    inspect_request: Callable[[RuntimePageVisualEditApplyRequest], None] | None = None,
) -> None:
    """替换尚未落地的 Runtime apply 端点并返回候选源码或稳定失败。"""

    async def apply(
        _self: RuntimeVisualEditClient,
        request: RuntimePageVisualEditApplyRequest,
    ) -> RuntimePageVisualEditApplyResponse:
        """模拟 Runtime 对整个操作批次执行 AST 改写。"""

        if inspect_request is not None:
            inspect_request(request)
        if failure is not None:
            raise failure
        return RuntimePageVisualEditApplyResponse(
            protocol_version=1,
            base_source_hash=request.source_hash,
            next_source_hash=build_page_visual_edit_source_hash(candidate_source),
            next_source=candidate_source,
            operations_applied=len(request.operations),
            canonical_diff="-旧标题\n+新标题",
        )

    monkeypatch.setattr(RuntimeVisualEditClient, "apply", apply)


@pytest.mark.asyncio
async def test_apply_should_save_one_version_for_complete_batch(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两个操作整批成功时应仅创建一个新版本，并且 Runtime 只能看到规范源码。"""

    page = await _create_page(authenticated_client)
    artifact = await _create_artifact(authenticated_client, page, monkeypatch)

    def inspect_request(request: RuntimePageVisualEditApplyRequest) -> None:
        """确认保存链路未从 artifact 读取插桩模块作为 canonical source。"""

        assert request.source == SOURCE
        assert "instrumented-only" not in request.source
        assert len(request.operations) == 2

    _patch_apply(monkeypatch, inspect_request=inspect_request)
    response = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/apply",
        json=_build_apply_payload(artifact),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["operations_applied"] == 2
    assert payload["previous_version_no"] == 1
    assert payload["current_version_no"] == 2
    assert payload["refresh_required"] is True
    page_response = await authenticated_client.get(f"/api/pages/{page['id']}")
    assert page_response.json()["page_content"] == NEXT_SOURCE
    assert page_response.json()["current_version_no"] == 2
    versions = await authenticated_client.get(f"/api/pages/{page['id']}/versions")
    assert [item["version_no"] for item in versions.json()] == [2, 1]


@pytest.mark.asyncio
async def test_apply_should_reject_expired_artifact(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """artifact 被清理后 apply 应返回稳定过期错误且页面保持 v1。"""

    page = await _create_page(authenticated_client)
    artifact = await _create_artifact(authenticated_client, page, monkeypatch)
    await RuntimeArtifactStore().delete_artifact(artifact["artifact_id"])
    response = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/apply",
        json=_build_apply_payload(artifact),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PAGE_VISUAL_EDIT_ARTIFACT_EXPIRED"
    page_response = await authenticated_client.get(f"/api/pages/{page['id']}")
    assert page_response.json()["current_version_no"] == 1


@pytest.mark.asyncio
async def test_apply_should_reject_artifact_from_another_page_scope(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """另一个项目页面签发的 artifact 不得用于当前页面，即使源码和版本恰好相同。"""

    source_page = await _create_page(authenticated_client)
    artifact = await _create_artifact(authenticated_client, source_page, monkeypatch)
    target_page = await _create_page(authenticated_client)
    apply_mock = AsyncMock()
    monkeypatch.setattr(RuntimeVisualEditClient, "apply", apply_mock)

    response = await authenticated_client.post(
        f"/api/pages/{target_page['id']}/visual-edit/apply",
        json=_build_apply_payload(artifact),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PAGE_VISUAL_EDIT_ARTIFACT_SCOPE_DENIED"
    apply_mock.assert_not_awaited()
    page_response = await authenticated_client.get(f"/api/pages/{target_page['id']}")
    assert page_response.json()["current_version_no"] == 1


@pytest.mark.asyncio
async def test_apply_should_reject_version_and_hash_conflicts(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """版本和 hash 乐观锁均应独立阻止旧编辑基线写入。"""

    page = await _create_page(authenticated_client)
    artifact = await _create_artifact(authenticated_client, page, monkeypatch)
    hash_conflict = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/apply",
        json=_build_apply_payload(
            artifact,
            source_hash=build_page_visual_edit_source_hash("other source"),
        ),
    )
    assert hash_conflict.status_code == 409
    assert hash_conflict.json()["code"] == "PAGE_VISUAL_EDIT_SOURCE_HASH_STALE"

    update = await authenticated_client.patch(
        f"/api/pages/{page['id']}",
        json={"page_content": "<template><main>并发更新</main></template>"},
    )
    assert update.status_code == 200
    version_conflict = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/apply",
        json=_build_apply_payload(artifact),
    )
    assert version_conflict.status_code == 409
    assert version_conflict.json()["code"] == "PAGE_VISUAL_EDIT_BASE_VERSION_STALE"


@pytest.mark.asyncio
async def test_apply_runtime_failure_should_not_create_version(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime 改写失败时 Backend 不得创建候选页面版本。"""

    page = await _create_page(authenticated_client)
    artifact = await _create_artifact(authenticated_client, page, monkeypatch)
    _patch_apply(
        monkeypatch,
        failure=AppException(
            status_code=502,
            code="RUNTIME_VISUAL_EDIT_FAILED",
            detail="Runtime apply 未就绪。",
        ),
    )
    response = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/apply",
        json=_build_apply_payload(artifact),
    )

    assert response.status_code == 502
    assert response.json()["code"] == "RUNTIME_VISUAL_EDIT_FAILED"
    page_response = await authenticated_client.get(f"/api/pages/{page['id']}")
    assert page_response.json()["current_version_no"] == 1


@pytest.mark.asyncio
async def test_apply_invalid_candidate_should_rollback_version(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """候选源码违反 Runtime Kit import 边界时应回滚 PageVersion 和页面当前指针。"""

    page = await _create_page(authenticated_client)
    artifact = await _create_artifact(authenticated_client, page, monkeypatch)
    invalid_candidate = """<script setup lang=\"ts\">
import Icon from '@runtime-kit/public/components/primitives/Icon.vue'
</script>
<template><Icon /></template>"""
    _patch_apply(monkeypatch, candidate_source=invalid_candidate)
    response = await authenticated_client.post(
        f"/api/pages/{page['id']}/visual-edit/apply",
        json=_build_apply_payload(artifact),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "RUNTIME_LOCAL_IMPORT_FORBIDDEN"
    page_response = await authenticated_client.get(f"/api/pages/{page['id']}")
    assert page_response.json()["page_content"] == SOURCE
    assert page_response.json()["current_version_no"] == 1
    versions = await authenticated_client.get(f"/api/pages/{page['id']}/versions")
    assert [item["version_no"] for item in versions.json()] == [1]
