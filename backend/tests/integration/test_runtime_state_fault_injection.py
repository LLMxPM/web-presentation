"""文件功能：注入运行态故障，验证已提交业务不被误报、预览不签发不可用 URL。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from httpx import AsyncClient

from app.services.redis_runtime_client import RedisRuntimeClient, RuntimeStateUnavailableError


def _inject_runtime_state_failure(
    monkeypatch: pytest.MonkeyPatch,
    failure: Callable[[], Any],
) -> None:
    """让运行态 facade 的批处理与读取整体失败，模拟运行态后端断连。"""

    def _failing_batch(self: RedisRuntimeClient) -> Any:  # noqa: ARG001
        return failure()

    def _failing_get(self: RedisRuntimeClient, key: str) -> Any:  # noqa: ARG001
        return failure()

    monkeypatch.setattr(RedisRuntimeClient, "batch", _failing_batch)
    monkeypatch.setattr(RedisRuntimeClient, "get", _failing_get)


async def _create_project_with_page(
    client: AsyncClient,
    *,
    name: str,
) -> tuple[int, int, int]:
    """创建一个带可见入口路由的工作空间 / 项目 / 页面。"""

    workspace_response = await client.post(
        "/api/workspaces",
        json={"name": f"{name}空间", "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = int(workspace_response.json()["id"])
    project_response = await client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": f"{name}项目"},
    )
    assert project_response.status_code == 200
    project_id = int(project_response.json()["id"])
    page_response = await client.post(
        "/api/pages",
        json={
            "project_id": project_id,
            "workspace_id": workspace_id,
            "title": f"{name}页面",
            "page_content": "<template><main>runtime state</main></template>",
            "file_type": "vue",
        },
    )
    assert page_response.status_code == 200
    page_id = int(page_response.json()["id"])
    route_response = await client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {"route_type": "page", "route": "home", "order": 1, "hidden": False, "page_id": page_id}
            ]
        },
    )
    assert route_response.status_code == 200
    return workspace_id, project_id, page_id


@pytest.mark.asyncio
async def test_build_job_creation_should_survive_runtime_state_failure(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缓存写失败不得把已提交到数据库的构建任务误报为未创建。"""

    _, project_id, _ = await _create_project_with_page(authenticated_client, name="构建缓存故障")

    def _raise() -> None:
        raise RuntimeStateUnavailableError("运行态存储连接失败。")

    _inject_runtime_state_failure(monkeypatch, _raise)

    create_response = await authenticated_client.post(f"/api/projects/{project_id}/build-jobs", json={})
    assert create_response.status_code == 200
    job = create_response.json()
    assert int(job["id"]) > 0
    assert job["status"] in {"pending", "running"}

    list_response = await authenticated_client.get(f"/api/projects/{project_id}/build-jobs")
    assert list_response.status_code == 200
    jobs = list_response.json()
    assert [int(item["id"]) for item in jobs] == [int(job["id"])]


@pytest.mark.asyncio
async def test_preview_creation_should_fail_with_retryable_error_when_runtime_state_down(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行态不可用时预览创建返回 503 可重试错误，不签发不可用 URL。"""

    _, project_id, _ = await _create_project_with_page(authenticated_client, name="预览缓存故障")

    def _raise() -> None:
        raise RuntimeStateUnavailableError("运行态存储连接失败。")

    _inject_runtime_state_failure(monkeypatch, _raise)

    response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "RUNTIME_STATE_UNAVAILABLE"
    assert "preview_url" not in body