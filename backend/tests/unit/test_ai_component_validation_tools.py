"""文件功能：验证 AI 组件创建、schema 修改和独立检查统一接入组件校验服务。"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.ai.agent import AGENT_COORDINATOR_AGENT_ID
from app.ai.auth_tokens import (
    CODE_CHECK_TOOL_SCOPES,
    COMPONENT_TOOL_READ_SCOPES,
    COMPONENT_TOOL_WRITE_SCOPES,
    build_agent_tool_token,
)
from app.ai.platform_tools import AgentToolContext
from app.ai.tools import code_check as code_check_tools
from app.ai.tools.code_check import build_check_component_code_tool
from app.ai.tools.component import component_library as component_library_tools
from app.ai.tools.component.component_library import (
    build_apply_component_edits_tool,
    build_create_component_tool,
    build_publish_component_tool,
    build_update_component_metadata_tool,
)
from app.ai.tools.shared import calculate_source_hash
from app.db.session import get_session_factory
from app.models.enums import PageFileType, RecordStatus, UserRole, WorkspaceComponentType
from app.models.user import User
from app.schemas.component import WorkspaceComponentItem
from app.services.auth_service import AuthContext
from app.services.code_check_service import CodeCheckService
from app.services.workspace_component_service import WorkspaceComponentService

PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","default":320}}}'


class _TransactionProbeSession:
    """记录CodeCheck进入慢Runtime诊断前是否主动结束数据库事务。"""

    def __init__(self) -> None:
        self.commit_count = 0

    def in_transaction(self) -> bool:
        return True

    async def commit(self) -> None:
        self.commit_count += 1


async def test_component_code_check_should_release_transaction_before_slow_diagnostics() -> None:
    """组件Worker可复用Session对象，但不得跨Runtime/Chromium等待持有数据库事务。"""

    session = _TransactionProbeSession()
    service = CodeCheckService(session)  # type: ignore[arg-type]

    await service._release_session_before_diagnostics()

    assert session.commit_count == 1


def _build_context(scopes: tuple[str, ...]) -> AgentToolContext:
    """构造包含指定工具权限的工作空间级运行上下文。"""

    current = AuthContext(
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
    run_id = "component-validation-run"
    session_id = "component-validation-session"
    dependencies = {
        "user_id": 1,
        "agent_id": AGENT_COORDINATOR_AGENT_ID,
        "run_id": run_id,
        "session_id": session_id,
        "workspace_id": 7,
        "project_id": None,
        "page_id": None,
        "component_id": None,
        "source": "test",
        "backend_session_id": "1",
    }
    dependencies["tool_auth_token"] = build_agent_tool_token(
        current,
        run_id=run_id,
        session_id=session_id,
        agent_id=AGENT_COORDINATOR_AGENT_ID,
        workspace_id=7,
        project_id=None,
        page_id=None,
        component_id=None,
        source="test",
        scopes=scopes,
    )
    return AgentToolContext(
        run_id=run_id,
        session_id=session_id,
        user_id="1",
        dependencies=dependencies,
    )


def _failed_validation() -> dict[str, object]:
    """返回确定性的候选渲染失败结果。"""

    return {
        "success": False,
        "valid": False,
        "status": "failed",
        "retryable": False,
        "diagnostics": [{
            "severity": "error",
            "code": "COMPONENT_RENDER_EMPTY",
            "message": "组件没有可见内容。",
        }],
    }


def _patch_resolved_tool_context(monkeypatch, module: object) -> None:
    """绕过与当前单元目标无关的 run 取消状态数据库查询。"""

    async def fake_resolve_tool_context(*args: object, **kwargs: object):
        return {"workspace_id": 7}, {"sub": "user:1"}

    monkeypatch.setattr(module, "resolve_tool_context", fake_resolve_tool_context)


async def test_create_component_should_validate_before_writing(monkeypatch) -> None:
    """新建组件校验失败时不得调用组件创建服务。"""

    calls = {"check": 0, "create": 0}

    async def fake_check(self, **kwargs):
        calls["check"] += 1
        assert kwargs["component_type"] == WorkspaceComponentType.CONTENT_COMPONENT
        assert kwargs["preview_schema"] == PREVIEW_SCHEMA
        return _failed_validation()

    async def fake_create(self, payload, operator_id):
        calls["create"] += 1
        raise AssertionError("校验失败后不应创建组件")

    monkeypatch.setattr(CodeCheckService, "check_component_code", fake_check)
    monkeypatch.setattr(WorkspaceComponentService, "create", fake_create)
    _patch_resolved_tool_context(monkeypatch, component_library_tools)
    tool = build_create_component_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_context(COMPONENT_TOOL_WRITE_SCOPES),
        name="失败组件",
        import_name="InvalidCard",
        content="<template><div /></template>",
        component_type=WorkspaceComponentType.CONTENT_COMPONENT,
        preview_schema=PREVIEW_SCHEMA,
    )

    assert result["applied"] is False
    assert result["validation"]["status"] == "failed"
    assert calls == {"check": 1, "create": 0}


async def test_preview_schema_update_should_validate_before_writing(monkeypatch) -> None:
    """preview_schema 候选校验失败时不得调用组件更新服务。"""

    calls = {"check": 0, "update": 0}
    component = SimpleNamespace(
        id=42,
        workspace_id=7,
        code="CMP000042",
        content="<template><div /></template>",
        preview_schema=PREVIEW_SCHEMA,
        component_type=WorkspaceComponentType.CONTENT_COMPONENT,
    )

    async def fake_get(self, component_id):
        return component

    async def fake_check(self, **kwargs):
        calls["check"] += 1
        assert kwargs["component_id"] == 42
        assert kwargs["preview_schema"] != PREVIEW_SCHEMA
        return _failed_validation()

    async def fake_update(self, component_id, payload, operator_id):
        calls["update"] += 1
        raise AssertionError("校验失败后不应更新组件")

    monkeypatch.setattr(WorkspaceComponentService, "get", fake_get)
    monkeypatch.setattr(CodeCheckService, "check_component_code", fake_check)
    monkeypatch.setattr(WorkspaceComponentService, "update", fake_update)
    _patch_resolved_tool_context(monkeypatch, component_library_tools)
    tool = build_update_component_metadata_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_context(COMPONENT_TOOL_WRITE_SCOPES),
        component_id=42,
        preview_schema={"props": {"height": {"type": "number", "default": 0}}},
    )

    assert result["applied"] is False
    assert result["validation"]["status"] == "failed"
    assert calls == {"check": 1, "update": 0}


def _passed_validation() -> dict[str, object]:
    """返回确定性的校验通过结果。"""

    return {"success": True, "valid": True, "status": "passed", "retryable": False, "diagnostics": []}


def _component_item(
    *,
    content: str = "<template><div>组件源码</div></template>",
    current_version_no: int = 0,
    draft_base_version_no: int = 0,
    has_unpublished_changes: bool = True,
) -> WorkspaceComponentItem:
    """构造组件写工具成功路径测试使用的组件响应模型。"""

    now = datetime(2026, 8, 10, tzinfo=timezone.utc)
    return WorkspaceComponentItem(
        id=81,
        workspace_id=7,
        workspace_name="测试工作空间",
        code="CMP20260810001",
        content=content,
        preview_schema=PREVIEW_SCHEMA,
        current_version_no=current_version_no,
        draft_base_version_no=draft_base_version_no,
        has_unpublished_changes=has_unpublished_changes,
        published_at=None,
        file_type=PageFileType.VUE,
        name="指标卡",
        import_name="MetricCard",
        component_type=WorkspaceComponentType.CONTENT_COMPONENT,
        summary="测试组件摘要",
        status=RecordStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        created_by=1,
        updated_by=1,
    )


def _assert_component_summary_without_echo(summary: dict[str, object], expected: WorkspaceComponentItem) -> None:
    """断言写入结果只包含摘要字段，不回显源码与 preview_schema。"""

    assert summary["id"] == expected.id
    assert summary["code"] == expected.code
    assert summary["draft_hash"] == calculate_source_hash(expected.content)
    assert "content" not in summary
    assert "preview_schema" not in summary


async def test_create_component_result_should_return_summary_without_source_echo(monkeypatch) -> None:
    """创建成功后只返回组件摘要，不回显模型刚提交的源码与 preview_schema。"""

    created_item = _component_item()

    async def fake_check(self, **kwargs):
        return _passed_validation()

    async def fake_create(self, payload, operator_id):
        return created_item

    monkeypatch.setattr(CodeCheckService, "check_component_code", fake_check)
    monkeypatch.setattr(WorkspaceComponentService, "create", fake_create)
    _patch_resolved_tool_context(monkeypatch, component_library_tools)
    tool = build_create_component_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_context(COMPONENT_TOOL_WRITE_SCOPES),
        name="指标卡",
        import_name="MetricCard",
        content=created_item.content,
        component_type=WorkspaceComponentType.CONTENT_COMPONENT,
        preview_schema=PREVIEW_SCHEMA,
    )

    assert result["applied"] is True
    _assert_component_summary_without_echo(result["component"], created_item)


async def test_apply_component_edits_result_should_return_summary_without_source_echo(monkeypatch) -> None:
    """组件源码 edits 成功后只返回摘要和编辑元数据，不回显完整源码。"""

    base_content = "<template><div>旧文案</div></template>"
    base_component = _component_item(content=base_content, draft_base_version_no=3)
    updated_item = _component_item(
        content="<template><div>新文案</div></template>",
        draft_base_version_no=3,
    )

    async def fake_get(self, component_id):
        return base_component

    async def fake_check(self, **kwargs):
        return _passed_validation()

    async def fake_update(self, component_id, payload, operator_id):
        return updated_item

    monkeypatch.setattr(WorkspaceComponentService, "get", fake_get)
    monkeypatch.setattr(CodeCheckService, "check_component_code", fake_check)
    monkeypatch.setattr(WorkspaceComponentService, "update", fake_update)
    _patch_resolved_tool_context(monkeypatch, component_library_tools)
    tool = build_apply_component_edits_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_context(COMPONENT_TOOL_WRITE_SCOPES),
        component_id=81,
        edits=[{"type": "replace_exact", "old_text": "旧文案", "new_text": "新文案"}],
        base_draft_hash=calculate_source_hash(base_content),
        base_published_version_no=3,
    )

    assert result["applied"] is True
    assert result["edits_applied"] == 1
    _assert_component_summary_without_echo(result["component"], updated_item)


async def test_update_component_metadata_result_should_return_summary_without_source_echo(monkeypatch) -> None:
    """组件元数据更新成功后只返回摘要，不回显源码与 preview_schema。"""

    base_component = _component_item()
    updated_item = _component_item(has_unpublished_changes=True)

    async def fake_get(self, component_id):
        return base_component

    async def fake_check(self, **kwargs):
        return _passed_validation()

    async def fake_update(self, component_id, payload, operator_id):
        return updated_item

    monkeypatch.setattr(WorkspaceComponentService, "get", fake_get)
    monkeypatch.setattr(CodeCheckService, "check_component_code", fake_check)
    monkeypatch.setattr(WorkspaceComponentService, "update", fake_update)
    _patch_resolved_tool_context(monkeypatch, component_library_tools)
    tool = build_update_component_metadata_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_context(COMPONENT_TOOL_WRITE_SCOPES),
        component_id=81,
        preview_schema={"props": {"height": {"type": "number", "default": 360}}},
    )

    assert result["applied"] is True
    _assert_component_summary_without_echo(result["component"], updated_item)


async def test_publish_component_result_should_return_summary_without_source_echo(monkeypatch) -> None:
    """组件发布成功后只返回摘要和引用用法，不回显源码与 preview_schema。"""

    base_component = _component_item()
    published_item = _component_item(
        current_version_no=1,
        draft_base_version_no=1,
        has_unpublished_changes=False,
    )

    async def fake_get(self, component_id):
        return base_component

    async def fake_publish(self, component_id, payload, operator_id):
        return published_item

    monkeypatch.setattr(WorkspaceComponentService, "get", fake_get)
    monkeypatch.setattr(WorkspaceComponentService, "publish", fake_publish)
    _patch_resolved_tool_context(monkeypatch, component_library_tools)
    tool = build_publish_component_tool(get_session_factory())

    result = await tool.entrypoint(
        _build_context(COMPONENT_TOOL_WRITE_SCOPES),
        component_id=81,
    )

    assert result["success"] is True
    assert result["import_usage"]
    _assert_component_summary_without_echo(result["component"], published_item)


async def test_independent_component_check_should_forward_component_type(monkeypatch) -> None:
    """独立组件 check 应把候选类型传给同一校验内核。"""

    captured: dict[str, object] = {}

    async def fake_check(self, **kwargs):
        captured.update(kwargs)
        return {"success": True, "valid": True, "status": "passed", "diagnostics": []}

    monkeypatch.setattr(CodeCheckService, "check_component_code", fake_check)
    _patch_resolved_tool_context(monkeypatch, code_check_tools)
    tool = build_check_component_code_tool(get_session_factory())
    scopes = tuple(dict.fromkeys((*COMPONENT_TOOL_READ_SCOPES, *CODE_CHECK_TOOL_SCOPES)))

    result = await tool.entrypoint(
        _build_context(scopes),
        content="<template><span>原子</span></template>",
        preview_schema={"props": {}},
        component_type=WorkspaceComponentType.ATOMIC_COMPONENT,
    )

    assert result["status"] == "passed"
    assert captured["component_type"] == WorkspaceComponentType.ATOMIC_COMPONENT
    assert captured["workspace_id"] == 7
