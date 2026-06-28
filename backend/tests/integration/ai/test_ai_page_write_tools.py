"""文件功能：验证 AI 页面写入工具对代码校验 warning/error 的处理契约。"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

import app.ai.tools.page.apply_page_edits as apply_page_edits_module
import app.ai.tools.project.project_pages as project_pages_module
from app.ai.agent import AGENT_COORDINATOR_AGENT_ID
from app.ai.auth_tokens import PAGE_TOOL_WRITE_SCOPES, PROJECT_TOOL_WRITE_SCOPES, build_agent_tool_token
from app.ai.platform_tools import AgentToolContext
from app.db.session import get_session_factory
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthContext


WARNING_DIAGNOSTIC = {
    "severity": "warning",
    "source": "runtime-render",
    "code": "PAGE_RENDER_BOTTOM_OVERFLOW",
    "message": "页面内容底部超出画布 42px。",
}


class FakeCodeCheckService:
    """测试用代码检查服务，按类变量返回预置结果。"""

    result: dict[str, Any] = {
        "success": True,
        "status": "passed",
        "summary": "代码检查通过。",
        "diagnostics": [],
    }
    calls: list[dict[str, Any]] = []

    def __init__(self, session: object) -> None:
        self.session = session

    async def check_page_code(self, **kwargs: Any) -> dict[str, Any]:
        """记录页面代码检查参数并返回预置结果。"""

        self.calls.append(kwargs)
        return dict(self.result)


@pytest.fixture(autouse=True)
def reset_fake_code_check() -> None:
    """每个测试前重置代码检查替身状态。"""

    FakeCodeCheckService.result = {
        "success": True,
        "status": "passed",
        "summary": "代码检查通过。",
        "diagnostics": [],
    }
    FakeCodeCheckService.calls = []


async def test_create_project_page_should_not_create_when_precheck_failed(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """创建页面前置校验失败时，不应写入页面记录。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 创建页面校验失败工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 创建页面校验失败项目")
    FakeCodeCheckService.result = {
        "success": False,
        "status": "failed",
        "summary": "发现 1 个错误。",
        "diagnostics": [
            {
                "severity": "error",
                "source": "vite",
                "code": "RUNTIME_VITE_COMPILE_FAILED",
                "message": "编译失败。",
            }
        ],
    }
    monkeypatch.setattr(project_pages_module, "CodeCheckService", FakeCodeCheckService)
    tool = project_pages_module.build_create_project_page_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_tool_run_context(
            workspace_id=workspace_id,
            project_id=project_id,
            scopes=PROJECT_TOOL_WRITE_SCOPES,
        ),
        title="失败页面",
        page_content="<template><main>失败</main></template>",
    )

    assert result["success"] is False
    assert result["message"] == "页面代码校验失败，未创建页面。"
    assert FakeCodeCheckService.calls[0]["page_id"] is None
    assert FakeCodeCheckService.calls[0]["project_id"] == project_id
    assert (await _list_project_pages(authenticated_client, project_id))["total"] == 0


async def test_create_project_page_should_create_and_return_warning(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """创建页面前置校验只有 warning 时，应创建页面并返回诊断。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 创建页面 warning 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 创建页面 warning 项目")
    FakeCodeCheckService.result = {
        "success": True,
        "status": "passed",
        "summary": "代码检查通过，发现 1 个布局警告。",
        "diagnostics": [WARNING_DIAGNOSTIC],
    }
    monkeypatch.setattr(project_pages_module, "CodeCheckService", FakeCodeCheckService)
    tool = project_pages_module.build_create_project_page_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_tool_run_context(
            workspace_id=workspace_id,
            project_id=project_id,
            scopes=PROJECT_TOOL_WRITE_SCOPES,
        ),
        title="Warning 页面",
        page_content="<template><main>Warning</main></template>",
    )

    assert result["success"] is True
    assert result["message"] == "页面已创建，但发现布局警告。"
    assert result["diagnostics"] == [WARNING_DIAGNOSTIC]
    assert result["code_check_summary"] == "代码检查通过，发现 1 个布局警告。"
    assert result["page_id"] > 0
    assert (await _list_project_pages(authenticated_client, project_id))["total"] == 1


async def test_apply_page_edits_should_save_and_return_warning(
    authenticated_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """应用页面 edits 校验只有 warning 时，应保存并透传诊断。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 应用页面 warning 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 应用页面 warning 项目")
    page = await _create_page(authenticated_client, workspace_id, project_id, "待编辑页面")
    FakeCodeCheckService.result = {
        "success": True,
        "status": "passed",
        "summary": "代码检查通过，发现 1 个布局警告。",
        "diagnostics": [WARNING_DIAGNOSTIC],
    }
    monkeypatch.setattr(apply_page_edits_module, "CodeCheckService", FakeCodeCheckService)
    tool = apply_page_edits_module.build_apply_page_edits_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_tool_run_context(
            workspace_id=workspace_id,
            project_id=project_id,
            page_id=page["id"],
            scopes=PAGE_TOOL_WRITE_SCOPES,
        ),
        page_id=page["id"],
        base_version_no=page["current_version_no"],
        edits=[
            {
                "type": "rewrite_file",
                "content": "<template><main>新内容</main></template>",
            }
        ],
    )

    assert result["success"] is True
    assert result["message"] == "页面代码已更新并生成新版本，但发现布局警告。"
    assert result["diagnostics"] == [WARNING_DIAGNOSTIC]
    assert result["code_check_summary"] == "代码检查通过，发现 1 个布局警告。"
    assert result["version_no"] == page["current_version_no"] + 1


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间。"""

    response = await authenticated_client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建测试项目。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


async def _create_page(
    authenticated_client: AsyncClient,
    workspace_id: int,
    project_id: int,
    title: str,
) -> dict[str, Any]:
    """创建测试页面。"""

    response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": title,
            "page_content": "<template><main>旧内容</main></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def _list_project_pages(authenticated_client: AsyncClient, project_id: int) -> dict[str, Any]:
    """读取项目页面列表。"""

    response = await authenticated_client.get("/api/pages", params={"project_id": project_id})
    assert response.status_code == 200, response.text
    return dict(response.json())


def _build_tool_run_context(
    *,
    workspace_id: int,
    project_id: int,
    scopes: tuple[str, ...],
    page_id: int | None = None,
) -> AgentToolContext:
    """构造页面写入工具需要的运行上下文和签名 token。"""

    current = _build_auth_context()
    run_id = "page-write-tool-run"
    session_id = "page-write-tool-session"
    dependencies = {
        "user_id": current.user.id,
        "agent_id": AGENT_COORDINATOR_AGENT_ID,
        "run_id": run_id,
        "session_id": session_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "page_id": page_id,
        "component_id": None,
        "source": "test",
        "backend_session_id": current.backend_session_id,
    }
    dependencies["tool_auth_token"] = build_agent_tool_token(
        current,
        run_id=run_id,
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
        component_id=None,
        source="test",
        scopes=scopes,
    )
    return AgentToolContext(
        run_id=run_id,
        session_id=session_id,
        user_id=str(current.user.id),
        dependencies=dependencies,
    )


def _build_auth_context() -> AuthContext:
    """构造带管理员身份的测试鉴权上下文。"""

    return AuthContext(
        user=User(
            id=1,
            username="admin",
            password_hash="",
            display_name="管理员",
            role=UserRole.PLATFORM_ADMIN.value,
            preview_size_presets=[],
        ),
        session_token="test-session-token",
        backend_session_id="1",
    )
