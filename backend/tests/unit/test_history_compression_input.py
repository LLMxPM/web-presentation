"""文件功能：验证工具交互结构化压缩输入的配对、分区和确定性裁剪。"""

from __future__ import annotations

from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart, UserPromptPart

from app.ai.history_compression_input import (
    _normalize_message_items,
    build_local_compression_input,
    render_deterministic_compression_text,
)


def test_build_local_compression_input_should_fold_tool_call_and_return() -> None:
    """工具调用与返回应折叠为一个交互项，而不是保留协议碎片。"""

    result = build_local_compression_input(
        [
            ModelRequest(
                parts=[UserPromptPart(content="读取页面")],
                metadata={"run_id": "run-1", "workspace_id": 10, "project_id": 20, "page_id": 30},
            ),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_page",
                        args={"page_id": 30},
                        tool_call_id="call-1",
                    )
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="get_page",
                        content={"page_id": 30, "summary": "页面摘要"},
                        tool_call_id="call-1",
                    )
                ]
            ),
        ]
    )

    interactions = [item for item in result.payload["items"] if item["kind"] == "tool_interaction"]
    assert len(interactions) == 1
    assert interactions[0]["tool_name"] == "get_page"
    assert interactions[0]["tool_call_id"] == "call-1"
    assert interactions[0]["status"] == "returned"
    assert interactions[0]["important_ids"]["page_id"] == 30
    assert all(item["kind"] not in {"tool-call", "tool-return"} for item in result.payload["items"])


def test_build_local_compression_input_should_keep_unknown_tool_explicit() -> None:
    """没有返回的工具调用不能被压缩器误判为成功。"""

    result = build_local_compression_input(
        [
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="update_page",
                        args={"page_id": 30},
                        tool_call_id="call-unknown",
                    )
                ]
            )
        ]
    )

    interaction = next(item for item in result.payload["items"] if item["kind"] == "tool_interaction")
    assert interaction["status"] == "unknown"
    assert interaction["must_verify"] is True
    assert result.stats.unknown_tool_count == 1


def test_normalize_message_items_should_use_tool_ledger_as_authority() -> None:
    """工具返回缺失时，已完成账本仍应恢复结果，但运行中状态必须保持未知。"""

    items = _normalize_message_items(
        [
            {
                "kind": "response",
                "metadata": {"run_id": "run-ledger"},
                "parts": [
                    {
                        "part_kind": "tool-call",
                        "tool_name": "update_page",
                        "tool_call_id": "call-ledger",
                        "args": {"page_id": 30},
                    }
                ],
            }
        ],
        run_contexts={},
        ledger_rows=[
            {
                "id": 1,
                "run_id": "run-ledger",
                "tool_call_id": "call-ledger",
                "tool_name": "update_page",
                "status": "completed",
                "input_payload": {"page_id": 30},
                "output_payload": {"page_id": 30, "status": "updated"},
                "message": None,
            }
        ],
        compaction_level=3,
    )

    interaction = next(item for item in items if item["kind"] == "tool_interaction")
    assert interaction["status"] == "completed"
    assert interaction["result"]["status"] == "updated"
    assert interaction["important_ids"]["page_id"] == 30


def test_build_local_compression_input_should_remove_existing_summary_message() -> None:
    """已有平台摘要只应通过 previous_summary 传入，不能在历史输入中重复出现。"""

    result = build_local_compression_input(
        [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content=(
                            "<application_context>\n"
                            "以下为较早智能体会话历史摘要，已替代压缩边界之前的原始消息：\n"
                            "旧摘要\n</application_context>"
                        )
                    )
                ]
            ),
            ModelRequest(parts=[UserPromptPart(content="新目标")]),
        ]
    )

    contents = [item.get("content") for item in result.payload["items"]]
    assert "旧摘要" not in contents
    assert "新目标" in contents


def test_render_deterministic_compression_text_should_not_depend_on_json_boundaries() -> None:
    """确定性 fallback 应输出可安全截断的事实文本，而不是 JSON 碎片。"""

    result = build_local_compression_input(
        [ModelRequest(parts=[UserPromptPart(content="用户目标"), UserPromptPart(content="更多约束")])]
    )
    rendered = render_deterministic_compression_text(result, previous_summary="", target_tokens=100)

    assert "结构化历史事实：" in rendered
    assert "用户目标" in rendered
    assert "{" not in rendered or "Run" in rendered
