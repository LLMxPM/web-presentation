"""文件功能：定义 E2E mock 普通对话、视觉与页面 external job 场景及注册表。"""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

from app.ai.testing.scenario_protocol import (
    AGENT_MODEL_ROLE,
    MockConversationState,
    MockScenario,
    MockScenarioError,
    ScenarioTransition,
)

SCENARIO_VERSION = "1"

AGENT_MOCK_MODEL_PREFIX = "e2e-mock-agent-"
VISION_MOCK_MODEL_PREFIX = "e2e-mock-vision-"
IMAGE_MOCK_MODEL_PREFIX = "e2e-mock-image-"
E2E_MOCK_MODEL_PREFIXES = (
    AGENT_MOCK_MODEL_PREFIX,
    VISION_MOCK_MODEL_PREFIX,
    IMAGE_MOCK_MODEL_PREFIX,
)

ANALYZE_VISUALS_TOOL = "analyze_visuals"
GENERATE_IMAGE_TOOL = "generate_image"
LIST_ENTITIES_TOOL = "list_entities"
CREATE_ENTITY_TOOL = "create_entity"

HELLO_SCENARIO_INPUT = "你好，我是 E2E mock 普通对话用例，请用一句话自我介绍。"
HELLO_SCENARIO_FINAL_TEXT = "你好，我是内容助手的 E2E mock 响应，用于验证真实会话链路。"

VISUAL_SCENARIO_INPUT = "请先分析这张参考图，然后基于它生成一张配图并保存到资源库。"
VISUAL_SCENARIO_ANALYZE_INSTRUCTION = "请描述这张参考图的主题、颜色和构图。"
VISUAL_SCENARIO_GENERATE_PROMPT = "基于参考图生成一张同风格的 E2E mock 配图。"
VISUAL_SCENARIO_ASSET_PREFIX = "e2e-mock-visual"
PAGE_EXTERNAL_SCENARIO_INPUT = "请在当前项目创建一页 E2E external job 验证页。"
PAGE_EXTERNAL_SCENARIO_TITLE = "E2E External Job Page"
PAGE_EXTERNAL_SCENARIO_FINAL_TEXT = "页面 external job 已完成并恢复父运行。"
PAGE_EXTERNAL_SCENARIO_PROJECT_NAME = "Smoke Project"


def normalize_user_input(text: str) -> str:
    """规范化用户输入：去除全部空白，使匹配不受换行和空格差异影响。"""

    return "".join(str(text or "").split())


def _build_hello_final_response(state: MockConversationState) -> ModelResponse:
    """普通对话终态：直接返回最终文本。"""

    _ = state
    return ModelResponse(parts=[TextPart(HELLO_SCENARIO_FINAL_TEXT)])


def _build_analyze_visuals_response(state: MockConversationState) -> ModelResponse:
    """视觉链路第一步：用真实附件 ID 调用图片理解工具。"""

    if not state.attachment_ids:
        raise MockScenarioError(
            scenario_id=VISUAL_SCENARIO.scenario_id,
            model_role=AGENT_MODEL_ROLE,
            detail="视觉场景要求用户输入携带可信附件引用，但未解析到 attachment_id。",
            observed_tools=state.called_tool_names(),
        )
    args = {
        "inputs": [
            {"source_type": "attachment", "attachment_id": attachment_id}
            for attachment_id in state.attachment_ids
        ],
        "instruction": VISUAL_SCENARIO_ANALYZE_INSTRUCTION,
        "analysis_type": "general",
        "detail": "auto",
    }
    return ModelResponse(
        parts=[ToolCallPart(ANALYZE_VISUALS_TOOL, args, tool_call_id="e2e-mock-call-analyze-visuals")]
    )


def _build_generate_image_response(state: MockConversationState) -> ModelResponse:
    """视觉链路第二步：基于理解结果发起图片生成，进入 deferred 暂停。"""

    args: dict[str, Any] = {
        "operation": "generate",
        "prompt": VISUAL_SCENARIO_GENERATE_PROMPT,
        "reference_attachment_ids": list(state.attachment_ids),
        "aspect_ratio": "auto",
        "resolution_tier": "auto",
        "quality": "auto",
        "count": 1,
        "asset_name_prefix": VISUAL_SCENARIO_ASSET_PREFIX,
        "description": "E2E mock 视觉链路生成的配图。",
        "tags": ["e2e", "mock"],
    }
    return ModelResponse(
        parts=[ToolCallPart(GENERATE_IMAGE_TOOL, args, tool_call_id="e2e-mock-call-generate-image")]
    )


def _build_visual_final_response(state: MockConversationState) -> ModelResponse:
    """视觉链路终态：从真实 deferred result 提取资源名称并给出用户可见结论。"""

    result = state.last_tool_return(GENERATE_IMAGE_TOOL)
    if isinstance(result, dict) and result.get("status") == "completed":
        assets = result.get("assets") or []
        first_asset = assets[0] if assets and isinstance(assets[0], dict) else {}
        asset_name = str(first_asset.get("name") or VISUAL_SCENARIO_ASSET_PREFIX)
        text = f"配图已生成并保存到资源库，资源名称：{asset_name}。"
        return ModelResponse(parts=[TextPart(text)])
    raise MockScenarioError(
        scenario_id=VISUAL_SCENARIO.scenario_id,
        model_role=AGENT_MODEL_ROLE,
        detail="generate_image 回灌结果不是完成状态，视觉场景不支持该终态。",
        observed_tools=state.called_tool_names(),
    )


