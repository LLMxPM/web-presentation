"""文件功能：承载 AI extra 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.ai.ai_agents_cases import *  # noqa: F403


async def test_tool_run_task_auth_should_refresh_window_and_reject_invalid_scope(
    authenticated_client: AsyncClient,
) -> None:
    """工具授权应来自 run task，成功校验后刷新短租约并拒绝缺失 scope。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具授权工作空间")
    current = _build_auth_context()
    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id="run-tool-auth",
            session_id="session-tool-auth",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=workspace_id, source="editor-agent-sidebar"),
            input_summary="工具授权测试",
            tool_scopes=COMPONENT_TOOL_DELETE_SCOPES,
        )
        original_expiry = task.tool_auth_expires_at
        original_max_expiry = task.tool_auth_max_expires_at
        await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={"tool_auth_expires_at": datetime.now(UTC) + timedelta(seconds=1)},
        )

        context, claims = await service.authorize_tool_call(
            run_id="run-tool-auth",
            user_id=current.user.id,
            session_id="session-tool-auth",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            backend_session_id=current.backend_session_id,
            source="editor-agent-sidebar",
            required_scopes=COMPONENT_TOOL_DELETE_SCOPES,
        )
        assert context["workspace_id"] == workspace_id
        assert claims["sub"] == f"user:{current.user.id}"
        refreshed_task = await service.get_task_by_run(run_id=task.run_id, user_id=current.user.id)
        assert refreshed_task is not None
        assert refreshed_task.tool_auth_expires_at is not None
        assert original_expiry is not None
        assert refreshed_task.tool_auth_expires_at > original_expiry - timedelta(seconds=5)
        assert refreshed_task.tool_auth_max_expires_at == original_max_expiry

        try:
            await service.authorize_tool_call(
                run_id="run-tool-auth",
                user_id=current.user.id,
                session_id="session-tool-auth",
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                backend_session_id=current.backend_session_id,
                source="editor-agent-sidebar",
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_SCOPE_DENIED"
        else:
            raise AssertionError("缺少工具 scope 时应拒绝调用。")

async def test_tool_run_task_auth_should_reject_expired_and_mismatched_context(
    authenticated_client: AsyncClient,
) -> None:
    """工具授权应拒绝过期授权、终态任务和上下文不匹配。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具授权拒绝工作空间")
    current = _build_auth_context()
    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id="run-tool-auth-reject",
            session_id="session-tool-auth-reject",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=workspace_id, source="editor-agent-sidebar"),
            input_summary="工具授权拒绝测试",
            tool_scopes=PROJECT_TOOL_READ_SCOPES,
        )

        try:
            await service.authorize_tool_call(
                run_id=task.run_id,
                user_id=current.user.id,
                session_id=task.session_id,
                agent_id=task.agent_id,
                backend_session_id=current.backend_session_id,
                source="other-source",
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_CONTEXT_MISMATCH"
        else:
            raise AssertionError("source 不匹配时应拒绝工具调用。")

        task = await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={"tool_auth_expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        )
        try:
            await service.authorize_tool_call(
                run_id=task.run_id,
                user_id=current.user.id,
                session_id=task.session_id,
                agent_id=task.agent_id,
                backend_session_id=current.backend_session_id,
                source=task.source,
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_AUTH_EXPIRED"
        else:
            raise AssertionError("短租约过期时应拒绝工具调用。")

        task = await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={
                "tool_auth_expires_at": datetime.now(UTC) + timedelta(minutes=5),
                "tool_auth_max_expires_at": datetime.now(UTC) - timedelta(seconds=1),
            },
        )
        try:
            await service.authorize_tool_call(
                run_id=task.run_id,
                user_id=current.user.id,
                session_id=task.session_id,
                agent_id=task.agent_id,
                backend_session_id=current.backend_session_id,
                source=task.source,
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_AUTH_EXPIRED"
        else:
            raise AssertionError("绝对上限过期时应拒绝工具调用。")

        task = await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={
                "tool_auth_expires_at": datetime.now(UTC) + timedelta(minutes=5),
                "tool_auth_max_expires_at": datetime.now(UTC) + timedelta(minutes=10),
            },
        )
        await service.mark_terminal(task=task, status="completed", content="done")
        try:
            await service.authorize_tool_call(
                run_id=task.run_id,
                user_id=current.user.id,
                session_id=task.session_id,
                agent_id=task.agent_id,
                backend_session_id=current.backend_session_id,
                source=task.source,
                required_scopes=PROJECT_TOOL_READ_SCOPES,
            )
        except AppException as exc:
            assert exc.code == "AI_TOOL_RUN_INACTIVE"
        else:
            raise AssertionError("终态任务不应允许工具调用。")

async def test_tool_auth_should_reset_window_when_paused_run_continues(
    authenticated_client: AsyncClient,
) -> None:
    """继续 paused run 时应从当前时间重开工具授权窗口和绝对上限。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具授权继续工作空间")
    current = _build_auth_context()
    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id="run-tool-auth-continue",
            session_id="session-tool-auth-continue",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=workspace_id, source="editor-agent-sidebar"),
            input_summary="工具授权继续测试",
            tool_scopes=PROJECT_TOOL_READ_SCOPES,
        )
        expired_at = datetime.now(UTC) - timedelta(hours=1)
        task = await service.run_state_store.update_run_fields(
            run_id=task.run_id,
            user_id=current.user.id,
            fields={
                "status": "paused",
                "tool_auth_expires_at": expired_at,
                "tool_auth_max_expires_at": expired_at,
            },
        )

        continued_at = datetime.now(UTC)
        task = await service.mark_running(task=task, reset_tool_auth=True)

        assert task.status == "running"
        assert task.tool_auth_expires_at is not None
        assert task.tool_auth_max_expires_at is not None
        refreshed_expires_at = task.tool_auth_expires_at
        if refreshed_expires_at.tzinfo is None:
            refreshed_expires_at = refreshed_expires_at.replace(tzinfo=UTC)
        assert refreshed_expires_at > continued_at
        assert task.tool_auth_max_expires_at > task.tool_auth_expires_at

        context, _ = await service.authorize_tool_call(
            run_id=task.run_id,
            user_id=current.user.id,
            session_id=task.session_id,
            agent_id=task.agent_id,
            backend_session_id=current.backend_session_id,
            source=task.source,
            required_scopes=PROJECT_TOOL_READ_SCOPES,
        )
        assert context["workspace_id"] == workspace_id

