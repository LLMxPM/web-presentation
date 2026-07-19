"""文件功能：验证 Runtime 页面可视化编辑内部客户端的线协议与错误归一化。"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.core.exceptions import AppException
from app.schemas.page_visual_edit import (
    PageVisualEditInstancePathSegment,
    PageVisualEditSetValueOperation,
)
from app.schemas.page_visual_edit_manifest import (
    PageVisualEditBinding,
    PageVisualEditManifest,
    PageVisualEditNode,
    PageVisualEditSourceRange,
    build_page_visual_edit_source_hash,
)
from app.schemas.runtime_page_visual_edit import (
    RuntimePageVisualEditAnalyzeRequest,
    RuntimePageVisualEditAnalyzeResponse,
    RuntimePageVisualEditApplyRequest,
    RuntimePageVisualEditApplyResponse,
)
from app.services.runtime_visual_edit_client import (
    RuntimeVisualEditClient,
    serialize_runtime_visual_edit_payload,
)
from app.services.token_service import TokenService


SOURCE = "<template><main>旧标题</main></template>"
NEXT_SOURCE = "<template><main>新标题</main></template>"
MODULE_PATH = "src/views/PGdemo.vue"


@pytest.fixture(autouse=True)
def stub_runtime_service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """避免单元测试依赖实际 Runtime 服务令牌密钥。"""

    monkeypatch.setattr(
        TokenService,
        "generate_runtime_service_access_token",
        staticmethod(lambda **_kwargs: "runtime-test-token"),
    )


def _build_manifest() -> PageVisualEditManifest:
    """构造客户端响应校验所需的最小 Manifest。"""

    child = PageVisualEditNode(
        node_id="node_title",
        kind="element",
        tag="main",
        source_range=PageVisualEditSourceRange(start=10, end=31),
        template_actions={"can_duplicate": True, "can_delete": True},
        bindings=[
            PageVisualEditBinding(
                binding_id="binding_title",
                node_id="node_title",
                kind="text",
                value_type="string",
                value="旧标题",
                source_range=PageVisualEditSourceRange(start=16, end=19),
                editable=True,
            )
        ],
    )
    return PageVisualEditManifest(
        protocol_version=1,
        source_hash=build_page_visual_edit_source_hash(SOURCE),
        module_path=MODULE_PATH,
        root=PageVisualEditNode(
            node_id="root",
            kind="root",
            tag="#document",
            source_range=PageVisualEditSourceRange(start=0, end=len(SOURCE)),
            template_actions={
                "can_duplicate": False,
                "can_delete": False,
                "readonly_reason": "STRUCTURE_ROOT_UNSUPPORTED",
            },
            children=[child],
        ),
        json_sources=[],
        tailwind_catalog={"version": 1, "groups": []},
    )


def _build_analyze_request() -> RuntimePageVisualEditAnalyzeRequest:
    """构造合法的 Runtime AST 分析请求。"""

    return RuntimePageVisualEditAnalyzeRequest(
        protocol_version=1,
        source_hash=build_page_visual_edit_source_hash(SOURCE),
        module_path=MODULE_PATH,
        source=SOURCE,
    )


def _build_analyze_response() -> RuntimePageVisualEditAnalyzeResponse:
    """构造合法的 Runtime AST 分析响应。"""

    return RuntimePageVisualEditAnalyzeResponse(
        protocol_version=1,
        manifest=_build_manifest(),
        instrumented_source=f"{SOURCE}\n<!-- instrumented -->",
    )


def _build_apply_request(
    *, second_operation: bool = False
) -> RuntimePageVisualEditApplyRequest:
    """构造合法的 Runtime AST 批量改写请求。"""

    operations = [
        PageVisualEditSetValueOperation(
            type="set_value",
            node_id="node_title",
            binding_id="binding_title",
            value="新标题",
        )
    ]
    if second_operation:
        operations.append(
            PageVisualEditSetValueOperation(
                type="set_value",
                node_id="node_subtitle",
                binding_id="binding_subtitle",
                value="新副标题",
            )
        )
    return RuntimePageVisualEditApplyRequest(
        protocol_version=1,
        source_hash=build_page_visual_edit_source_hash(SOURCE),
        module_path=MODULE_PATH,
        source=SOURCE,
        operations=operations,
    )


def _build_apply_response(
    *, operations_applied: int = 1
) -> RuntimePageVisualEditApplyResponse:
    """构造合法的 Runtime AST 改写响应。"""

    return RuntimePageVisualEditApplyResponse(
        protocol_version=1,
        base_source_hash=build_page_visual_edit_source_hash(SOURCE),
        next_source_hash=build_page_visual_edit_source_hash(NEXT_SOURCE),
        next_source=NEXT_SOURCE,
        operations_applied=operations_applied,
        canonical_diff="-旧标题\n+新标题",
    )


def _build_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.MockTransport:
    """用同步处理函数构造 httpx 内存传输层。"""

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_analyze_should_send_camel_case_payload_and_parse_response() -> None:
    """分析请求应使用 Runtime camelCase 线协议并校验响应源码身份。"""

    def handler(request: httpx.Request) -> httpx.Response:
        """断言请求协议并返回 camelCase 分析结果。"""

        payload = json.loads(request.content)
        assert request.url.path == "/__runtime_internal/v1/visual-edit/analyze"
        assert payload["protocolVersion"] == 1
        assert payload["sourceHash"] == build_page_visual_edit_source_hash(SOURCE)
        assert payload["modulePath"] == MODULE_PATH
        assert "source_hash" not in payload
        assert request.headers["x-runtime-service-token"] == "runtime-test-token"
        return httpx.Response(
            200, json=serialize_runtime_visual_edit_payload(_build_analyze_response())
        )

    response = await RuntimeVisualEditClient(
        transport=_build_transport(handler)
    ).analyze(_build_analyze_request())

    assert response.manifest.root.children[0].node_id == "node_title"
    assert response.instrumented_source is not None
    assert response.instrumented_source.endswith("instrumented -->")


@pytest.mark.asyncio
async def test_apply_should_serialize_nested_operation_targets() -> None:
    """改写请求中的 node、binding 与实例路径字段应递归转为 camelCase。"""

    request = _build_apply_request()
    request.operations[0].instance_path.append(
        PageVisualEditInstancePathSegment(loop_node_id="loop_items", key="b", index=1)
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        """检查嵌套操作线格式并返回候选源码。"""

        payload = json.loads(http_request.content)
        operation = payload["operations"][0]
        assert operation["nodeId"] == "node_title"
        assert operation["bindingId"] == "binding_title"
        assert operation["instancePath"][0] == {
            "loopNodeId": "loop_items",
            "key": "b",
            "index": 1,
        }
        return httpx.Response(
            200, json=serialize_runtime_visual_edit_payload(_build_apply_response())
        )

    response = await RuntimeVisualEditClient(transport=_build_transport(handler)).apply(
        request
    )

    assert response.next_source == NEXT_SOURCE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_status"),
    [(422, 422), (500, 502)],
)
async def test_http_errors_should_be_normalized(
    status_code: int, expected_status: int
) -> None:
    """Runtime 业务错误保留状态，服务端错误统一映射为 Backend 502。"""

    transport = _build_transport(
        lambda _request: httpx.Response(
            status_code,
            json={"code": "VISUAL_EDIT_REJECTED", "message": "无法分析动态表达式。"},
        )
    )

    with pytest.raises(AppException) as exc_info:
        await RuntimeVisualEditClient(transport=transport).analyze(
            _build_analyze_request()
        )

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.code == "VISUAL_EDIT_REJECTED"
    assert exc_info.value.detail == "无法分析动态表达式。"


@pytest.mark.asyncio
async def test_timeout_should_be_normalized() -> None:
    """Runtime 请求超时应转换为稳定的 504 业务错误。"""

    def handler(request: httpx.Request) -> httpx.Response:
        """模拟 Runtime 读取超时。"""

        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(AppException) as exc_info:
        await RuntimeVisualEditClient(transport=_build_transport(handler)).analyze(
            _build_analyze_request()
        )

    assert exc_info.value.status_code == 504
    assert exc_info.value.code == "RUNTIME_VISUAL_EDIT_TIMEOUT"


@pytest.mark.asyncio
async def test_invalid_json_should_be_normalized() -> None:
    """Runtime 非 JSON 成功响应不得进入后续页面保存流程。"""

    transport = _build_transport(lambda _request: httpx.Response(200, text="not-json"))

    with pytest.raises(AppException) as exc_info:
        await RuntimeVisualEditClient(transport=transport).analyze(
            _build_analyze_request()
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "RUNTIME_VISUAL_EDIT_RESPONSE_INVALID"


@pytest.mark.asyncio
async def test_protocol_mismatch_should_be_rejected() -> None:
    """Runtime 返回非 v1 协议时应返回明确的不兼容错误。"""

    payload = serialize_runtime_visual_edit_payload(_build_analyze_response())
    payload["protocolVersion"] = 2
    transport = _build_transport(lambda _request: httpx.Response(200, json=payload))

    with pytest.raises(AppException) as exc_info:
        await RuntimeVisualEditClient(transport=transport).analyze(
            _build_analyze_request()
        )

    assert exc_info.value.code == "RUNTIME_VISUAL_EDIT_PROTOCOL_MISMATCH"


@pytest.mark.asyncio
async def test_analyze_source_mismatch_should_be_rejected() -> None:
    """Runtime 分析响应绑定其他源码时应拒绝，不能生成错误 artifact。"""

    response = _build_analyze_response()
    other_source = "<template><main>其他</main></template>"
    other_hash = build_page_visual_edit_source_hash(other_source)
    response.manifest.source_hash = other_hash
    transport = _build_transport(
        lambda _request: httpx.Response(
            200, json=serialize_runtime_visual_edit_payload(response)
        )
    )

    with pytest.raises(AppException) as exc_info:
        await RuntimeVisualEditClient(transport=transport).analyze(
            _build_analyze_request()
        )

    assert exc_info.value.code == "RUNTIME_VISUAL_EDIT_SOURCE_MISMATCH"


@pytest.mark.asyncio
async def test_partial_apply_should_be_rejected() -> None:
    """Runtime 未完整应用批次时应拒绝整次结果。"""

    request = _build_apply_request(second_operation=True)
    transport = _build_transport(
        lambda _request: httpx.Response(
            200,
            json=serialize_runtime_visual_edit_payload(
                _build_apply_response(operations_applied=1)
            ),
        )
    )

    with pytest.raises(AppException) as exc_info:
        await RuntimeVisualEditClient(transport=transport).apply(request)

    assert exc_info.value.code == "RUNTIME_VISUAL_EDIT_PARTIAL_APPLY"


@pytest.mark.asyncio
async def test_invalid_response_shape_should_be_rejected() -> None:
    """带正确协议号但缺少必需字段的响应应归一化为结构错误。"""

    transport = _build_transport(
        lambda _request: httpx.Response(200, json={"protocolVersion": 1})
    )

    with pytest.raises(AppException) as exc_info:
        await RuntimeVisualEditClient(transport=transport).analyze(
            _build_analyze_request()
        )

    assert exc_info.value.code == "RUNTIME_VISUAL_EDIT_RESPONSE_INVALID"
