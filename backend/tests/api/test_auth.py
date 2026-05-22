"""文件功能：验证用户登录、登出、获取当前用户与密码修改流程。"""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.time_utils import normalize_utc
from app.db.session import get_session_factory
from app.models.user import UserSession
from app.schemas.preview_size_preset import build_default_preview_size_presets


async def test_login_and_get_me(client: AsyncClient) -> None:
    """登录成功后应能读取当前用户信息，并持有会话 Cookie。"""

    login_response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Admin123456"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["username"] == "admin"
    assert login_response.json()["user"]["role"] == "platform_admin"

    me_response = await client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["display_name"] == get_settings().default_admin_display_name
    assert me_response.json()["preview_size_presets"] == build_default_preview_size_presets()


async def test_update_preview_size_presets(authenticated_client: AsyncClient) -> None:
    """当前用户应能维护自己的预设尺寸 JSON。"""

    update_response = await authenticated_client.patch(
        "/api/auth/me/preview-size-presets",
        json={
            "presets": [
                {"name": "演示大屏", "width": 2560, "height": 1440},
                {"name": "竖版海报", "width": 1080, "height": 1920},
            ]
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["preview_size_presets"] == [
        {
            "name": "演示大屏",
            "width": 2560,
            "height": 1440,
            "base_font_size": "20px",
            "icon_default_stroke_width": 2,
        },
        {
            "name": "竖版海报",
            "width": 1080,
            "height": 1920,
            "base_font_size": "20px",
            "icon_default_stroke_width": 2,
        },
    ]

    me_response = await authenticated_client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["preview_size_presets"][0]["name"] == "演示大屏"

    invalid_response = await authenticated_client.patch(
        "/api/auth/me/preview-size-presets",
        json={"presets": [{"name": "", "width": 0, "height": 1080}]},
    )
    assert invalid_response.status_code == 422

    legacy_field_response = await authenticated_client.patch(
        "/api/auth/me/preview-size-presets",
        json={"presets": [{"name": "旧字段", "width": 1920, "height": 1080, "icon_default_size": 20}]},
    )
    assert legacy_field_response.status_code == 422


async def test_logout_invalidates_session(authenticated_client: AsyncClient) -> None:
    """登出后再次访问受保护接口应被拒绝。"""

    logout_response = await authenticated_client.post("/api/auth/logout")
    assert logout_response.status_code == 200

    me_response = await authenticated_client.get("/api/auth/me")
    assert me_response.status_code == 401


async def test_change_password_requires_old_password(authenticated_client: AsyncClient) -> None:
    """修改密码需要正确的旧密码，并允许随后使用新密码登录。"""

    change_response = await authenticated_client.post(
        "/api/auth/change-password",
        json={"old_password": "Admin123456", "new_password": "Admin654321"},
    )
    assert change_response.status_code == 200

    await authenticated_client.post("/api/auth/logout")
    relogin_response = await authenticated_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Admin654321"},
    )
    assert relogin_response.status_code == 200


async def test_change_password_short_password_uses_chinese_message(authenticated_client: AsyncClient) -> None:
    """修改密码的新密码不符合长度要求时应返回中文规范提示。"""

    response = await authenticated_client.post(
        "/api/auth/change-password",
        json={"old_password": "Admin123456", "new_password": "short"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "新密码长度必须为 8 到 128 位。"


async def test_get_me_accepts_aware_session_expiry(client: AsyncClient) -> None:
    """会话过期时间即便带有时区信息，也应能被认证逻辑正确识别。"""

    login_response = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "Admin123456"},
    )
    assert login_response.status_code == 200

    async with get_session_factory()() as session:
        session_model = await session.scalar(select(UserSession).where(UserSession.is_active.is_(True)))
        assert session_model is not None
        session_model.expires_at = datetime.now(UTC) + timedelta(hours=1)
        await session.commit()

    me_response = await client.get("/api/auth/me")
    assert me_response.status_code == 200


async def test_auth_session_touch_should_be_throttled(authenticated_client: AsyncClient) -> None:
    """近期活跃会话不应在每个鉴权请求中写库，但每次响应仍应刷新浏览器 Cookie。"""

    async with get_session_factory()() as session:
        recent_session = await session.scalar(select(UserSession).where(UserSession.is_active.is_(True)))
        assert recent_session is not None
        recent_last_active_at = recent_session.last_active_at
        recent_expires_at = recent_session.expires_at

    recent_response = await authenticated_client.get("/api/auth/me")
    assert recent_response.status_code == 200
    assert get_settings().session_cookie_name in recent_response.headers["set-cookie"]

    async with get_session_factory()() as session:
        untouched_session = await session.scalar(select(UserSession).where(UserSession.is_active.is_(True)))
        assert untouched_session is not None
        assert normalize_utc(untouched_session.last_active_at) == normalize_utc(recent_last_active_at)
        assert normalize_utc(untouched_session.expires_at) == normalize_utc(recent_expires_at)

        old_last_active_at = datetime.now(UTC) - timedelta(minutes=5)
        old_expires_at = datetime.now(UTC) + timedelta(hours=1)
        untouched_session.last_active_at = old_last_active_at
        untouched_session.expires_at = old_expires_at
        await session.commit()

    stale_response = await authenticated_client.get("/api/auth/me")
    assert stale_response.status_code == 200

    async with get_session_factory()() as session:
        touched_session = await session.scalar(select(UserSession).where(UserSession.is_active.is_(True)))
        assert touched_session is not None
        assert normalize_utc(touched_session.last_active_at) > old_last_active_at
        assert normalize_utc(touched_session.expires_at) > old_expires_at


async def test_auth_session_expiry_should_slide_when_near_expiration(authenticated_client: AsyncClient) -> None:
    """会话临近过期时，即便近期活跃，也应主动延长服务端过期时间。"""

    async with get_session_factory()() as session:
        session_model = await session.scalar(select(UserSession).where(UserSession.is_active.is_(True)))
        assert session_model is not None
        recent_last_active_at = datetime.now(UTC)
        old_expires_at = datetime.now(UTC) + timedelta(minutes=1)
        session_model.last_active_at = recent_last_active_at
        session_model.expires_at = old_expires_at
        await session.commit()

    response = await authenticated_client.get("/api/auth/me")
    assert response.status_code == 200

    async with get_session_factory()() as session:
        renewed_session = await session.scalar(select(UserSession).where(UserSession.is_active.is_(True)))
        assert renewed_session is not None
        assert normalize_utc(renewed_session.expires_at) > old_expires_at
