"""文件功能：验证 AI 会话历史保留清理服务的删除策略与启动开关。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.config import AppSettings
from app.services.ai_session_retention_service import (
    AiSessionRetentionService,
    run_ai_session_retention_once_safely,
    should_start_ai_session_retention_task,
)


_NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


class _FakeAgnoDb:
    """模拟 Agno DB 的分页查询和批量删除接口。"""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """保存 session 原始行，并记录删除调用。"""

        self.rows = list(rows)
        self.deleted_calls: list[list[str]] = []
        self.get_calls: list[dict[str, Any]] = []

    def get_sessions(self, **kwargs: Any):  # noqa: ANN201
        """按 updated_at 升序返回一页 session，兼容 Agno deserialize=False 返回形态。"""

        self.get_calls.append(dict(kwargs))
        limit = int(kwargs["limit"])
        page = int(kwargs["page"])
        sorted_rows = sorted(self.rows, key=_postgres_updated_at_sort_key)
        offset = (page - 1) * limit
        return sorted_rows[offset : offset + limit], len(sorted_rows)

    def delete_sessions(self, session_ids: list[str], user_id: str | None = None) -> None:
        """删除指定 session_id；user_id 参数用于兼容 Agno DB 签名。"""

        _ = user_id
        self.deleted_calls.append(list(session_ids))
        deleting = set(session_ids)
        self.rows = [row for row in self.rows if row.get("session_id") not in deleting]


class _BrokenRetentionService:
    """模拟清理过程抛出异常的服务。"""

    async def cleanup_once(self) -> None:
        """始终抛出异常，验证安全执行包装不会向外传播。"""

        raise RuntimeError("cleanup failed")


async def test_ai_session_retention_should_delete_sessions_older_than_retention_days() -> None:
    """updated_at 超过保留期的 session 应被整条删除。"""

    agno_db = _FakeAgnoDb(
        [
            _session_row("old-session", updated_days_ago=16),
            _session_row("recent-session", updated_days_ago=14),
        ]
    )
    service = _build_service(agno_db)

    stats = await service.cleanup_once()

    assert stats.deleted_sessions == 1
    assert agno_db.deleted_calls == [["old-session"]]
    assert [row["session_id"] for row in agno_db.rows] == ["recent-session"]


async def test_ai_session_retention_should_keep_recent_sessions() -> None:
    """15 天内更新过的 session 不应被删除。"""

    agno_db = _FakeAgnoDb(
        [
            _session_row("recent-1", updated_days_ago=1),
            _session_row("recent-2", updated_days_ago=15, seconds_offset=1),
        ]
    )
    service = _build_service(agno_db)

    stats = await service.cleanup_once()

    assert stats.deleted_sessions == 0
    assert agno_db.deleted_calls == []
    assert {row["session_id"] for row in agno_db.rows} == {"recent-1", "recent-2"}


async def test_ai_session_retention_should_fallback_to_created_at_when_updated_at_missing() -> None:
    """updated_at 缺失时，应按 created_at 判断是否过期。"""

    agno_db = _FakeAgnoDb(
        [
            _session_row("legacy-old", updated_days_ago=None, created_days_ago=20),
            _session_row("legacy-recent", updated_days_ago=None, created_days_ago=2),
        ]
    )
    service = _build_service(agno_db)

    stats = await service.cleanup_once()

    assert stats.deleted_sessions == 1
    assert agno_db.deleted_calls == [["legacy-old"]]
    assert [row["session_id"] for row in agno_db.rows] == ["legacy-recent"]


async def test_ai_session_retention_should_delete_multiple_old_batches() -> None:
    """旧 session 超过单批大小时，应连续分页清理多批。"""

    agno_db = _FakeAgnoDb(
        [
            *[_session_row(f"old-{index}", updated_days_ago=20 + index) for index in range(5)],
            _session_row("recent", updated_days_ago=1),
        ]
    )
    service = _build_service(agno_db, batch_size=2)

    stats = await service.cleanup_once()

    assert stats.deleted_sessions == 5
    assert agno_db.deleted_calls == [["old-4", "old-3"], ["old-2", "old-1"], ["old-0"]]
    assert [row["session_id"] for row in agno_db.rows] == ["recent"]


def test_ai_session_retention_task_should_not_start_when_interval_disabled() -> None:
    """清理间隔为 0 时，不应启动后台任务。"""

    settings = AppSettings(_env_file=None, ai_session_cleanup_interval_seconds=0)

    assert should_start_ai_session_retention_task(settings, object()) is False


def test_ai_session_retention_settings_should_use_expected_defaults() -> None:
    """AI 会话清理配置默认值应与保留策略一致。"""

    settings = AppSettings(_env_file=None)

    assert settings.ai_session_retention_days == 15
    assert settings.ai_session_cleanup_interval_seconds == 21600
    assert settings.ai_session_cleanup_batch_size == 500


def test_ai_session_retention_task_should_not_start_when_ai_disabled() -> None:
    """AI 功能关闭时，不应启动 session 清理后台任务。"""

    settings = AppSettings(_env_file=None, ai_enabled=False)

    assert should_start_ai_session_retention_task(settings, object()) is False


async def test_ai_session_retention_safe_runner_should_swallow_cleanup_exception() -> None:
    """后台清理异常应被记录并吞掉，避免影响应用运行。"""

    result = await run_ai_session_retention_once_safely(_BrokenRetentionService())  # type: ignore[arg-type]

    assert result is None


def _build_service(agno_db: _FakeAgnoDb, *, batch_size: int = 500) -> AiSessionRetentionService:
    """构造固定当前时间的清理服务，保证测试阈值稳定。"""

    return AiSessionRetentionService(
        agno_db=agno_db,
        retention_days=15,
        batch_size=batch_size,
        now_factory=lambda: _NOW,
    )


def _session_row(
    session_id: str,
    *,
    updated_days_ago: int | None,
    created_days_ago: int | None = None,
    seconds_offset: int = 0,
) -> dict[str, Any]:
    """生成 Agno session 原始行，时间字段使用秒级 Unix 时间戳。"""

    created_days = created_days_ago if created_days_ago is not None else updated_days_ago
    return {
        "session_id": session_id,
        "updated_at": _timestamp_days_ago(updated_days_ago, seconds_offset=seconds_offset)
        if updated_days_ago is not None
        else None,
        "created_at": _timestamp_days_ago(created_days or 0),
    }


def _timestamp_days_ago(days: int, *, seconds_offset: int = 0) -> int:
    """把相对天数转换为测试用时间戳。"""

    return int((_NOW - timedelta(days=days) + timedelta(seconds=seconds_offset)).timestamp())


def _postgres_updated_at_sort_key(row: dict[str, Any]) -> tuple[bool, int]:
    """模拟 PostgreSQL updated_at asc 默认 nulls first 排序。"""

    updated_at = row.get("updated_at")
    return (updated_at is not None, int(updated_at or 0))
