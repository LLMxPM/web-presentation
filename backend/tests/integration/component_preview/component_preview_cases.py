"""文件功能：验证工作空间组件版本管理、源码依赖索引与预览模块图发布行为。"""

from httpx import AsyncClient

CONTENT_COMPONENT_SIZE_PREVIEW_SCHEMA = '{"props":{"height":{"type":"number","label":"高度","default":320}}}'


async def create_workspace(authenticated_client: AsyncClient, name: str = "组件工作空间") -> int:
    """创建一个启用中的工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def create_project(authenticated_client: AsyncClient, workspace_id: int, name: str = "组件项目") -> int:
    """创建一个启用中的项目并返回主键。"""

    response = await authenticated_client.post(
        "/api/projects",
        json={"workspace_id": workspace_id, "name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def upload_icon_asset(
    authenticated_client: AsyncClient,
    workspace_id: int,
    *,
    file_name: str,
) -> dict[str, object]:
    """向工作空间上传一个 SVG 图标资产，供预览配置校验使用。"""

    upload_file_name = file_name if file_name.endswith(".svg") else f"{file_name}.svg"
    response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": (upload_file_name, f"<svg><path d='{file_name}'/></svg>".encode("utf-8"), "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]", "name": file_name},
    )
    assert response.status_code == 200
    return response.json()


async def publish_component(
    authenticated_client: AsyncClient,
    component_id: int,
    *,
    release_name: str | None = None,
    change_note: str | None = "发布测试版本",
) -> dict[str, object]:
    """发布组件草稿并返回最新组件响应。"""

    response = await authenticated_client.post(
        f"/api/components/{component_id}/publish",
        json={"release_name": release_name, "change_note": change_note},
    )
    assert response.status_code == 200
    return response.json()

__all__ = [name for name in globals() if not name.startswith("__")]
