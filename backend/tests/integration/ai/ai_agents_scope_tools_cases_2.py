"""文件功能：承载 AI scope tools 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.ai.ai_agents_cases import *  # noqa: F403


async def test_apply_component_edits_should_return_diagnostics_without_saving(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """组件 apply 内置 Runtime validate 失败时，应返回诊断且不保存草稿。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch, success=False)
    workspace_id = await _create_workspace(authenticated_client, "AI 组件 Validate 失败工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "Validate 失败组件",
            "import_name": "ValidateFailComponent",
            "content": "<template><article>draft</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    apply_tool = _find_tool(build_component_manager_tools(get_session_factory()), "apply_component_edits")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await apply_tool.entrypoint(
        run_context,
        component_id=component["id"],
        edits=[{"type": "replace_exact", "old_text": "draft", "new_text": "updated"}],
        base_draft_hash=calculate_source_hash(component["content"]),
        base_published_version_no=0,
    )

    component_response = await authenticated_client.get(f"/api/components/{component['id']}")
    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "RUNTIME_TEST_FAILED"
    assert "updated" in str(result["canonical_diff"])
    assert result["edits_applied"] == 1
    assert runtime_calls
    assert component_response.json()["content"] == component["content"]

async def test_apply_component_edits_should_reject_invalid_edits_before_validate(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """组件 edits 命中失败时，应在 Runtime validate 前返回结构化诊断。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 组件 Edits 失败工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "Edits 失败组件",
            "import_name": "EditFailComponent",
            "content": "<template><article>draft</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    apply_tool = _find_tool(build_component_manager_tools(get_session_factory()), "apply_component_edits")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await apply_tool.entrypoint(
        run_context,
        component_id=component["id"],
        edits=[{"type": "replace_exact", "old_text": "missing", "new_text": "updated"}],
        base_draft_hash=calculate_source_hash(component["content"]),
        base_published_version_no=0,
    )

    assert result["success"] is False
    assert result["diagnostics"][0]["code"] == "AI_SOURCE_EDIT_NO_MATCH"
    assert runtime_calls == []

async def test_workspace_font_asset_tool_should_return_runtime_font_fields(authenticated_client: AsyncClient) -> None:
    """字体资源查询工具应返回 Agent 生成字体声明所需的资源名和字体族。"""

    workspace_id = await _create_workspace(authenticated_client, "字体工具工作空间")
    asset_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("BrandSerif.woff2", b"font-data-tool", "font/woff2")},
        data={"asset_type": "font", "tags": "[]", "name": "BrandSerif"},
    )
    assert asset_response.status_code == 200
    font_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/fonts",
        json={
            "asset_id": asset_response.json()["id"],
            "font_family": "Brand Serif",
            "font_weight": "400",
            "font_style": "normal",
            "font_display": "swap",
            "status": "active",
        },
    )
    assert font_response.status_code == 200

    tool = build_list_workspace_font_assets_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        page_id=1,
    )
    result = await tool.entrypoint(run_context, keyword="Brand", limit=10)

    assert result[0]["asset_name"] == "BrandSerif"
    assert result[0]["font_family"] == "Brand Serif"
    assert result[0]["font_weight"] == "400"

async def test_apply_unified_diff_should_apply_and_reject_invalid_patch() -> None:
    """Unified Diff 应能正确应用，并在冲突时拒绝执行。"""

    current_content = "<template><div>draft</div></template>\n"
    valid_patch = (
        "--- current\n"
        "+++ proposed\n"
        "@@ -1 +1 @@\n"
        "-<template><div>draft</div></template>\n"
        "+<template><div>after-confirm</div></template>\n"
    )
    assert apply_unified_diff(current_content, valid_patch) == "<template><div>after-confirm</div></template>\n"

    invalid_patch = (
        "--- current\n"
        "+++ proposed\n"
        "@@ -1 +1 @@\n"
        "-<template><div>other</div></template>\n"
        "+<template><div>after-confirm</div></template>\n"
    )
    try:
        apply_unified_diff(current_content, invalid_patch)
    except AppException as exc:
        assert exc.code == "AI_PAGE_DIFF_CONFLICT"
        assert "hunk #1" in exc.detail
        assert "期望" in exc.detail
        assert "实际为" in exc.detail
    else:
        raise AssertionError("冲突 patch 应抛出统一错误。")

async def test_apply_unified_diff_should_ignore_crlf_differences() -> None:
    """当前源码和 patch 即使混用 CRLF/LF，也应先统一为 LF 再应用。"""

    current_content = "<template>\r\n  <div>draft</div>\r\n</template>\r\n"
    patch = (
        "--- current\n"
        "+++ proposed\n"
        "@@ -1,3 +1,3 @@\n"
        " <template>\n"
        "-  <div>draft</div>\n"
        "+  <div>after-confirm</div>\n"
        " </template>\n"
    )

    assert apply_unified_diff(current_content, patch) == "<template>\n  <div>after-confirm</div>\n</template>\n"

async def test_apply_unified_diff_with_repair_should_relocate_misaligned_hunk() -> None:
    """当 hunk 起始行号轻微漂移但旧内容完整时，应能自动重定位并重建 canonical diff。"""

    current_content = "alpha\nbeta\ngamma\ndelta\n"
    misaligned_patch = (
        "--- a/page.vue\n"
        "+++ b/page.vue\n"
        "@@ -2,2 +2,2 @@\n"
        " gamma\n"
        "-delta\n"
        "+zeta\n"
    )

    patch_result = apply_unified_diff_with_repair(current_content, misaligned_patch)

    assert patch_result.repaired is True
    assert patch_result.next_content == "alpha\nbeta\ngamma\nzeta\n"
    assert patch_result.canonical_diff.startswith("--- current\n+++ proposed\n@@ ")
    assert "-delta\n+zeta\n" in patch_result.canonical_diff

async def test_apply_unified_diff_should_allow_missing_final_lf_on_last_patch_line() -> None:
    """patch 最后一条 hunk 行若仅缺少尾随 LF，也应能正常应用。"""

    current_content = "alpha\nbeta\ngamma\n"
    patch = (
        "--- current\n"
        "+++ proposed\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+zeta\n"
        " gamma"
    )

    assert apply_unified_diff(current_content, patch) == "alpha\nzeta\ngamma\n"

async def test_apply_unified_diff_with_repair_should_allow_missing_final_lf_on_last_window_line() -> None:
    """自动重定位时，旧内容窗口最后一行若只缺少尾随 LF，也应能匹配成功。"""

    current_content = "head\nalpha\nbeta\ngamma\n"
    misaligned_patch = (
        "--- a/page.vue\n"
        "+++ b/page.vue\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+zeta\n"
        " gamma"
    )

    patch_result = apply_unified_diff_with_repair(current_content, misaligned_patch)

    assert patch_result.repaired is True
    assert patch_result.next_content == "head\nalpha\nzeta\ngamma\n"
    assert patch_result.canonical_diff.startswith("--- current\n+++ proposed\n@@ ")
    assert "-beta\n+zeta\n" in patch_result.canonical_diff

async def test_get_page_content_prompt_should_render_source() -> None:
    """页面源码读取工具应向模型提供原始源码文本。"""

    page_item = _build_page_item(
        page_id=88,
        content="<template>\n  <div>hello</div>\n</template>\n",
        speaker_notes="演讲时强调 hello 页面。",
    )
    prompt = build_page_content_prompt(page_item)

    assert "页面源信息：" in prompt
    assert "目标页面 ID：88" in prompt
    assert "演讲者备注：演讲时强调 hello 页面。" in prompt
    assert "源码：" in prompt
    assert "行号版源码：" not in prompt
    assert "```vue" not in prompt
    assert "0001 |" not in prompt
    assert "<template>\n  <div>hello</div>\n</template>\n" in prompt
    assert "直接复制源码中的真实片段作为 old_text、anchor_text 或 content" in prompt
    assert "每个 edit 对象必须包含 type 字段" in prompt

def test_get_component_detail_prompt_should_render_source() -> None:
    """组件详情读取工具应向模型提供原始源码和草稿锁字段。"""

    component = _build_component_item(
        component_id=18,
        content="<template>\n  <section>hello</section>\n</template>\n",
    )
    prompt = build_component_detail_prompt(component)

    assert "组件编码：CMP18" in prompt
    assert "源码引用名：TestComponent" in prompt
    assert "draft_hash（草稿内容指纹）：" in prompt
    assert "base_published_version_no（草稿基线版本号）：0" in prompt
    assert "源码：" in prompt
    assert "行号版源码：" not in prompt
    assert "```vue" not in prompt
    assert "0001 |" not in prompt
    assert "<template>\n  <section>hello</section>\n</template>\n" in prompt
    assert "直接复制源码中的真实片段作为 old_text、anchor_text 或 content" in prompt

async def test_get_page_content_tool_should_render_page_canvas_config(
    authenticated_client: AsyncClient,
) -> None:
    """页面源码读取工具应把真实画布尺寸和基础字号写入返回文本。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 页面尺寸工具工作空间")
    project_id = await _create_project(
        authenticated_client,
        workspace_id,
        "AI 页面尺寸工具项目",
        page_width=1366,
        page_height=768,
        base_font_size="18px",
        icon_default_stroke_width=3,
        style_spec_markdown="## 页面规范\n- 保持网格对齐。",
    )
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="尺寸上下文页面",
        content="<template><div>size</div></template>",
    )
    tool = build_get_page_content_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )
    run_context.dependencies["page_width"] = 1366
    run_context.dependencies["page_height"] = 768
    run_context.dependencies["base_font_size"] = "18px"

    result = await tool.entrypoint(run_context)

    assert "当前页面画布尺寸（page_width / page_height）：1366 x 768 px" in result.content
    assert "当前项目基础字号（base_font_size）：18px" in result.content
    assert "base_font_size 作用：text-base 等于该值" in result.content
    assert "page_width/page_height 不参与该换算" in result.content
    assert "固定尺度说明：直接写 px、rem 或 Tailwind arbitrary values 不会随 base_font_size 自动变化" in result.content
    assert "按真实画布编写" in result.content
    assert "px、rem 或 Tailwind arbitrary values" in result.content
    assert "authoring_width" not in result.content
    assert "作者画布" not in result.content
    assert "当前项目默认图标规格" not in result.content
    assert "<template><div>size</div></template>" in result.content
    assert "0001 |" not in result.content

