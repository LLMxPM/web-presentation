"""文件功能：承载 AI scope tools 场景的拆分测试用例。"""

from __future__ import annotations

from tests.integration.ai.ai_agents_cases import *  # noqa: F403


async def test_agent_token_should_embed_audience_and_scope() -> None:
    """Agent Token 应包含约定 audience 和运行范围，不再携带工具访问令牌。"""

    fake_user = User(
        id=1,
        username="admin",
        password_hash="fake",
        display_name="平台系统管理员",
        status="active",
    )
    current = AuthContext(
        user=fake_user,
        session_token="session-token",
        backend_session_id="42",
    )

    agent_access_token = build_agent_access_token(
        current,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        session_id="session-1",
        workspace_id=11,
        project_id=21,
        page_id=31,
        role="admin",
    )
    agent_claims = TokenService.verify_signed_token(agent_access_token, audience="backend-agentos")
    assert "tool_access_token" not in agent_claims
    assert agent_claims["page_id"] == 31
    assert f"agents:{AGENT_COORDINATOR_AGENT_ID}:run" in agent_claims["scopes"]

async def test_agent_registry_should_expose_coordinator_and_component_manager() -> None:
    """Agent 注册表应暴露统一智能体和组件助手入口。"""

    registry = AgentRegistry(AIAgentFactory(agno_db=None, session_factory=None))
    descriptors = {item.id: item for item in registry.list_descriptors()}

    assert list(descriptors) == [AGENT_COORDINATOR_AGENT_ID, COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID]
    assert len({descriptor.icon for descriptor in descriptors.values()}) == 3
    assert descriptors[AGENT_COORDINATOR_AGENT_ID].icon == "content-spark"
    assert descriptors[AGENT_COORDINATOR_AGENT_ID].entry_kind == "team"
    assert descriptors[AGENT_COORDINATOR_AGENT_ID].llm_slot == "agent_coordinator"
    assert descriptors[AGENT_COORDINATOR_AGENT_ID].scope_type == "workspace"
    assert descriptors[COMPONENT_MANAGER_AGENT_ID].icon == "component-blocks"
    assert descriptors[COMPONENT_MANAGER_AGENT_ID].entry_kind == "agent"
    assert descriptors[COMPONENT_MANAGER_AGENT_ID].llm_slot == "component_manager"
    assert descriptors[COMPONENT_MANAGER_AGENT_ID].scope_type == "workspace"
    assert descriptors[RESOURCE_MANAGER_AGENT_ID].icon == "resource-images"
    assert descriptors[RESOURCE_MANAGER_AGENT_ID].entry_kind == "agent"
    assert descriptors[RESOURCE_MANAGER_AGENT_ID].llm_slot == "resource_manager"
    assert descriptors[RESOURCE_MANAGER_AGENT_ID].scope_type == "workspace"

