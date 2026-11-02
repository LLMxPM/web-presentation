"""文件功能：验证 External API 页面版本重点快照与历史版本预览的契约、幂等、权限与当前页面隔离语义。"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.user import User
from app.schemas.api_access_token import ApiAccessTokenCreateRequest
from app.schemas.release import PreviewArtifactResponse
from app.services.api_access_token_service import ApiAccessTokenService
from app.services.preview_service import PreviewService

_READ_WRITE_SCOPES = ["page:read", "page:write", "preview:run"]
_VERSION_CONTENTS = {
    1: "<template><div>版本一</div></template>\n",
    2: "<template><div>版本二</div></template>",
    3: "<template><div>版本三</div></template>\n",
}


async def _create_pat(*, workspace_ids: list[int], scopes: list[str], suffix: str) -> str:
    """为默认管理员签发指定授权空间与 Scope 的 PAT，返回明文令牌。"""

    session_factory = get_session_factory()
    async with session_factory() as session:
        user = await session.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        token_result = await ApiAccessTokenService(session).create_token(
            user_id=user.id,
            payload=ApiAccessTokenCreateRequest(
                name=f"Version-Control-PAT-{suffix}",
                workspace_ids=workspace_ids,
                all_workspaces=False,
                scopes=scopes,
                expires_in_days=30,
            ),
        )
        await session.commit()
        return token_result.token


async def _seed_page(document_client: AsyncClient) -> dict[str, Any]:
    """创建带三个内容与备注各不相同的版本的页面，并签发可读写 PAT。"""

    workspace = await document_client.post("/api/workspaces", json={"name": "版本控制空间", "status": "active"})
    assert workspace.status_code == 200, workspace.text
    workspace_id = workspace.json()["id"]
    project = await document_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": "版本控制项目", "status": "active"},
    )
    assert project.status_code == 200, project.text
    page = await document_client.post(
        "/api/pages",
        json={
            "page_content": _VERSION_CONTENTS[1],
            "file_type": "vue",
            "title": "版本控制页面",
            "speaker_notes": "第一版备注",
            "status": "active",
            "workspace_id": workspace_id,
            "project_id": project.json()["id"],
        },
    )
    assert page.status_code == 200, page.text
    page_id = page.json()["id"]

    for version_no in (2, 3):
        updated = await document_client.patch(
            f"/api/pages/{page_id}",
            json={
                "page_content": _VERSION_CONTENTS[version_no],
                "file_type": "vue",
                "speaker_notes": f"第{version_no}版备注",
                "change_note": f"更新到第 {version_no} 版",
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["current_version_no"] == version_no

    token = await _create_pat(workspace_ids=[workspace_id], scopes=_READ_WRITE_SCOPES, suffix=str(workspace_id))
    return {
        "workspace_id": workspace_id,
        "project_id": project.json()["id"],
        "page_id": page_id,
        "page_code": page.json()["code"],
        "token": token,
    }


def _headers(context: dict[str, Any], *, idempotency_key: str | None = None) -> dict[str, str]:
    """构造 External API 认证与可选幂等头。"""

    headers = {
        "Authorization": f"Bearer {context['token']}",
        "X-Workspace-ID": str(context["workspace_id"]),
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


@pytest.fixture
async def version_page(authenticated_client: AsyncClient) -> dict[str, Any]:
    """准备带多版本内容的页面与对应 External 凭证。"""

    return await _seed_page(authenticated_client)


@pytest.mark.asyncio
async def test_external_version_list_keeps_array_shape(
    version_page: dict[str, Any],
    authenticated_client: AsyncClient,
) -> None:
    """版本列表保持顶层数组与既有字段，不因新增命令改为分页 envelope。"""

    response = await authenticated_client.get(
        f"/api/v1/pages/{version_page['page_id']}/versions",
        headers=_headers(version_page),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    assert [item["version_no"] for item in body] == [3, 2, 1]
    assert body[0]["is_current"] is True
    assert set(body[0]) >= {
        "version_no",
        "version_label",
        "storage_type",
        "is_important",
        "is_current",
        "snapshot_name",
        "change_note",
        "content_size",
        "created_at",
        "created_by",
    }


@pytest.mark.asyncio
async def test_external_snapshot_marks_version_without_touching_current_page(
    version_page: dict[str, Any],
    authenticated_client: AsyncClient,
) -> None:
    """标记重点快照物化完整内容，但不新增版本、不切换当前版本、不改源码与备注。"""

    page_id = version_page["page_id"]
    response = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/2/snapshot",
        json={"snapshot_name": "内容确认版"},
        headers=_headers(version_page, idempotency_key="page-version-snapshot-2"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version_no"] == 2
    assert body["is_important"] is True
    assert body["snapshot_name"] == "内容确认版"
    assert body["storage_type"] == "snapshot"
    assert body["content_mode"] == "full"
    assert body["resolved_content"] == _VERSION_CONTENTS[2]
    assert body["speaker_notes"] == "第2版备注"
    assert body["version_label"] == "V1"

    current = await authenticated_client.get(f"/api/v1/pages/{page_id}", headers=_headers(version_page))
    assert current.status_code == 200, current.text
    assert current.json()["current_version_no"] == 3
    versions = await authenticated_client.get(f"/api/v1/pages/{page_id}/versions", headers=_headers(version_page))
    assert len(versions.json()) == 3


@pytest.mark.asyncio
async def test_external_snapshot_renames_and_stays_idempotent(
    version_page: dict[str, Any],
    authenticated_client: AsyncClient,
) -> None:
    """同键重放返回首次结果；换键重命名保留版本节点与展示版号；旧键重放不撤销新名称。"""

    page_id = version_page["page_id"]
    first_headers = _headers(version_page, idempotency_key="page-version-snapshot-rename-1")
    first = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/1/snapshot",
        json={"snapshot_name": "初版"},
        headers=first_headers,
    )
    assert first.status_code == 200, first.text
    original = first.json()

    replay = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/1/snapshot",
        json={"snapshot_name": "初版"},
        headers=first_headers,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == original

    conflict = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/1/snapshot",
        json={"snapshot_name": "另一个名字"},
        headers=first_headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD"

    renamed = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/1/snapshot",
        json={"snapshot_name": "重命名后的初版"},
        headers=_headers(version_page, idempotency_key="page-version-snapshot-rename-2"),
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["snapshot_name"] == "重命名后的初版"
    assert renamed.json()["version_label"] == original["version_label"]
    assert renamed.json()["version_no"] == original["version_no"]

    stale_replay = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/1/snapshot",
        json={"snapshot_name": "初版"},
        headers=first_headers,
    )
    assert stale_replay.status_code == 200
    assert stale_replay.json()["snapshot_name"] == "初版"

    versions = await authenticated_client.get(
        f"/api/v1/pages/{page_id}/versions", headers=_headers(version_page)
    )
    labelled = [item for item in versions.json() if item["version_no"] == 1][0]
    assert labelled["snapshot_name"] == "重命名后的初版"
    assert labelled["is_important"] is True
    assert len(versions.json()) == 3


@pytest.mark.asyncio
async def test_external_snapshot_rejects_missing_key_and_missing_scope(
    version_page: dict[str, Any],
    authenticated_client: AsyncClient,
) -> None:
    """快照必须携带幂等键；只读凭证不能标记重点快照。"""

    page_id = version_page["page_id"]
    missing_key = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/1/snapshot",
        json={"snapshot_name": "缺键"},
        headers=_headers(version_page),
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    read_only_token = await _create_pat(
        workspace_ids=[version_page["workspace_id"]],
        scopes=["page:read", "preview:run"],
        suffix="read-only",
    )
    read_only = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/1/snapshot",
        json={"snapshot_name": "只读"},
        headers={
            "Authorization": f"Bearer {read_only_token}",
            "X-Workspace-ID": str(version_page["workspace_id"]),
            "Idempotency-Key": "page-version-snapshot-read-only",
        },
    )
    assert read_only.status_code == 403
    details = read_only.json()
    assert details["code"] == "INSUFFICIENT_SCOPE"
    assert details["data"]["missing_scopes"] == ["page:write"]


@pytest.mark.asyncio
async def test_external_snapshot_unknown_version_returns_version_not_found(
    version_page: dict[str, Any],
    authenticated_client: AsyncClient,
) -> None:
    """授权页面内不存在的版本返回 404 PAGE_VERSION_NOT_FOUND。"""

    response = await authenticated_client.post(
        f"/api/v1/pages/{version_page['page_id']}/versions/99/snapshot",
        json={"snapshot_name": "不存在"},
        headers=_headers(version_page, idempotency_key="page-version-snapshot-missing"),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PAGE_VERSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_external_snapshot_keeps_chain_restorable_after_new_version(
    version_page: dict[str, Any],
    authenticated_client: AsyncClient,
) -> None:
    """标记后继续保存新版本，重点标记不丢失且所有版本仍可完整还原。"""

    page_id = version_page["page_id"]
    snapshot = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/3/snapshot",
        json={"snapshot_name": "当前确认版"},
        headers=_headers(version_page, idempotency_key="page-version-snapshot-current"),
    )
    assert snapshot.status_code == 200, snapshot.text

    saved = await authenticated_client.patch(
        f"/api/pages/{page_id}",
        json={"page_content": "<template><div>版本四</div></template>", "file_type": "vue", "change_note": "继续创作"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["current_version_no"] == 4

    versions = await authenticated_client.get(
        f"/api/v1/pages/{page_id}/versions", headers=_headers(version_page)
    )
    marked = [item for item in versions.json() if item["version_no"] == 3][0]
    assert marked["is_important"] is True
    assert marked["snapshot_name"] == "当前确认版"
    assert marked["storage_type"] == "snapshot"

    expected_contents = {**_VERSION_CONTENTS, 4: "<template><div>版本四</div></template>"}
    for version_no, expected in expected_contents.items():
        detail = await authenticated_client.get(
            f"/api/v1/pages/{page_id}/versions/{version_no}", headers=_headers(version_page)
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["resolved_content"] == expected


@pytest.fixture
def captured_preview(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """替换 Runtime 预览创建，记录进入 preview 服务的真实参数。"""

    captured: list[dict[str, Any]] = []

    async def _fake_create_preview_artifact(self, **kwargs: Any) -> PreviewArtifactResponse:
        """记录调用参数并返回统一预览响应。"""

        captured.append(kwargs)
        return PreviewArtifactResponse(
            preview_url="https://preview.example.test/artifact?token=stub",
            artifact_id="rt_version_preview",
            preview_kind="page",
            entry_descriptor=kwargs["entry_descriptor"],
            viewport_width=1920,
            viewport_height=1080,
            project_id=kwargs["project_id"],
            expires_at="2026-11-02T05:00:00Z",
        )

    monkeypatch.setattr(PreviewService, "create_preview_artifact", _fake_create_preview_artifact)
    return captured


@pytest.mark.asyncio
async def test_external_version_preview_uses_target_version_override(
    version_page: dict[str, Any],
    authenticated_client: AsyncClient,
    captured_preview: list[dict[str, Any]],
) -> None:
    """历史预览把目标版本源码与备注注入 override，返回统一预览响应且不改当前页面。"""

    page_id = version_page["page_id"]
    response = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/1/preview-artifact",
        headers=_headers(version_page),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["artifact_id"] == "rt_version_preview"
    assert body["preview_kind"] == "page"
    assert body["expires_at"] == "2026-11-02T05:00:00Z"
    assert body["entry_descriptor"] == {
        "entry_type": "module",
        "module_path": f"src/views/{version_page['page_code']}.vue",
    }
    assert len(captured_preview) == 1
    call = captured_preview[0]
    override = call["page_module_overrides"][f"src/views/{version_page['page_code']}.vue"]
    assert override.content == _VERSION_CONTENTS[1]
    assert override.speaker_notes == "第一版备注"
    assert override.override_speaker_notes is True

    current = await authenticated_client.get(f"/api/v1/pages/{page_id}", headers=_headers(version_page))
    assert current.json()["current_version_no"] == 3
    source = await authenticated_client.get(f"/api/v1/pages/{page_id}/source", headers=_headers(version_page))
    assert source.json()["source_code"] == _VERSION_CONTENTS[3]


@pytest.mark.asyncio
async def test_external_version_preview_requires_preview_scope_and_existing_version(
    version_page: dict[str, Any],
    authenticated_client: AsyncClient,
    captured_preview: list[dict[str, Any]],
) -> None:
    """历史预览同时要求 page:read 与 preview:run，且版本不存在时不进入预览服务。"""

    page_id = version_page["page_id"]
    page_only_token = await _create_pat(
        workspace_ids=[version_page["workspace_id"]],
        scopes=["page:read"],
        suffix="page-only",
    )
    insufficient = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/1/preview-artifact",
        headers={
            "Authorization": f"Bearer {page_only_token}",
            "X-Workspace-ID": str(version_page["workspace_id"]),
        },
    )
    assert insufficient.status_code == 403
    assert insufficient.json()["code"] == "INSUFFICIENT_SCOPE"
    assert insufficient.json()["data"]["missing_scopes"] == ["preview:run"]

    missing_version = await authenticated_client.post(
        f"/api/v1/pages/{page_id}/versions/42/preview-artifact",
        headers=_headers(version_page),
    )
    assert missing_version.status_code == 404
    assert missing_version.json()["code"] == "PAGE_VERSION_NOT_FOUND"
    assert captured_preview == []


@pytest.mark.asyncio
async def test_external_version_preview_requires_project_binding(
    authenticated_client: AsyncClient,
    captured_preview: list[dict[str, Any]],
) -> None:
    """页面未关联项目时按 PAGE_PROJECT_REQUIRED 拒绝，不回退当前版本预览。"""

    workspace = await authenticated_client.post("/api/workspaces", json={"name": "无项目空间", "status": "active"})
    assert workspace.status_code == 200, workspace.text
    workspace_id = workspace.json()["id"]
    page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>无项目</div></template>",
            "file_type": "vue",
            "title": "无项目页面",
            "status": "active",
            "workspace_id": workspace_id,
        },
    )
    assert page.status_code == 200, page.text
    token = await _create_pat(workspace_ids=[workspace_id], scopes=_READ_WRITE_SCOPES, suffix="projectless")

    response = await authenticated_client.post(
        f"/api/v1/pages/{page.json()['id']}/versions/1/preview-artifact",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-ID": str(workspace_id)},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PAGE_PROJECT_REQUIRED"
    assert captured_preview == []


@pytest.mark.asyncio
async def test_external_version_preview_rejects_unauthorized_workspace(
    version_page: dict[str, Any],
    authenticated_client: AsyncClient,
) -> None:
    """PAT 未授权目标工作空间时历史预览不泄漏对象存在性。"""

    other = await authenticated_client.post("/api/workspaces", json={"name": "其它空间", "status": "active"})
    assert other.status_code == 200, other.text
    other_workspace_id = other.json()["id"]
    token = await _create_pat(workspace_ids=[other_workspace_id], scopes=_READ_WRITE_SCOPES, suffix="cross-workspace")

    response = await authenticated_client.post(
        f"/api/v1/pages/{version_page['page_id']}/versions/1/preview-artifact",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-ID": str(version_page["workspace_id"])},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"


@pytest.mark.asyncio
async def test_external_version_preview_hides_projectless_page_from_unauthorized_pat(
    authenticated_client: AsyncClient,
    captured_preview: list[dict[str, Any]],
) -> None:
    """未授权 PAT 访问无项目页面时必须先按工作空间拒绝，不能用 409 泄漏绑定状态。"""

    workspace = await authenticated_client.post("/api/workspaces", json={"name": "隐藏无项目空间", "status": "active"})
    assert workspace.status_code == 200, workspace.text
    workspace_id = workspace.json()["id"]
    page = await authenticated_client.post(
        "/api/pages",
        json={
            "page_content": "<template><div>未授权目标</div></template>",
            "file_type": "vue",
            "title": "未授权无项目页面",
            "status": "active",
            "workspace_id": workspace_id,
        },
    )
    assert page.status_code == 200, page.text

    other = await authenticated_client.post("/api/workspaces", json={"name": "旁路空间", "status": "active"})
    assert other.status_code == 200, other.text
    token = await _create_pat(workspace_ids=[other.json()["id"]], scopes=_READ_WRITE_SCOPES, suffix="hidden-projectless")

    omitted_header = await authenticated_client.post(
        f"/api/v1/pages/{page.json()['id']}/versions/1/preview-artifact",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert omitted_header.status_code == 403
    assert omitted_header.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"

    other_workspace_header = await authenticated_client.post(
        f"/api/v1/pages/{page.json()['id']}/versions/1/preview-artifact",
        headers={"Authorization": f"Bearer {token}", "X-Workspace-ID": str(other.json()["id"])},
    )
    assert other_workspace_header.status_code == 403
    assert other_workspace_header.json()["code"] == "WORKSPACE_NOT_AUTHORIZED"
    assert captured_preview == []