async def test_replayed_pause_event_after_continue_should_not_disable_tool_auth(
    authenticated_client: AsyncClient,
) -> None:
    """继续 paused run 后，旧 pause 事件回放不应把 task 再次写回暂停态。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 继续回放 Pause 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 继续回放 Pause 项目")
    current = _build_auth_context()
    run_id = "run-tool-auth-replayed-pause"
    session_id = "session-tool-auth-replayed-pause"
    requirement = AgentPendingRequirement(
        kind="confirmation",
        run_id=run_id,
        session_id=session_id,
        tool_name="apply_project_route_tree",
        tool_execution={
            "tool_call_id": "tool-route-confirm-continue",
            "tool_name": "apply_project_route_tree",
            "tool_args": {"routes": []},
            "requires_confirmation": True,
        },
    )

    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(
                scope_type="project",
                workspace_id=workspace_id,
                project_id=project_id,
                source="editor-page-detail",
            ),
            input_summary="继续后回放 pause 测试",
            tool_scopes=(*PROJECT_TOOL_READ_SCOPES, *PROJECT_TOOL_WRITE_SCOPES),
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id),
        )
        await service.mark_paused(task=task, pending_requirement=requirement)
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="context.status", run_id=run_id, session_id=session_id, data={}),
        )
        task = await service.mark_running(task=task, reset_tool_auth=True)

        replayed = await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(
                event="run.paused",
                run_id=run_id,
                session_id=session_id,
                data={"requirement": requirement.model_dump(mode="json")},
            ),
        )
        task = await service.get_task_by_run(run_id=run_id, user_id=current.user.id)
        assert task is not None

        assert replayed is None
        assert task.status == "running"
        assert task.pending_requirement_json is None
        context, _ = await service.authorize_tool_call(
            run_id=run_id,
            user_id=current.user.id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            backend_session_id=current.backend_session_id,
            source="editor-page-detail",
            required_scopes=PROJECT_TOOL_READ_SCOPES,
        )
        assert context["project_id"] == project_id
        events = await service.list_events_after(
            run_id=run_id,
            user_id=current.user.id,
            after_sequence=0,
        )

    assert [event.event for event in events] == ["run.started", "run.paused", "context.status"]

async def test_continue_non_paused_run_should_not_reset_tool_auth(
    authenticated_client: AsyncClient,
) -> None:
    """非 paused run 调 continue 应保持原错误，并且不能重置工具授权。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 非暂停继续授权工作空间")
    current = _build_auth_context()
    async with get_session_factory()() as session:
        service = AiAgentRunService(session)
        task = await service.create_task(
            run_id="run-tool-auth-non-paused",
            session_id="session-tool-auth-non-paused",
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=current.user.id,
            backend_session_id=current.backend_session_id,
            scope=AgentScopeContext(scope_type="workspace", workspace_id=workspace_id, source="editor-agent-sidebar"),
            input_summary="非暂停继续授权测试",
            tool_scopes=PROJECT_TOOL_READ_SCOPES,
        )
        original_expiry = task.tool_auth_expires_at
        original_max_expiry = task.tool_auth_max_expires_at

    response = await authenticated_client.post(
        f"/api/ai/runs/{task.run_id}/continue",
        json={"tool_execution": {}},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "AI_SESSION_RUN_NOT_PAUSED"
    async with get_session_factory()() as session:
        persisted = await AiAgentRunService(session).get_task_by_run(run_id=task.run_id, user_id=current.user.id)
    assert persisted is not None
    assert persisted.status == "pending"
    assert persisted.tool_auth_expires_at == original_expiry
    assert persisted.tool_auth_max_expires_at == original_max_expiry

def test_resource_create_tool_should_repair_stringified_tags_before_validation() -> None:
    """资源创建工具应在校验前修复模型把 tags 数组二次编码成字符串的参数。"""

    create_tool = _find_tool(build_resource_manager_tools(get_session_factory()), "create_resource_asset")
    tags_schema = create_tool.parameters["properties"]["tags"]
    assert tags_schema["anyOf"][0]["type"] == "array"

    function_call = FunctionCall(
        function=create_tool,
        arguments={"tags": '["物理学", "电磁学", "麦克斯韦方程组", "物理学"]'},
    )
    assert create_tool.pre_hook is not None
    create_tool.pre_hook(fc=function_call)

    assert function_call.arguments == {"tags": ["物理学", "电磁学", "麦克斯韦方程组"]}

async def test_workspace_component_list_tool_should_default_to_project_suggested_components(
    authenticated_client: AsyncClient,
) -> None:
    """内容助手组件列表工具默认应优先返回项目建议组件，并在为空时回退全库。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 建议组件空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 建议组件项目")
    suggested_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "推荐指标卡",
            "import_name": "SuggestedMetricCard",
            "content": "<template><section>Suggested</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert suggested_response.status_code == 200
    suggested_publish_response = await authenticated_client.post(
        f"/api/components/{suggested_response.json()['id']}/publish",
        json={"release_name": None, "change_note": "发布建议组件"},
    )
    assert suggested_publish_response.status_code == 200
    suggested_component = suggested_publish_response.json()
    general_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "全库图表",
            "import_name": "GeneralChartBlock",
            "content": "<template><section>General</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert general_response.status_code == 200
    general_publish_response = await authenticated_client.post(
        f"/api/components/{general_response.json()['id']}/publish",
        json={"release_name": None, "change_note": "发布全库组件"},
    )
    assert general_publish_response.status_code == 200
    general_component = general_publish_response.json()
    save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-components",
        json={"component_ids": [suggested_component["id"]]},
    )
    assert save_response.status_code == 200

    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    list_tool = build_list_workspace_components_tool(get_session_factory())

    suggested_result = await list_tool.entrypoint(run_context, limit=10)
    fallback_result = await list_tool.entrypoint(run_context, keyword="全库", limit=10)
    all_result = await list_tool.entrypoint(run_context, scope="all", limit=10)

    assert suggested_result["source"] == "project_suggested"
    assert suggested_result["fallback_reason"] is None
    assert [item["component_code"] for item in suggested_result["items"]] == [suggested_component["code"]]
    assert fallback_result["source"] == "workspace_all"
    assert fallback_result["fallback_reason"] == "suggested_filter_empty"
    assert [item["component_code"] for item in fallback_result["items"]] == [general_component["code"]]
    assert all_result["source"] == "workspace_all"
    assert all_result["fallback_reason"] is None
    assert {item["component_code"] for item in all_result["items"]} == {
        suggested_component["code"],
        general_component["code"],
    }

async def test_coordinator_runtime_kit_tools_should_query_agent_capabilities(
    authenticated_client: AsyncClient,
) -> None:
    """内容助手应能直接查询开放给 Agent 的 Runtime Kit 能力。"""

    workspace_id = await _create_workspace(authenticated_client, "内容助手 Runtime Kit 工作空间")
    tools = build_unified_agent_tools(session_factory=get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )

    list_tool = _find_tool(tools, "list_runtime_kit_capabilities")
    listed = await list_tool.entrypoint(run_context, keyword="page", limit=100)
    names = {item["name"] for item in listed["items"]}
    assert "usePageSize.v1" in names

    detail_tool = _find_tool(tools, "get_runtime_kit_capability")
    detail = await detail_tool.entrypoint(run_context, name="DefaultContainer.v1", kind="component")
    assert detail["import_path"] == "@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue"
    assert "agent" in detail["audiences"]

    asset_image_detail = await detail_tool.entrypoint(run_context, name="AssetImage", kind="component")
    assert asset_image_detail["name"] == "AssetImage.v1"
    assert asset_image_detail["import_path"] == "@runtime-kit/public/components/assets/AssetImage.v1.vue"
    asset_image_text = json.dumps(asset_image_detail, ensure_ascii=False)
    assert "外层图片框" in asset_image_text
    assert "fit 控制 object-fit" in asset_image_text

async def test_project_route_tools_should_list_project_pages_with_user_context(
    authenticated_client: AsyncClient,
) -> None:
    """项目路由页面列表工具应把授权用户透传给页面服务。"""

    workspace_id = await _create_workspace(authenticated_client, "项目路由页面列表工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "项目路由页面列表项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="路由候选页面",
        content="<template><main>路由候选</main></template>",
    )
    tools = build_project_tools(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    list_tool = _find_tool(tools, "list_project_pages")
    result = await list_tool.entrypoint(run_context, keyword="路由候选", limit=10)

    assert result["total"] == 1
    assert result["items"][0]["page_id"] == page_id
    assert result["items"][0]["title"] == "路由候选页面"

async def test_publish_component_tool_should_create_reusable_version(
    authenticated_client: AsyncClient,
) -> None:
    """组件发布工具应把当前草稿发布为可引用的正式版本。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 组件发布工具工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "发布测试组件",
            "import_name": "PublishTestComponent",
            "content": "<template><article>publish</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    publish_tool = _find_tool(build_component_manager_tools(get_session_factory()), "publish_component")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await publish_tool.entrypoint(
        run_context,
        component_id=component_id,
        release_name="首版",
        change_note="AI 助手发布测试版本",
    )

    assert result["success"] is True
    assert result["component"]["current_version_no"] == 1
    assert result["component"]["has_unpublished_changes"] is False
    assert result["import_usage"]["import_path"] == f"@workspace-components/{result['component']['code']}/v/1"
    assert "PublishTestComponent" in result["import_usage"]["import_statement"]