async def test_agent_coordinator_availability_should_require_project_scope(authenticated_client: AsyncClient) -> None:
    """内容助手只能在具体项目范围启动，工作空间范围仅保留其他专长助手。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 内容助手项目限制工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 内容助手项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 内容助手页面",
        content="<template><div>content agent</div></template>",
    )

    workspace_agents_response = await authenticated_client.get(
        "/api/ai/agents",
        params={"workspace_id": workspace_id, "scope_type": "workspace"},
    )
    assert workspace_agents_response.status_code == 200
    workspace_agents = {item["id"]: item for item in workspace_agents_response.json()}
    assert workspace_agents[AGENT_COORDINATOR_AGENT_ID]["available"] is False
    assert workspace_agents[AGENT_COORDINATOR_AGENT_ID]["unavailable_reason"] == "内容助手需要进入具体项目后才能启动。"
    assert workspace_agents[COMPONENT_MANAGER_AGENT_ID]["available"] is True
    assert workspace_agents[RESOURCE_MANAGER_AGENT_ID]["available"] is True

    project_agents_response = await authenticated_client.get(
        "/api/ai/agents",
        params={"workspace_id": workspace_id, "project_id": project_id, "scope_type": "project"},
    )
    assert project_agents_response.status_code == 200
    project_agents = {item["id"]: item for item in project_agents_response.json()}
    assert project_agents[AGENT_COORDINATOR_AGENT_ID]["available"] is True

    page_agents_response = await authenticated_client.get(
        "/api/ai/agents",
        params={"workspace_id": workspace_id, "project_id": project_id, "page_id": page_id, "scope_type": "page"},
    )
    assert page_agents_response.status_code == 200
    page_agents = {item["id"]: item for item in page_agents_response.json()}
    assert page_agents[AGENT_COORDINATOR_AGENT_ID]["available"] is True

    workspace_session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "工作空间内容助手会话",
            "scope": {
                "scope_type": "workspace",
                "workspace_id": workspace_id,
                "source": "editor-agent-sidebar",
            },
        },
    )
    assert workspace_session_response.status_code == 409
    assert workspace_session_response.json()["code"] == "AI_AGENT_SCOPE_UNAVAILABLE"

    project_session_response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": AGENT_COORDINATOR_AGENT_ID,
            "session_name": "项目内容助手会话",
            "scope": {
                "scope_type": "project",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "source": "editor-agent-sidebar",
            },
        },
    )
    assert project_session_response.status_code == 201

async def test_component_and_coordinator_agents_should_register_expected_tools() -> None:
    """当前开放 Agent 应注册组件管理工具与内容助手当前路由业务工具。"""

    component_agent = build_component_manager_agent(
        agno_db=None,
        session_factory=None,
        model=None,
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-agent-sidebar",
        ),
    )
    component_tools = {tool.name: tool for tool in component_agent.tools}
    assert component_agent.store_events is True
    assert component_agent.events_to_skip == [RunEvent.run_content]
    assert "list_runtime_kit_capabilities" in component_tools
    assert "get_runtime_kit_capability" in component_tools
    assert "list_resource_assets" in component_tools
    assert "get_resource_asset_content" in component_tools
    assert "list_resource_tags" in component_tools
    assert "create_component_draft" not in component_tools
    assert "preview_component_edits" not in component_tools
    assert component_tools["create_component"].requires_confirmation is False
    assert component_tools["apply_component_edits"].requires_confirmation is False
    assert component_tools["update_component_metadata"].requires_confirmation is False
    assert component_tools["publish_component"].requires_confirmation is False
    assert component_tools["delete_component"].requires_confirmation is True
    component_instruction_text = "\n".join(component_agent.instructions)
    assert "封装 Runtime Kit 能力" in component_instruction_text
    assert "主题 Tailwind 样式" in component_instruction_text
    assert "内容助手复用" in component_instruction_text
    assert "font-heading" in component_instruction_text
    assert "bg-background" in component_instruction_text
    assert "primary、secondary、invert" in component_instruction_text
    assert "link、link-hover、link-visited" in component_instruction_text
    assert "ThemeLogo 组件" in component_instruction_text
    assert "themeLogo、themeInvertLogo、themeStyles" in component_instruction_text
    assert "不要硬编码主题 Logo 路径" in component_instruction_text

    coordinator = build_agent_coordinator_agent(
        agno_db=None,
        session_factory=None,
        model=None,
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-agent-sidebar",
        ),
    )
    assert coordinator.mode == TeamMode.coordinate
    assert coordinator.store_events is True
    assert coordinator.events_to_skip == [
        RunEvent.run_content,
        TeamRunEvent.run_content,
        TeamRunEvent.run_intermediate_content,
    ]
    assert {member.id for member in coordinator.members} == {COMPONENT_MANAGER_AGENT_ID, RESOURCE_MANAGER_AGENT_ID}
    assert all(member.store_events is True for member in coordinator.members)
    assert all(member.events_to_skip == [RunEvent.run_content] for member in coordinator.members)
    coordinator_tools = {tool.name: tool for tool in coordinator.tools}
    coordinator_tool_names = set(coordinator_tools)
    assert "get_page_content" in coordinator_tool_names
    assert "list_workspace_styles" not in coordinator_tool_names
    assert "get_workspace_style" not in coordinator_tool_names
    assert "get_project_style_config" in coordinator_tool_names
    assert coordinator_tools["update_project_style_config"].requires_confirmation is True
    assert "list_workspace_components" in coordinator_tool_names
    assert "get_workspace_component_usage" in coordinator_tool_names
    assert "list_resource_assets" in coordinator_tool_names
    assert "get_resource_asset_content" in coordinator_tool_names
    assert "list_resource_tags" in coordinator_tool_names
    assert "list_components" not in coordinator_tool_names
    assert "get_component_detail" not in coordinator_tool_names
    assert "list_component_versions" not in coordinator_tool_names
    assert "get_component_dependencies" not in coordinator_tool_names
    assert "list_runtime_kit_capabilities" in coordinator_tool_names
    assert "get_runtime_kit_capability" in coordinator_tool_names
    assert "create_component" not in coordinator_tool_names
    assert "apply_component_edits" not in coordinator_tool_names
    assert "publish_component" not in coordinator_tool_names
    assert "delete_component" not in coordinator_tool_names
    assert "create_resource_asset" not in coordinator_tool_names
    assert "apply_resource_content_diff" not in coordinator_tool_names
    assert "archive_resource_asset" not in coordinator_tool_names
    assert "request_tool_disclosure" not in coordinator_tool_names
    coordinator_instruction_text = "\n".join(coordinator.instructions)
    assert "主执行助手" in coordinator_instruction_text
    assert "不要为了形式化协作而委派" in coordinator_instruction_text
    assert "Runtime Kit 能力事实、已发布组件用法和资源读取由你直接查询" in coordinator_instruction_text
    assert "font-heading、font-body、font-code" in coordinator_instruction_text
    assert "bg-background" in coordinator_instruction_text
    assert "accent1 到 accent6" in coordinator_instruction_text
    assert "primary、secondary、invert" in coordinator_instruction_text
    assert "link、link-hover、link-visited" in coordinator_instruction_text
    assert "ThemeLogo 组件" in coordinator_instruction_text
    assert "themeLogo、themeInvertLogo、themeStyles" in coordinator_instruction_text
    assert "不要硬编码主题 Logo 路径" in coordinator_instruction_text
    assert "公开 import_path" in coordinator_instruction_text
    assert "@runtime-kit/components/" not in coordinator_instruction_text
    assert "AssetRenderer" not in coordinator_instruction_text
    assert "DefaultCoverPage" not in coordinator_instruction_text
    assert "DefaultContentPage" not in coordinator_instruction_text

    resource_agent = build_resource_manager_agent(
        agno_db=None,
        session_factory=None,
        model=None,
        runtime_context=AgentRuntimeContext(
            scope_type="workspace",
            workspace_id=1,
            source="editor-asset-library",
        ),
    )
    resource_tools = {tool.name: tool for tool in resource_agent.tools}
    assert resource_agent.store_events is True
    assert resource_agent.events_to_skip == [RunEvent.run_content]
    assert "list_resource_assets" in resource_tools
    assert "preview_resource_references" not in resource_tools
    assert "create_resource_asset" in resource_tools
    assert "archive_resource_asset" in resource_tools
    assert "delete_resource_asset" not in resource_tools
    assert resource_tools["create_resource_asset"].requires_confirmation is False
    assert resource_tools["apply_resource_content_diff"].requires_confirmation is False
    assert resource_tools["archive_resource_asset"].requires_confirmation is False
    assert any("资源库" in instruction for instruction in resource_agent.instructions)

async def test_resource_list_tool_should_return_active_non_history_assets_by_tag(
    authenticated_client: AsyncClient,
) -> None:
    """资源列表工具应只给 LLM 返回 active 非历史资源摘要，并支持标签过滤。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 资源列表过滤工作空间")
    create_brand_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": "brand_icon",
            "original_name": "brand_icon.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M1 1"/></svg>',
            "description": "品牌主 Logo，用于封面页。",
            "tags": ["品牌", "首页"],
        },
    )
    assert create_brand_response.status_code == 200
    brand_asset_id = create_brand_response.json()["id"]

    create_other_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": "other_icon",
            "original_name": "other_icon.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M2 2"/></svg>',
            "description": "非品牌图标。",
            "tags": ["其他"],
        },
    )
    assert create_other_response.status_code == 200

    update_brand_response = await authenticated_client.put(
        f"/api/workspaces/{workspace_id}/assets/{brand_asset_id}/content",
        json={
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M3 3"/></svg>',
            "change_note": "生成历史副本",
        },
    )
    assert update_brand_response.status_code == 200

    create_archived_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/content",
        json={
            "asset_type": "icon",
            "name": "archived_icon",
            "original_name": "archived_icon.svg",
            "content": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M4 4"/></svg>',
            "description": "已归档品牌图标。",
            "tags": ["品牌"],
        },
    )
    assert create_archived_response.status_code == 200
    archive_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/{create_archived_response.json()['id']}/archive",
        json={"archive_reason": "测试归档"},
    )
    assert archive_response.status_code == 200

    list_tool = _find_tool(build_resource_manager_tools(get_session_factory()), "list_resource_assets")
    parameters = list_tool.parameters["properties"]
    assert "tag" in parameters
    assert "status" not in parameters
    assert "include_history" not in parameters
    assert "history_only" not in parameters

    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=RESOURCE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )
    result = await list_tool.entrypoint(run_context, tag="品牌", limit=10)

    assert result["total"] == 1
    item = result["items"][0]
    assert item["id"] == brand_asset_id
    assert item["description"] == "品牌主 Logo，用于封面页。"
    assert item["tags"] == ["品牌", "首页"]
    assert "url" not in item
    assert "status" not in item
    assert "source_asset_id" not in item
    assert "history_kind" not in item