def _build_list_projects_response(state: MockConversationState) -> ModelResponse:
    """页面链路第一步：按 E2E 当前项目名称筛选，避免并发夹具改变目标项目。"""

    _ = state
    return ModelResponse(
        parts=[ToolCallPart(
            LIST_ENTITIES_TOOL,
            {
                "resource_type": "project",
                "filters": {"keyword": PAGE_EXTERNAL_SCENARIO_PROJECT_NAME},
                "collection": "items",
            },
            tool_call_id="e2e-mock-call-list-projects",
        )]
    )


def _build_create_page_response(state: MockConversationState) -> ModelResponse:
    """从真实项目查询结果提取 ID，并调用重资源页面创建工具进入 external job。"""

    listed = state.last_tool_return(LIST_ENTITIES_TOOL)
    data = listed.get("data") if isinstance(listed, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    first = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else None
    project_id = first.get("id") if first else None
    if not isinstance(project_id, int):
        raise MockScenarioError(
            scenario_id=PAGE_EXTERNAL_SCENARIO.scenario_id,
            model_role=AGENT_MODEL_ROLE,
            detail="页面场景未从 list_entities 结果解析到项目 ID。",
            observed_tools=state.called_tool_names(),
        )
    content = (
        '<template><main class="page"><h1>E2E External Job</h1></main></template>'
        '<style scoped>.page{width:1920px;height:1080px;padding:96px;background:#fff;color:#111}</style>'
    )
    return ModelResponse(
        parts=[ToolCallPart(
            CREATE_ENTITY_TOOL,
            {
                "resource_type": "page",
                "mode": "new",
                "payload": {
                    "project_id": project_id,
                    "title": PAGE_EXTERNAL_SCENARIO_TITLE,
                    "content": content,
                    "summary": "验证父 Run 直接恢复的 E2E 页面。",
                    "route_placement": "none",
                },
            },
            tool_call_id="e2e-mock-call-create-page-external",
        )]
    )


def _build_page_external_final_response(state: MockConversationState) -> ModelResponse:
    """页面任务结果回灌后返回稳定终态文本。"""

    if state.has_tool_return(CREATE_ENTITY_TOOL):
        return ModelResponse(parts=[TextPart(PAGE_EXTERNAL_SCENARIO_FINAL_TEXT)])
    raise MockScenarioError(
        scenario_id=PAGE_EXTERNAL_SCENARIO.scenario_id,
        model_role=AGENT_MODEL_ROLE,
        detail="create_entity 外部任务结果尚未回灌。",
        observed_tools=state.called_tool_names(),
    )


HELLO_SCENARIO = MockScenario(
    scenario_id="e2e-agent-hello",
    model_role=AGENT_MODEL_ROLE,
    initial_inputs=(HELLO_SCENARIO_INPUT,),
    final_expectation=HELLO_SCENARIO_FINAL_TEXT,
    transitions=(
        ScenarioTransition(
            name="final_text",
            match=lambda state: not state.tool_calls,
            build_response=_build_hello_final_response,
        ),
    ),
)

VISUAL_SCENARIO = MockScenario(
    scenario_id="e2e-agent-visual-link",
    model_role=AGENT_MODEL_ROLE,
    initial_inputs=(VISUAL_SCENARIO_INPUT,),
    final_expectation="配图已生成并保存到资源库",
    transitions=(
        ScenarioTransition(
            name="call_analyze_visuals",
            match=lambda state: not state.tool_calls,
            build_response=_build_analyze_visuals_response,
        ),
        ScenarioTransition(
            name="call_generate_image",
            match=lambda state: state.has_tool_return(ANALYZE_VISUALS_TOOL)
            and not state.has_called(GENERATE_IMAGE_TOOL),
            build_response=_build_generate_image_response,
        ),
        ScenarioTransition(
            name="final_text",
            match=lambda state: state.has_tool_return(GENERATE_IMAGE_TOOL),
            build_response=_build_visual_final_response,
        ),
    ),
)

PAGE_EXTERNAL_SCENARIO = MockScenario(
    scenario_id="e2e-agent-page-external",
    model_role=AGENT_MODEL_ROLE,
    initial_inputs=(PAGE_EXTERNAL_SCENARIO_INPUT,),
    final_expectation=PAGE_EXTERNAL_SCENARIO_FINAL_TEXT,
    transitions=(
        ScenarioTransition(
            name="list_projects",
            match=lambda state: not state.tool_calls,
            build_response=_build_list_projects_response,
        ),
        ScenarioTransition(
            name="create_page_external",
            match=lambda state: state.has_tool_return(LIST_ENTITIES_TOOL)
            and not state.has_called(CREATE_ENTITY_TOOL),
            build_response=_build_create_page_response,
        ),
        ScenarioTransition(
            name="final_text",
            match=lambda state: state.has_tool_return(CREATE_ENTITY_TOOL),
            build_response=_build_page_external_final_response,
        ),
    ),
)

AGENT_SCENARIOS: tuple[MockScenario, ...] = (HELLO_SCENARIO, VISUAL_SCENARIO, PAGE_EXTERNAL_SCENARIO)


def select_agent_scenario(normalized_input: str) -> MockScenario:
    """按规范化初始用户输入选择内容助手场景；未知输入立即报错，不回退真实模型。"""

    for scenario in AGENT_SCENARIOS:
        for candidate in scenario.initial_inputs:
            if normalize_user_input(candidate) and normalize_user_input(candidate) in normalized_input:
                return scenario
    raise MockScenarioError(
        scenario_id="<unmatched>",
        model_role=AGENT_MODEL_ROLE,
        detail="没有匹配任何已知 E2E mock 场景的初始用户输入。",
    )
