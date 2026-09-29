"""文件功能：双入口 Top 操作契约对拍——Internal 与 External 的路径、响应与有意差异。"""

from __future__ import annotations

from copy import deepcopy

import pytest
from app.core.external_operations import _OPERATION_HTTP_CONTRACTS, OPERATION_REGISTRY
from app.main import create_app

pytestmark = pytest.mark.unit

# Top 操作矩阵（与 docs/developer/architecture/dual-entry-contract-matrix.md 同步）
# 每项：(操作名, Internal 路径或 None, External 路径, 对齐类型, 有意差异说明或 None)
TOP_OPERATIONS: list[tuple[str, str | None, str, str, str | None]] = [
    (
        "page.list",
        "/api/pages",
        "/api/v1/projects/{project_id}/pages",
        "PagedResponse[PageItem]",
        None,
    ),
    ("page.get", "/api/pages/{id}", "/api/v1/pages/{id}", "PageItem", None),
    (
        "page.create",
        "/api/pages",
        "/api/v1/pages",
        "async_job",
        "Internal 同步 PageItem；External 202 MutationJob",
    ),
    (
        "page.update",
        "/api/pages/{id}",
        "/api/v1/pages/{id}",
        "PageItem",
        "External 仅元数据，源码走 /edits",
    ),
    (
        "page.validate",
        None,
        "/api/v1/pages/{page_id}/validate",
        "external_only",
        "Internal 无 HTTP 端点（仅 AI 工具）",
    ),
    (
        "validate.entity",
        None,
        "/api/v1/validate/entity",
        "external_only",
        "Internal 无 HTTP 端点（仅 AI 工具）",
    ),
    (
        "project.preview",
        "/api/projects/{id}/preview-artifacts",
        "/api/v1/projects/{project_id}/preview-artifact",
        "PreviewArtifactResponse",
        "入参 shape 不同",
    ),
    (
        "page.preview",
        "/api/pages/{id}/versions/{n}/preview-artifact",
        "/api/v1/pages/{page_id}/preview-artifact",
        "PreviewArtifactResponse",
        "粒度不同",
    ),
    (
        "page.archive",
        "/api/pages/{id}",
        "/api/v1/pages/{page_id}/archive",
        "message",
        "DELETE vs POST",
    ),
]

# External 注册表使用的 path_template（相对 /api/v1）
EXTERNAL_PATH_TEMPLATES = {
    "page.list": "/projects/{project_id}/pages",
    "page.get": "/pages/{page_id}",
    "page.create": "/pages",
    "page.update": "/pages/{page_id}",
    "page.validate": "/pages/{page_id}/validate",
    "validate.entity": "/validate/entity",
    "project.preview": "/projects/{project_id}/preview-artifact",
    "page.preview": "/pages/{page_id}/preview-artifact",
    "page.archive": "/pages/{page_id}/archive",
}


# 独立声明预期方法，不能从被测注册表反向派生以掩盖漂移。
EXPECTED_METHODS = {
    "page.list": ("get", "get"),
    "page.get": ("get", "get"),
    "page.create": ("post", "post"),
    "page.update": ("patch", "patch"),
    "page.validate": (None, "post"),
    "validate.entity": (None, "post"),
    "project.preview": ("post", "post"),
    "page.preview": ("post", "post"),
    "page.archive": ("delete", "post"),
}


def _paths_structurally_equal(a: str, b: str) -> bool:
    """比较两条 OpenAPI 路径是否同构（仅允许路径参数名不同）。"""

    parts_a = [p for p in a.strip("/").split("/") if p]
    parts_b = [p for p in b.strip("/").split("/") if p]
    if len(parts_a) != len(parts_b):
        return False
    for pa, pb in zip(parts_a, parts_b):
        if pa.startswith("{") and pb.startswith("{"):
            continue
        if pa != pb:
            return False
    return True


@pytest.fixture(scope="module")
def openapi_document() -> dict:
    """离线导出 FastAPI OpenAPI，不依赖运行中的服务。"""

    app = create_app()
    return app.openapi()


def test_external_registry_covers_all_top_operations() -> None:
    """Top 操作必须全部登记在 External 操作注册表中。"""

    for key, expected_path in EXTERNAL_PATH_TEMPLATES.items():
        assert key in OPERATION_REGISTRY, f"External 注册表缺少 Top 操作 {key}"
        assert key in _OPERATION_HTTP_CONTRACTS, f"External HTTP 契约缺少 {key}"
        method, path = _OPERATION_HTTP_CONTRACTS[key]
        assert path == expected_path, f"{key} path_template 漂移：{path}"
        assert method.lower() == EXPECTED_METHODS[key][1]


