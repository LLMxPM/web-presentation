"""文件功能：验证统一视觉工具对附件和页面截图的输入解析与可信元数据组装。"""

from types import SimpleNamespace

import pytest

from app.ai.platform_tools import AgentToolContext
from app.ai.tools.visual.analyze_visuals import build_analyze_visuals_tool, _resolve_asset_image_content_type
from app.core.exceptions import AppException


@pytest.mark.asyncio
async def test_analyze_visuals_combines_attachment_asset_and_page_screenshot(monkeypatch) -> None:
    """统一工具应保持三种图片来源的输入顺序，并只把像素交给图片理解服务。"""

    attachment = SimpleNamespace(
        id=7,
        original_name="reference.png",
        content_type="image/png",
        storage_key="attachments/reference.png",
        width=800,
        height=600,
        source_kind="user_upload",
        tool_name=None,
        sha256="reference-sha",
    )
    screenshot_attachment = SimpleNamespace(
        id=9,
        original_name="page_demo.png",
        content_type="image/png",
        width=1920,
        height=1080,
        source_kind="tool_output",
        tool_name="analyze_visuals",
        sha256="screenshot-sha",
    )
    asset_attachment = SimpleNamespace(
        id=10,
        original_name="workspace.png",
        content_type="image/png",
        width=1200,
        height=800,
        source_kind="tool_output",
        tool_name="analyze_visuals",
        sha256="asset-sha",
    )
    asset = SimpleNamespace(
        id=8,
        name="workspace_hero",
        original_name="workspace.png",
        content_type="image/png",
        file_name="asset-storage.png",
        file_size=11,
        asset_type="image",
        status="active",
        source_asset_id=None,
        history_kind=None,
    )
    screenshot = SimpleNamespace(
        content=b"page-image",
        refreshed=True,
        page=SimpleNamespace(id=3, code="page_demo", title="演示页", screenshot_version_no=5),
    )
    captured: dict[str, object] = {}

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, traceback):  # noqa: ANN001
            return False

    class FakeAttachmentService:
        def __init__(self, session, *, user_id):  # noqa: ANN001
            self.object_storage_service = SimpleNamespace(read_object=self.read_object)
            self.settings = SimpleNamespace(ai_image_attachment_max_bytes=10 * 1024 * 1024)

        async def validate_attachments_for_run(self, **kwargs):  # noqa: ANN003
            assert kwargs["attachment_ids"] == [7]
            return [attachment]

        async def read_object(self, storage_key: str) -> bytes:
            assert storage_key == "attachments/reference.png"
            return b"attachment-image"

        async def register_tool_image(self, **kwargs):  # noqa: ANN003
            assert kwargs["tool_name"] == "analyze_visuals"
            if kwargs["original_name"] == "workspace.png":
                assert kwargs["content"] == b"asset-image"
                return asset_attachment
            assert kwargs["content"] == b"page-image"
            return screenshot_attachment

    class FakeAssetService:
        def __init__(self, session):  # noqa: ANN001
            self.driver = SimpleNamespace(read_content=self.read_content)

        async def _get_asset_or_raise(self, workspace_id: int, asset_id: int):
            assert (workspace_id, asset_id) == (2, 8)
            return asset

        async def read_content(self, workspace_id: int, file_name: str) -> bytes:
            assert (workspace_id, file_name) == (2, "asset-storage.png")
            return b"asset-image"

    class FakeScreenshotService:
        def __init__(self, session):  # noqa: ANN001
            pass

        async def ensure_latest_page_screenshot_via_queue(self, **kwargs):  # noqa: ANN003
            assert kwargs["page_id"] == 3
            return screenshot

    class FakeUnderstandingService:
        def __init__(self, session, *, user_id):  # noqa: ANN001
            assert user_id == 1

        async def analyze(self, **kwargs):  # noqa: ANN003
            captured.update(kwargs)
            return {"summary": "已分析", "items": []}

    async def fake_resolve_tool_context(*args, **kwargs):  # noqa: ANN002, ANN003
        return (
            {
                "workspace_id": 2,
                "project_id": 4,
                "current_tool_name": "analyze_visuals",
                "current_tool_call_id": "call-1",
            },
            {"sub": "user:1"},
        )

    monkeypatch.setattr("app.ai.tools.visual.analyze_visuals.resolve_tool_context", fake_resolve_tool_context)
    monkeypatch.setattr("app.ai.tools.visual.analyze_visuals.AgentImageAttachmentService", FakeAttachmentService)
    monkeypatch.setattr("app.ai.tools.visual.analyze_visuals.AssetService", FakeAssetService)
    monkeypatch.setattr("app.ai.tools.visual.analyze_visuals.PageScreenshotJobService", FakeScreenshotService)
    monkeypatch.setattr("app.ai.tools.visual.analyze_visuals.ImageUnderstandingService", FakeUnderstandingService)

    tool = build_analyze_visuals_tool(lambda: FakeSessionContext())
    result = await tool.entrypoint(
        AgentToolContext(
            run_id="run-1",
            session_id="session-1",
            dependencies={"allowed_visual_input_types": ["attachment", "asset", "page_screenshot"]},
        ),
        inputs=[
            {"source_type": "attachment", "attachment_id": 7},
            {"source_type": "asset", "asset_id": 8},
            {"source_type": "page_screenshot", "page_id": 3},
        ],
        instruction="比较参考图与页面",
        analysis_type="comparison",
    )

    assert result["summary"] == "已分析"
    analysis_inputs = captured["inputs"]
    assert [item.source["source_type"] for item in analysis_inputs] == ["attachment", "asset", "page_screenshot"]
    assert analysis_inputs[0].content == b"attachment-image"
    assert analysis_inputs[1].source["asset_id"] == 8
    assert analysis_inputs[1].content == b"asset-image"
    assert analysis_inputs[2].source["page_version_no"] == 5
    assert analysis_inputs[2].source["screenshot_refreshed"] is True


@pytest.mark.asyncio
async def test_resource_analyze_visuals_rejects_page_screenshot_before_access() -> None:
    """资源助手即使绕过模型 Schema，也不能请求页面截图。"""

    tool = build_analyze_visuals_tool(lambda: None)  # type: ignore[arg-type]
    with pytest.raises(AppException) as exc_info:
        await tool.entrypoint(
            AgentToolContext(
                run_id="run-1",
                session_id="session-1",
                dependencies={"allowed_visual_input_types": ["attachment", "asset"]},
            ),
            inputs=[{"source_type": "page_screenshot", "page_id": 3}],
            instruction="识别页面",
        )

    assert exc_info.value.code == "AI_VISUAL_INPUT_SOURCE_DENIED"


def test_analyze_visuals_schema_uses_discriminated_inputs() -> None:
    """工具参数 schema 应通过 source_type 约束两种统一输入。"""

    tool = build_analyze_visuals_tool(lambda: None)  # type: ignore[arg-type,return-value]
    inputs_schema = tool.parameters["properties"]["inputs"]

    assert inputs_schema["minItems"] == 1
    assert inputs_schema["maxItems"] == 4
    assert inputs_schema["items"]["discriminator"]["propertyName"] == "source_type"
    assert "asset" in inputs_schema["items"]["discriminator"]["mapping"]


def test_asset_visual_input_rejects_unsupported_image_format() -> None:
    """资源输入应在读取模型前拒绝当前视觉附件链路不支持的格式。"""

    with pytest.raises(AppException) as exc_info:
        _resolve_asset_image_content_type("diagram.svg", "image/svg+xml")

    assert exc_info.value.code == "AI_VISUAL_ASSET_FORMAT_UNSUPPORTED"
