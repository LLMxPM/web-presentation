"""文件功能：SQLite 写路径可观测打点，默认关闭，仅在基线采集期开启。"""

from __future__ import annotations

import contextvars
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

# 当前后台循环/请求归因标签；由 worker 入口绑定
loop_name_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "db_write_path_loop",
    default="unknown",
)

_metrics_enabled = False
_lock = threading.Lock()


@dataclass
class LoopStats:
    """单个循环/归因桶的写路径统计。"""

    sql_total: int = 0
    sql_read: int = 0
    sql_write: int = 0
    sql_duration_ms_total: float = 0.0
    sql_duration_ms_max: float = 0.0
    write_conflicts: int = 0
    invalid_writes: int = 0
    effective_writes: int = 0
    empty_polls: int = 0
    total_polls: int = 0
    tick_count: int = 0
    tick_duration_ms_samples: list[float] = field(default_factory=list)
    busy_timeouts: int = 0

    def snapshot(self) -> dict[str, Any]:
        """导出可序列化快照。"""

        samples = sorted(self.tick_duration_ms_samples)
        p50 = samples[len(samples) // 2] if samples else 0.0
        p95 = samples[int(len(samples) * 0.95)] if samples else 0.0
        return {
            "sql_total": self.sql_total,
            "sql_read": self.sql_read,
            "sql_write": self.sql_write,
            "sql_avg_ms": round(self.sql_duration_ms_total / self.sql_total, 3) if self.sql_total else 0.0,
            "sql_max_ms": round(self.sql_duration_ms_max, 3),
            "write_conflicts": self.write_conflicts,
            "invalid_writes": self.invalid_writes,
            "effective_writes": self.effective_writes,
            "empty_polls": self.empty_polls,
            "total_polls": self.total_polls,
            "empty_poll_ratio": (
                round(self.empty_polls / self.total_polls, 4) if self.total_polls else 0.0
            ),
            "tick_count": self.tick_count,
            "tick_p50_ms": round(p50, 3),
            "tick_p95_ms": round(p95, 3),
            "busy_timeouts": self.busy_timeouts,
        }


_stats: dict[str, LoopStats] = defaultdict(LoopStats)
_started_at = time.monotonic()
_write_statements = ("insert", "update", "delete", "replace")


def set_metrics_enabled(enabled: bool) -> None:
    """开启或关闭写路径打点；默认关闭以避免监听器开销。"""

    global _metrics_enabled
    _metrics_enabled = bool(enabled)


def metrics_enabled() -> bool:
    """返回当前打点开关状态。"""

    return _metrics_enabled


def bind_loop_name(name: str) -> contextvars.Token[str]:
    """绑定当前任务的归因循环名。"""

    return loop_name_var.set(str(name or "unknown"))


def reset_loop_name(token: contextvars.Token[str]) -> None:
    """恢复上一跳归因循环名。"""

    loop_name_var.reset(token)


def _bucket() -> LoopStats:
    return _stats[loop_name_var.get()]


def record_sql(
    *,
    statement: str,
    duration_ms: float,
    rowcount: int | None = None,
) -> None:
    """记录一条 SQL 的读写分类、耗时与（可选）rowcount。"""

    if not _metrics_enabled:
        return
    text = (statement or "").lstrip().lower()
    is_write = text.startswith(_write_statements)
    with _lock:
        bucket = _bucket()
        bucket.sql_total += 1
        if is_write:
            bucket.sql_write += 1
            if rowcount is not None:
                if int(rowcount) > 0:
                    bucket.effective_writes += 1
                else:
                    bucket.invalid_writes += 1
        else:
            bucket.sql_read += 1
        bucket.sql_duration_ms_total += duration_ms
        if duration_ms > bucket.sql_duration_ms_max:
            bucket.sql_duration_ms_max = duration_ms


def record_write_conflict() -> None:
    """记录一次 SQLite BUSY/LOCKED 判据命中。"""

    if not _metrics_enabled:
        return
    with _lock:
        _bucket().write_conflicts += 1


def record_busy_timeout() -> None:
    """记录一次 busy_timeout 耗尽或等待超时。"""

    if not _metrics_enabled:
        return
    with _lock:
        _bucket().busy_timeouts += 1


def record_poll(*, empty: bool) -> None:
    """记录一次认领/扫描轮询是否空转。"""

    if not _metrics_enabled:
        return
    with _lock:
        bucket = _bucket()
        bucket.total_polls += 1
        if empty:
            bucket.empty_polls += 1


def record_tick(duration_ms: float) -> None:
    """记录一次 loop tick 耗时，用于 P50/P95。"""

    if not _metrics_enabled:
        return
    with _lock:
        bucket = _bucket()
        bucket.tick_count += 1
        # 有界采样，避免长期运行无限增长
        if len(bucket.tick_duration_ms_samples) < 10_000:
            bucket.tick_duration_ms_samples.append(duration_ms)


def snapshot() -> dict[str, Any]:
    """导出全量写路径指标快照，供基线采集与诊断 CLI 使用。"""

    with _lock:
        loops = {name: bucket.snapshot() for name, bucket in sorted(_stats.items())}
        totals = LoopStats()
        for bucket in _stats.values():
            totals.sql_total += bucket.sql_total
            totals.sql_read += bucket.sql_read
            totals.sql_write += bucket.sql_write
            totals.sql_duration_ms_total += bucket.sql_duration_ms_total
            totals.sql_duration_ms_max = max(totals.sql_duration_ms_max, bucket.sql_duration_ms_max)
            totals.write_conflicts += bucket.write_conflicts
            totals.invalid_writes += bucket.invalid_writes
            totals.effective_writes += bucket.effective_writes
            totals.empty_polls += bucket.empty_polls
            totals.total_polls += bucket.total_polls
            totals.tick_count += bucket.tick_count
            totals.busy_timeouts += bucket.busy_timeouts
            totals.tick_duration_ms_samples.extend(bucket.tick_duration_ms_samples[:200])
    return {
        "enabled": _metrics_enabled,
        "uptime_seconds": round(time.monotonic() - _started_at, 3),
        "totals": totals.snapshot(),
        "loops": loops,
    }


def reset() -> None:
    """清空统计，供测试与基线轮次开始时调用。"""

    global _started_at
    with _lock:
        _stats.clear()
        _started_at = time.monotonic()
