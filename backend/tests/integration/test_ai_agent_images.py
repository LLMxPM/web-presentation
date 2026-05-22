"""文件功能：验证 Agent 图片附件、模型视觉能力校验与图片传输策略。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.services.agent_image_transport_resolver import AgentImageTransportResolver


async def _create_workspace(authenticated_client: AsyncClient, name: str = "图片输入工作空间") -> int:
    """创建测试工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_project(authenticated_client: AsyncClient, workspace_id: int, name: str = "图片输入项目") -> int:
    """创建测试项目并返回主键。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_agent_session(authenticated_client: AsyncClient, workspace_id: int) -> tuple[str, int]:
    """创建项目级内容助手会话，并返回会话 ID 与项目 ID。"""

    project_id = await _create_project(authenticated_client, workspace_id)

    response = await authenticated_client.post(
        "/api/ai/sessions",
        json={
            "agent_id": "agent-coordinator",
            "session_name": "图片会话",
            "scope": {
                "scope_type": "project",
                "workspace_id": workspace_id,
                "project_id": project_id,
                "source": "test",
            },
        },
    )
    assert response.status_code == 201
    return response.json()["session_id"], project_id


async def _bind_agent_model(authenticated_client: AsyncClient, *, supports_image_input: bool) -> int:
    """创建并绑定总控智能体模型。"""

    create_response = await authenticated_client.post(
        "/api/ai/llm-configs",
        json={
            "name": "图片测试模型",
            "provider_key": "openai",
            "model_id": "gpt-4.1-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "thinking_enabled": False,
            "supports_image_input": supports_image_input,
            "advanced_config_json": {},
        },
    )
    assert create_response.status_code == 201
    config_id = create_response.json()["id"]
    bind_response = await authenticated_client.put(
        "/api/ai/llm-slots/agent_coordinator",
        json={"llm_config_id": config_id},
    )
    assert bind_response.status_code == 200
    return config_id


async def test_image_attachment_upload_should_reject_oversized_file(authenticated_client: AsyncClient) -> None:
    """上传超过 10MB 的图片应返回稳定错误码。"""

    workspace_id = await _create_workspace(authenticated_client)
    session_id, project_id = await _create_agent_session(authenticated_client, workspace_id)

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/attachments/images",
        params={"workspace_id": workspace_id, "project_id": project_id, "scope_type": "project", "agent_id": "agent-coordinator"},
        files={"file": ("large.png", b"x" * (10 * 1024 * 1024 + 1), "image/png")},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "AI_IMAGE_ATTACHMENT_TOO_LARGE"


async def test_image_attachment_upload_should_reject_non_image(authenticated_client: AsyncClient) -> None:
    """上传非 png/jpg/webp 图片应被拒绝。"""

    workspace_id = await _create_workspace(authenticated_client)
    session_id, project_id = await _create_agent_session(authenticated_client, workspace_id)

    response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/attachments/images",
        params={"workspace_id": workspace_id, "project_id": project_id, "scope_type": "project", "agent_id": "agent-coordinator"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "AI_IMAGE_ATTACHMENT_TYPE_UNSUPPORTED"


async def test_run_with_image_attachment_should_require_visual_model(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """不支持图片输入的绑定模型不能发送图片附件。"""

    await _bind_agent_model(authenticated_client, supports_image_input=False)
    workspace_id = await _create_workspace(authenticated_client)
    session_id, project_id = await _create_agent_session(authenticated_client, workspace_id)

    async def fake_put_object(self, storage_key: str, content: bytes, content_type: str | None = None) -> str:  # noqa: ANN001
        return storage_key

    monkeypatch.setattr("app.services.agent_image_attachment_service.ObjectStorageService.put_object", fake_put_object)
    upload_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/attachments/images",
        params={"workspace_id": workspace_id, "project_id": project_id, "scope_type": "project", "agent_id": "agent-coordinator"},
        files={"file": ("shot.png", b"png-bytes", "image/png")},
    )
    assert upload_response.status_code == 201

    run_response = await authenticated_client.post(
        f"/api/ai/sessions/{session_id}/runs/stream",
        params={"workspace_id": workspace_id, "project_id": project_id, "scope_type": "project", "agent_id": "agent-coordinator"},
        json={"message": "", "image_attachment_ids": [upload_response.json()["id"]]},
    )

    assert run_response.status_code == 409
    assert run_response.json()["code"] == "AI_LLM_IMAGE_INPUT_UNSUPPORTED"


async def test_image_transport_resolver_should_use_base64_when_url_unavailable(monkeypatch) -> None:
    """auto 模式下无法生成公网 HTTPS URL 时应回退到 bytes/base64 路径。"""

    get_settings.cache_clear()
    monkeypatch.setenv("AI_IMAGE_TRANSPORT_MODE", "auto")

    class FakeStorage:
        async def generate_presigned_url(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return None

    resolved = await AgentImageTransportResolver(FakeStorage()).resolve_image(
        storage_key="images/a.png",
        content=b"image-bytes",
        mime_type="image/png",
        original_name="a.png",
    )

    assert resolved.transport == "base64"
    assert resolved.image.content == b"image-bytes"
    get_settings.cache_clear()


async def test_image_transport_resolver_url_mode_should_reject_private_url(monkeypatch) -> None:
    """url 强制模式下，内网或非 HTTPS 地址不可作为模型视觉输入。"""

    get_settings.cache_clear()
    monkeypatch.setenv("AI_IMAGE_TRANSPORT_MODE", "url")

    class FakeStorage:
        async def generate_presigned_url(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return "http://127.0.0.1:9000/private/a.png"

    with pytest.raises(AppException) as exc_info:
        await AgentImageTransportResolver(FakeStorage()).resolve_image(
            storage_key="images/a.png",
            content=b"image-bytes",
            mime_type="image/png",
            original_name="a.png",
        )

    assert exc_info.value.code == "AI_IMAGE_URL_UNAVAILABLE"
    get_settings.cache_clear()