async def test_resource_create_tool_should_support_svg_image_asset(
    authenticated_client: AsyncClient,
) -> None:
    """资源助手创建工具应能把非图标 SVG 保存为 image 内容资源。"""

    workspace_id = await _create_workspace(authenticated_client, "AI SVG 图片资源工作空间")
    create_tool = _find_tool(build_resource_manager_tools(get_session_factory()), "create_resource_asset")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=RESOURCE_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await create_tool.entrypoint(
        run_context,
        asset_type="image",
        name="hero_illustration",
        original_name="illustration.svg",
        content='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540"><rect width="960" height="540" fill="#f8fafc"/></svg>',
        description="资源助手生成的封面 SVG 图片。",
        tags=["AI", "插画"],
    )

    assert result["success"] is True
    asset = result["asset"]
    assert asset["asset_type"] == "image"
    assert asset["asset_role"] == "content"
    assert asset["render_type"] == "image"
    assert asset["original_name"] == "illustration.svg"
    assert asset["content_editable"] is True
    assert asset["analysis_metadata"] is None

async def test_resource_member_write_tool_should_accept_member_token_from_coordinator_run(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """内容助手委派资源助手时，资源写入工具应能使用成员助手 token 授权。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 资源成员授权工作空间")
    now = datetime.now(UTC)

    async def fake_create_content_asset(self, workspace_id: int, **kwargs):  # type: ignore[no-untyped-def]
        """替换真实对象存储写入，只保留工具授权链路验证。"""

        asset_type = str(getattr(kwargs["asset_type"], "value", kwargs["asset_type"]))
        content = str(kwargs["content"])
        return SimpleNamespace(
            id=801,
            workspace_id=workspace_id,
            name=kwargs["name"],
            file_name="mass-energy-equation.tex",
            original_name=kwargs["original_name"],
            description=kwargs.get("description"),
            file_size=len(content.encode("utf-8")),
            file_hash="fake-formula-hash",
            content_type="text/plain",
            asset_type=asset_type,
            tags=kwargs.get("tags") or [],
            analysis_metadata=None,
            render_metadata=None,
            status=RecordStatus.ACTIVE.value,
            archived_at=None,
            archive_reason=None,
            source_asset_id=None,
            history_kind=None,
            font_config=None,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr("app.services.asset_service.AssetService.create_content_asset", fake_create_content_asset)
    current = _build_auth_context()
    create_tool = _find_tool(build_resource_manager_tools(get_session_factory()), "create_resource_asset")
    run_context = await _build_tool_run_context(
        current=current,
        tool_scopes=RESOURCE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )
    dependencies = run_context.dependencies
    assert dependencies is not None
    member_scopes = AgentSessionFacade._resolve_tool_scopes(agent_id=RESOURCE_MANAGER_AGENT_ID)
    dependencies["member_tool_auth_tokens"] = {
        RESOURCE_MANAGER_AGENT_ID: build_agent_tool_token(
            current,
            run_id=dependencies["run_id"],
            session_id=dependencies["session_id"],
            agent_id=RESOURCE_MANAGER_AGENT_ID,
            workspace_id=workspace_id,
            project_id=None,
            page_id=None,
            component_id=None,
            source=dependencies["source"],
            scopes=member_scopes,
        )
    }
    dependencies["member_tool_scopes"] = {RESOURCE_MANAGER_AGENT_ID: list(member_scopes)}

    result = await create_tool.entrypoint(
        run_context,
        asset_type="formula",
        name="mass-energy-equation",
        original_name="mass-energy-equation.tex",
        content="\\[ E = mc^{2} \\]",
        description="爱因斯坦质能方程，揭示质量与能量的等价关系",
        tags=["physics", "relativity", "einstein"],
    )

    assert result["success"] is True
    asset = result["asset"]
    assert asset["asset_type"] == "formula"
    assert asset["original_name"] == "mass-energy-equation.tex"

async def test_workspace_component_usage_tools_should_not_require_page_scope(
    authenticated_client: AsyncClient,
) -> None:
    """工作空间组件查询和用法工具只应依赖 workspace_id，不要求当前页面上下文。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 组件用法工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "营销卡片",
            "import_name": "MarketingCard",
            "content": "<template><section>Card</section></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component = create_response.json()
    publish_response = await authenticated_client.post(
        f"/api/components/{component['id']}/publish",
        json={"release_name": None, "change_note": "发布测试版本"},
    )
    assert publish_response.status_code == 200
    published_component = publish_response.json()

    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        page_id=None,
    )
    list_tool = build_list_workspace_components_tool(get_session_factory())
    usage_tool = build_get_workspace_component_usage_tool(get_session_factory())

    list_result = await list_tool.entrypoint(run_context, limit=10)
    usage_result = await usage_tool.entrypoint(run_context, component_code=published_component["code"])

    assert list_result == {
        "source": "workspace_all",
        "fallback_reason": "no_project_context",
        "total": 1,
        "items": [
            {
                "name": "营销卡片",
                "import_name": "MarketingCard",
                "description": None,
                "component_code": published_component["code"],
                "current_version_no": 1,
            }
        ],
    }
    assert usage_result["component_code"] == published_component["code"]
    assert usage_result["import_path"] == f"@workspace-components/{published_component['code']}/v/1"