async def test_agent_runtime_context_should_include_project_suggested_reference_assets(
    authenticated_client: AsyncClient,
) -> None:
    """页面或项目会话上下文应默认带入项目建议引用内容资源精简摘要。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 建议资源上下文空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 建议资源上下文项目")
    asset_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "image",
            "name": "hero_illustration",
            "original_name": "hero.svg",
            "description": "首页主视觉插图",
            "content": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 16 16\"><rect width=\"16\" height=\"16\"/></svg>",
            "tags": ["不应进入上下文"],
        },
    )
    assert asset_response.status_code == 200
    save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": [asset_response.json()["id"]]},
    )
    assert save_response.status_code == 200
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="建议资源页面",
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

    assert [item["name"] for item in runtime_context.suggested_reference_assets] == ["hero_illustration"]
    assert set(runtime_context.suggested_reference_assets[0]) == {
        "id",
        "name",
        "original_name",
        "description",
        "asset_type",
        "content_editable",
    }
    scope_text = build_scope_context_text(runtime_context)
    assert "以下为项目建议引用资源" in scope_text
    assert "需要使用资源素材时，建议优先考虑这些资源" in scope_text
    assert "hero_illustration" in scope_text
    assert "url" not in scope_text
    assert "tags" not in scope_text
    assert "不应进入上下文" not in scope_text

async def test_project_suggested_reference_assets_tool_should_return_slim_items(
    authenticated_client: AsyncClient,
) -> None:
    """项目建议引用资源工具应要求项目上下文，并返回不含 URL 和标签的精简字段。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 建议资源工具空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 建议资源工具项目")
    asset_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "mermaid",
            "name": "process_flow",
            "original_name": "process.mmd",
            "description": "流程图素材",
            "content": "flowchart TD\n  A[开始] --> B[结束]",
            "tags": ["不应返回"],
        },
    )
    assert asset_response.status_code == 200
    save_response = await authenticated_client.put(
        f"/api/projects/{project_id}/suggested-reference-assets",
        json={"asset_ids": [asset_response.json()["id"]]},
    )
    assert save_response.status_code == 200

    tool_item = _find_tool(build_resource_manager_tools(get_session_factory()), "list_project_suggested_reference_assets")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=RESOURCE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    result = await tool_item.entrypoint(run_context)

    assert result["total"] == 1
    assert result["items"][0]["name"] == "process_flow"
    assert set(result["items"][0]) == {"id", "name", "original_name", "description", "asset_type", "content_editable"}

    missing_project_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=RESOURCE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )
    try:
        await tool_item.entrypoint(missing_project_context)
    except AppException as error:
        assert error.code == "AI_TOOL_SCOPE_REQUIRED"
    else:  # pragma: no cover
        raise AssertionError("缺少 project_id 时应拒绝调用项目建议资源工具。")

