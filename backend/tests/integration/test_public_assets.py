"""文件功能：验证公开资源入口对 SVG 图标代理与普通资源直连策略的分流行为。"""

from __future__ import annotations

from httpx import AsyncClient

from app.core.config import get_settings
from app.services.object_storage_service import ObjectStorageService


async def _create_workspace(authenticated_client: AsyncClient, name: str) -> int:
    """创建测试工作空间并返回主键。"""

    response = await authenticated_client.post(
        "/api/workspaces",
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def test_public_asset_should_proxy_svg_icon_with_s3_driver(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """S3 模式下 SVG 图标应由 Backend 直接返回，保证 Runtime 可读取文本并内联着色。"""

    workspace_id = await _create_workspace(authenticated_client, "SVG 图标代理工作空间")
    svg_content = b"<svg><path fill='currentColor' d='M0 0'/></svg>"

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("brand.svg", svg_content, "image/svg+xml")},
        data={"asset_type": "icon", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    uploaded_asset = upload_response.json()

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    get_settings.cache_clear()
    calls = {"presign": 0, "read": 0}

    async def fake_generate_download_url(  # noqa: ANN001, ARG001
        self,
        workspace_id,
        file_name,
        original_name,
        download=False,
    ):
        calls["presign"] += 1
        return "https://s3.example.com/brand.svg"

    async def fake_read_s3_object(  # noqa: ANN001, ARG001
        self: ObjectStorageService,
        storage_key: str,
        *,
        bucket_name: str | None = None,
    ) -> bytes:
        calls["read"] += 1
        assert storage_key == f"assets/{workspace_id}/{uploaded_asset['file_name']}"
        return svg_content

    monkeypatch.setattr(
        "app.services.asset_storage_drivers.S3StorageDriver.generate_download_url",
        fake_generate_download_url,
    )
    monkeypatch.setattr(ObjectStorageService, "_read_s3_object", fake_read_s3_object)

    response = await authenticated_client.get(f"/public/assets/{workspace_id}/{uploaded_asset['file_hash']}")

    assert response.status_code == 200
    assert response.content == svg_content
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "location" not in response.headers
    assert calls == {"presign": 0, "read": 1}
    get_settings.cache_clear()


async def test_public_asset_should_keep_s3_redirect_for_non_svg_resource(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """普通图片资源仍应保持 S3 直连重定向，避免把大资源带宽压到 Backend。"""

    workspace_id = await _create_workspace(authenticated_client, "普通资源直连工作空间")

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("cover.png", b"png-bytes", "image/png")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    uploaded_asset = upload_response.json()

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    get_settings.cache_clear()
    calls = {"presign": 0, "read": 0}

    async def fake_generate_download_url(  # noqa: ANN001, ARG001
        self,
        workspace_id,
        file_name,
        original_name,
        download=False,
    ):
        calls["presign"] += 1
        return "https://s3.example.com/cover.png"

    async def fake_read_content(self, workspace_id, file_name):  # noqa: ANN001, ARG001
        calls["read"] += 1
        return b"unexpected"

    monkeypatch.setattr(
        "app.services.asset_storage_drivers.S3StorageDriver.generate_download_url",
        fake_generate_download_url,
    )
    monkeypatch.setattr(
        "app.services.asset_storage_drivers.S3StorageDriver.read_content",
        fake_read_content,
    )

    response = await authenticated_client.get(
        f"/public/assets/{workspace_id}/{uploaded_asset['file_hash']}",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "https://s3.example.com/cover.png"
    assert calls == {"presign": 1, "read": 0}
    get_settings.cache_clear()


async def test_public_font_asset_should_redirect_to_stable_public_bucket_url(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """S3 模式下字体资源应使用公开 bucket 稳定 URL，避免每次预览生成新的签名地址。"""

    workspace_id = await _create_workspace(authenticated_client, "公开字体资源工作空间")

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("BrandSerif.woff2", b"font-bytes", "font/woff2")},
        data={"asset_type": "font", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    uploaded_asset = upload_response.json()

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    monkeypatch.setenv("S3_BUCKET", "private-assets")
    monkeypatch.setenv("S3_PUBLIC_BUCKET", "public-fonts")
    monkeypatch.setenv("S3_PUBLIC_BASE_URL", "https://public-fonts.example.com/")
    get_settings.cache_clear()

    response = await authenticated_client.get(
        f"/public/assets/{workspace_id}/{uploaded_asset['file_hash']}",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        f"https://public-fonts.example.com/assets/{workspace_id}/{uploaded_asset['file_name']}"
    )
    get_settings.cache_clear()


async def test_public_asset_should_proxy_text_render_asset_with_s3_driver(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """S3 模式下 Mermaid/Draw.io 等文本渲染资源应由 Backend 代理，避免 Runtime fetch 被对象存储 CORS 阻断。"""

    workspace_id = await _create_workspace(authenticated_client, "文本渲染资源代理工作空间")
    cases = [
        {
            "asset_type": "mermaid",
            "name": "preview_flow",
            "original_name": "preview_flow.mmd",
            "content": "flowchart TD\n  A[开始] --> B[结束]",
            "content_type_prefix": "text/plain",
        },
        {
            "asset_type": "drawio",
            "name": "preview_diagram",
            "original_name": "preview_diagram.drawio",
            "content": "<mxfile><diagram id=\"demo\"><mxGraphModel><root /></mxGraphModel></diagram></mxfile>",
            "content_type_prefix": "application/xml",
        },
    ]

    calls = {"presign": 0, "read": 0}
    content_by_key: dict[str, bytes] = {}
    created_assets: list[tuple[dict[str, object], dict[str, str]]] = []

    async def fake_generate_download_url(  # noqa: ANN001, ARG001
        self,
        workspace_id,
        file_name,
        original_name,
        download=False,
    ):
        calls["presign"] += 1
        return "https://s3.example.com/text-resource"

    async def fake_read_s3_object(  # noqa: ANN001, ARG001
        self: ObjectStorageService,
        storage_key: str,
        *,
        bucket_name: str | None = None,
    ) -> bytes:
        calls["read"] += 1
        return content_by_key[storage_key]

    def fake_guess_type(file_name: str) -> tuple[str | None, None]:
        """模拟 CI 镜像系统 MIME 表对文本渲染资源扩展名的非通用识别。"""

        if file_name.endswith(".mmd"):
            return ("application/vnd.chipnuts.karaoke-mmd", None)
        if file_name.endswith(".drawio"):
            return ("application/vnd.jgraph.mxfile", None)
        return (None, None)

    for item in cases:
        create_response = await authenticated_client.post(
            f"/api/workspaces/{workspace_id}/assets/content",
            json={**item, "tags": []},
        )
        assert create_response.status_code == 200
        uploaded_asset = create_response.json()
        content_by_key[f"assets/{workspace_id}/{uploaded_asset['file_name']}"] = item["content"].encode("utf-8")
        created_assets.append((item, uploaded_asset))

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.asset_storage_drivers.S3StorageDriver.generate_download_url",
        fake_generate_download_url,
    )
    monkeypatch.setattr(ObjectStorageService, "_read_s3_object", fake_read_s3_object)
    monkeypatch.setattr("app.api.routes.public_assets.mimetypes.guess_type", fake_guess_type)

    for item, uploaded_asset in created_assets:
        response = await authenticated_client.get(f"/public/assets/{workspace_id}/{uploaded_asset['file_hash']}")

        assert response.status_code == 200
        assert response.text == item["content"]
        assert response.headers["content-type"].startswith(item["content_type_prefix"])
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert response.headers["access-control-allow-origin"] == "*"
        assert "location" not in response.headers

    assert calls == {"presign": 0, "read": len(cases)}
    get_settings.cache_clear()


async def test_public_asset_should_keep_s3_redirect_for_svg_image_resource(
    authenticated_client: AsyncClient,
    monkeypatch,
) -> None:
    """SVG 图片资源不属于 Icon 着色链路，仍应保持 S3 直连重定向。"""

    workspace_id = await _create_workspace(authenticated_client, "SVG 图片直连工作空间")

    upload_response = await authenticated_client.post(
        f"/api/workspaces/{workspace_id}/assets/upload",
        files={"file": ("diagram.svg", b"<svg><rect width='10' height='10'/></svg>", "image/svg+xml")},
        data={"asset_type": "image", "tags": "[]"},
    )
    assert upload_response.status_code == 200
    uploaded_asset = upload_response.json()

    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "s3")
    get_settings.cache_clear()
    calls = {"presign": 0, "read": 0}

    async def fake_generate_download_url(  # noqa: ANN001, ARG001
        self,
        workspace_id,
        file_name,
        original_name,
        download=False,
    ):
        calls["presign"] += 1
        return "https://s3.example.com/diagram.svg"

    async def fake_read_content(self, workspace_id, file_name):  # noqa: ANN001, ARG001
        calls["read"] += 1
        return b"unexpected"

    monkeypatch.setattr(
        "app.services.asset_storage_drivers.S3StorageDriver.generate_download_url",
        fake_generate_download_url,
    )
    monkeypatch.setattr(
        "app.services.asset_storage_drivers.S3StorageDriver.read_content",
        fake_read_content,
    )

    response = await authenticated_client.get(
        f"/public/assets/{workspace_id}/{uploaded_asset['file_hash']}",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "https://s3.example.com/diagram.svg"
    assert calls == {"presign": 1, "read": 0}
    get_settings.cache_clear()