async def test_workspace_render_assets_tool_should_include_video_assets(
    authenticated_client: AsyncClient,
) -> None:
    """页面资源查询工具应把视频作为可渲染内容资源返回。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 视频资源工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "AI 视频资源项目")
    page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=project_id,
        title="AI 视频资源页面",
        content="<template><div>video</div></template>",
    )
    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("intro.mp4", b"fake-intro-video", "video/mp4")},
        data={"asset_type": "video", "tags": '["演示"]', "name": "intro_video"},
    )
    assert upload_response.status_code == 200

    list_tool = build_list_workspace_render_assets_tool(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PAGE_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
        page_id=page_id,
    )
    result = await list_tool.entrypoint(run_context, render_type="video", limit=10)

    assert result == [
        {
            "name": "intro_video",
            "extension": "mp4",
            "type": "video",
            "description": None,
        }
    ]

def test_coordinator_should_expose_component_resource_and_runtime_kit_read_tools() -> None:
    """内容助手直接工具应暴露组件、资源和 Runtime Kit 只读查询能力。"""

    definitions = get_tool_group_definitions(session_factory=get_session_factory())
    assert "content_read" in definitions
    content_read_tools = set(definitions["content_read"].tool_keys)
    assert {
        "get_page_content",
        "get_project_style_config",
        "list_project_pages",
        "get_project_route_tree",
        "preview_project_route_tree",
    } <= content_read_tools
    component_read_tools = set(definitions["component_read"].tool_keys)
    assert component_read_tools == {"list_workspace_components", "get_workspace_component_usage"}
    runtime_kit_tools = set(definitions["runtime_kit"].tool_keys)
    assert runtime_kit_tools == {"list_runtime_kit_capabilities", "get_runtime_kit_capability"}
    resource_read_tools = set(definitions["resource_read"].tool_keys)
    assert resource_read_tools == {"list_resource_assets", "get_resource_asset_content", "list_resource_tags"}
    assert "list_workspace_render_assets" not in content_read_tools
    assert "list_workspace_icon_assets" not in content_read_tools
    assert "list_workspace_font_assets" not in content_read_tools
    assert "list_components" not in component_read_tools
    assert "get_component_detail" not in component_read_tools
    assert "list_component_versions" not in component_read_tools
    assert "get_component_dependencies" not in component_read_tools
    assert "component_write" not in definitions
    assert "resource_write" not in definitions

    coordinator_scopes = AgentSessionFacade._resolve_tool_scopes(
        agent_id=AGENT_COORDINATOR_AGENT_ID,
    )
    assert COMPONENT_TOOL_READ_SCOPES[0] in coordinator_scopes
    assert RESOURCE_TOOL_READ_SCOPES[0] in coordinator_scopes
    assert COMPONENT_TOOL_WRITE_SCOPES[0] not in coordinator_scopes
    assert COMPONENT_TOOL_DELETE_SCOPES[0] not in coordinator_scopes
    assert RESOURCE_TOOL_WRITE_SCOPES[0] not in coordinator_scopes

def test_component_manager_should_receive_component_write_tool_scopes() -> None:
    """组件助手应固定获得组件读写删除、资源读取和代码检查工具权限。"""

    component_scopes = AgentSessionFacade._resolve_tool_scopes(
        agent_id=COMPONENT_MANAGER_AGENT_ID,
        enabled_tool_groups=(),
    )
    assert COMPONENT_TOOL_READ_SCOPES[0] in component_scopes
    assert COMPONENT_TOOL_WRITE_SCOPES[0] in component_scopes
    assert COMPONENT_TOOL_DELETE_SCOPES[0] in component_scopes
    assert RESOURCE_TOOL_READ_SCOPES[0] in component_scopes

def test_ai_session_scope_should_use_hierarchical_route_containment() -> None:
    """session scope 应按 workspace/project/page/component 层级判断当前路由是否可运行。"""

    page_route_scope = AgentScopeContext(
        scope_type="page",
        workspace_id=11,
        project_id=21,
        page_id=31,
        source="editor-page-detail",
    )
    component_route_scope = AgentScopeContext(
        scope_type="component",
        workspace_id=11,
        component_id=91,
        source="editor-component-library",
    )

    assert AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "workspace", "workspace_id": 11},
        page_route_scope,
    )
    assert AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "project", "workspace_id": 11, "project_id": 21},
        page_route_scope,
    )
    assert AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "page", "workspace_id": 11, "project_id": 21, "page_id": 31},
        page_route_scope,
    )
    assert not AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "page", "workspace_id": 11, "project_id": 21, "page_id": 32},
        page_route_scope,
    )
    assert AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "component", "workspace_id": 11, "component_id": 91},
        component_route_scope,
    )
    assert not AgentSessionFacade._route_scope_within_session_scope(
        {"scope_type": "component", "workspace_id": 11, "component_id": 92},
        component_route_scope,
    )

def test_ai_run_scope_should_prefer_run_metadata_over_session_scope() -> None:
    """继续 paused run 时应优先使用 run 创建时记录的运行上下文。"""

    run = RunOutput(
        run_id="run-original-scope",
        session_id="session-project",
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        status=RunStatus.paused,
        metadata={
            "run_scope": {
                "scope_type": "page",
                "workspace_id": 11,
                "project_id": 21,
                "page_id": 31,
                "source": "editor-page-detail",
            },
        },
    )

    resolved_scope = AgentSessionFacade._resolve_run_scope(
        run,
        fallback_metadata={"scope_type": "project", "workspace_id": 11, "project_id": 21},
    )

    assert resolved_scope is not None
    assert resolved_scope.scope_type == "page"
    assert resolved_scope.page_id == 31

async def test_project_page_tools_should_create_and_update_metadata(authenticated_client: AsyncClient) -> None:
    """项目页面工具应能创建页面并维护页面名称与说明。"""

    workspace_id = await _create_workspace(authenticated_client, "项目页面工具工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "项目页面工具项目")
    tools = build_project_tools(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    create_tool = _find_tool(tools, "create_project_page")
    page_content = "<template>\n  <main>占位页面</main>\n</template>\n"
    created = await create_tool.entrypoint(
        run_context,
        title="新建页面",
        summary="用于后续细化的占位页面",
        speaker_notes="创建时的演讲备注",
        page_content=page_content,
    )
    assert created["success"] is True
    assert created["title"] == "新建页面"
    assert created["speaker_notes"] == "创建时的演讲备注"
    assert created["project_id"] == project_id

    get_response = await authenticated_client.get(f"/api/pages/{created['page_id']}")
    assert get_response.status_code == 200
    page_payload = get_response.json()
    assert page_payload["page_content"] == page_content
    assert page_payload["summary"] == "用于后续细化的占位页面"
    assert page_payload["speaker_notes"] == "创建时的演讲备注"

    update_tool = _find_tool(tools, "update_page_metadata")
    updated = await update_tool.entrypoint(
        run_context,
        page_id=created["page_id"],
        title="更新后的页面",
        summary="",
        change_note="更新页面标题并清空说明",
    )
    assert updated["success"] is True
    assert updated["title"] == "更新后的页面"
    assert updated["summary"] == ""
    assert updated["speaker_notes"] == "创建时的演讲备注"

    updated_response = await authenticated_client.get(f"/api/pages/{created['page_id']}")
    assert updated_response.status_code == 200
    updated_payload = updated_response.json()
    assert updated_payload["title"] == "更新后的页面"
    assert updated_payload["summary"] == ""
    assert updated_payload["speaker_notes"] == "创建时的演讲备注"

    notes_updated = await update_tool.entrypoint(
        run_context,
        page_id=created["page_id"],
        speaker_notes="单独更新后的演讲备注",
        change_note="更新演讲者备注",
    )
    assert notes_updated["success"] is True
    assert notes_updated["speaker_notes"] == "单独更新后的演讲备注"

async def test_project_style_config_tools_should_read_and_update_with_confirmation(
    authenticated_client: AsyncClient,
) -> None:
    """项目样式配置工具应只暴露真实画布、基础字号、主题摘要与样式规范。"""

    workspace_id = await _create_workspace(authenticated_client, "项目样式工具工作空间")
    project_response = await authenticated_client.post(
        "/api/projects",
        json={
            "workspace_id": workspace_id,
            "name": "项目样式工具项目",
            "description": "用于内容助手读取项目描述。",
            "status": "active",
            "page_width": 1280,
            "page_height": 720,
            "base_font_size": "16px",
            "icon_default_stroke_width": 2,
            "show_pdf_export_button": True,
            "menu_mode": "preview",
            "style_spec_markdown": "## 版式\r\n- 使用清晰标题。",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    tools = build_project_tools(get_session_factory())
    tool_names = {tool.name for tool in tools}
    assert "list_workspace_styles" not in tool_names
    assert "get_workspace_style" not in tool_names

    read_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    get_tool = _find_tool(tools, "get_project_style_config")
    config = await get_tool.entrypoint(read_context)
    assert config["page_width"] == 1280
    assert config["page_height"] == 720
    assert config["base_font_size"] == "16px"
    assert config["theme"]["palette"]["text"]["primary"] == "#0D286A"
    assert config["theme"]["typography"]["headingfont"] == "system-ui"
    assert config["style_spec_markdown"] == "## 版式\n- 使用清晰标题。"
    assert "project" not in config
    assert "style_config" not in config
    assert "authoring_width" not in config
    assert "authoring_height" not in config
    assert "theme_key" not in config
    assert "theme_config_yaml" not in config
    assert "effective_app_config" not in config
    assert "effective_theme_config" not in config

    write_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    update_tool = _find_tool(tools, "update_project_style_config")
    assert update_tool.requires_confirmation is True
    updated = await update_tool.entrypoint(
        write_context,
        style_spec_markdown="## 新规范\n- 使用克制留白。",
    )
    assert updated["success"] is True
    assert updated["style_spec_markdown"] == "## 新规范\n- 使用克制留白。"
    assert "project" not in updated
    assert "style_config" not in updated

    persisted_response = await authenticated_client.get(f"/api/projects/{project_id}")
    assert persisted_response.status_code == 200
    persisted = persisted_response.json()
    assert persisted["page_width"] == 1280
    assert persisted["page_height"] == 720
    assert persisted["base_font_size"] == "16px"
    assert persisted["menu_mode"] == "preview"
    assert persisted["style_spec_markdown"] == "## 新规范\n- 使用克制留白。"

async def test_project_page_tools_should_reject_invalid_scope_or_payload(authenticated_client: AsyncClient) -> None:
    """项目页面工具应拒绝空页面源码、缺少项目上下文和跨项目元数据修改。"""

    workspace_id = await _create_workspace(authenticated_client, "项目页面工具拒绝工作空间")
    project_id = await _create_project(authenticated_client, workspace_id, "目标项目")
    other_project_id = await _create_project(authenticated_client, workspace_id, "其他项目")
    other_page_id = await _create_page(
        authenticated_client,
        workspace_id=workspace_id,
        project_id=other_project_id,
        title="其他项目页面",
        content="<template><div>other</div></template>",
    )
    tools = build_project_tools(get_session_factory())
    valid_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=project_id,
    )

    create_tool = _find_tool(tools, "create_project_page")
    try:
        await create_tool.entrypoint(valid_context, title="空内容页面", page_content="   ")
    except AppException as exc:
        assert exc.code == "AI_PAGE_CONTENT_REQUIRED"
    else:
        raise AssertionError("创建页面时 page_content 为空应拒绝。")

    missing_project_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=PROJECT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
        project_id=None,
    )
    try:
        await create_tool.entrypoint(
            missing_project_context,
            title="缺项目页面",
            page_content="<template><div>draft</div></template>",
        )
    except AppException as exc:
        assert exc.code == "AI_TOOL_SCOPE_REQUIRED"
    else:
        raise AssertionError("缺少 project_id 时应拒绝创建项目页面。")

    update_tool = _find_tool(tools, "update_page_metadata")
    try:
        await update_tool.entrypoint(valid_context, page_id=other_page_id, title="越权更新")
    except AppException as exc:
        assert exc.code == "AI_PAGE_SCOPE_DENIED"
    else:
        raise AssertionError("跨项目页面元数据修改应拒绝。")

async def test_component_manager_runtime_kit_tools_should_query_agent_capabilities(authenticated_client: AsyncClient) -> None:
    """组件管理 Runtime Kit 工具应只读查询开放给 Agent 的能力目录。"""

    workspace_id = await _create_workspace(authenticated_client, "Runtime Kit 工具工作空间")
    tools = build_component_manager_tools(get_session_factory())
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )

    list_tool = _find_tool(tools, "list_runtime_kit_capabilities")
    listed = await list_tool.entrypoint(run_context, keyword="page", limit=100)
    names = {item["name"] for item in listed["items"]}
    assert "usePageSize.v1" in names
    assert all(item["import_path"].startswith("@runtime-kit/") for item in listed["items"])
    assert all("/internal/" not in item["import_path"] for item in listed["items"])

    component_listed = await list_tool.entrypoint(run_context, kind="component", keyword="Icon")
    component_names = {item["name"] for item in component_listed["items"]}
    assert "Icon.v1" in component_names

    font_listed = await list_tool.entrypoint(run_context, keyword="font", limit=100)
    font_capability_names = {item["name"] for item in font_listed["items"]}
    assert "useAssetFontFamily.v1" in font_capability_names
    assert "resolveAssetFontFamily.v1" in font_capability_names

    detail_tool = _find_tool(tools, "get_runtime_kit_capability")
    icon_detail = await detail_tool.entrypoint(run_context, name="Icon.v1", kind="component")
    assert icon_detail["import_path"] == "@runtime-kit/public/components/primitives/Icon.v1.vue"
    assert len(icon_detail["usage"]) >= 1
    assert len(icon_detail["constraints"]) >= 1

    asset_drawio_detail = await detail_tool.entrypoint(run_context, name="AssetDrawio.v1", kind="component")
    asset_drawio_props = asset_drawio_detail["preview_schema"]["props"]
    assert "content" in asset_drawio_props
    assert "fallback" not in asset_drawio_props
    assert "fallback" not in json.dumps(asset_drawio_detail, ensure_ascii=False)
    assert "name 与 content 二选一" in "\n".join(asset_drawio_detail["constraints"])

    asset_video_detail = await detail_tool.entrypoint(run_context, name="AssetVideo.v1", kind="component")
    asset_video_props = asset_video_detail["preview_schema"]["props"]
    assert "fallback" not in asset_video_props
    assert "posterFallback" not in asset_video_props
    assert "fallback" not in json.dumps(asset_video_detail, ensure_ascii=False)

    util_detail = await detail_tool.entrypoint(run_context, name="resolveResourcePath.v1")
    assert util_detail["kind"] == "util"
    assert util_detail["import_path"] == "@runtime-kit/public/utils/assets.v1"
    assert "/internal/" not in util_detail["import_path"]

    theme_detail = await detail_tool.entrypoint(run_context, name="useTheme.v1")
    assert theme_detail["kind"] == "composable"
    assert theme_detail["import_path"] == "@runtime-kit/public/composables/theme/useTheme.v1"

async def test_get_component_detail_tool_should_render_source(
    authenticated_client: AsyncClient,
) -> None:
    """组件详情工具应返回原始源码和草稿锁字段。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 组件详情工具工作空间")
    component_content = "<template>\n  <article>detail</article>\n</template>\n"
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "详情测试组件",
            "import_name": "DetailTestComponent",
            "content": component_content,
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    detail_tool = _find_tool(build_component_manager_tools(get_session_factory()), "get_component_detail")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_READ_SCOPES,
        workspace_id=workspace_id,
    )

    result = await detail_tool.entrypoint(run_context, component_id=component_id)

    assert "组件名称：详情测试组件" in result.content
    assert "源码引用名：DetailTestComponent" in result.content
    assert "draft_hash（草稿内容指纹）：" in result.content
    assert "base_published_version_no（草稿基线版本号）：0" in result.content
    assert "源码：" in result.content
    assert "行号版源码：" not in result.content
    assert "0001 |" not in result.content
    assert component_content in result.content