def _assert_operations(paths: dict) -> None:
    """完整匹配段数、字面路径和 HTTP 方法；只允许参数名字不同。"""
    for key, internal, external, _align, _diff in TOP_OPERATIONS:
        for path, method in zip((internal, external), EXPECTED_METHODS[key]):
            if path is None:
                continue
            candidates = [
                value
                for candidate, value in paths.items()
                if _paths_structurally_equal(candidate, path)
            ]
            assert len(candidates) == 1 and method in candidates[0], (
                f"缺少 {method} {path}"
            )


def test_top_operations_exist_in_openapi(openapi_document: dict) -> None:
    """所有声明的 method/path 必须真实注册。"""
    _assert_operations(openapi_document["paths"])


@pytest.mark.parametrize("mutation", ["path", "method"])
def test_missing_operation_cannot_hide_behind_path_prefix(
    openapi_document: dict, mutation: str
) -> None:
    """删除精确路径或方法，保留相同前缀及其它方法也必须失败。"""
    paths = deepcopy(openapi_document["paths"])
    target = "/api/v1/pages/{page_id}/preview-artifact"
    if mutation == "path":
        paths.pop(target)
    else:
        paths[target]["get"] = paths[target].pop("post")
    with pytest.raises(AssertionError, match="preview-artifact"):
        _assert_operations(paths)


def test_intentional_differences_are_registered() -> None:
    """有意差异必须在矩阵中显式登记，防止静默漂移。"""

    differences = {row[0]: row[4] for row in TOP_OPERATIONS if row[4]}
    # 创建：async vs sync
    assert "async" in differences["page.create"] or "202" in differences["page.create"]
    # 归档：DELETE vs POST
    assert (
        "DELETE" in differences["page.archive"]
        and "POST" in differences["page.archive"]
    )
    # 校验：Internal 单侧缺失
    assert "Internal 无 HTTP" in differences["page.validate"]
    assert "Internal 无 HTTP" in differences["validate.entity"]


def test_aligned_operations_share_response_schema_names(openapi_document: dict) -> None:
    """声明对齐的操作，两侧成功响应应引用同一 schema 名或同名字段集合。"""

    paths = openapi_document["paths"]
    components = openapi_document.get("components", {}).get("schemas", {})

    def resolve_response_schema(path: str, method: str) -> str | None:
        # 精确匹配或仅参数名不同（{id} vs {page_id}）的同构路径
        normalized_target = path
        for candidate in paths:
            if not _paths_structurally_equal(candidate, normalized_target):
                continue
            if method not in paths[candidate]:
                continue
            responses = paths[candidate][method].get("responses", {})
            for status in ("200", "201"):
                if status not in responses:
                    continue
                content = responses[status].get("content", {})
                for media in content.values():
                    schema = media.get("schema", {})
                    ref = schema.get("$ref", "")
                    if ref:
                        return ref.rsplit("/", 1)[-1]
                    if "items" in schema:
                        item_ref = schema["items"].get("$ref", "")
                        if item_ref:
                            return item_ref.rsplit("/", 1)[-1]
        return None

    for key, internal, external, _align, _diff in TOP_OPERATIONS:
        if key not in {
            "page.list",
            "page.get",
            "page.update",
            "project.preview",
            "page.preview",
        }:
            continue
        internal_method, external_method = EXPECTED_METHODS[key]
        internal_schema = resolve_response_schema(internal, internal_method)
        external_schema = resolve_response_schema(external, external_method)
        assert internal_schema is not None and internal_schema == external_schema, key
    assert components, "OpenAPI components.schemas 为空，无法对拍"


def test_creation_status_and_validation_asymmetry(openapi_document: dict) -> None:
    """锁定创建的同步/异步响应及 Internal 校验缺口，不只检查描述文字。"""
    paths = openapi_document["paths"]
    assert "200" in paths["/api/pages"]["post"]["responses"]
    assert "202" in paths["/api/v1/pages"]["post"]["responses"]
    for internal in ["/api/pages/{id}/validate", "/api/validate/entity"]:
        assert not any(_paths_structurally_equal(path, internal) for path in paths)
