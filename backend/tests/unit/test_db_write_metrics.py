"""文件功能：验证 SQLite 写路径打点开关、分类计数与快照导出。"""

from __future__ import annotations

from app.db import metrics as write_path_metrics


def test_metrics_disabled_by_default() -> None:
    """打点默认关闭，避免监听器开销影响生产路径。"""

    write_path_metrics.reset()
    write_path_metrics.set_metrics_enabled(False)
    write_path_metrics.record_sql(statement="SELECT 1", duration_ms=1.0)
    snapshot = write_path_metrics.snapshot()
    assert snapshot["enabled"] is False
    assert snapshot["totals"]["sql_total"] == 0


def test_metrics_record_sql_read_write_and_rowcount() -> None:
    """开启后应分列读写 SQL，并按 rowcount 区分有效/无效写。"""

    write_path_metrics.reset()
    write_path_metrics.set_metrics_enabled(True)
    try:
        write_path_metrics.bind_loop_name("render-coordinator")
        write_path_metrics.record_sql(statement="SELECT id FROM pages", duration_ms=2.0)
        write_path_metrics.record_sql(statement="UPDATE pages SET a=1", duration_ms=3.0, rowcount=1)
        write_path_metrics.record_sql(statement="UPDATE pages SET a=2", duration_ms=1.0, rowcount=0)
        write_path_metrics.record_write_conflict()
        write_path_metrics.record_poll(empty=True)
        write_path_metrics.record_poll(empty=False)
        write_path_metrics.record_tick(12.0)
        snapshot = write_path_metrics.snapshot()
    finally:
        write_path_metrics.set_metrics_enabled(False)
        write_path_metrics.reset()

    totals = snapshot["totals"]
    assert totals["sql_total"] == 3
    assert totals["sql_read"] == 1
    assert totals["sql_write"] == 2
    assert totals["effective_writes"] == 1
    assert totals["invalid_writes"] == 1
    assert totals["write_conflicts"] == 1
    assert totals["empty_polls"] == 1
    assert totals["total_polls"] == 2
    assert totals["tick_count"] == 1
    assert "render-coordinator" in snapshot["loops"]
