# SQLite 写路径基线（采集模板）

> 状态：**打点与采集入口已就绪，两轮实测待目标机执行**。P1 只增加打点，不改任何节奏。  
> 采集目标机：Lite 2C4G。采集前确认 `DATABASE_WRITE_PATH_METRICS_ENABLED=true`。  
> 静态推导对照值见 [`architecture-assessment-sqlite-2026-09.md`](./architecture-assessment-sqlite-2026-09.md) §3.3（约 22 次写 DML / 秒）。

## 1. 开启打点

```powershell
# 仅采集期开启；生产默认 false
$env:DATABASE_WRITE_PATH_METRICS_ENABLED = "true"
```

打点覆盖：

| 指标 | 来源 |
| :--- | :--- |
| SQL 数与耗时（读/写分列，按 loop 归因） | `app/db/session.py` → `before/after_cursor_execute` |
| 写冲突次数 | `is_sqlite_lock_error` 两份判据命中时 `record_write_conflict` |
| 有效/无效写（rowcount） | SQL 打点携带 `cursor.rowcount` |
| 空轮询比例 | `record_poll(empty=...)`（需在各 claim 入口调用） |
| tick P50/P95 | `record_tick(duration_ms)`（需在各 loop 入口调用） |
| busy_timeout 耗尽 | `record_busy_timeout`（捕获 `OperationalError` 时） |

## 2. 采集口径

两种负载各一轮：

1. **空闲 10 分钟**：无用户请求、无 AI Run、Renderer 可达。
2. **混合负载**：5 个页面变更 + 截图 + 预览并发。

每轮记录：

- SQL/s（读写分列）
- 写事务/s
- `database is locked` 次数
- busy_timeout 命中与耗尽比
- 最长写等待
- 各 tick P50/P95
- 容器 RSS

导出快照：

```powershell
# 运行中 Backend（推荐）
curl -fsS http://127.0.0.1:8000/metrics/db-write > .tmp/baseline-sqlite-idle.json

# 或同进程 CLI
uv run --project backend python -m app.scripts.dump_db_write_metrics
```

说明：打点默认关闭；采集前确认 Backend 以 `DATABASE_WRITE_PATH_METRICS_ENABLED=true` 启动，否则快照 `enabled=false` 且计数为 0。

## 3. 原始数据

### 3.1 空闲 10 分钟

| 字段 | 值 |
| :--- | :--- |
| 采集时间 | _待填_ |
| 环境 | _待填_ |
| SQL/s 读 | _待填_ |
| SQL/s 写 | _待填_ |
| 写事务/s | _待填_ |
| database is locked | _待填_ |
| busy_timeout 耗尽 | _待填_ |
| 最长写等待 | _待填_ |
| tick P50/P95 | _待填_ |
| RSS | _待填_ |
| 快照 JSON | 见附录 |

### 3.2 混合负载

| 字段 | 值 |
| :--- | :--- |
| 采集时间 | _待填_ |
| 负载描述 | 5 页面变更 + 截图 + 预览 |
| SQL/s 读 | _待填_ |
| SQL/s 写 | _待填_ |
| 写事务/s | _待填_ |
| database is locked | _待填_ |
| busy_timeout 耗尽 | _待填_ |
| 最长写等待 | _待填_ |
| tick P50/P95 | _待填_ |
| RSS | _待填_ |
| 快照 JSON | 见附录 |

## 4. 与静态推导对照

| 口径 | 静态推导（§3.3） | 实测空闲 | 实测混合 |
| :--- | ---: | ---: | ---: |
| 写 DML / 秒 | ≈22 | _待填_ | _待填_ |
| 空闲态写事务 | >0（6 处无条件写） | _待填_ | — |
| external cleanup 4×UPDATE | 2Hz | _待填_ | — |
| render tick expire+heartbeat | 4Hz×(1+W) | _待填_ | — |

## 5. 决策门 D2（结构性判据）

| 判据 | 若成立 | 若不成立 | 本轮结论 |
| :--- | :--- | :--- | :--- |
| 空闲态写事务数 > 0 | P3 全做，目标空闲零写 DML | P3 只做退避 + 死代码清理 | _待填_ |
| 混合负载出现 `database is locked` | `run_with_write_retry` 提为 P3 前置 | P2 可按 D1 裁剪 | _待填_ |
| 某 loop tick P95 > 轮询间隔 | 该 loop 优先开刀 | 按 §6.4 既定顺序 | _待填_ |

## 6. 验收

- [ ] 基线文档含采集命令、环境与原始输出，可复现。
- [ ] 打点在 PG 上零行为变更（只计数）。
- [ ] `database_write_path_metrics_enabled=false` 时无监听器安装、无计数开销路径生效。

## 附录：快照导出

```powershell
curl -fsS http://127.0.0.1:8000/metrics/db-write > .tmp/baseline-sqlite-idle.json
# 或混合负载轮次
curl -fsS http://127.0.0.1:8000/metrics/db-write > .tmp/baseline-sqlite-mixed.json
```