def test_ai_continue_requirement_should_persist_confirmation_decision() -> None:
    """确认/拒绝 HITL 时 RunRequirement 与 ToolExecution 都应带上用户决策。"""

    confirmed = _build_run_requirement_from_tool_execution_payload(
        {
            "tool_call_id": "tool-confirmed",
            "tool_name": "apply_project_route_tree",
            "requires_confirmation": True,
            "confirmed": True,
        }
    )
    assert confirmed.confirmation is True
    assert confirmed.tool_execution is not None
    assert confirmed.tool_execution.confirmed is True
    assert confirmed.is_resolved() is True

    rejected = _build_run_requirement_from_tool_execution_payload(
        {
            "tool_call_id": "tool-rejected",
            "tool_name": "apply_project_route_tree",
            "requires_confirmation": True,
            "confirmed": False,
            "confirmation_note": "用户拒绝执行。",
        }
    )
    assert rejected.confirmation is False
    assert rejected.confirmation_note == "用户拒绝执行。"
    assert rejected.tool_execution is not None
    assert rejected.tool_execution.confirmed is False
    assert rejected.tool_execution.confirmation_note == "用户拒绝执行。"
    assert rejected.is_resolved() is True

def test_team_run_output_continue_should_support_agent_tool_events() -> None:
    """Agno Team continue 复用 Agent 工具事件 helper 时，不应因缺少 agent_id 失败。"""

    run = TeamRunOutput(
        run_id="team-continue-run",
        session_id="team-continue-session",
        team_id=AGENT_COORDINATOR_AGENT_ID,
        team_name="内容助手",
    )
    patched_run = _prepare_team_run_output_for_agno_continue(
        run,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        agent_name="内容助手",
    )

    assert patched_run is run
    event = create_tool_call_started_event(
        run,
        ToolExecution(
            tool_call_id="tool-confirm-route",
            tool_name="apply_project_route_tree",
            tool_args={},
        ),
    )
    assert event.agent_id == AGENT_COORDINATOR_AGENT_ID
    assert event.agent_name == "内容助手"

