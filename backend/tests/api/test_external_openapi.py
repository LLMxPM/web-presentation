"""文件功能：验证 External 多视图操作自省、动态权限、媒体类型和全部公开响应引用。"""

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.external_operations import OPERATION_REGISTRY


def _references(value: Any) -> Iterator[str]:
    """递归收集契约引用，确保客户端能完整解析而非退回自带 DTO。"""

    if isinstance(value, dict):
        if "$ref" in value:
            yield value["$ref"]
        for child in value.values():
            yield from _references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _references(child)


async def test_all_external_routes_have_resolvable_response_and_operation_contracts(client: AsyncClient) -> None:
    """87 个外部路径/方法均有契约；引用可解析，Header 必填与真实路由一致。"""

    response = await client.get("/openapi.json")
    assert response.status_code == 200
    document = response.json()
    annotated = 0
    for path, methods in document["paths"].items():
        for operation in methods.values():
            if not any(tag.startswith("External ") for tag in operation.get("tags", [])):
                continue
            annotated += 1
            metadata = operation["x-wp-operation"]
            assert metadata["version"] == 1
            headers = {parameter["name"].lower(): parameter for parameter in operation.get("parameters", []) if parameter["in"] == "header"}
            assert metadata["workspace_header_required"] == headers.get("x-workspace-id", {}).get("required", False)
            if "key" in metadata:
                spec = OPERATION_REGISTRY[metadata["key"]]
                assert metadata["required_scopes"] == list(spec.scopes)
                assert metadata["scope_mode"] == spec.scope_mode
                assert metadata["idempotency_key_required"] is spec.requires_idempotency_key
            for code, result in operation["responses"].items():
                if code.startswith("2"):
                    assert result["content"]
                    for media in result["content"].values():
                        schema = media["schema"]
                        assert schema and schema.get("additionalProperties") is not True, path
    assert annotated == 87
    for reference in _references(document):
        assert reference.startswith("#/"), reference
        value = document
        for segment in reference[2:].split("/"):
            value = value[segment.replace("~1", "/").replace("~0", "~")]


@pytest.mark.parametrize("resource,identifier,views", [
    ("pages", "page_id", ["", "/source", "/versions", "/versions/{version_no}"]),
    ("components", "component_id", ["", "/draft", "/versions", "/versions/{version_no}"]),
])
async def test_read_views_publish_their_shared_operation_without_losing_schemas(
    client: AsyncClient, resource: str, identifier: str, views: list[str],
) -> None:
    """同一读取操作的附加视图共享权限，而各自保持准确成功响应。"""

    document = (await client.get("/openapi.json")).json()
    key = "page.get" if resource == "pages" else "component.get"
    schemas = []
    for view in views:
        route = document["paths"][f"/api/v1/{resource}/{{{identifier}}}{view}"]["get"]
        assert route["x-wp-operation"]["key"] == key
        assert route["x-wp-operation"]["workspace_header_required"] is False
        schemas.append(route["responses"]["200"]["content"]["application/json"]["schema"])
    assert len({str(schema) for schema in schemas}) == len(views)


@pytest.mark.parametrize("method,suffix,action", [("get", "", "status"), ("post", "/cancel", "cancel"), ("post", "/retry", "retry")])
async def test_mutation_job_metadata_keeps_permissions_dynamic(client: AsyncClient, method: str, suffix: str, action: str) -> None:
    """通用 Job 路由按真实 job_type 分派，不能错误静态声明为 page 权限。"""

    document = (await client.get("/openapi.json")).json()
    metadata = document["paths"][f"/api/v1/jobs/mutations/{{job_id}}{suffix}"][method]["x-wp-operation"]
    assert metadata["resolution"] == "mutation_job_type"
    assert metadata["action"] == action
    assert "key" not in metadata and "required_scopes" not in metadata
    assert metadata["idempotency_key_required"] is (action != "status")
    for resource, candidate in metadata["candidates"].items():
        assert candidate["key"] == f"jobs.mutation.{resource}.{action}"
        assert candidate["required_scopes"] == [f"{resource}:{'read' if action == 'status' else 'write'}"]
    responses = document["paths"][f"/api/v1/jobs/mutations/{{job_id}}{suffix}"][method]["responses"]
    expected = {"200", "202"} if action == "cancel" else {"202"} if action == "retry" else {"200"}
    assert {code for code in responses if code.startswith("2")} == expected
    assert all(responses[code]["content"]["application/json"]["schema"]["$ref"].endswith("/ExternalMutationJobResponse") for code in expected)


async def test_png_and_any_scope_contracts_are_explicit(client: AsyncClient) -> None:
    """PNG 成功响应不能宣称 JSON，any Scope 也不能被元数据转换为 all。"""

    document = (await client.get("/openapi.json")).json()
    png = document["paths"]["/api/v1/pages/{page_id}/screenshot"]["get"]["responses"]["200"]
    assert set(png["content"]) == {"image/png"}
    assert png["content"]["image/png"]["schema"] == {"type": "string", "format": "binary"}
    assert set(png["headers"]) == {"X-Page-ID", "X-Page-Version-No"}
    validation = document["paths"]["/api/v1/validate/entity"]["post"]["x-wp-operation"]
    assert validation["scope_mode"] == "any"
    assert validation["required_scopes"] == ["page:read", "component:read"]
    public_version = await client.get("/api/v1/system/version")
    assert public_version.status_code == 200
    assert "cache-control" not in public_version.headers
