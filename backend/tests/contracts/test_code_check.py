"""文件功能：验证页面/组件代码检查服务的 diff 校验、Runtime 调用映射与临时依赖图构建。"""

from __future__ import annotations

from httpx import AsyncClient

from app.db.session import get_session_factory
from app.services.code_check_service import CodeCheckService
from app.services.token_service import TokenService


class FakeRuntimeDiagnosticsClient:
    """测试用 Runtime 诊断客户端，记录调用并返回固定结果。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def dispatch_artifact_diagnostics(
        self,
        *,
        artifact_id: str,
        diagnostics_token: str,
        label: str | None = None,
    ) -> dict[str, object]:
        """记录诊断调用并返回通过结果。"""

        self.calls.append(
            {
                "artifact_id": artifact_id,
                "diagnostics_token": diagnostics_token,
                "label": label,
            }
        )
        return {
            "success": True,
            "status": "passed",
            "artifact_id": artifact_id,
            "summary": "代码检查通过。",
            "diagnostics": [],
        }


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间。"""

    response = await authenticated_client.post("/api/workspaces", json={"name": name, "status": "active"})
    assert response.status_code == 200
    return response.json()["id"]


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str) -> int:
    """创建测试项目。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _publish_component(authenticated_client: AsyncClient, component_id: int) -> dict[str, object]:
    """发布组件草稿。"""

    response = await authenticated_client.post(
        f"/api/components/{component_id}/publish",
        json={"change_note": "发布供代码检查引用"},
    )
    assert response.status_code == 200
    return response.json()


async def test_code_check_should_reject_invalid_edits_before_runtime(authenticated_client: AsyncClient) -> None:
    """非法 edits 应在 Backend 阶段失败，不应调用 Runtime。"""

    workspace_id = await _create_workspace(authenticated_client, "代码检查 edits 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "代码检查 edits 项目")
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "Edits 页面",
            "page_content": "<template><main>旧内容</main></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert page_response.status_code == 200
    fake_runtime = FakeRuntimeDiagnosticsClient()

    async with get_session_factory()() as session:
        result = await CodeCheckService(session, runtime_client=fake_runtime).check_page_code(
            page_id=page_response.json()["id"],
            workspace_id=workspace_id,
            user_id=1,
            edits=[{"type": "replace_exact", "old_text": "不存在", "new_text": "新内容"}],
        )

    assert result["success"] is False
    assert result["diagnostics"][0]["code"] == "AI_SOURCE_EDIT_NO_MATCH"
    assert fake_runtime.calls == []


def test_runtime_diagnostics_token_should_embed_artifact_scope() -> None:
    """Runtime 诊断命令令牌应绑定 artifact 与工作空间范围。"""

    token = TokenService.generate_runtime_diagnostics_command_token(
        artifact_id="123",
        workspace_id=9,
        project_id=8,
    )
    claims = TokenService.verify_runtime_diagnostics_command_token(token)

    assert claims["aud"] == "runtime-diagnostics"
    assert claims["artifact_id"] == "123"
    assert claims["workspace_id"] == "9"
    assert claims["project_id"] == "8"


async def test_page_code_check_should_build_transient_dependency_graph(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """页面候选源码新增组件 import 时，临时 artifact 应包含新依赖组件版本。"""

    workspace_id = await _create_workspace(authenticated_client, "代码检查页面依赖工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "代码检查页面依赖项目")
    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "检查用组件",
            "import_name": "CheckCard",
            "content": "<template><article>组件内容</article></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    component = await _publish_component(authenticated_client, component_response.json()["id"])
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "候选页面",
            "page_content": "<template><main>原页面</main></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert page_response.status_code == 200
    candidate_content = f"""
<template>
  <main><CheckCard /></main>
</template>
<script setup lang="ts">
import CheckCard from '@workspace-components/{component["code"]}/v/1'
</script>
    """.strip()
    fake_runtime = FakeRuntimeDiagnosticsClient()

    async with get_session_factory()() as session:
        result = await CodeCheckService(session, runtime_client=fake_runtime).check_page_code(
            page_id=page_response.json()["id"],
            workspace_id=workspace_id,
            user_id=1,
            content=candidate_content,
        )

    assert result["success"] is True
    artifact_id = result["artifact_id"]
    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers=runtime_service_headers,
    )
    assert manifest_response.status_code == 200
    assert f"src/workspace-components/{component['code']}/v/1.vue" in manifest_response.json()["modules"]


async def test_page_code_check_should_accept_unsaved_project_page_content(
    authenticated_client: AsyncClient,
    runtime_service_headers: dict[str, str],
) -> None:
    """新增页面尚无 page_id 时，应允许用项目上下文检查完整候选源码。"""

    workspace_id = await _create_workspace(authenticated_client, "代码检查新增页面工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "代码检查新增页面项目")
    fake_runtime = FakeRuntimeDiagnosticsClient()

    async with get_session_factory()() as session:
        result = await CodeCheckService(session, runtime_client=fake_runtime).check_page_code(
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=1,
            content="<template><main>新增页面</main></template>",
        )

    assert result["success"] is True
    assert fake_runtime.calls[0]["label"] == f"page:draft:{project_id}"
    artifact_id = result["artifact_id"]
    module_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/modules",
        headers=runtime_service_headers,
        params={"path": "src/views/__ai_page_draft__.vue"},
    )
    assert module_response.status_code == 200
    assert module_response.text == "<template><main>新增页面</main></template>"


async def test_component_code_check_should_return_edits_metadata(authenticated_client: AsyncClient) -> None:
    """组件 edits 检查应返回实际检查的 canonical diff。"""

    workspace_id = await _create_workspace(authenticated_client, "代码检查组件工作空间")
    component_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "检查组件",
            "import_name": "CheckComponent",
            "content": "<template><section>旧内容</section></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert component_response.status_code == 200
    fake_runtime = FakeRuntimeDiagnosticsClient()

    async with get_session_factory()() as session:
        result = await CodeCheckService(session, runtime_client=fake_runtime).check_component_code(
            component_id=component_response.json()["id"],
            workspace_id=workspace_id,
            user_id=1,
            edits=[
                {
                    "type": "replace_exact",
                    "old_text": "<template><section>旧内容</section></template>",
                    "new_text": "<template><section>新内容</section></template>",
                }
            ],
        )

    assert result["success"] is True
    assert result["patch_repaired"] is False
    assert "新内容" in str(result["canonical_diff"])
    assert fake_runtime.calls


async def test_component_code_check_should_return_dynamic_icon_name_diagnostic(
    authenticated_client: AsyncClient,
) -> None:
    """组件代码检查遇到无法静态解析的 Icon name 时，应返回可修复诊断而不是抛异常。"""

    workspace_id = await _create_workspace(authenticated_client, "代码检查动态图标工作空间")
    fake_runtime = FakeRuntimeDiagnosticsClient()

    async with get_session_factory()() as session:
        result = await CodeCheckService(session, runtime_client=fake_runtime).check_component_code(
            workspace_id=workspace_id,
            user_id=1,
            content='<template><section><Icon :name="iconName" /></section></template>',
        )

    assert result["success"] is False
    assert result["diagnostics"][0]["code"] == "PREVIEW_ICON_NAME_DYNAMIC_UNSUPPORTED"
    assert "顶层 const 数组对象字面量" in result["diagnostics"][0]["message"]
    assert fake_runtime.calls == []
