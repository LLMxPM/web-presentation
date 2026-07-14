"""文件功能：验证页面/组件代码检查服务的 diff 校验、Runtime 调用映射与临时依赖图构建。"""

from __future__ import annotations

from httpx import AsyncClient

from app.db.session import get_session_factory
from app.services.code_check_service import CodeCheckService
from app.services.runtime_artifact_store import RuntimeArtifactStore
from app.services.token_service import TokenService

CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'


class FakeRuntimeDiagnosticsClient:
    """测试用 Runtime 诊断客户端，记录调用并返回固定结果。"""

    def __init__(
        self,
        result: dict[str, object] | None = None,
        *,
        module_paths: list[str] | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = result
        self.module_paths = module_paths or []
        self.artifact_snapshots: dict[str, dict[str, object]] = {}

    async def dispatch_artifact_diagnostics(
        self,
        *,
        artifact_id: str,
        diagnostics_token: str,
        label: str | None = None,
    ) -> dict[str, object]:
        """记录诊断调用，并在主动清理前保存 Runtime 实际可读取的 artifact。"""

        self.calls.append(
            {
                "artifact_id": artifact_id,
                "diagnostics_token": diagnostics_token,
                "label": label,
            }
        )
        artifact_store = RuntimeArtifactStore()
        manifest = await artifact_store.get_manifest(artifact_id)
        modules: dict[str, str | None] = {}
        if manifest is not None:
            manifest_module_paths = manifest.get("modules", [])
            for logical_path in [*manifest_module_paths, *self.module_paths]:
                if isinstance(logical_path, str):
                    modules[logical_path] = await artifact_store.get_module(artifact_id, logical_path)
        self.artifact_snapshots[artifact_id] = {
            "manifest": manifest,
            "modules": modules,
        }
        if self.result is not None:
            return {
                "artifact_id": artifact_id,
                **self.result,
            }
        return {
            "success": True,
            "status": "passed",
            "artifact_id": artifact_id,
            "summary": "代码检查通过。",
            "diagnostics": [],
        }


class FakePageRenderDiagnosticsService:
    """测试用页面渲染诊断服务，记录调用并返回固定 warning。"""

    def __init__(self, diagnostics: list[dict[str, object]] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.diagnostics = diagnostics or []

    async def diagnose_preview(self, preview_url: str, viewport: object) -> list[dict[str, object]]:
        """记录渲染诊断调用并返回预置结果。"""

        self.calls.append({"preview_url": preview_url, "viewport": viewport})
        return list(self.diagnostics)


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
    fake_render = FakePageRenderDiagnosticsService()

    async with get_session_factory()() as session:
        result = await CodeCheckService(
            session,
            runtime_client=fake_runtime,
            render_diagnostics_service=fake_render,
        ).check_page_code(
            page_id=page_response.json()["id"],
            workspace_id=workspace_id,
            user_id=1,
            edits=[{"type": "replace_exact", "old_text": "不存在", "new_text": "新内容"}],
        )

    assert result["success"] is False
    assert result["diagnostics"][0]["code"] == "AI_SOURCE_EDIT_NO_MATCH"
    assert fake_runtime.calls == []
    assert fake_render.calls == []


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
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
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
    fake_render = FakePageRenderDiagnosticsService()

    async with get_session_factory()() as session:
        result = await CodeCheckService(
            session,
            runtime_client=fake_runtime,
            render_diagnostics_service=fake_render,
        ).check_page_code(
            page_id=page_response.json()["id"],
            workspace_id=workspace_id,
            user_id=1,
            content=candidate_content,
        )

    assert result["success"] is True
    assert fake_render.calls
    artifact_id = result["artifact_id"]
    snapshot = fake_runtime.artifact_snapshots[str(artifact_id)]
    manifest = snapshot["manifest"]
    assert isinstance(manifest, dict)
    assert f"src/workspace-components/{component['code']}/v/1.vue" in manifest["modules"]
    assert await RuntimeArtifactStore().get_manifest(str(artifact_id)) is None


async def test_page_code_check_should_accept_unsaved_project_page_content(
    authenticated_client: AsyncClient,
) -> None:
    """新增页面尚无 page_id 时，应允许用项目上下文检查完整候选源码。"""

    workspace_id = await _create_workspace(authenticated_client, "代码检查新增页面工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "代码检查新增页面项目")
    fake_runtime = FakeRuntimeDiagnosticsClient(module_paths=["src/views/__ai_page_draft__.vue"])
    fake_render = FakePageRenderDiagnosticsService()

    async with get_session_factory()() as session:
        result = await CodeCheckService(
            session,
            runtime_client=fake_runtime,
            render_diagnostics_service=fake_render,
        ).check_page_code(
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=1,
            content="<template><main>新增页面</main></template>",
        )

    assert result["success"] is True
    assert fake_runtime.calls[0]["label"] == f"page:draft:{project_id}"
    assert fake_render.calls
    artifact_id = result["artifact_id"]
    snapshot = fake_runtime.artifact_snapshots[str(artifact_id)]
    modules = snapshot["modules"]
    assert isinstance(modules, dict)
    assert "src/views/__ai_page_draft__.vue" in modules, snapshot
    assert modules["src/views/__ai_page_draft__.vue"] == "<template><main>新增页面</main></template>"
    assert await RuntimeArtifactStore().get_module(str(artifact_id), "src/views/__ai_page_draft__.vue") is None


async def test_page_code_check_should_append_render_warning_after_runtime_passed(
    authenticated_client: AsyncClient,
) -> None:
    """Runtime 检查通过后，应追加页面渲染底部溢出 warning 且保持通过状态。"""

    workspace_id = await _create_workspace(authenticated_client, "代码检查渲染 warning 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "代码检查渲染 warning 项目")
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "渲染 warning 页面",
            "page_content": "<template><main>原页面</main></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert page_response.status_code == 200
    fake_runtime = FakeRuntimeDiagnosticsClient()
    fake_render = FakePageRenderDiagnosticsService([
        {
            "severity": "warning",
            "source": "runtime-render",
            "code": "PAGE_RENDER_BOTTOM_OVERFLOW",
            "message": "页面内容底部超出画布 42px。",
        }
    ])

    async with get_session_factory()() as session:
        result = await CodeCheckService(
            session,
            runtime_client=fake_runtime,
            render_diagnostics_service=fake_render,
        ).check_page_code(
            page_id=page_response.json()["id"],
            workspace_id=workspace_id,
            user_id=1,
            content="<template><main>新页面</main></template>",
        )

    assert result["success"] is True
    assert result["status"] == "passed"
    assert result["summary"] == "代码检查通过，发现 1 个布局警告。"
    assert result["diagnostics"][0]["severity"] == "warning"
    assert result["diagnostics"][0]["code"] == "PAGE_RENDER_BOTTOM_OVERFLOW"
    assert fake_render.calls


async def test_page_code_check_should_skip_render_warning_when_runtime_failed(
    authenticated_client: AsyncClient,
) -> None:
    """Runtime 编译失败时不应继续执行页面渲染诊断。"""

    workspace_id = await _create_workspace(authenticated_client, "代码检查跳过渲染工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "代码检查跳过渲染项目")
    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": "跳过渲染页面",
            "page_content": "<template><main>原页面</main></template>",
            "file_type": "vue",
            "status": "active",
        },
    )
    assert page_response.status_code == 200
    fake_runtime = FakeRuntimeDiagnosticsClient({
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
    })
    fake_render = FakePageRenderDiagnosticsService([
        {
            "severity": "warning",
            "source": "runtime-render",
            "code": "PAGE_RENDER_BOTTOM_OVERFLOW",
            "message": "不应出现。",
        }
    ])

    async with get_session_factory()() as session:
        result = await CodeCheckService(
            session,
            runtime_client=fake_runtime,
            render_diagnostics_service=fake_render,
        ).check_page_code(
            page_id=page_response.json()["id"],
            workspace_id=workspace_id,
            user_id=1,
            content="<template><main>新页面</main></template>",
        )

    assert result["success"] is False
    assert result["diagnostics"][0]["code"] == "RUNTIME_VITE_COMPILE_FAILED"
    assert fake_render.calls == []


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
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
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
