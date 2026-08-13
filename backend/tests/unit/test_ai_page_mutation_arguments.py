"""文件功能：验证页面持久化任务兼容直接工具与通用工具的参数结构。"""

from __future__ import annotations

import pytest

from app.ai.page_mutation_arguments import (
    normalize_page_mutation_arguments,
    normalize_page_mutation_result,
)
from app.core.exceptions import AppException


def test_create_entity_page_arguments_should_unwrap_payload() -> None:
    """通用页面创建调用应解包 payload，并保留页面源码和可选元数据。"""

    arguments = normalize_page_mutation_arguments(
        operation="create_page",
        tool_name="create_entity",
        raw_arguments={
            "resource_type": "page",
            "mode": "new",
            "payload": {
                "project_id": 52,
                "title": "Tool Evaluation & Benchmarking",
                "content": "<template><main /></template>",
                "summary": "选型对比",
            },
        },
        project_id=52,
        page_id=None,
        base_version_no=None,
    )

    assert arguments["title"] == "Tool Evaluation & Benchmarking"
    assert arguments["page_content"] == "<template><main /></template>"
    assert arguments["summary"] == "选型对比"


def test_create_entity_page_arguments_should_decode_json_payload() -> None:
    """持久化的通用页面创建参数即使把 payload 编码为 JSON 字符串也应正常执行。"""

    arguments = normalize_page_mutation_arguments(
        operation="create_page",
        tool_name="create_entity",
        raw_arguments={
            "resource_type": "page",
            "mode": "new",
            "payload": (
                '{"project_id": 52, "title": "封面", '
                '"content": "<template><main /></template>", '
                '"speaker_notes": "{\\"keep\\": \\"text\\"}"}'
            ),
        },
        project_id=52,
        page_id=None,
        base_version_no=None,
    )

    assert arguments["title"] == "封面"
    assert arguments["page_content"] == "<template><main /></template>"
    assert arguments["speaker_notes"] == '{"keep": "text"}'


def test_update_entity_page_arguments_should_decode_repeated_json_payload() -> None:
    """页面更新任务应兼容有限层数内被重复 JSON 编码的 payload。"""

    arguments = normalize_page_mutation_arguments(
        operation="apply_page_edits",
        tool_name="update_entity",
        raw_arguments={
            "resource_type": "page",
            "target_id": 81,
            "action": "content",
            "payload": '"{\\"edits\\":[{\\"old\\":\\"旧\\",\\"new\\":\\"新\\"}],\\"base_version_no\\":3}"',
        },
        project_id=52,
        page_id=81,
        base_version_no=3,
    )

    assert arguments == {
        "edits": [{"old": "旧", "new": "新"}],
        "base_version_no": 3,
    }


def test_update_entity_page_arguments_should_unwrap_content_payload() -> None:
    """通用页面内容修改调用应解包 edits，并校验外层 target_id。"""

    edits = [{"old": "旧内容", "new": "新内容"}]
    arguments = normalize_page_mutation_arguments(
        operation="apply_page_edits",
        tool_name="update_entity",
        raw_arguments={
            "resource_type": "page",
            "target_id": 81,
            "action": "content",
            "payload": {"edits": edits, "base_version_no": 3, "change_note": "更新内容"},
        },
        project_id=52,
        page_id=81,
        base_version_no=3,
    )

    assert arguments == {"edits": edits, "base_version_no": 3, "change_note": "更新内容"}


def test_direct_page_tool_arguments_should_remain_compatible() -> None:
    """历史直接页面工具任务仍按原有扁平参数执行。"""

    arguments = normalize_page_mutation_arguments(
        operation="create_page",
        tool_name="create_project_page",
        raw_arguments={"title": "封面", "page_content": "<template />"},
        project_id=52,
        page_id=None,
        base_version_no=None,
    )

    assert arguments == {"title": "封面", "page_content": "<template />"}


def test_generic_deferred_result_should_keep_mutation_envelope() -> None:
    """通用页面工具续跑结果应与同步通用工具的 mutation envelope 一致。"""

    created = normalize_page_mutation_result(
        operation="create_page",
        tool_name="create_entity",
        result={"success": True, "message": "页面已创建。", "page_id": 91},
        page_id=None,
    )
    updated = normalize_page_mutation_result(
        operation="apply_page_edits",
        tool_name="update_entity",
        result={"success": True, "message": "页面代码已更新并生成新版本。", "page_id": 91},
        page_id=91,
    )

    assert created["operation"] == "create"
    assert created["effect"] == "create"
    assert created["target"] == {"id": 91, "resource_type": "page"}
    assert created["mutation"]["kind"] == "project-pages"
    assert created["data"]["page_id"] == 91
    assert updated["operation"] == "update"
    assert updated["action"] == "content"
    assert updated["target"] == {"id": 91, "resource_type": "page"}


def test_recoverable_deferred_result_should_not_be_wrapped() -> None:
    """校验失败结果应原样返回，避免被成功 mutation envelope 覆盖。"""

    result = {"success": False, "code": "PAGE_CODE_INVALID"}

    assert normalize_page_mutation_result(
        operation="create_page",
        tool_name="create_entity",
        result=result,
        page_id=None,
    ) is result


@pytest.mark.parametrize(
    ("tool_name", "raw_arguments"),
    [
        ("create_entity", {"resource_type": "component", "mode": "new", "payload": {}}),
        ("create_entity", {"resource_type": "page", "mode": "new", "payload": "[]"}),
        ("create_entity", {"resource_type": "page", "mode": "new", "payload": "not-json"}),
        (
            "update_entity",
            {"resource_type": "page", "target_id": 81, "action": "metadata", "payload": {}},
        ),
        (
            "update_entity",
            {"resource_type": "page", "target_id": 82, "action": "content", "payload": {"edits": []}},
        ),
    ],
)
def test_generic_page_arguments_should_reject_contract_mismatch(
    tool_name: str,
    raw_arguments: dict[str, object],
) -> None:
    """资源类型、payload、action 或目标不一致时必须终止任务。"""

    operation = "create_page" if tool_name == "create_entity" else "apply_page_edits"
    with pytest.raises(AppException) as error:
        normalize_page_mutation_arguments(
            operation=operation,
            tool_name=tool_name,
            raw_arguments=raw_arguments,
            project_id=52,
            page_id=81,
            base_version_no=3,
        )

    assert error.value.code == "AI_PAGE_MUTATION_ARGUMENTS_INVALID"