async def test_get_page_content_tool_should_accept_explicit_page_id(
    authenticated_client: AsyncClient,
) -> None:
    """页面源码读取工具应允许显式读取当前项目内指定页面。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 显式页面读取工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 显式页面读取项目")
    context_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="上下文页面",
        content="<template><div>context</div></template>",
    )
    target_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="目标页面",
        content="<template><div>target</div></template>",
    )
    tool = build_get_page_content_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=context_page_id,
    )

    result = await tool.entrypoint(run_context, page_id=target_page_id)

    assert "读取方式：工具参数 page_id" in result.content
    assert f"目标页面 ID：{target_page_id}" in result.content
    assert f"上下文页面 ID：{context_page_id}" in result.content
    assert "<template><div>target</div></template>" in result.content
    assert "0001 |" not in result.content

async def test_apply_page_edits_tool_should_accept_explicit_page_id(authenticated_client: AsyncClient, monkeypatch) -> None:
    """页面 edits 写入工具应允许在项目上下文中显式指定目标页面。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 显式页面写入工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 显式页面写入项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="显式写入目标页面",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    result = await tool.entrypoint(
        run_context,
        page_id=page_id,
        edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
        base_version_no=1,
    )

    assert result["success"] is True
    assert result["page_id"] == page_id
    assert result["version_no"] == 2
    assert result["edits_applied"] == 1
    assert runtime_calls