async def test_update_component_metadata_tool_should_not_require_import_name(
    authenticated_client: AsyncClient,
) -> None:
    """组件元数据工具未改引用名时应允许省略 import_name。"""

    workspace_id = await _create_workspace(authenticated_client, "AI 组件元数据工具工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "元数据测试组件",
            "import_name": "MetadataTestComponent",
            "content": "<template><article>metadata</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    metadata_tool = _find_tool(build_component_manager_tools(get_session_factory()), "update_component_metadata")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    result = await metadata_tool.entrypoint(
        run_context,
        component_id=component_id,
        summary="更新后的组件说明",
    )

    assert result["success"] is True
    assert result["component"]["import_name"] == "MetadataTestComponent"
    assert result["component"]["summary"] == "更新后的组件说明"

async def test_apply_component_edits_should_reject_stale_draft_hash(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """组件草稿内容变化后，旧 draft_hash 不应继续写入。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 组件草稿指纹工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "草稿指纹组件",
            "import_name": "DraftHashComponent",
            "content": "<template><article>v1</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    publish_response = await authenticated_client.post(f"/api/components/{component_id}/publish", json={})
    assert publish_response.status_code == 200
    stale_hash = calculate_source_hash(publish_response.json()["content"])
    update_response = await authenticated_client.patch(
        f"/api/components/{component_id}",
        json={"content": "<template><article>draft changed</article></template>"},
    )
    assert update_response.status_code == 200
    apply_tool = _find_tool(build_component_manager_tools(get_session_factory()), "apply_component_edits")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    try:
        await apply_tool.entrypoint(
            run_context,
            component_id=component_id,
            edits=[{"type": "replace_exact", "old_text": "draft changed", "new_text": "after"}],
            base_draft_hash=stale_hash,
            base_published_version_no=1,
        )
    except AppException as exc:
        assert exc.code == "AI_COMPONENT_DRAFT_STALE"
        assert "组件草稿已变化" in exc.detail
    else:
        raise AssertionError("旧 draft_hash 应被拒绝。")
    assert runtime_calls == []

async def test_apply_component_edits_should_reject_stale_draft_base_after_restore(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """组件草稿从历史版本恢复后，旧草稿基线版本号不应继续写入。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 组件草稿基线工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "草稿基线组件",
            "import_name": "DraftBaseComponent",
            "content": "<template><article>v1</article></template>",
            "preview_schema": CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA,
            "file_type": "vue",
            "status": "active",
        },
    )
    assert create_response.status_code == 200
    component_id = create_response.json()["id"]
    assert (await authenticated_client.post(f"/api/components/{component_id}/publish", json={})).status_code == 200
    assert (
        await authenticated_client.patch(
            f"/api/components/{component_id}",
            json={"content": "<template><article>v2</article></template>"},
        )
    ).status_code == 200
    publish_v2_response = await authenticated_client.post(f"/api/components/{component_id}/publish", json={})
    assert publish_v2_response.status_code == 200
    restore_response = await authenticated_client.post(f"/api/components/{component_id}/versions/1/restore-to-draft", json={})
    assert restore_response.status_code == 200
    restored = restore_response.json()
    apply_tool = _find_tool(build_component_manager_tools(get_session_factory()), "apply_component_edits")
    run_context = await _build_tool_run_context(
        current=_build_auth_context(),
        tool_scopes=COMPONENT_TOOL_WRITE_SCOPES,
        workspace_id=workspace_id,
    )

    try:
        await apply_tool.entrypoint(
            run_context,
            component_id=component_id,
            edits=[{"type": "replace_exact", "old_text": "v1", "new_text": "after"}],
            base_draft_hash=calculate_source_hash(restored["content"]),
            base_published_version_no=publish_v2_response.json()["draft_base_version_no"],
        )
    except AppException as exc:
        assert exc.code == "AI_COMPONENT_DRAFT_BASE_STALE"
        assert "组件草稿基线已变化" in exc.detail
    else:
        raise AssertionError("旧 base_published_version_no 应被拒绝。")
    assert runtime_calls == []

async def test_apply_component_edits_should_allow_new_unpublished_component(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """新建未发布组件应使用 draft_base_version_no=0 和 draft_hash 正常写入草稿。"""

    runtime_calls = _patch_runtime_diagnostics(monkeypatch)
    workspace_id = await _create_workspace(authenticated_client, "AI 未发布组件 Edits 工作空间")
    create_response = await authenticated_client.post(
        "/api/components",
        json={
            "workspace_id": workspace_id,
            "name": "未发布组件",
            "import_name": "UnpublishedComponent",
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

    assert result["success"] is True
    assert result["version_no"] == 0
    assert result["component"]["draft_base_version_no"] == 0
    assert result["component"]["has_unpublished_changes"] is True
    assert "updated" in result["component"]["content"]
    assert runtime_calls
