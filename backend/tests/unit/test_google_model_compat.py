"""文件功能：验证 Google Gemini function response 的 JSON Schema 引用兼容处理。"""

from __future__ import annotations

import json

import pytest
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.providers.google import GoogleProvider

from app.ai.google_model_compat import GoogleCompatibleModel, inline_google_local_schema_refs
from app.ai.tool_specs import get_operation_guide_spec


def test_google_response_schema_refs_should_be_inlined() -> None:
    """页面源码编辑手册中的 ReplaceExactEdit 引用应被展开且不再携带 $defs。"""

    guide = get_operation_guide_spec("page.update.content")
    assert guide is not None

    sanitized = inline_google_local_schema_refs(guide.to_payload())
    serialized = json.dumps(sanitized, ensure_ascii=False)
    edit_item = sanitized["parameters"]["properties"]["payload"]["properties"]["edits"]["items"]

    assert "#/$defs/" not in serialized
    assert "$defs" not in serialized
    assert edit_item["oneOf"][0]["properties"]["old_text"]["minLength"] == 1
    assert edit_item["oneOf"][1]["properties"]["anchor_text"]["minLength"] == 1


def test_google_response_schema_refs_should_preserve_external_refs() -> None:
    """真实文件或多模态引用不是本地 Schema 引用时不得被改写。"""

    payload = {
        "image_ref": {"$ref": "instrument.jpg"},
        "external_ref": {"$ref": "https://example.com/resource"},
    }

    assert inline_google_local_schema_refs(payload) == payload


def test_google_response_without_schema_refs_should_preserve_defs_data() -> None:
    """没有本地引用的业务字段不应被兼容层误删。"""

    payload = {"$defs": {"metadata": {"type": "string"}}, "value": "plain text"}

    assert inline_google_local_schema_refs(payload) == payload


@pytest.mark.asyncio
async def test_google_model_should_sanitize_function_response_before_request() -> None:
    """GoogleModel 映射工具返回时应移除 Gemini 会误判的本地 Schema 引用。"""

    guide = get_operation_guide_spec("page.update.content")
    assert guide is not None
    model = GoogleCompatibleModel(
        "gemini-3.6-flash",
        provider=GoogleProvider(api_key="test"),
    )
    tool_return = ToolReturnPart(
        tool_name="get_operation_guide",
        content=guide.to_payload(),
        tool_call_id="call-1",
    )

    mapped = await model._map_tool_return(tool_return)
    response = mapped[0]["function_response"]["response"]
    serialized = json.dumps(response, ensure_ascii=False)

    assert "#/$defs/" not in serialized
    assert "$defs" not in serialized
    assert response["operation_key"] == "page.update.content"