async def test_apply_page_edits_should_return_diagnostics_without_saving(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """页面 apply 内置 Runtime validate 失败时，应返回诊断且不保存新版本。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch, success=False)
    workspace_id = await _create_workspace(authenticated_client, "AI 页面 Validate 失败工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 页面 Validate 失败项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="Validate 失败页面",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )

    result = await tool.entrypoint(
        run_context,
        page_id=page_id,
        edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
        base_version_no=1,
    )

    page_response = await authenticated_client.get(f"/api/pages/{page_id}")
    assert result["success"] is False
    assert result["status"] == "failed"
    assert result["diagnostics"][0]["code"] == "RUNTIME_TEST_FAILED"
    assert "new" in str(result["canonical_diff"])
    assert result["edits_applied"] == 1
    assert runtime_calls
    assert page_response.json()["current_version_no"] == 1
    assert page_response.json()["page_content"] == "<template><main>old</main></template>"

async def test_apply_page_edits_should_reject_invalid_edits_before_validate(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """页面 edits 命中失败时，应在 Runtime validate 前返回结构化诊断。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 页面 Edits 失败工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 页面 Edits 失败项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="Edits 失败页面",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )

    result = await tool.entrypoint(
        run_context,
        page_id=page_id,
        edits=[{"type": "replace_exact", "old_text": "missing", "new_text": "new"}],
        base_version_no=1,
    )

    assert result["success"] is False
    assert result["diagnostics"][0]["code"] == "AI_SOURCE_EDIT_NO_MATCH"
    assert runtime_calls == []

