"""文件功能：验证 Runtime 服务令牌内部换票链路的授权范围、过期拒绝与最小权限约束。"""

from __future__ import annotations

import time

from httpx import AsyncClient

from app.services.token_service import TokenService


def _generate_preview_token(
    *,
    artifact_id: str = "artifact-exchange-1",
    expires_in_seconds: int = 3600,
) -> str:
    """签发测试用 PreviewContextToken。"""

    return TokenService.generate_preview_context_token(
        artifact_id=artifact_id,
        preview_kind="page",
        scope_type="project",
        workspace_id=1,
        project_id=1,
        entry_descriptor={"entry_type": "module", "module_path": "src/views/Foo.vue"},
        asset_base_url="http://127.0.0.1:8000/public/assets/1",
        trace_id="req-exchange-test",
        tenant_id="tenant_1",
        expires_in_seconds=expires_in_seconds,
    )


async def _create_project_preview_artifact(
    authenticated_client: AsyncClient,
    *,
    workspace_name: str,
    project_name: str,
) -> tuple[str, str]:
    """创建最小项目预览 artifact，并返回 (artifact_id, preview_token)。"""

    workspace_response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": workspace_name, "status": "active"},
    )
    assert workspace_response.status_code == 200
    workspace_id = workspace_response.json()["id"]

    project_response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": project_name, "status": "active"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    page_response = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>exchange-page</div></template>",
            "file_type": "vue",
            "title": "换票页面",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project_id,
        },
    )
    assert page_response.status_code == 200
    page = page_response.json()

    route_response = await authenticated_client.put(
        f"/api/projects/{project_id}/routes",
        json={
            "routes": [
                {
                    "route_type": "page",
                    "route": "home",
                    "order": 0,
                    "page_id": page["id"],
                }
            ]
        },
    )
    assert route_response.status_code == 200

    preview_response = await authenticated_client.post(
        f"/api/projects/{project_id}/preview-artifacts",
        json={"entry_descriptor": {"entry_type": "route", "route": "/home"}},
    )
    assert preview_response.status_code == 200
    preview_data = preview_response.json()
    artifact_id = str(preview_data["artifact_id"])

    # 预览令牌只出现在 preview_url 查询串中，浏览器仅持有该最小权限票据
    preview_url = str(preview_data["preview_url"])
    assert "token=" in preview_url
    preview_token = preview_url.split("token=", 1)[1].split("&", 1)[0]
    return artifact_id, preview_token


async def test_exchange_should_return_artifact_scoped_service_token(
    authenticated_client: AsyncClient,
) -> None:
    """换票应返回绑定 artifact 的短期服务令牌，并可读取该 artifact 的内部清单。"""

    artifact_id, preview_token = await _create_project_preview_artifact(
        authenticated_client,
        workspace_name="换票工作空间",
        project_name="换票项目",
    )

    exchange_response = await authenticated_client.post(
        "/internal/runtime/preview-service-token",
        json={"preview_token": preview_token},
    )
    assert exchange_response.status_code == 200
    payload = exchange_response.json()
    assert payload["token_type"] == "Bearer"
    assert payload["artifact_id"] == artifact_id
    assert payload["scope"] == "runtime-artifact-read"
    assert payload["expires_in"] >= 60
    assert "preview_token" not in payload
    service_token = payload["service_token"]
    assert service_token != preview_token

    claims = TokenService.verify_runtime_service_access_token(service_token)
    assert claims["sub"] == "runtime-service"
    assert claims["scope"] == "runtime-artifact-read"
    assert claims["artifact_id"] == artifact_id
    assert int(claims["exp"]) <= int(time.time()) + payload["expires_in"] + 5

    manifest_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{artifact_id}/manifest",
        headers={"Authorization": f"Bearer {service_token}"},
    )
    assert manifest_response.status_code == 200
    assert manifest_response.json()["artifact_id"] == artifact_id


async def test_exchange_should_reject_expired_preview_token(
    authenticated_client: AsyncClient,
) -> None:
    """过期的 PreviewContextToken 必须被换票端点拒绝。"""

    expired_token = _generate_preview_token(expires_in_seconds=-30)

    exchange_response = await authenticated_client.post(
        "/internal/runtime/preview-service-token",
        json={"preview_token": expired_token},
    )
    assert exchange_response.status_code == 401
    assert exchange_response.json()["code"] == "PREVIEW_CONTEXT_INVALID"


async def test_exchange_should_reject_invalid_or_missing_preview_token(
    authenticated_client: AsyncClient,
) -> None:
    """伪造或缺失的预览令牌不能换出服务令牌。"""

    invalid_response = await authenticated_client.post(
        "/internal/runtime/preview-service-token",
        json={"preview_token": "not-a-valid-token"},
    )
    assert invalid_response.status_code == 401
    assert invalid_response.json()["code"] == "PREVIEW_CONTEXT_INVALID"

    missing_response = await authenticated_client.post(
        "/internal/runtime/preview-service-token",
        json={"preview_token": ""},
    )
    assert missing_response.status_code == 422

    no_body_response = await authenticated_client.post(
        "/internal/runtime/preview-service-token",
    )
    assert no_body_response.status_code == 422


async def test_exchanged_service_token_should_be_artifact_scoped(
    authenticated_client: AsyncClient,
) -> None:
    """换出的服务令牌只能访问其绑定的 artifact，跨 artifact 请求必须拒绝。"""

    source_token = _generate_preview_token(artifact_id="artifact-exchange-a")
    other_artifact_id = "artifact-exchange-b"

    exchange_response = await authenticated_client.post(
        "/internal/runtime/preview-service-token",
        json={"preview_token": source_token},
    )
    assert exchange_response.status_code == 200
    service_token = exchange_response.json()["service_token"]

    cross_response = await authenticated_client.get(
        f"/internal/runtime/preview-artifacts/{other_artifact_id}/manifest",
        headers={"Authorization": f"Bearer {service_token}"},
    )
    assert cross_response.status_code == 403
    assert cross_response.json()["code"] == "PREVIEW_ARTIFACT_MISMATCH"

    own_response = await authenticated_client.get(
        "/internal/runtime/preview-artifacts/artifact-exchange-a/manifest",
        headers={"Authorization": f"Bearer {service_token}"},
    )
    # 目标 artifact 不存在时业务层 404，但鉴权已通过，证明令牌作用域正确
    assert own_response.status_code == 404


async def test_exchange_response_should_not_accept_service_token_as_credential(
    authenticated_client: AsyncClient,
) -> None:
    """换票只接受 PreviewContextToken，服务令牌或空凭据不能再次换票。"""

    preview_token = _generate_preview_token(artifact_id="artifact-exchange-c")
    exchange_response = await authenticated_client.post(
        "/internal/runtime/preview-service-token",
        json={"preview_token": preview_token},
    )
    assert exchange_response.status_code == 200
    service_token = exchange_response.json()["service_token"]

    replay_response = await authenticated_client.post(
        "/internal/runtime/preview-service-token",
        json={"preview_token": service_token},
    )
    assert replay_response.status_code == 401
    assert replay_response.json()["code"] == "PREVIEW_CONTEXT_INVALID"
