"""文件功能：验证业务时区工具对版本号与业务日期段的格式化行为。"""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.core.time_utils import format_in_app_timezone, get_app_date_code, normalize_utc


def test_time_utils_should_follow_app_timezone_env(monkeypatch) -> None:
    """业务时区格式化应严格遵循 APP_TIMEZONE 配置。"""

    monkeypatch.setenv("APP_TIMEZONE", "Asia/Tokyo")
    get_settings.cache_clear()

    try:
        source_time = datetime(2026, 3, 31, 15, 30, tzinfo=UTC)
        assert format_in_app_timezone(source_time) == "20260401-003000"
        assert get_app_date_code(source_time) == "20260401"
    finally:
        get_settings.cache_clear()


def test_normalize_utc_should_promote_naive_datetime_to_utc() -> None:
    """历史 naive 时间在进入统一工具层后应被视为 UTC。"""

    naive_time = datetime(2026, 3, 31, 9, 45, 0)
    normalized = normalize_utc(naive_time)
    assert normalized.tzinfo == UTC
    assert normalized.isoformat() == "2026-03-31T09:45:00+00:00"


@pytest.mark.parametrize("value", [
    datetime(2026, 9, 21, 2),
    datetime(2026, 9, 21, 10, tzinfo=timezone(timedelta(hours=8))),
])
def test_ai_runtime_should_serialize_history_as_utc(value: datetime) -> None:
    """AI 快照与 SSE 时间直接补齐历史 UTC，并保留带偏移时间的实际时间点。"""

    from app.ai.platform_runtime import _iso

    assert _iso(value) == "2026-09-21T02:00:00+00:00"
    assert _iso(None) is None