async def test_apply_page_edits_tool_should_reject_page_outside_context(authenticated_client: AsyncClient) -> None:
    """页面 edits 写入工具应拒绝跨项目 page_id，避免显式参数越权。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 页面写入边界工作空间")
    source_project_id = await _create_project(authenticated_client, workspace_id, "AI 页面写入来源项目")
    other_project_id = await _create_project(authenticated_client, workspace_id, "AI 页面写入其他项目")
    other_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=other_project_id,
        title="其他项目页面",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=source_project_id,
    )

    try:
        await tool.entrypoint(
            run_context,
            page_id=other_page_id,
            edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
            base_version_no=1,
        )
    except AppException as exc:
        assert exc.code == "AI_TOOL_CONTEXT_MISMATCH"
        assert "目标页面不属于当前工具上下文绑定的项目" in exc.detail
    else:
        raise AssertionError("跨项目 page_id 应被拒绝。")

async def test_apply_page_edits_should_reject_stale_base_version(authenticated_client: AsyncClient, monkeypatch) -> None:
    """页面 edits 写入应使用 current_version_no 做乐观锁。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 页面 Edits 乐观锁工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 页面 Edits 乐观锁项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="页面 Edits 乐观锁",
        content="<template><main>old</main></template>",
    )
    tool = build_apply_page_edits_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )

    try:
        await tool.entrypoint(
            run_context,
            page_id=page_id,
            edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
            base_version_no=0,
        )
    except AppException as exc:
        assert exc.code == "AI_PAGE_BASE_VERSION_STALE"
        assert "页面版本已变化" in exc.detail
    else:
        raise AssertionError("旧 base_version_no 应被拒绝。")
    assert runtime_calls == []

    result = await tool.entrypoint(
        run_context,
        page_id=page_id,
        edits=[{"type": "replace_exact", "old_text": "old", "new_text": "new"}],
        base_version_no=1,
    )

    assert result["success"] is True
    assert result["version_no"] == 2
    assert result["edits_applied"] == 1
    assert runtime_calls

