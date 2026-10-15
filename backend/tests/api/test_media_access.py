"""文件功能：验证对象存储根目录不会通过 /media 暴露给匿名或已登录客户端。"""

from pathlib import Path

import pytest
from httpx import AsyncClient


MEDIA_OBJECT_KEYS = (
    "ai_secret.key",
    "runtime_rsa_key.pem",
    "web_presentation.db",
    "_object-cache/cached-object.bin",
    "assets/1/example.png",
    "page-screenshots/1/v1/example/1920x1080.png",
)
PRIVATE_CONTENT = b"synthetic-private-object"


@pytest.fixture(autouse=True)
def isolated_object_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """在应用创建前设置隔离存储根目录，只写入虚构敏感文件和业务对象。"""

    root = tmp_path / "objects"
    for key in MEDIA_OBJECT_KEYS:
        target = root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(PRIVATE_CONTENT)
    monkeypatch.setenv("PAGE_SCREENSHOT_LOCAL_ROOT", str(root))
    monkeypatch.setenv("ASSET_STORAGE_DRIVER", "local")
    return root


@pytest.mark.parametrize("authenticated", [False, True], ids=["anonymous", "authenticated"])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
async def test_media_root_is_not_accessible(
    client: AsyncClient,
    authenticated: bool,
    method: str,
) -> None:
    """不论登录状态，读取存储根目录或任何已存在对象都应返回 404。"""

    if authenticated:
        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Admin123456"},
        )
        assert login.status_code == 200

    paths = ["/media", "/media/", *(f"/media/{key}" for key in MEDIA_OBJECT_KEYS)]
    for path in paths:
        response = await client.request(method, path, follow_redirects=True)
        assert response.status_code == 404, (method, path, response.status_code)
        assert PRIVATE_CONTENT not in response.content