async def test_ai_active_run_cancel_should_not_fail_when_agno_cancel_returns_false(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """Agno graceful cancel 返回 False 时，BFF 仍应进入 cancelling 并允许 force 兜底清理。"""

    workspace_id = await _create_workspace(authenticated_client, "AI Graceful Cancel 工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI Graceful Cancel 项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI Graceful Cancel 页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "Graceful Cancel 会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-cancel-false"
    scope = AgentScopeContext(workspace_id=workspace_id, project_id=project_id, page_id=page_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="需要取消的长任务",
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id, data={}),
        )

    cancel_calls: list[str] = []

    def fake_cancel_run(cancel_run_id: str) -> bool:
        cancel_calls.append(cancel_run_id)
        return False

    monkeypatch.setattr("app.ai.run_background.AgnoAgent.cancel_run", fake_cancel_run)
    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    manager = app.state.ai_run_manager
    dummy_task = asyncio.create_task(asyncio.sleep(3600))
    manager._tasks[run_id] = dummy_task  # noqa: SLF001
    try:
        cancel_response = await authenticated_client.post(
            f"/api/ai/sessions/{session_id}/active-run/cancel",
            params={
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
            },
            json={"session_id": session_id},
        )
        assert cancel_response.status_code == 200
        assert cancel_response.json()["run_id"] == run_id
        assert cancel_calls == [run_id]

        active_response = await authenticated_client.get(
            f"/api/ai/sessions/{session_id}/active-run",
            params={
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
            },
        )
        assert active_response.status_code == 200
        active_payload = active_response.json()
        assert active_payload["status"] == "cancelling"
        assert active_payload["cancel_requested_at"] is not None

        force_response = await authenticated_client.post(
            f"/api/ai/sessions/{session_id}/active-run/cancel",
            params={
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
            },
            json={"session_id": session_id, "force": True},
        )
        assert force_response.status_code == 200
        assert force_response.json()["run_id"] == run_id

        final_response = await authenticated_client.get(
            f"/api/ai/sessions/{session_id}/active-run",
            params={
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "agent_id": AGENT_COORDINATOR_AGENT_ID,
            },
        )
        assert final_response.status_code == 200
        assert final_response.json() is None
        async with get_session_factory()() as db_session:
            service = AiAgentRunService(db_session)
            task = await service.get_task_by_run(run_id=run_id, user_id=1)
            ignored_event = await service.append_event(
                run_id=run_id,
                event=AgentRunEvent(event="run.completed", run_id=run_id, session_id=session_id, data={}),
            )
            events = await service.list_events_after(run_id=run_id, user_id=1, after_sequence=0)
        assert task is not None
        assert task.status == "cancelled"
        assert ignored_event is None
        assert [event.event for event in events] == ["run.started", "run.cancelling", "run.cancelled"]
    finally:
        manager._tasks.pop(run_id, None)  # noqa: SLF001
        dummy_task.cancel()
        await asyncio.gather(dummy_task, return_exceptions=True)

async def test_ai_user_cancel_should_preserve_streamed_delta_in_agno_history(authenticated_client: AsyncClient) -> None:
    """用户主动停止时，应把已流出的 assistant 文本补写进 Agno 历史。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 停止保留工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 停止保留项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 停止保留页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "停止保留会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-preserve-cancel"
    await _append_test_run(
        authenticated_client,
        session_id=session_id,
        run=RunOutput(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            status=RunStatus.running,
            messages=[
                Message(role="assistant", content="旧历史回复", from_history=True),
                Message(role="user", content="请生成一段长内容"),
            ],
        ),
    )
    scope = AgentScopeContext(workspace_id=workspace_id, project_id=project_id, page_id=page_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary="请生成一段长内容",
        )
        await service.append_event(run_id=run_id, event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id))
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="message.delta", run_id=run_id, session_id=session_id, content="第一段，"),
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="message.delta", run_id=run_id, session_id=session_id, content="第二段。"),
        )
        await service.mark_cancelling(task=task)

    response = await authenticated_client.post(
        f"/api/ai/runs/{run_id}/cancel",
        json={"force": True},
    )
    assert response.status_code == 200

    messages_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [item["role"] for item in messages] == ["assistant", "user", "assistant"]
    assert messages[-1]["content"] == "第一段，第二段。"

    app = authenticated_client._transport.app  # type: ignore[attr-defined]
    session_detail = await asyncio.to_thread(app.state.ai_db.get_session, session_id, SessionType.TEAM, "1", True)
    assert isinstance(session_detail, TeamSession)
    run = session_detail.get_run(run_id)
    assert run is not None
    assert run.content == "第一段，第二段。"
    assert run.metadata is not None
    assert run.metadata["user_cancel_preserved"] is True

async def test_ai_user_cancel_should_preserve_full_user_input_and_reasoning(authenticated_client: AsyncClient) -> None:
    """用户停止首轮会话时，应完整保留用户输入、正文与已展示 reasoning。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 停止保留完整输入工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 停止保留完整输入项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 停止保留完整输入页面",
        content="<template><div>draft</div></template>",
    )
    session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "停止保留完整输入会话",
            "scope": {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "page_id": page_id,
                "source": "editor-page-detail",
            },
        },
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]
    run_id = "run-preserve-full-input"
    long_message = "请详细分析停止后是否保留历史。" * 80
    scope = AgentScopeContext(workspace_id=workspace_id, project_id=project_id, page_id=page_id)
    async with get_session_factory()() as db_session:
        service = AiAgentRunService(db_session)
        task = await service.create_task(
            run_id=run_id,
            session_id=session_id,
            agent_id=AGENT_COORDINATOR_AGENT_ID,
            user_id=1,
            backend_session_id=None,
            scope=scope,
            input_summary=long_message,
            input_payload_json=build_agent_run_input_payload(message=long_message, image_attachment_ids=[]),
        )
        await service.append_event(run_id=run_id, event=AgentRunEvent(event="run.started", run_id=run_id, session_id=session_id))
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(
                event="message.delta",
                run_id=run_id,
                session_id=session_id,
                content="",
                data={"reasoning_content": "先判断取消时机。"},
            ),
        )
        await service.append_event(
            run_id=run_id,
            event=AgentRunEvent(event="message.delta", run_id=run_id, session_id=session_id, content="已经输出的正文。"),
        )
        await service.mark_cancelling(task=task)

    response = await authenticated_client.post(f"/api/ai/runs/{run_id}/cancel", json={"force": True})
    assert response.status_code == 200

    messages_response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/messages",
        params={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "page_id": page_id,
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
        },
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == long_message
    assert messages[1]["content"] == "已经输出的正文。"
    assert messages[1]["reasoning_content"] == "先判断取消时机。"
    assert messages[0]["run_id"] == run_id
    assert messages[1]["run_id"] == run_id