async def test_agent_runtime_context_should_include_page_canvas_config(
    authenticated_client: AsyncClient,
) -> None:
    """运行时上下文应从页面绑定项目读取真实画布和基础字号。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 运行上下文尺寸工作空间")
    project_id = await _create_project(
        authenticated_client,
        workspace_id,
        "AI 运行上下文尺寸项目",
        page_width=1600,
        page_height=900,
        base_font_size="18px",
        icon_default_stroke_width=3,
        style_spec_markdown="## 页面规范\n- 保持网格对齐。",
    )
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="运行上下文尺寸页面",
        content="<template><div>context</div></template>",
    )

    async with get_session_factory()() as session:
        runtime_context = await build_agent_runtime_context(
            session=session,
            scope=AgentScopeContext(
                scope_type="page",
                workspace_id=workspace_id,
                page_id=page_id,
                source="editor-page-detail",
            ),
        )

    assert runtime_context.project_id == project_id
    assert runtime_context.page_width == 1600
    assert runtime_context.page_height == 900
    assert runtime_context.base_font_size == "18px"
    assert runtime_context.style_spec_markdown == "## 页面规范\n- 保持网格对齐。"
    scope_text = build_scope_context_text(runtime_context)
    assert "当前页面画布尺寸（page_width / page_height）：1600 x 900 px" in scope_text
    assert "当前项目基础字号（base_font_size）：18px" in scope_text
    assert "base_font_size 是页面 Tailwind 字号和间距的基础尺度" in scope_text
    assert "page_width/page_height 不参与该换算" in scope_text
    assert "px、rem 或 Tailwind arbitrary values 属于固定 CSS 尺度" in scope_text
    assert "不会随 base_font_size 自动变化" in scope_text
    assert "按真实画布编写 Vue 与 Tailwind" in scope_text
    assert "px、rem 或 Tailwind arbitrary values" in scope_text
    assert "authoring_width" not in scope_text
    assert "作者画布" not in scope_text
    assert "当前项目默认图标规格" not in scope_text
    assert "当前项目样式规范" in scope_text
    assert "保持网格对齐" in scope_text

async def test_agent_tool_dependencies_and_scope_summary_should_include_page_canvas_config() -> None:
    """工具依赖和当前范围摘要应包含真实画布和基础字号。"""

    facade = AgentSessionFacade.__new__(AgentSessionFacade)
    facade._current = _build_auth_context()
    runtime_context = AgentRuntimeContext(
        scope_type="page",
        workspace_id=11,
        project_id=21,
        page_id=31,
        page_width=1600,
        page_height=900,
        base_font_size="18px",
        style_spec_markdown="## 规范\n- 使用统一标题。",
        source="editor-page-detail",
    )
    dependencies = facade._build_tool_dependencies(
        scope=AgentScopeContext(
            scope_type="page",
            workspace_id=11,
            project_id=21,
            page_id=31,
            source="editor-page-detail",
        ),
        session_id="session-page-size",
        run_id="run-page-size",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        runtime_context=runtime_context,
        session_metadata={},
        agent_config=None,  # type: ignore[arg-type]
    )
    assert dependencies["page_width"] == 1600
    assert dependencies["page_height"] == 900
    assert dependencies["base_font_size"] == "18px"
    assert "authoring_width" not in dependencies
    assert "authoring_height" not in dependencies
    assert "icon_default_size" not in dependencies
    assert "icon_default_stroke_width" not in dependencies
    assert dependencies["style_spec_markdown"] == "## 规范\n- 使用统一标题。"
    assert "page_size" not in dependencies
    assert dependencies["run_id"] == "run-page-size"
    assert "tool_access_token" not in dependencies
    assert "allowed_tool_groups" not in dependencies
    assert "tool_group_catalog" not in dependencies
    assert RESOURCE_TOOL_WRITE_SCOPES[0] not in dependencies["tool_scopes"]
    assert set(dependencies["member_tool_auth_tokens"]) == {COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID}
    assert COMPONENT_TOOL_WRITE_SCOPES[0] in dependencies["member_tool_scopes"][COMPONENT_MANAGER_AGENT_ID]
    assert RESOURCE_TOOL_WRITE_SCOPES[0] in dependencies["member_tool_scopes"][RESOURCE_MANAGER_AGENT_ID]