async def test_ai_runtime_timeline_should_preserve_post_tool_assistant_message_from_history(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """工具前已有流式 assistant 时，工具后的 assistant message 仍应按工具锚点补齐。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 工具后消息补齐工作空间")
    run_id = "run-post-tool-assistant-fallback"
    session_id = "session-post-tool-assistant-fallback"
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "工具后消息补齐会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[
                    Message(role="user", content="先读取资源，再告诉我结论"),
                    Message(role="assistant", content="我先读取资源。"),
                    Message(
                        role="tool",
                        content='{"total": 2, "items": ["a", "b"]}',
                        tool_name="list_workspace_render_assets",
                        tool_call_id="tool-assets-post-message",
                        tool_args={"workspace_id": workspace_id},
                        tool_call_error=False,
                    ),
                    Message(role="assistant", content="资源读取完成，共 2 个。"),
                ],
                events=[
                    {
                        "event": "RunContent",
                        "run_id": run_id,
                        "content": "我先读取资源。",
                    },
                    {
                        "event": "ToolCallStarted",
                        "run_id": run_id,
                        "tool": {
                            "tool_name": "list_workspace_render_assets",
                            "tool_call_id": "tool-assets-post-message",
                            "tool_args": {"workspace_id": workspace_id},
                        },
                    },
                    {
                        "event": "ToolCallCompleted",
                        "run_id": run_id,
                        "content": "工具调用完成。",
                        "tool": {
                            "tool_name": "list_workspace_render_assets",
                            "tool_call_id": "tool-assets-post-message",
                        },
                    },
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-post-tool-assistant-fallback"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return _build_empty_context_status(session_id, retained_recent_message_count=4)

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    timeline_items = response.json()["timeline_items"]
    assert [
        (item["kind"], item["role"], item["content"], item["tool"]["tool_name"] if item["tool"] else None)
        for item in timeline_items
    ] == [
        ("message", "user", "先读取资源，再告诉我结论", None),
        ("message", "assistant", "我先读取资源。", None),
        ("tool", None, None, "list_workspace_render_assets"),
        ("message", "assistant", "资源读取完成，共 2 个。", None),
        ("run_status", None, "运行已完成。", None),
    ]
    tool_item = next(item for item in timeline_items if item["kind"] == "tool")
    assert tool_item["status"] == "completed"
    assert tool_item["tool"]["status"] == "completed"
    assert tool_item["tool"]["input_payload"] == {"workspace_id": workspace_id}
    assert tool_item["tool"]["output_payload"] == {"total": 2, "items": ["a", "b"]}
    assert tool_item["tool"]["message"] == "工具调用完成。"

async def test_ai_runtime_timeline_should_split_alternating_reasoning_and_content_events(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """reasoning 与 assistant 交替流出时，刷新恢复后不应分别合并成两大块。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 思考正文交替工作空间")
    run_id = "run-alternating-reasoning-content"
    session_id = "session-alternating-reasoning-content"
    timeline_session = AgentSession(
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        user_id="1",
        session_data={"session_name": "思考正文交替会话"},
        metadata={"scope_type": "workspace", "workspace_id": workspace_id, "source": "editor-agent-sidebar"},
        agent_data={"agent_id": AGENT_COORDINATOR_AGENT_ID},
        runs=[
            RunOutput(
                run_id=run_id,
                session_id=session_id,
                agent_id=AGENT_COORDINATOR_AGENT_ID,
                messages=[Message(role="user", content="分步说明")],
                events=[
                    {"event": "ReasoningContentDelta", "run_id": run_id, "reasoning_content": "先判断。"},
                    {"event": "RunContent", "run_id": run_id, "content": "第一步。"},
                    {"event": "ReasoningContentDelta", "run_id": run_id, "reasoning_content": "再确认。"},
                    {"event": "RunContent", "run_id": run_id, "content": "第二步。"},
                ],
                status=RunStatus.completed,
            )
        ],
    )

    async def fake_ensure_session_access(self, *, session_id: str, agent_id: str, scope):  # type: ignore[no-untyped-def]
        assert session_id == "session-alternating-reasoning-content"
        assert agent_id == AGENT_COORDINATOR_AGENT_ID
        assert scope.workspace_id == workspace_id
        return timeline_session

    async def fake_get_context_status(self, **_: object) -> AgentContextStatusItem:
        return _build_empty_context_status(session_id, retained_recent_message_count=1)

    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.ensure_session_access", fake_ensure_session_access)
    monkeypatch.setattr("app.api.routes.agents.AgentSessionFacade.get_context_status", fake_get_context_status)

    response = await authenticated_client.get(
        f"/api/ai/sessions/{session_id}/runtime",
        params={"workspace_id": workspace_id, "agent_id": AGENT_COORDINATOR_AGENT_ID},
    )

    assert response.status_code == 200
    assert [
        (item["kind"], item["role"], item["content"])
        for item in response.json()["timeline_items"]
    ] == [
        ("message", "user", "分步说明"),
        ("reasoning", None, "先判断。"),
        ("message", "assistant", "第一步。"),
        ("reasoning", None, "再确认。"),
        ("message", "assistant", "第二步。"),
        ("run_status", None, "运行已完成。"),
    ]
