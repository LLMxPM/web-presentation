# 架构评估：SQLite 兼容与定时任务写路径

> **D1 决策更新（2026-09-24）**：SQLite Lite **长期一等公民**（选项 A）。本文 §6.0/§6.3.1 中「D1 未决 ⇒ 从裁剪」的 2b/2d 剩余项应按现行评估重新立项；BoolInt 维持裁剪。现行结论与执行序见 [`../architecture-assessment-2026-09-24.md`](../architecture-assessment-2026-09-24.md)。

> 评估日期：2026-09-23；**核对修订：2026-09-24**（对照 HEAD `44282d6` 逐条复核，全部结论已带 `file:line` 证据）。  
> 对象为当前工作区 Backend 持久化层、迁移与后台循环。  
> 本文只阐述 **SQLite 兼容**导致的架构不规范，以及 **定时/后台任务**如何在单写库模型下放大锁竞争。  
> 进程内状态、`memory://` 假 Redis、普通 Run 绑进程等见姊妹篇 [`architecture-assessment-memory-2026-09.md`](./architecture-assessment-memory-2026-09.md)。  
> 问题状态归类见 [`docs-temp-issue-status-2026-09.md`](./docs-temp-issue-status-2026-09.md)；旧合并稿见 [`architecture-assessment-sqlite-jobs-2026-09.md`](./architecture-assessment-sqlite-jobs-2026-09.md)（已拆分，仅存档）。

**ID 约定**：`S1–S8` 是 SQLite 兼容债条目（§2），`Q0–Q12` 是风险分级条目（§4），`P0–P5` 是整改阶段（§6）。三者映射见 §4.2。

---

## 0. 本轮核对修订摘要

2026-09-24 对照代码逐条复核，**主要结论全部成立**，但下列细节需修正，且新发现 3 项：

| # | 修订 | 依据 |
| :--- | :--- | :--- |
| C1 | `busy_timeout` 的 PRAGMA 单位是**毫秒**（`max(1, int(seconds*1000))`），配置默认 `database_connect_timeout_seconds=10.0` ⇒ **10000ms**；7000ms 只出现在单测 | `db/session.py:139,147`；`core/config.py:36`；`tests/unit/test_sqlite_session.py:15,30` |
| C2 | `idempotency_service.SQLITE_BUSY_RETRIES = 3` 是**死常量**（全仓仅定义处引用）；真实重试是 `SQLITE_BACKOFF_DELAYS = [0.05,0.1,0.2]` 且重试的是**读**（SELECT）不是写 | `services/idempotency_service.py:27,28,169-184` |
| C3 | JSON 双方言**不是逐列粘贴**：3 个 model 文件各自定义了 file-local `JSONType` 别名，另有 1 处内联在迁移里。问题是「别名定义 3 份」，不是「每列一份」 | `models/render_request.py:17`、`render_execution.py:17`、`render_attempt.py:17`；`migrations/versions/20260910_0100_remote_render_service.py:24` |
| C4 | `page-screenshot-queue` 的实际租约是 **300s**（走 `durable_job_lease_seconds`），`page_screenshot_job_lease_seconds=180` 是**永不生效的 `getattr` fallback** | `services/page_screenshot_job_service.py:786-799`；`core/config.py:104,115` |
| C5 | `lock_scheduler_state_for_queue_admission` 的版本递增在 PG 上**不是无意义**：它故意用 UPDATE 锁住单例状态行（等价 SELECT-FOR-UPDATE）。无意义的是**版本值**，不是**这次写** | `services/rendering/repository.py:59-67`（注释 :63-64） |
| C6 | `_has_sqlite_write_transaction` 的两处降级都是 **fail-safe**（非 SQLite 直接 False；`getattr(driver_connection,"in_transaction",False)`）。真实风险不是「误判」，而是「优化静默失效」+「补丁被测试固化成契约」 | `ai/platform_runtime.py:463-470`；`tests/integration/test_ai_platform_runtime_concurrency.py:240-274` |
| C7 | 空闲后台循环是 **13 条**（11 条 lifespan + 2 条派生 worker），不是「8–10 条」；`AgentBackgroundRunManager` **不是轮询循环**（按需派生 per-run task），不应计入 | `main.py:71-152`；`ai/background_run_manager.py:46-49` |
| C8 | 租约恢复实现是 **4 套以上**（原文写「三套」），且差异可具体指认：`MutationJobService` 版本**缺 `lease IS NULL` 分支**、requeue 判定 `attempt+1 < max` 与通用实现**差一**；backoff 三套（无 / +5s / +2s） | `durable_job_lease_service.py:206-310`；`mutation_job_service.py:813-875`；`rendering/repository.py:461-517`；`ai/external_task_queue.py:176-241` |
| **N1** | **新发现**：`ai-image-generation-queue` 的节奏**全部硬编码无配置项**（poll 0.5s、heartbeat 30s、lease 120s），且每轮空闲都发一条**无条件 UPDATE**（`_promote_due_provider_jobs`）+ 每轮重跑一次启动恢复 | `ai/image_generation_queue.py:38-40,89,90,471-487` |
| **N2** | **新发现**：`external_terminal_cleanup` 每次调用执行 **4 条无条件 UPDATE**（tasks/batches/requirements/tool_calls，各带子查询），而它被 0.5s 的 audit 每轮调用 ⇒ **空闲态 2Hz × 4 条写 DML** | `ai/external_terminal_cleanup.py:28-100`；`ai/external_task_queue.py:244-427` |
| **N3** | **新发现**：`page_mutation_queue._run_continuation_coordinator`（含 `_heartbeat_batch_lease` 与 30s in-coordinator recovery）**从未被启动**，是死代码；活跃的 batch 心跳在 `external_task_queue._heartbeat_batch` | `ai/page_mutation_queue.py:59-84,462-496`（:75-76 注释）；`ai/external_task_queue.py:717-751` |
| **N4** | **新发现**：`asset-render-hint-backfill` 的 180s 是 **Redis 锁 TTL**，没有 DB 租约也没有 DB 心跳；其恢复扫描**完全没有 lease/过期谓词**（直接捞全部 `running`），max_attempts=2 | `services/asset_render_hint_backfill_job_service.py:37,214-235,377-388,500-510` |

**Q0 状态：仍未修复**（HEAD `44282d6`）。`_append_page_render_diagnostics` 依旧只改 `diagnostics`/`layout_analysis`/`summary`，`success`/`status`/`retryable` 原样继承编译结果；`compile_status`/`render_status` 未引入；3 份 `_is_validation_passed` 未合并；跨阶段写阻断测试仍缺。详见 §6.1。

**自 2026-09-23 起无任何相关整改落地**：`44282d6` 纯前端；`6ee199d` 只改了一行日志字段；`0c6fcc8`/`c261054`/`b3a268e` 为文档、配置清理与 `utc_now()` 替换，均未改任何节奏、租约或校验语义。

---

## 1. 结论摘要

平台用一套代码同时支撑 **SQLite Lite** 与 **PostgreSQL**，做了许多正确工程（WAL、busy_timeout、条件 UPDATE 认领、租约、空闲免写），但：

1. **方言特判渗入类型、索引、迁移、错误处理、事务探测**——正确性依赖维护者是否记得分支。已核实：10 处双方言 partial index（6 个 model 文件）+ 6 个迁移文件重复同样谓词；2 个迁移裸判 `dialect.name`；`driver_connection` 下钻 1 处。
2. **SQLite 单写入者约束上浮进业务方法**（读事务尽早提交、假写抢锁、锁序反转探测），全部内联并靠注释提醒，无 API 收口。
3. **写冲突处理有 4 套彼此独立的重试策略 + 2 份逐字重复的 BUSY 判据 + 1 个死常量**，判据一旦变更必漏。
4. **后台任务以 0.25–1s 轮询 + 15–30s 心跳写 + 4 套以上恢复扫描为主**，13 条循环同进程；其中 2 条在**完全空闲**时仍发无条件写 DML（render tick 4Hz、external coordinator 2Hz×4 条），1 条节奏全硬编码不可配（image queue）。
5. **缺少 SQLite 锁等待/SQL 速率基线**，结构风险清楚，程度未量化——因此本文所有优先级按**结构风险**排序，不按实测排序。

**总体判断**：Lite 若是长期一等公民，应抽出**持久化适配层 + 统一任务运行时**；若 Lite 只是过渡，应限缩能力（单进程、单 Backend、并发=1），停止往通用路径堆碎片补丁。**这个分叉必须先决策**（§6.0），否则 §6.3/§6.4 的投入无法定档。

---

## 2. SQLite 兼容不规范清单

### 2.1 连接层（合理，边界未收口）

| 位置 | 行为 | 评价 |
| :--- | :--- | :--- |
| `db/session.py:129` `_configure_sqlite_engine` | 文件库：`foreign_keys=ON`(:146)、`busy_timeout`(:147)、`journal_mode=WAL`(:148-149)；`enable_wal = _is_file_sqlite_database(url)`(:140)，`:memory:` / `file::memory:` 不启 WAL(:154-160) | **正确且必要** |
| `db/session.py:139` | `busy_timeout_ms = max(1, int(settings.database_connect_timeout_seconds * 1000))`；默认 10.0 ⇒ **10000ms** | 单位是毫秒（见 C1） |
| `db/types.py:12` `UTCDateTime` | `process_bind_param`(:18) 仅在 sqlite 分支 `replace(tzinfo=None)`(:24)；`process_result_value`(:26) 双方言统一 `normalize_utc`(:29，来自 `core/time_utils`) | **必要适配**；绕过即回归时区 bug |
| `db/session.py:27` `AgentWriteGuardedAsyncSession` | `commit()`(:30-40) 先 `current_agent_run_write_fence().ensure_owned(...)`，`AgentRunWriteFenceLost` 时回滚 | 与 SQLite 无关，但与会话工厂同文件（工厂 :62，`class_=` 装配 :69），职责混杂 |
| `db/errors.py`(121 行) | **连接态**分类器：`is_database_connectivity_error` / `is_database_timeout_error` / `format_database_connectivity_error` / `describe_database_target` | 已是错误分类的落点，但**不含写冲突语义**；§6.3 应扩展它而非新建模块 |

`backend/app/db/` 当前只有 5 个文件：`__init__.py`(1)、`base.py`(7)、`errors.py`(121)、`session.py`(160)、`types.py`(29)。**没有** `dialect.py` / `compat.py` / `retry.py` / `locks.py`；§6.3 提议的 helper 一个都还不存在。

**问题**：没有「方言能力矩阵」与设计期约束；兼容性靠 `tests/integration/test_sqlite_migration.py`(369 行) + `tests/unit/test_sqlite_session.py`(68 行) + `tests/unit/test_utc_datetime.py`(120 行) 事后拦（注意跨两个目录）。

---

### 2.2 S1 — 时区双写语义藏在 TypeDecorator

- **现象**：`db/types.py:24` 在 sqlite 分支 `replace(tzinfo=None)`；:29 统一 `normalize_utc`。
- **风险**：历史 naive 值、直接用裸 `DateTime` 的新字段、原生 SQL 时间比较，都会再次踩坑。
- **规范目标**：模型层禁用裸 `DateTime`（lint/测试门禁）；比较一律 `utc_now()` + `UTCDateTime` 列。

---

### 2.3 S2 — 部分索引谓词双方言双写

同一谓词用 `sqlite_where=` 与 `postgresql_where=` 各写一遍。**已核实完整清单：6 个 model 文件、10 个索引**（模型在 `backend/app/models/`，不是 `db/models/`）：

| 表 | 索引 | 谓词 | 位置 |
| :--- | :--- | :--- | :--- |
| `render_attempts` | `uq_render_attempts_worker_epoch_active` | `active_occupancy = 1`（槽位唯一） | `models/render_attempt.py:31-32` |
| `page_screenshot_jobs` | `ix_page_screenshot_jobs_dedupe_active` | `status IN ('pending','running')` | `models/page_screenshot_job.py:26-27` |
| `ai_agent_external_batches` | — | `status = 'resuming'` | `models/ai_external_task.py:26-27` |
| `ai_agent_external_batches` | — | `status = 'collecting'` | `models/ai_external_task.py:33-34` |
| `ai_agent_runs` | — | `status IN ('running','paused','waiting_external','cancelling')` | `models/ai_agent_runtime.py:46-47` |
| `ai_agent_requirements` | — | `kind='external_job' AND status IN ('pending','resolving')` | `models/ai_agent_runtime.py:138-139` |
| `ai_chat_slot_bindings` | — | `scope = 'personal'` / `scope = 'global'` | `models/ai_llm.py:121-122,128-129` |
| `ai_image_slot_bindings` | — | `scope = 'personal'` / `scope = 'global'` | `models/ai_image_model.py:58-59,65-66` |

**原文漏计的一面**：同样的双写还重复出现在 **6 个迁移文件**里，改造时不能只改 model：

`20260730_0100_font_family_entities.py:525-526,1045-1046,1301,1417,1444`、`20260812_0100_split_chat_image_models.py:200-201,239-240`、`20260813_0100_unified_ai_external_tasks.py:103`、`20260814_0100_external_continuation_handoff_guards.py:68,76,84,92`、`20260818_0100_remove_self_delegation.py:49,72,80`、`20260910_0100_remote_render_service.py:120`。

**风险**：漏改一侧 → 某库唯一性或查询计划静默失效。`ai_llm` / `ai_image_model` 的索引物理上落在 slot-binding 表，命名与归属不一致，更容易漏。  
**规范目标**：`partial_index(name, columns, predicate, *, unique=False)` 一次描述谓词，生成双方言（§6.3）。

---

### 2.4 S3 — JSON / JSONB `with_variant` 别名定义 3 份

修正见 C3：不是逐列粘贴，而是**同一别名在 3 个文件各定义一次** + 1 处迁移内联：

| 位置 | 形态 |
| :--- | :--- |
| `models/render_request.py:17` | `JSONType = JSON().with_variant(JSONB(), "postgresql")` |
| `models/render_execution.py:17` | 同上（复用于 :33,51,71,72,73） |
| `models/render_attempt.py:17` | 同上 |
| `migrations/versions/20260910_0100_remote_render_service.py:24` | `sa.JSON().with_variant(postgresql.JSONB(), "postgresql")` 内联 |

**规范目标**：`app/db/types.py` 单点定义 `JSONPayload`，3 个 file-local 别名改 import；迁移侧用 helper 生成的类型，不再内联。

---

### 2.5 S4 — 迁移方言手工分支（高风险）

全仓**恰好 2 个**迁移裸判方言：

| 迁移 | 现象 | 位置 |
| :--- | :--- | :--- |
| `20260818_0100_remove_self_delegation.py` | 3 处 `if op.get_bind().dialect.name == "sqlite":`；SQLite 走 `batch_alter_table(..., recreate="always")`，PG 走原地 drop / `sa.inspect(op.get_bind())` | `:130,156,189`（PG 侧 :138） |
| `20260910_0100_remote_render_service.py` | `if bind.dialect.name in {"postgresql","sqlite"}:`（`bind = op.get_bind()` @:23）；内含**不可逆离线转换** | `:193`，转换体 `:191-206` |

`20260910_0100` 的不可逆转换原文（清除全部当前截图指针）：

```python
# 离线转换：清除无法证明新输入/profile 身份的当前有效截图指针，历史对象保留...
if bind.dialect.name in {"postgresql", "sqlite"}:
    op.execute("""
        UPDATE pages
        SET screenshot_storage_key = NULL, screenshot_version_no = NULL,
            screenshot_config_hash = NULL, screenshot_viewport_width = NULL,
            screenshot_viewport_height = NULL, screenshot_updated_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE screenshot_storage_key IS NOT NULL
    """)
```

`downgrade()` 文档串（`:210`）明写「不恢复历史截图指针」——**不可逆已确认**。

集成测试 `tests/integration/test_sqlite_migration.py` 在**固化补丁形态**而不是消灭补丁：

- `:195` `assert 'if op.get_bind().dialect.name == "sqlite":' in source`（要求迁移源码文本里必须出现方言分支）
- `:192-194` `assert 'postgresql_where=sa.text("status = \'collecting\'")' in source`（要求谓词字符串出现）
- `:31-32` `assert "thinking_enabled = 0" not in source` + `assert "thinking_enabled IS FALSE" in source`（禁止整数比较布尔）

**风险**：Lite 只验 SQLite、集群只验 PG，「同一 migration 语义等价」无机器证明；升级窗口数据分叉；而现有测试断言的是**源码字符串**，重构 helper 时会红，反而阻止收口。  
**规范目标**：迁移 helper 封装方言差异；**双库 contract test 对拍转换前后业务不变量**；测试断言行为而非源码文本；禁止 migration 里裸 `dialect.name`（helper 内部除外）。见 §6.5。

---

### 2.6 S5 — BUSY 判据两份逐字拷贝 + 4 套重试策略

**判据拷贝**（除常量名前缀与 docstring 外**逐字相同**：双方言 guard → `sqlite_errorcode & 0xFF ∈ {5,6}` → 小写消息子串）：

| 文件 | 内容 | 消费方 |
| :--- | :--- | :--- |
| `ai/run_event_writer.py:55-68`（常量 :14-16：`SQLITE_BUSY_ERROR_CODE=5`、`SQLITE_LOCKED_ERROR_CODE=6`、`SQLITE_LOCK_MESSAGES`） | 判据 A | `ai/platform_runtime.py:23`（用于 :357）、`ai/page_mutation_executor.py:20`（用于 :453） |
| `services/durable_job_lease_service.py:44-57`（常量 :18-20，同值同消息） | 判据 B（**同逻辑再抄一份**） | `services/page_screenshot_job_service.py:31`（用于 :504） |

无第三份定义。另有 `services/idempotency_service.py:181` 裸 `except OperationalError`，**完全不做锁判定**。

**重试策略（4 套 + 1 个驱动兜底 + 1 个死常量）**：

| 路径 | 实际策略 | 位置 |
| :--- | :--- | :--- |
| `platform_runtime._append_event_with_retry` | rollback + 指数退避，**最多 4 次**，base **25ms**（`0.025 * 2**attempt`） | `ai/platform_runtime.py:345-368`（常量 :64-65，rollback :360，sleep :367） |
| 截图终写 | rollback + 指数退避，**3 次**，base **50ms**（`0.05 * 2**attempt`） | `services/page_screenshot_job_service.py:437-516`（`SQLITE_LOCK_RETRY_ATTEMPTS=3` @:51，delay :506） |
| 页面 mutation 终写 | rollback + 指数退避，**3 次**，base **50ms**（**第 4 份同形拷贝，原文漏计**） | `ai/page_mutation_executor.py:442-457`（`max_attempts=3` @:445，rollback :452，sleep :455） |
| `idempotency_service` | 固定延迟表 `[50,100,200]ms`，重试的是 **SELECT（读）** | `services/idempotency_service.py:28,169-184` |
| ~~`SQLITE_BUSY_RETRIES = 3`~~ | **死常量**，全仓仅定义处引用（C2） | `services/idempotency_service.py:27` |
| 连接层 | `PRAGMA busy_timeout` **10000ms** 由驱动兜底 | `db/session.py:139,147` |

覆盖重试的测试：`tests/integration/test_page_screenshot_job_durability.py:129` 在 `test_screenshot_job_final_sqlite_retry_should_not_recapture`(:97) 内注入 `OperationalError("UPDATE pages", {}, sqlite3.OperationalError("database is locked"))`；`tests/integration/test_ai_platform_runtime_concurrency.py:159-237` monkeypatch `_SQLITE_EVENT_WRITE_MAX_ATTEMPTS=2`(:212) 并断言精确 rollback 次数(:233-234)。

**风险**：判据变更（驱动包装、新错误码）必漏一处；4 套次数/退避各不相同，PG 路径携带无效复杂度；死常量误导后续维护。  
**规范目标**：单一 `is_transient_write_error` + `run_with_write_retry`（§6.3）。**先统一实现、保留各自数值参数**，避免一次改动同时变更行为。

---

### 2.7 S6 — 锁序反转与驱动对象下钻

`ai/platform_runtime.py:328-343` 实际控制流：

```python
has_sqlite_write_transaction = await self._has_sqlite_write_transaction()      # :332
retry_after_rollback = (commit and not has_sqlite_write_transaction
                        and not self._session_has_pending_changes())           # :333-337
if has_sqlite_write_transaction:
    return await self._append_event_once(run_model, event, commit=commit)      # :338-339
async with _get_run_event_lock(run_id):                                        # :340
    if retry_after_rollback:
        return await self._append_event_with_retry(run_model, event)           # :341-342
    return await self._append_event_once(run_model, event, commit=commit)       # :343
```

`_has_sqlite_write_transaction`（`:463-470`，docstring :464 明写为避免**锁序反转**）下钻驱动：

```python
driver_connection = connection.sync_connection.connection.driver_connection   # :469
return bool(getattr(driver_connection, "in_transaction", False))              # :470
```

进程锁为 per-run：`_RUN_EVENT_LOCKS: WeakValueDictionary[str, asyncio.Lock]`(:67)，`_get_run_event_lock`(:1717-1724)。BUSY 重试仅在 `commit=True` **且**会话无 pending 变更时启用（`_session_has_pending_changes`:453-461，防 rollback 丢数据）。

**风险**（按 C6 修正）：

1. 降级是 fail-safe 的——非 SQLite 在 :466-467 直接 False，驱动属性消失时 `getattr(...,False)` 也是 False，两者都落回进程锁路径。**所以真实风险不是「误判导致错误」，而是「优化静默失效」**：换驱动后退回全量走进程锁，表现为吞吐下降而无任何告警。
2. 此逻辑同时服务 PG（探测恒 False）与 SQLite，**没有方言策略对象**；`driver_connection` 是全仓 `app/db/` 之外的**唯一**一处（`app/db/` 内部反而没有）。
3. 与进程内锁（内存篇 M4）纠缠：换分布式锁必须整段重设计锁序。
4. `tests/integration/test_ai_platform_runtime_concurrency.py:240-274` 把补丁测成契约——`test_append_event_should_avoid_process_lock_after_sqlite_write` 用 monkeypatch 让 `_get_run_event_lock` 抛 `AssertionError("不应在持有 SQLite 写锁后申请进程级 run 锁")`(:258-263)，先做 UPDATE 开写事务(:252-256) 再断言 append 成功。收口到 `app/db` 时这条测试必须同步迁移，不能简单删。

**规范目标**：`holds_write_lock(session)` 收口到 `app/db/locks.py`；业务禁止 `driver_connection`（加 grep 门禁）；探测失效时**打点告警**而不是静默降级。

---

### 2.8 S7 — 业务方法内联 SQLite 事务技巧

| 技巧 | 位置 | 意图（原注释） |
| :--- | :--- | :--- |
| 候选 SELECT 后立即 `session.commit()` | `services/durable_job_lease_service.py:81-83` | :82「候选读取不应维持 SQLite 读事务，否则并发认领时可能升级写锁失败。」 |
| 空队列先 SELECT 再决定 UPDATE | `services/durable_job_lease_service.py:221-233` | :221-222「定时恢复在空闲期会频繁执行。先只读筛选，避免 SQLite 因无命中 UPDATE 反复争抢 writer 锁」；:231「只结束本次只读事务，不发送任何 UPDATE。」 |
| 诊断前 `_release_session_before_diagnostics` | `services/code_check_service.py:403-407`（调用 :147,228,317） | :404「结束 artifact 准备阶段的只读事务，避免等待 Runtime/Chromium 时占用 SQLite 锁。」 |
| `lock_scheduler_state_for_queue_admission` 假写抢锁 | `services/rendering/repository.py:59-67`（`state.version += 1` @:65，flush :66） | :63-64「UPDATE 在 PostgreSQL 中锁住单行，在 SQLite 中提前取得写事务，使 queue_size/workspace_queue 与后续 INSERT 不再存在检查竞态。」 |

**问题**：正确但内联；SQLite 原因写在业务注释里；在 PG 上「删掉多余 commit」的重构会破坏 Lite。

**按 C5 修正**：最后一项**不能**描述为「PG 上无意义版本递增」——PG 侧这次 UPDATE 是**故意的单行锁**（SELECT-FOR-UPDATE 等价物），删掉会重新引入准入竞态。无意义的只是 `version` 的**数值**。收口时保留写、改名表达意图（如 `acquire_admission_lock(state)`），并去掉「假写」这个会误导重构的措辞。

**规范目标**：`read_probe()` / `commit_end_read()` / `acquire_admission_lock()` 等命名 API；业务只调语义，SQLite 原因写进 helper docstring。

---

### 2.9 S8 — 伪布尔与状态字符串约定

- `models/render_attempt.py:48`：`active_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, default=1)`（:47 注释：1=占用 Worker/epoch 槽位，终态清理后置 0）；迁移侧同样 `sa.Integer()`（`20260910_0100:92`）。**全仓无任何 `BoolInt` 式别名**。
- 状态值、错误码散落字符串字面量（`"pending"` / `"running"` / `"resuming"` / `"collecting"` / `"database is locked"`…），并被 `test_sqlite_migration.py:192-194` 以源码字符串形式断言。

**规范目标**：`BoolInt` 类型别名 + 状态/错误码枚举模块。范围大，§6.3 列为**可选项**，不阻塞其余收口。

---

### 2.10 S9 / S10 归属说明

旧合并稿的 10 条清单中：

- **S9**（`memory://` 与 SQLite 持久化语义分裂）⇒ 已移入内存篇 §3.1，本文不重复。
- **S10**（定时任务写放大）⇒ 即本文 §3，不再占用 S 编号。

因此本文的兼容债条目是 **S1–S8 共 8 类**；旧稿「10 类」的说法以本条为准。

---

## 3. 定时任务与后台循环（SQLite 写路径视角）

### 3.1 任务全景（已核实实际值）

「节奏来源」列标注 **cfg** = 有配置项，**hard** = 硬编码无配置项。

| 任务 | 注册 | 轮询 | 空闲写库？ | 心跳 | 租约 | 恢复扫描 | 节奏来源 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `render-coordinator` | `main.py:106-109` | **0.25s**（下限 50ms，`coordinator.py:120`） | **是（4Hz）**：`expire_requests` 每 tick **无条件 UPDATE**（`repository.py:874-897`）+ 每 tick 每 worker 一次 `upsert_worker_heartbeat` UPDATE（`repository.py:147-196`，:193 写 `last_heartbeat_at`，`coordinator.py:210` commit） | Worker 表每次能力探测 | `render_attempt_lease_seconds=180` | `release_expired_attempt_leases` 同 tick（先查后写，`repository.py:461-517`） | cfg `render_scheduler_poll_interval_seconds=0.25`(`config.py:66`) |
| Render `wait_for_terminal` | `coordinator.py:122-175` | **100ms**（:168） | 读为主；`drive_dispatch=True` 时驱动 `ensure_progress`(:136→:67-84)，按 0.25s 节流并触发整个 `tick()` | — | — | — | **hard** 0.1 |
| `api-mutation-worker` | `main.py:115-118` | 空闲 **1.0s** / 异常 **2.0s**（`mutation_job_service.py:891,897`） | 认领 SELECT(limit 10,:349-361) + CAS 条件 UPDATE(:366-381) | **15s**/任务（`_heartbeat_loop`:421-454） | 45s | — | **hard** 1.0/2.0；cfg `mutation_job_heartbeat_seconds=15`、`mutation_job_lease_seconds=45` |
| `api-mutation-sweeper` | `main.py:119-122` | **30s**（:906）/异常 5s(:913) | **否**：`recovered_count>0` 才 commit(:871-873) | — | — | 孤儿 `running`（`recover_expired_running_jobs`:813-875） | cfg `mutation_job_recovery_interval_seconds=30` |
| `ai-page-mutation-queue` → `ai-page-mutation-worker-N` | `main.py:124-127`；worker 派生 `page_mutation_queue.py:68-74` | 唤醒或 **0.5s**（`GenerationWakeup.wait`，:338；下限 0.05 @:311） | 认领 | **30s** job（`_heartbeat_job_lease`:860-895） | 300s | 启动一次（`recover_interrupted_ai_page_mutation_jobs_on_startup`:87-107 ← `main.py:100`） | cfg `ai_page_mutation_poll_interval_seconds=0.5`、`durable_job_heartbeat_seconds=30`、`durable_job_lease_seconds=300` |
| **`ai-external-task-coordinator`** | `main.py:132-135` | **0.5s**（复用 `ai_page_mutation_poll_interval_seconds`，`external_task_queue.py:55`，**无专属配置项**） | **是（2Hz，最严重）**：每轮 `synchronize_external_task_states`(:84-173，**无条件 commit @:173**) + `recover_external_continuations`(:176-241) + `audit_external_state_consistency`(:244-427，**无条件 commit @:427**)；audit 每轮调 `cleanup_terminal_run_external_state` ⇒ **4 条无条件 UPDATE**（`external_terminal_cleanup.py:45-67,68-76,77-85,86-94`）；每 120 轮（≈60s）再跑 `cleanup_expired_external_results`(:449-483) | Batch 心跳 30s（`_heartbeat_batch`:717-751） | 300s | 每轮（仅 `if batches:` 才 commit @:240，空闲免写） | **hard**（复用页面 poll 键） |
| `ai-image-generation-queue` | `main.py:128-131` | **0.5s**（`image_generation_queue.py:90`）/异常 1s(:95) | **是（2Hz）**：每轮 `_promote_due_provider_jobs` **无条件 UPDATE**(:471-487) + cancel 探测 SELECT(:490-530) | **30s**（`_HEARTBEAT_SECONDS`:39，用于 :370-373） | **120s**（`_LEASE_SECONDS`:38，用于 :107,390）——**注意不是 300s** | 启动(:43-68 ← `main.py:101`) **且每轮空闲重跑同一恢复**(:89) | **全 hard，零配置项**（N1） |
| `ai-component-mutation-queue` → `ai-component-mutation-worker-N` | `main.py:136-139`；派生 `component_mutation_queue.py:35-41` | **0.5s**（:96；纯 `asyncio.sleep` @:124，**无 GenerationWakeup**） | 认领 | **30s**（:225-229） | 300s（`max(durable_job_lease_seconds, 3×heartbeat)`，:97,227） | 启动（`recover_interrupted_component_mutation_tasks`:52-89 ← `main.py:102`） | cfg（复用页面 poll 键） |
| `page-screenshot-queue` | `main.py:105` → `:343-349` | **1.0s**（`page_screenshot_queue_worker.py:77`，下限 0.1） | 认领 | 30s（`min(30, lease//2)`，:187-188） | **300s**（走 `durable_job_lease_seconds`；`page_screenshot_job_lease_seconds=180` 是死 fallback，C4） | 启动(:158-170 ← `main.py:97`) **+ 循环内每 30s**(:79,89-91) | cfg `page_screenshot_queue_poll_interval_seconds=1.0` |
| `asset-render-hint-backfill-queue` | `main.py:110` → `:352-358` | **1.0s**（`asset_render_hint_backfill_job_service.py:467`） | 认领 | **无 DB 心跳** | **无 DB 租约**；180s 是 Redis 锁 TTL（`SET NX EX`，:377-388,513-516；`memory://` 回落 `InMemoryRedis`，`redis_runtime_client.py:86-87`） | 启动(:500-510 ← `main.py:98`)，**无 lease/过期谓词**，捞全部 `running`(:214-235)，max_attempts=**2**(:37) | cfg poll；**hard** 锁 TTL 语义（N4） |
| `runtime-artifact-sweeper` | `main.py:111-114` | **30s**（`runtime_artifact_store.py:223`） | **否**（零 DB 访问）；`sweep_expired`(:176-179) → duck-typing `getattr(client,"purge_expired",None)`(`redis_runtime_client.py:74`)，真 Redis 返 0 | — | — | — | cfg `runtime_artifact_sweep_interval_seconds=30.0` |
| `ai-model-catalog-sync` | `main.py:140-144` | **3600s** 唤醒（`ai_model_catalog_service.py:346`） | **否**：唤醒后 `SELECT ... FOR UPDATE` 单例状态行(:234)，距上次成功 <24h 直接返回不提交(:241-242)；真正写目录（`_apply_catalog`:249-324）或 304 状态触碰(:192-198) **最多 1/24h** | — | `LEASE_DURATION=10min`(:30) | — | **hard** 3600；`SYNC_INTERVAL=24h`(:29)；cfg 开关 `ai_model_catalog_sync_enabled` |
| `AgentBackgroundRunManager` | `create_app` @`main.py:192`；lifespan 读 :87，shutdown :152 | **不是轮询循环**（C7）：按需派生 `ai-agent-run-{run_id}` task（`background_run_manager.py:46-49`），空闲不轮询 | 模型执行中写事件 | 进程内 | — | 启动收敛 `AI_RUN_PROCESS_STOPPED`（`ai/run_recovery.py:12`） | — |

**空闲态并发循环数：13**（11 条 lifespan 任务 + `ai-page-mutation-worker-N` + `ai-component-mutation-worker-N`；默认 `ai_page_mutation_concurrency=1`，`config.py:94`，**对所有数据库生效，无 SQLite 分支**）。其中 12 条在亚分钟级触碰 DB/Redis，只有 catalog-sync 睡 3600s。

**生命周期**：全部挂在 FastAPI `lifespan`(`main.py:71`)。**已核实无独立 Worker 进程入口**：全仓无 `QUEUE_WORKERS_ENABLED` / `app.workers`；`backend/pyproject.toml` 无 `[project.scripts]`，唯一入口是 `app.main:main()` → uvicorn(`main.py:390-401`)；`backend/app/scripts/` 只有一次性维护 CLI。Renderer 是唯一独立进程（uv workspace 成员 `backend` / `renderer` / `packages/render-contracts`）。

配置全表（含原文未提及的调优项与硬编码项）见 **附录 A**。

### 3.2 四种模式及其 SQLite 代价

**A. 亚秒轮询认领**  
`while True: claim → empty? sleep`。只有页面队列有进程内代次唤醒（`GenerationWakeup`，`ai/page_mutation_wakeup.py:8`，实例 :46-47；见内存篇 §3.4），component / image / screenshot / external **全是纯 sleep**。**跨进程一律退回轮询**。多队列叠乘 ⇒ 空闲 SELECT/写探测风暴。

**B. 独立心跳协程定期 UPDATE**  
每执行中任务 15–30s 一次续租写（`_heartbeat_job_lease` / `_heartbeat_batch` / `MutationJobService._heartbeat_loop` / screenshot heartbeat）。长诊断 × 多任务时与事件追加、终写抢单写锁。  
→ **不能删租约**；应**批量续租或惰性延长**（阶段边界 + 余量）。注意 image queue 的 lease 只有 **120s** 且硬编码，与 `durable_job_lease_seconds=300` 不一致，也不受 `config.py:279-285`「lease ≥ 3× heartbeat」校验器约束。

**C. 4 套以上 sweeper / recover（原文写「三套」，见 C8）**

| 实现 | 过期谓词 | max_attempts | backoff | 空闲写 |
| :--- | :--- | :--- | :--- | :--- |
| `durable_job_lease_service.recover_expired_running_jobs:206-310` | `lease IS NULL OR <= now`(:218) | 参数化：页面 3(`page_mutation_queue.py:41,96`)、截图 3(`page_screenshot_job_service.py:50,586`) | 无（立即重入 pending） | 先查后写，空则不 UPDATE(:223-233)——**已为 SQLite 专门加固** |
| `MutationJobService.recover_expired_running_jobs:813-875` | `lease <= now`，**缺 `IS NULL` 分支**(:830) | 行内 `max_attempts`（默认 3）；requeue 判定 `attempt+1 < max`(:834)——**与通用实现差一** | 固定 `next_attempt_at = now+5s`(:846) | `recovered>0` 才 commit(:871) |
| `RenderRepository.release_expired_attempt_leases:461-517` | `lease IS NULL OR <= now`(:476-481)，limit 20 | attempt 级无；父请求受 `render_max_attempts=3`(:538) | 固定 `retry_after = +2s`(:549) | 先查后写，但**被放在一个已经写过的 tick 里** |
| `recover_external_continuations:176-241` | `resuming` + (`lease IS NULL OR <= now`)(:186-187) | 无（单次；按 run 状态重入 `ready` 或 fail/cancel） | 无 | `if batches:` 才 commit(:240) |
| `recover_interrupted_image_generation_jobs_on_startup:43-68` | — | 3 | 无 | **每轮空闲 0.5s 重跑**(:89) |
| `recover_interrupted_component_mutation_tasks:52-89` | — | 3(`_MAX_ATTEMPTS`:27) | 无 | 仅启动 |
| `asset_render_hint_backfill.recover_interrupted_jobs:214-235` | **完全没有 lease/过期谓词**，捞全部 `running` | **2**(`:37`) | 无 | 仅启动 |
| `page_screenshot_queue_worker` in-loop recovery | — | — | — | **每 30s**(:79,89-91)，与启动恢复并存 |
| `cleanup_expired_external_results:449-483` | 保留期 **7d 硬编码**，limit 100 | — | — | ≈60s |
| `cleanup_terminal_run_external_state`(`external_terminal_cleanup.py:28-100`) | 终态 run 子查询 | — | — | **4 条无条件 UPDATE / 每 0.5s** |
| 死代码：`_run_continuation_coordinator`(`page_mutation_queue.py:462-496`) 的 30s recovery(:477-479) | — | — | — | **从未启动**（N3） |
| 仅启动：`recover_interrupted_build_jobs_on_startup`(`project_build_service.py:434`)、`recover_interrupted_agent_runs_on_startup`(`ai/run_recovery.py:12`) | — | — | — | — |

阈值、max_attempts、backoff **各自为政**；external 把 recover+audit 绑进 0.5s 主循环，**空闲成本最高**。

**D. 等待 API 自旋**  
`wait_for_terminal` 100ms 轮询，且默认 `drive_dispatch=True` 会顺带触发整个 `tick()`；长任务读放大，与 SSE DB 回放轮询同类。生产调用方 `services/rendering/domain_facade.py:263-267`。

### 3.3 冲突场景（SQLite 单写者）

| 场景 | 机制 | 后果 |
| :--- | :--- | :--- |
| external 2Hz（3 扫描 + 4 条无条件 UPDATE + 2 次无条件 commit） × page worker 2Hz claim × image queue 2Hz（1 条无条件 UPDATE + 恢复重跑） | 三个 2Hz 写者高频拿写事务 | locked、认领延迟抖动 |
| render tick 4Hz：`expire_requests` 无条件 UPDATE + 每 worker 心跳 UPDATE | 与截图终写、Mutation finalize 交错 | **零渲染流量也持续写**；busy_timeout 10s 排队 |
| 长诊断期间 N 条心跳 UPDATE（15–30s） | 插进事件追加/终写事务 | 触发 S5 的 4 套重试路径、延迟尖峰 |
| 启动时多个 recover 并发（page/image/component/screenshot/asset/build/run 共 7 处） | 并发 UPDATE 同租约表 | 启动写风暴（部分已靠「先读后写」缓解，asset 侧无谓词最危险） |
| `wait_for_terminal` 100ms 自旋 + `ensure_progress` 触发整 tick + sweeper | 读锁/页缓存压力，且读路径会**反向引发写** | 混合负载 P95 不稳 |

**空闲态无条件写 DML 的确切来源（可直接当基线口径）**：

| 来源 | 频率 | 位置 |
| :--- | :--- | :--- |
| `expire_requests` UPDATE | 4Hz | `rendering/repository.py:874-897` |
| `upsert_worker_heartbeat` UPDATE × 可达 worker 数 | 4Hz | `rendering/repository.py:147-196` |
| `cleanup_terminal_run_external_state` 4 × UPDATE | 2Hz | `ai/external_terminal_cleanup.py:45-94` |
| `synchronize_external_task_states` 无条件 commit | 2Hz | `ai/external_task_queue.py:173` |
| `audit_external_state_consistency` 无条件 commit | 2Hz | `ai/external_task_queue.py:427` |
| `_promote_due_provider_jobs` UPDATE | 2Hz | `ai/image_generation_queue.py:471-487` |

即**零业务负载下**（W = 可达 Renderer worker 数，默认部署 W=1）：

```text
render tick        4Hz × (1 条 expire UPDATE + W 条 heartbeat UPDATE)  = 4×(1+W) = 8
external cleanup   2Hz × 4 条无条件 UPDATE                              =           8
external commit    2Hz × 2 次无条件 commit（sync :173 + audit :427）     =           4
image promote      2Hz × 1 条无条件 UPDATE                              =           2
                                                                       ─────────────
                                                              合计 ≈     22 次/秒
```

约 **22 次写 DML / 写事务动作每秒**，其中 18 条是写 DML、4 次是空提交。这是本文能给出的最强量化结论，但仍是**从代码静态推导**，不是实测——实测口径见 §6.2。

**未量化**：真实 SQL/s、`database is locked` 次数、busy_timeout 耗尽比、最长写等待、各 tick P50/P95。§6.2 要求先采基线。

---

## 4. 风险分级（仅 SQLite / 任务写路径）

### 4.1 分级表

| 级别 | ID | 问题 | 证据 |
| :--- | :--- | :--- | :--- |
| **P0** | Q0 | 页面校验跨阶段语义仍把 Renderer 不可用报成通过并写库（**HEAD `44282d6` 复核：仍未修**） | `code_check_service.py:409-472`；§6.1 |
| **P0** | Q4 | 迁移方言分支无双库语义等价证明；含不可逆截图指针清除；现有测试断言源码文本而非行为 | `20260910_0100:191-206,210`；`test_sqlite_migration.py:31-32,192-195` |
| **P1** | Q1 | 13 条循环 × 亚秒轮询 × 心跳写放大，缺锁/SQL 基线 | §3.1、§3.3 |
| **P1** | Q2 | external coordinator 每 0.5s 跑 sync + recover + audit，并触发 4 条无条件 UPDATE | `external_task_queue.py:54-68`；`external_terminal_cleanup.py:45-94` |
| **P1** | Q3 | S6 驱动下钻锁序探测（fail-safe 但静默失效，且被测试固化） | `platform_runtime.py:463-470` |
| **P1** | Q10 | **新增**：image queue 节奏全硬编码（0.5/30/120s）+ 每轮空闲无条件 UPDATE + 每轮重跑恢复；lease 120s 脱离 `lease ≥ 3×heartbeat` 校验器 | `image_generation_queue.py:38-40,89,471-487` |
| **P2** | Q5 | S5 BUSY 双份逐字拷贝、4 套重试策略、1 个死常量 | §2.6 |
| **P2** | Q6 | S2/S3/S8 双方言约定分散（10 索引 + 6 迁移重复谓词、3 份 JSONType 别名、无 BoolInt） | §2.3、§2.4、§2.9 |
| **P2** | Q7 | S7 业务内联事务技巧（含被误述的「假写」） | §2.8 |
| **P2** | Q8 | **4 套以上**租约恢复语义不统一（谓词、max_attempts、backoff、差一 bug） | §3.2 C |
| **P2** | Q9 | 等待 API / SSE 无跨进程完成通知；`wait_for_terminal` 100ms 自旋还会反向触发 tick | `coordinator.py:122-175` |
| **P2** | Q11 | **新增**：死代码与死配置误导维护——`_run_continuation_coordinator`(:462-496) 从未启动、`page_screenshot_job_lease_seconds=180` 永不生效、`SQLITE_BUSY_RETRIES` 无引用 | N3、C4、C2 |
| **P2** | Q12 | **新增**：`asset-render-hint-backfill` 恢复扫描无 lease 谓词、max_attempts=2 与他处不一致；180s 只是 Redis 锁 TTL，无 DB 租约/心跳 ⇒ 与「持久化租约队列」叙事不符 | `asset_render_hint_backfill_job_service.py:37,214-235,377-388` |

### 4.2 ID 映射

| S（兼容债） | Q（风险） | Phase（整改） |
| :--- | :--- | :--- |
| — | Q0 | P0 |
| S4 | Q4 | P4 |
| S1 | （含在 S2/S3 门禁内） | P2 |
| S2 / S3 / S8 | Q6 | P2 |
| S5 | Q5 | P2 |
| S6 | Q3 | P2 |
| S7 | Q7 | P2 |
| （§3 任务写路径） | Q1 / Q2 / Q8 / Q9 / Q10 / Q11 / Q12 | P1（基线）→ P3（任务运行时） |
| （部署边界） | Q1（容量前提） | P5 |

Q0 的完整事实链与文档冲突证据见 [`docs-temp-issue-status-2026-09.md`](./docs-temp-issue-status-2026-09.md) §2 P0；本文 §6.1 只给整改步骤与验收。

---

## 5. 明确不做 / 误方向

| 不做 | 原因 |
| :--- | :--- |
| 删除持久化租约改纯内存队列 | 丢重启/跨实例正确性（亦与内存篇边界冲突） |
| 删 Runtime 编译只留 Chromium | 失败集合不同 |
| SQLite 上引入分布式锁中间件 | 过度；先减写者与频率 |
| 用缓存/只读副本掩盖轮询 | 问题在任务模型 |
| 无基线就写死 1.5GB / 降延迟 40% | 未验证假设 |
| **删掉 `lock_scheduler_state_for_queue_admission` 的「假写」** | 按 C5，PG 侧那是**必要的单行锁**；删掉重新引入准入竞态。只改名与注释，不删写 |
| **直接删掉 `test_sqlite_migration.py` 的源码文本断言** | 它当前是唯一挡住「迁移里整数比较布尔」的闸；必须先换成行为断言（P4），再删文本断言 |
| **在收口 S5 时顺手统一重试次数/退避** | 会把「结构重构」与「行为变更」混在一次改动里，出问题无法归因。先统一实现、保留各自数值 |
| **把 `_has_sqlite_write_transaction` 简单删掉** | 会退回全量进程锁路径并触发 `test_ai_platform_runtime_concurrency.py:240-274` 红；必须连同测试一起迁移到 `app/db` |
| **先做 Backend 多副本 / Browserless** | 前置条件未满足（Q0 未关、无基线、`memory://` 与进程内锁未切割）；见 issue-status §5.2 |

---

## 6. 整改计划（SQLite 专项）

### 6.0 前置决策与阶段总览

**决策门 D1（必须先答）**：SQLite Lite 是**长期一等公民**还是**过渡形态**？

| 选项 | P0 | P1 | P2 | P3 | P4 | P5 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A. 长期一等公民** | 必做 | 必做 | **全做** | **全做** | 必做 | 必做 |
| **B. 过渡形态** | 必做 | 必做 | 只做 `errors`+`retry`+`locks`（正确性风险收口），跳过 `types`/`indexes`/枚举 | 只做「空闲零写 + 死代码清理 + 空队列退避」，跳过统一任务运行时 | 必做（数据不可逆风险与部署形态无关） | 必做 |

未决策时的默认执行序：**P0 → P1 → P5 → P4 → P2 → P3**。理由：P0/P1/P5/P4 在两种选项下都必做且互不冲突；P2/P3 的投入规模取决于 D1，应在基线（P1）出来后再定档。

**阶段依赖**：

```text
D1 决策 ──┐
          ├─► P0 正确性(Q0) ──► P1 基线 ──┬─► P3 任务运行时(Q1/Q2/Q8/Q9/Q10/Q11/Q12)
          │                              │
          └─► P5 Lite 边界 ──────────────┤
                                         │
             P4 迁移等价(Q4) ────────────┤   （P4 独立，可与 P1 并行）
                                         │
             P2 持久化适配层(Q3/Q5/Q6/Q7) ┘   （P2 是 P3 的前置：P3 要用 is_transient_write_error / read_probe）
```

| 阶段 | 目标 | 关闭的风险 | 阻塞关系 | 可独立发布 |
| :--- | :--- | :--- | :--- | :--- |
| P0 | 页面跨阶段校验语义正确 | Q0 | 无 | 是 |
| P1 | 有可复现的 SQLite 写路径基线 | Q1（度量部分） | 依赖 P0（否则基线含错误通过路径） | 是（只加打点） |
| P2 | 持久化适配层收口方言 | Q3 Q5 Q6 Q7 | P3 的前置 | 每步独立 |
| P3 | 任务运行时：空闲零写 + 节奏统一 | Q1 Q2 Q8 Q9 Q10 Q11 Q12 | 依赖 P1（定档）+ P2（用 helper） | 每队列独立 |
| P4 | 迁移双方言等价可证明 | Q4 | 独立 | 是 |
| P5 | Lite 单实例边界固化 | Q1（前提部分） | 独立 | 是 |

---

### 6.1 P0 — 正确性：页面跨阶段校验语义（Q0）

**现状（已复核，仍未修）**：`code_check_service.py:409-472` 的 `_append_page_render_diagnostics` 只改 3 个字段——`diagnostics`(:462)、`layout_analysis`(:463-467)、`summary`(:470-471)，`success`/`status`/`retryable` 经 `**result` 原样继承编译结果。合并只在编译已通过时发生（`_dispatch_diagnostics` 门 :372 → `_is_runtime_diagnostics_passed`:512-515），因此 Renderer 不可用 ⇒ 结果仍 `success=true / status="passed"`，`summary` 甚至写「代码检查通过」。不可用结果本身是正确的：`page_render_diagnostics_service.py:94-97` 捕获 `RENDER_SERVICE_UNAVAILABLE` / `RENDER_RESULT_LOST` / `RENDER_DEADLINE_EXCEEDED`，`:100-129` `_build_unavailable_result` 返回 `status="unavailable" / retryable=True / severity="warning" / source="infrastructure"`。

**违反的已成文契约**：

- `docs/developer/backend/resource-queues.md:25`：「Renderer 离线或执行不可用时返回 `RENDER_*` 基础设施错误，**不能映射为『源码有错』或『检查通过』**。」
- `docs/developer/backend/remote-render-service-design.md:453`：「页面/组件校验区分内容失败与执行不可用；**执行不可用不能映射为『源码有错』或『检查通过』**。」（错误分类表 :434 将 `RENDER_SERVICE_UNAVAILABLE` 列为 infrastructure）

**步骤**：

1. **分阶段字段**。页面校验结果引入 `stages: {compile, render}`，对齐组件侧已有形态（`component_validation_service.py:88-93,115`）。`render` 取值 `passed | warning | unavailable | failed | skipped`。全仓当前**不存在** `compile_status` / `render_status` / `render_availability`（已 grep 确认）。
2. **改合并语义**。`_append_page_render_diagnostics`：当 render 阶段为 `unavailable` 时，不得输出 `status="passed"`；改输出 `status="unavailable"`、`retryable=True`，并改写 `summary`（禁止「代码检查通过」措辞）。内容级 `warning` 保持 `passed` 不变。
3. **单一判定谓词**。新建 `app/services/validation_result.py`，提供 `is_validation_passed(result, *, require_render: bool = True)`。替换现有 **3 份逐字相同**的拷贝 + **2 个同义谓词**：
   - `ai/tools/page/apply_page_edits.py:128-131`
   - `ai/tools/project/project_pages.py:248-251`
   - `ai/tools/component/component_library.py:540-543`
   - `code_check_service._is_runtime_diagnostics_passed:512-515`
   - `component_validation_service._compile_passed:223-226`
   
   现有 import 关系需同步改：`page_mutation_planner.py:14-16`、`page_mutation_executor.py:28-30`（引 `project_pages` 版）；`component_mutation_planner.py:14`、`component_mutation_executor.py:15`（引 `component_library` 版）。组件侧调用点 `require_render=False`（组件只做契约 + 编译）。
4. **写入门槛**。以下 gate 在 render `unavailable` 时必须拒写：`apply_page_edits.py:100`（通过则 :102-109 建新版本）、`project_pages.py:108`、`page_mutation_executor.py:225`（create；失败走 `_finish_without_page_write`:226-231）、`:370`（update；:371-376 后 :381+ `save()`）、`page_mutation_planner.py:100,160`。  
   提供**显式可审计**逃生口：`skip_visual_verification: bool = False` 参数，为真时允许写入但必须在 job result 与 AI 事件里留痕；默认关闭。
5. **External API 一致性**。`api/routes/external/validate.py:50-56,85` 当前 `valid = bool(result.get("success"))`——Renderer 故障期间会对外报 `valid=true`。改为 `valid` 与 `status` 一致：`unavailable` ⇒ `valid=false` + 明确基础设施错误码，不得静默 200/true。
6. **文档回填**。若最终语义与 `resource-queues.md` / `remote-render-service-design.md` 措辞有出入（例如引入 `skipped`），同步更新两处；AGENTS.md §5 要求契约变化先落文档。

**验收标准**：

- [ ] 新增跨阶段契约测试：**Runtime 编译通过 + Renderer 不可用 ⇒ `success is not True` 且 `status == "unavailable"`，且 `pages` / `page_versions` 无新行**。AI 写工具路径与 External API 路径**各一条**。（当前**确认缺失**：`test_ai_page_mutation_queue.py` / `test_ai_page_write_tools.py` / `test_page_mutation_planner.py` 全文无 `unavailable`；队列集成测试把 `check_page_code` stub 成 `{"success":True,"status":"passed"}` 并断言**有**新行，见 `test_ai_page_mutation_queue.py:458-462,602-607`。）
- [ ] 现有只验证结果对象的测试保持绿：`tests/unit/test_render_control_plane.py:389-398` `test_page_unavailable_is_not_content_error`、`tests/unit/test_browser_capture_service.py:59-71`、`test_render_control_plane.py:479-519`。
- [ ] 内容级 warning 语义不回归：`tests/contracts/test_code_check.py:369-415` 仍应通过（render warning 保持 `success=True`）。
- [ ] 组件侧语义不变：`component_validation_service.py:97-124` 的 `success=False / status="unavailable" / retryable=True / stages.compile="unavailable"` 仍被 gate 拒绝。
- [ ] 防漂移测试：全仓 `def _is_validation_passed` 定义数 == 0，`is_validation_passed` 定义数 == 1（AST 或 grep 断言）。

**验证命令**：`pnpm run test:backend:unit`、`pnpm run test:backend:api`、`pnpm run test:backend:integration`、`pnpm run test:contracts`、`pnpm run test:e2e`（默认 auth+smoke）。

**风险与回滚**：会把此前「看起来通过」的写入变成用户可见失败，Lite 上 Renderer 未起时尤其明显。缓解：(a) `skip_visual_verification` 显式开关；(b) 错误文案给出可操作指引（指向 Renderer 状态）；(c) 发布前跑一次 E2E smoke。回滚只需还原步骤 2 的合并分支——步骤 1/3 是纯结构改动，可保留。

---

### 6.2 P1 — 可观测：SQLite 写路径基线（Q1）

**目标**：把 §3.3 的静态推导换成实测，作为 P3 定档的唯一依据。**本阶段只加打点与采集，不改任何节奏。**

**打点位置**：

| 指标 | 埋点 |
| :--- | :--- |
| SQL 数与耗时（读/写分列，按 loop 名归因） | `db/session.py` 挂 SQLAlchemy `before_cursor_execute` / `after_cursor_execute`；loop 名用 `contextvars` 从各 worker 入口传入 |
| 写冲突次数与判据命中 | 在 `is_sqlite_lock_error` 两份拷贝（`run_event_writer.py:55-68`、`durable_job_lease_service.py:44-57`）各加计数——P2 合并后自然收口为单点 |
| 心跳/认领/恢复的**有效性** | 记录每次 UPDATE 的 `rowcount`；`rowcount == 0` 即「无效写」 |
| 空轮询比例 | 各 claim 返回 `None` 次数 / 总轮询次数 |
| 每 loop tick 耗时 | P50 / P95，按 task name 分组 |
| busy_timeout 是否耗尽 | 捕获 `OperationalError` 时记录已等待时长（对比 10000ms 上限） |

**采集口径**（两种负载各一轮，Lite 目标机 2C4G）：

1. **空闲 10 分钟**：无用户请求、无 AI Run、Renderer 可达。
2. **混合负载**：5 个页面变更 + 截图 + 预览并发。

每轮记录：SQL/s（读写分列）、写事务/s、`database is locked` 次数、busy_timeout 命中与耗尽比、最长写等待、各 tick P50/P95、容器 RSS。

**产出**：`docs/temp/baseline-sqlite-2026-09.md`，含采集命令、原始数据与本文 §3.3 静态推导值的对照。

**决策门 D2**（用**结构性判据**而非拍脑袋数值，避免重犯「1.5GB / 40%」的错误）：

| 判据 | 若成立 | 若不成立 |
| :--- | :--- | :--- |
| 空闲态写事务数 > 0 | P3 按 §6.4 顺序全做，**目标：空闲态零写 DML** | P3 降级为「只做退避 + 死代码清理」 |
| 混合负载出现 `database is locked` | P2 的 `run_with_write_retry` 提为 P3 前置必做 | P2 可按 D1 选项裁剪 |
| 某 loop 的 tick P95 > 其轮询间隔 | 该 loop 优先开刀（当前静态推导指向 render tick 与 external coordinator） | 按 §6.4 既定顺序 |

**验收**：基线文档存在且可复现（命令 + 环境 + 原始输出）；打点在 PG 上零行为变更（只是计数）。

**风险**：`before/after_cursor_execute` 监听器本身有开销 ⇒ 用配置开关默认关闭，仅采集期开启。

---

### 6.3 P2 — 持久化适配层（`app/db/`）

**落点原则**：`app/db/` 现只有 5 个文件，`errors.py` 已是错误分类器 ⇒ **扩展它**，不新建平行模块。每一步独立可发布、独立带防漂移测试。

**执行顺序：2a → 2b → 2c → 2d → 2e → 2f**（前三步收正确性风险，后三步收维护成本）。

| 步 | 新增/扩展 | 收口内容 | 替换点 | 防漂移门禁 |
| :--- | :--- | :--- | :--- | :--- |
| **2a** | `db/errors.py` 扩展 `is_transient_write_error(exc) -> bool` | S5 判据合并；PG 分支映射 deadlock(`40P01`) / serialization_failure(`40001`) | 删 `ai/run_event_writer.py:55-68` 与 `services/durable_job_lease_service.py:44-57` 两份拷贝，3 个消费方改 import（`platform_runtime.py:23`、`page_mutation_executor.py:20`、`page_screenshot_job_service.py:31`）；顺带处理 `idempotency_service.py:181` 的裸 `except OperationalError` | grep 断言 `def is_sqlite_lock_error` 定义数 == 1（在 `db/errors.py`） |
| **2b** | `db/retry.py` 新建 `run_with_write_retry(session, fn, *, attempts, base_delay, on_retry=None)` | 4 套重试统一实现，**保留各自数值作为参数**（4×25ms / 3×50ms / 3×50ms / [50,100,200]ms） | `platform_runtime.py:345-368`、`page_screenshot_job_service.py:437-516`、`page_mutation_executor.py:442-457`、`idempotency_service.py:169-184`；删死常量 `SQLITE_BUSY_RETRIES`(:27) | 断言 `test_page_screenshot_job_durability.py:97` 与 `test_ai_platform_runtime_concurrency.py:159-237` 行为不变（含精确 rollback 次数 :233-234） |
| **2c** | `db/locks.py` 新建 `holds_write_lock(session) -> bool` | S6 驱动下钻搬进 `app/db`；探测不可用时**打点告警**而非静默 False | `platform_runtime.py:463-470` 改为调用；`_RUN_EVENT_LOCKS` 锁序逻辑保持 | grep 断言 `driver_connection` 在 `app/db/locks.py` 之外出现次数 == 0；`test_ai_platform_runtime_concurrency.py:240-274` 同步迁移（monkeypatch 目标改为 `app.db.locks`），**不得删除该测试** |
| **2d** | `db/tx.py` 新建 `read_probe(session)` / `commit_end_read(session)` / `acquire_admission_lock(state)` | S7 内联技巧语义化；SQLite 原因移入 helper docstring | `durable_job_lease_service.py:81-83`、`:221-233`、`code_check_service.py:403-407`、`rendering/repository.py:59-67`（按 C5 **保留写**，只改名 + 纠正注释，禁用「假写」措辞） | 断言业务文件中不再出现「SQLite」字样的事务性注释（移入 helper） |
| **2e** | `db/types.py` 扩展 `JSONPayload`、`BoolInt` | S3 / S8 | `models/render_request.py:17`、`render_execution.py:17`、`render_attempt.py:17` 三份 `JSONType` 改 import；`render_attempt.py:48` `active_occupancy` 改 `BoolInt`；`migrations/versions/20260910_0100:24` 内联改 helper | 断言 `with_variant(JSONB` 在 `db/types.py` 之外出现次数 == 0（迁移 helper 内部除外） |
| **2f** | `db/indexes.py` 新建 `partial_index(name, columns, predicate, *, unique=False)` | S2 | §2.3 表中 6 个 model 文件、10 个索引全部改造；**迁移侧 6 个文件另行处理**（历史迁移不改写，见 P4 步骤 4：只约束**新**迁移） | 断言 `sqlite_where=` 在 model 文件中出现次数 == 0；对每个索引生成 SQLite 与 PG 两份 DDL 并比对谓词文本一致 |

**可选（不阻塞）**：状态字符串 / 错误码枚举模块（S8 后半）。范围横跨模型、迁移、契约测试与 `test_sqlite_migration.py` 的源码文本断言，建议单独立项，且必须在 P4 之后（否则与迁移文本断言冲突）。

**验收（整阶段）**：SQLite 与 PG 双库分别跑 `pnpm run test:backend:integration` 全绿；上述 6 条 grep/AST 门禁进入 `pnpm run test:repository` 或 backend 单测；`app/db/` 之外无方言判断残留（`dialect.name` grep）。

#### 6.3.1 P2 实施结果（2026-09-24 收口，含裁剪决定）

首轮实施只落了「新增/扩展」列、没落「替换点」列，导致 helper 全部零调用点。本轮按 **D1 未决 ⇒ P2 从裁剪** 处理：正确性收益（判据合并、驱动下钻收口、索引谓词单源）保留，纯维护性收益（重试/事务/布尔别名统一）裁剪并删除 helper，不留零调用点抽象。

| 步 | 结果 | 说明 |
| :--- | :--- | :--- |
| **2a** | **完成，但改名** | 判据合并为单函数 `db/errors.detect_transient_write_conflict(exc)`（判定 + 打点同一入口，PG/SQLite 两分支都计数）。`is_transient_write_error` 与 `is_sqlite_lock_error` **均已删除**，`run_event_writer.py` / `durable_job_lease_service.py` 的再导出 shim 一并移除，5 个消费方直接 import。原门禁「`def is_sqlite_lock_error` 定义数 == 1」作废，替换为「写冲突判据函数在 `app/` 内定义数 == 1 且名字属于既定集合」，见 `test_db_adapter_layer.py::test_write_conflict_predicate_has_single_definition`。 |
| **2b** | **已裁剪** | `db/retry.py` 已删除。理由：4 个替换点的会话语义互不兼容——`page_mutation_executor._run_final_write` 每次尝试**新建并关闭 session**（与 `run_with_write_retry(session, fn)` 的单 session 签名冲突）；`platform_runtime._append_event_with_retry` 需要在尝试间 `populate_existing` 刷新 run 实体并在刷新失败时转 `ValueError`；`idempotency_service` 依赖 `for...else` 兜底再读一次；`page_screenshot_job_service` 在重试分支内打结构化日志。统一后需要额外的 session 工厂 / 结果回调 / 日志钩子参数，抽象成本高于 4 处各约 10 行的重复。§6.2 决策门 D2 的「混合负载出现 `database is locked` ⇒ 2b 提为 P3 前置必做」仍然有效：**若基线采集真的观测到写冲突，应按 D2 重新立项**，届时以 session 工厂为参数重新设计，而不是恢复当前签名。 |
| **2c** | **完成** | `db/locks.holds_write_lock` 已接管 `platform_runtime._has_sqlite_write_transaction`；探测失败打点告警而非静默 False。门禁 `driver_connection` 在 `app/db/locks.py` 之外出现数 == 0 已落地为 `test_db_adapter_layer.py::test_driver_connection_only_in_db_locks`。 |
| **2d** | **部分完成，其余裁剪** | `commit_end_read(session)` 已接管 `code_check_service._release_session_before_diagnostics`。`read_probe` 别名与 `acquire_admission_lock(state, session)` **已删除**：前者是无调用点的兼容别名；后者规划替换点 `rendering/repository.py:59-67` 的准入锁与其后 `queue_size`/`workspace_queue` 计算同处一个方法，抽出去只搬走 2 行 `version += 1 / flush()` 而把 C5 强调的「故意的单行锁」语义拆到另一个模块，注释反而更容易与代码脱节——已就地改写注释表达意图。`durable_job_lease_service.py:81-83`/`:221-233` 未改。 |
| **2e** | **JSONPayload 完成，BoolInt 裁剪** | 3 份 model 内联 `JSONType` 已收口到 `db/types.JSONPayload`；`20260910_0100:23` 的内联 `with_variant(JSONB()` 已移到 `migrations/helpers/dialect.json_payload_type()`（迁移不 import `app.db.types`，避免历史迁移随模型漂移）。门禁「`with_variant(JSONB` 只出现在 `db/types.py` 与迁移 helper」已落地为 `test_json_payload_variant_has_single_source`。`BoolInt` **已删除**：`active_occupancy` 的取值 1/0 由 `partial_index` 谓词 `active_occupancy = 1` 约束，`int` 别名不提供任何运行时或 DDL 保证，属纯命名糖。 |
| **2f** | **完成** | 6 个 model / 10 个索引全部改用 `partial_index`；`sqlite_where=` 在 model 中出现数 == 0 已落地为 `test_models_should_not_declare_dialect_specific_index_predicates`。签名最终为 `partial_index(name, columns, predicate, *, unique=False)`，规划外的 `index_predicate_sql` 与未用形参 `table_name` 已删除。历史迁移未改写（与 P4 步骤 4「只约束新迁移」一致）。 |

**遗留缺口（未在 P2 内解决）**：`app/scripts/test_data.py:114` 仍有 `connection.dialect.name == "postgresql"` 判断，不满足「`app/db/` 之外无方言判断残留」的整阶段验收。该文件是开发期种子脚本、不在运行态写路径上，且 `app/db` 目前没有面向运行态代码的通用方言判定入口（`holds_write_lock` 是专用谓词，迁移 helper 只服务 Alembic）。建议随 S8 后半（状态/错误码枚举模块）单独立项，或在该脚本内就地注释说明为何例外。

---

### 6.4 P3 — 任务运行时（`app/jobs/`，按队列渐进）

**目标能力**：

| 能力 | 现状 | 目标 |
| :--- | :--- | :--- |
| 认领 | 各队列各自 `claim_*` | 单一 FIFO + 条件 UPDATE 策略 |
| 心跳 | 4 份 `_heartbeat_*`，15–30s，每任务一条 | 批量续租（同 worker 一次 `UPDATE ... WHERE worker_id=?`）或惰性延长（阶段超时 + 余量）；**不删租约** |
| 恢复 | 4 套以上，谓词/max_attempts/backoff 各异（§3.2 C） | 统一 `recover_expired(table, policy)`，`policy = {expiry_predicate, max_attempts, backoff}`；**按最近 `lease_expires_at` 退避唤醒**，禁止固定 0.5s 全量 |
| 轮询 | 只有页面队列有 `GenerationWakeup` | 抽成通用 `JobWakeup`（内存篇 §3.4 / §6.5），component / image / screenshot / external 全部接入；空队列指数退避到 2–5s |
| 生命周期 | 13 条循环全绑 lifespan，无独立入口 | `app/jobs/` 设计上允许从 lifespan 外启动（本期**不实现**独立进程，只保留形状） |

**开刀顺序（按空闲写放大 × 改造风险排序）**：

| # | 对象 | 具体动作 | 关闭 |
| :--- | :--- | :--- | :--- |
| **1** | `ai-external-task-coordinator`（`external_task_queue.py:47-81`） | ① `audit_external_state_consistency` 从每轮拆出，降到 30–60s；② `cleanup_terminal_run_external_state` 的 **4 条无条件 UPDATE**（`external_terminal_cleanup.py:45-67,68-76,77-85,86-94`）改为「先 SELECT 命中集，命中才 UPDATE」，对齐 `durable_job_lease_service.py:223-233` 已有的空闲免写模式；③ `synchronize_external_task_states` 的 per-task 关联 SELECT(:102-136) 改批量 `IN` 查询，:173 的无条件 commit 改「有变更才提交」；④ `audit` 的 :427 无条件 commit 同上；⑤ `recover_external_continuations` 保持空闲免写(:240)，但改为按最近 `lease_expires_at` 退避；⑥ 主循环空闲 sleep 从 0.5s 指数退避到 2–5s，有非终态 task 时恢复短间隔；⑦ 给它一个**专属配置项**（当前复用 `ai_page_mutation_poll_interval_seconds`） | Q2 |
| **2** | `ai-image-generation-queue`（`image_generation_queue.py`） | ① `_promote_due_provider_jobs`(:471-487) 的无条件 UPDATE 改先查后写；② 每轮空闲重跑的 `recover_interrupted_image_generation_jobs_on_startup`(:89 → :43-68) 改为按 lease(120s) 到期退避；③ `_HEARTBEAT_SECONDS=30`(:39)、`_LEASE_SECONDS=120`(:38)、poll 0.5s(:90) 提为配置项，并纳入 `config.py:279-285` 的「lease ≥ 3× heartbeat」校验器口径（120 vs 300 的不一致要么修数值要么写明豁免） | Q10 |
| **3** | `render-coordinator`（`rendering/coordinator.py` + `repository.py`） | ① `expire_requests`(:874-897) 的每 tick 无条件 UPDATE 改先 SELECT 到期集；② `upsert_worker_heartbeat`(:147-196) 按 `heartbeat_interval` 节流（建议 ≥5s 或 lease 的 1/3），不必 4Hz；③ 空闲 tick 自适应：无 pending/active request 时 sleep 退避到 0.5–1s，保留 50ms 下限给活跃态；④ `wait_for_terminal`(:122-175) 的 100ms(:168) 改 200ms–1s + 进程内条件唤醒（终态到达 notify）；⑤ 复核 `drive_dispatch=True` 时 `ensure_progress`(:67-84) 触发整 tick 的必要性——等待路径反向引发写 | Q1 Q9 |
| **4** | 心跳合并 | `mutation_job_service._heartbeat_loop`(:421-454) 的 15s 细粒度改批量/惰性；`_heartbeat_job_lease`(`page_mutation_queue.py:860-895`)、`_heartbeat_batch`(`external_task_queue.py:717-751`)、screenshot heartbeat(`page_screenshot_job_service.py:183-188`) 统一走 `app/jobs` 心跳器 | Q1 |
| **5** | 恢复统一 | `app/jobs/recovery.py`：`recover_expired(table, policy)`。收敛 §3.2 C 表中全部差异，**含两个实质 bug**：`MutationJobService.recover_expired_running_jobs:830` 缺 `lease IS NULL` 分支、`:834` 的 `attempt+1 < max` 与通用实现差一。backoff 三套（无 / +5s / +2s）统一为 policy 参数。`asset_render_hint_backfill.recover_interrupted_jobs:214-235` 补 lease/过期谓词，max_attempts 从 2 对齐到 policy | Q8 Q12 |
| **6** | 认领退避 + 通用唤醒 | `GenerationWakeup`(`page_mutation_wakeup.py:8`) 抽为 `app/jobs/wakeup.py` 的 `JobWakeup`；component(`component_mutation_queue.py:124`)、image、screenshot、external 接入（当前均为纯 sleep）；空队列连续 N 次后退避到 2–5s，`notify` 立即恢复。**跨进程通知明确不做**（内存篇 §6.5） | Q1 Q9 |
| **7** | 死代码 / 死配置清理 | 删 `page_mutation_queue._run_continuation_coordinator`(:462-496，含 `_heartbeat_batch_lease`:898-944 与 30s recovery :477-479)——已核实从未启动；删或接线 `page_screenshot_job_lease_seconds=180`(`config.py:115`)；删 `idempotency_service.SQLITE_BUSY_RETRIES`（若 2b 未处理） | Q11 |
| **8** | 硬编码节奏提配置 | `mutation_job_service.py:891,897` 的 1.0s/2.0s、`ai_model_catalog_service.py:346` 的 3600s、`external_task_queue.py:63` 的 60s 清理窗口、`image_generation_queue.py:38-40,90`（见 #2）、`external_terminal_cleanup` 的 7d 保留期 | Q10 |

**新增循环门禁**：任何新的亚秒级循环必须 (a) 带空闲退避，(b) 空闲态零写 DML。加一条架构测试扫描 `while True` + `asyncio.sleep(<1.0)` 组合并要求白名单登记。

**验收（整阶段）**：

- [ ] **空闲 10 分钟写事务数 == 0**（结构性判据，不依赖性能假设）。
- [ ] 混合负载 `database is locked` 次数相对 P1 基线下降，且**认领延迟 P95 不劣化**。
- [ ] 各 loop tick P95 < 其轮询间隔（否则说明间隔设得过小）。
- [ ] 恢复语义统一后，重启/租约过期回归测试全绿：`test:e2e`、`test:backend:integration`，特别是页面 mutation 的租约、取消、版本复核、SSE `waiting_external` 与自动续跑（AGENTS.md §3 明确要求）。
- [ ] 13 条循环的**节奏与租约全部可由配置表达**，附录 A 的「hard」项清零。

---

### 6.5 P4 — 迁移双方言等价证明（Q4）

1. **迁移 helper**。新建 `backend/migrations/helpers/dialect.py`，封装 `batch_alter` / `recreate` / DDL 差异；把 `20260818_0100:130,156,189` 的 3 处 `== "sqlite"` 与 `20260910_0100:193` 的 `in {"postgresql","sqlite"}` 收进去。**历史迁移不改写语义**，只在 helper 落地后按需重构（重构必须过步骤 2 的对拍测试）。
2. **双库对拍 contract test**。同一份 seed → 分别对 SQLite 与 PG 跑全量 `upgrade head` → 断言业务不变量一致：表集合、行数、关键列值、唯一性实际生效（插入违例应被拒）。这是 Q4 唯一能给出「机器证明」的形式。
3. **把源码文本断言换成行为断言**。`test_sqlite_migration.py` 的 `:195`（要求方言分支字符串存在）、`:192-194`（要求谓词字符串存在）在 helper 收口后必然变红——**先写好步骤 2 的行为断言，再删这些文本断言**（见 §5「明确不做」）。`:31-32`（禁止整数比较布尔）应保留为行为/AST 检查而非字符串检查。
4. **新迁移的谓词单点化**。步骤 2 通过后，新迁移一律用 P2 2f 的 `partial_index` 生成 DDL，不再手写 `sqlite_where` + `postgresql_where` 两份。§2.3 列出的 6 个历史迁移文件不改写。
5. **不可逆转换的运维约束**。`20260910_0100:191-206` 清除全部 `pages.screenshot_*` 指针，`downgrade` 明写不恢复(:210)。补：(a) `docs/developer/` 升级注记说明该迁移会清空当前截图指针、需先备份；(b) 立规——后续同类不可逆转换必须走「先备份到影子表 → 再清除」形态，并加一条迁移审查检查项。

**验收**：双库对拍测试进入 `pnpm run test:contracts`；CI 上 SQLite 与 PG 两条迁移路径都实际执行（不是只跑一边）；`migrations/versions/` 中裸 `dialect.name` 出现次数 == 0（helper 内部除外）。

---

### 6.6 P5 — Lite 边界固化

1. **单进程强制**。`DATABASE_URL` 为 SQLite 文件库时，启动校验拒绝多进程共享同一 db 文件（`uvicorn --workers > 1`，或多容器挂同一卷）；启动日志打印 `sqlite_single_process=true`。AGENTS.md §3 已声明「项目通常已经启动」，校验必须幂等且不误伤已运行实例。
2. **并发上限写进部署模板**。已核实 `ai_page_mutation_concurrency=1`(`config.py:94`) **对所有数据库生效、无 SQLite 分支**——这是好的（不要在代码里加方言分支），因此 Lite 的全部 `*_CONCURRENCY=1` 应作为 **compose 模板约束**固化，而不是代码特判。同时把 `render_global_concurrency=1` / `render_workspace_concurrency=1`(:60-61) 一并写清。
3. **新增循环门禁**（同 §6.4 末尾）。
4. **readiness**（与内存篇 §6.2、issue-status P1-Health 交叉）。Backend 当前 `/healthz` 固定 `{"status":"ok"}`，不探 DB / 协调器 / Renderer。增加 readiness 暴露：DB 可写、render coordinator 存活、Renderer 能力、各队列积压深度、`artifact_store_ephemeral`。`/healthz` 保持纯 liveness（compose 的 `service_healthy` 依赖它）。
5. **拓扑优先级**。2C4G 长期目标优先拆 Runtime / Backend 容器与减写，**而不是先上 Browserless**（`cdp.md` 仍是未实施规划，见 issue-status §5.1）。

**验收**：SQLite 多进程启动被拒并有明确错误；readiness 端点存在且被 compose/部署文档引用；`pnpm run test:contracts:docker-context` 与 `pnpm run test:repository` 通过。

---

### 6.7 统一验证口径

按 AGENTS.md §4「优先运行与改动范围匹配的最小测试集，并在最终说明中写清已运行和未运行的测试」：

| 阶段 | 必跑 |
| :--- | :--- |
| P0 | `test:backend:unit`、`test:backend:api`、`test:backend:integration`、`test:contracts`、`test:e2e` |
| P1 | `test:backend:unit`（打点不改变行为）+ 基线采集脚本 |
| P2 | 每步：`test:backend:unit` + `test:backend:integration`；整阶段：**SQLite 与 PG 双库**各跑一遍 `test:backend:integration` |
| P3 | `test:backend:integration`、`test:e2e`、`test:contracts`；涉及渲染节奏时加 `test:render-e2e`（需 Node/Python 两套 Playwright Chromium） |
| P4 | `test:contracts`（双库对拍）、`test:backend:integration` |
| P5 | `test:repository`、`test:contracts:docker-context`、`test:e2e:regression` |
| 全量回归 | `test:python-workspace`、`test:e2e:all` |

P2/P3 的 grep/AST 防漂移门禁应挂进 `test:repository` 或 backend 单测，避免靠人工记得。

### 6.8 跨阶段风险

| 风险 | 缓解 |
| :--- | :--- |
| P0 让用户可见失败增加 | `skip_visual_verification` 逃生口 + 可操作错误文案 + E2E smoke 前置 |
| P2 重构与行为变更混淆 | 严格分步（2a→2f），每步只动一类；重试次数/退避**先不动数值** |
| P3 降频导致认领延迟上升 | 以 D2 判据为准；保留 `notify` 立即唤醒；验收含「P95 不劣化」 |
| P3 触碰页面 mutation 续跑链路 | AGENTS.md §3 要求同时检查租约、取消、页面版本复核、SSE `waiting_external`、自动续跑测试——列为 P3 强制回归项 |
| P4 让现有迁移测试变红 | 先建行为断言，再删文本断言（顺序不可颠倒） |
| 未提交的用户改动被覆盖 | 各阶段独立小步提交；不动无关文件（AGENTS.md §1） |

---

## 7. 与前序文档关系

| 前序 | 本文 |
| :--- | :--- |
| 「多轮询 Worker → database is locked」 | 结构属实；**程度待基线**（P1）；碎片补丁本身成债 |
| 「事件化、消灭心跳」 | 保留唤醒 + 轮询兜底；心跳合并/惰性化，**不删租约** |
| 「内存全局锁阻水平扩展」 | 见内存篇；本篇强调与 SQLite 写锁的**锁序耦合**（S6 ↔ M4） |
| 1.5GB / 40% 验收 | 废弃，改 §6.2 基线 + D2 结构性判据 |
| `runtime-multi-deployment-scaling-plan.md` 阶段 0 | 其阶段 0 的「不可用≠通过」即本文 Q0 / P0；**阶段 0 未关闭前不应启动阶段 1+** |
| `cdp.md`（Browserless） | 未实施规划；本文 P5 明确「先拆容器与减写，不先上 Browserless」 |

**交叉引用勘误**：内存篇 §4 与 §7 写的「SQLite 篇 §4」「SQLite 篇 §4–6」应指本文 **§3**（定时任务）与 **§3–§6**；本文 §4 是风险分级。建议同步修正内存篇。

---

## 8. 一页结论

1. **8 类兼容债（S1–S8）**里优先 **S5**（BUSY 两份逐字拷贝 + 4 套重试 + 1 个死常量）、**S6**（`driver_connection` 下钻，fail-safe 但静默失效且被测试固化）、**S7**（内联事务技巧，含被误述为「假写」的必要 PG 行锁）、**S4**（2 个迁移裸判方言 + 不可逆截图指针清除 + 测试断言源码文本）。
2. **定时任务是写放大器**：13 条同进程循环；零负载下静态推导约 **22 次写 DML / 写事务动作每秒**（render tick 4Hz×(1+W) + external coordinator 2Hz×(4 UPDATE + 2 空提交) + image queue 2Hz×1 UPDATE，明细见 §3.3）。优先改 **external coordinator → image queue → render tick**，再统一 recover / 心跳。
3. **P0 两项**：Q0 页面校验语义（**HEAD `44282d6` 复核仍未修**，且 External API `validate.py` 同样会对外报 `valid=true`）；Q4 迁移双方言等价无机器证明。两者都要在「继续堆调度补丁」之前处理。
4. **本轮新增 4 项**：Q10（image queue 全硬编码 + 空闲无条件 UPDATE + lease 120s 脱离校验器）、Q11（死代码 `_run_continuation_coordinator` / 死配置 `page_screenshot_job_lease_seconds` / 死常量 `SQLITE_BUSY_RETRIES`）、Q12（asset backfill 恢复无 lease 谓词、max_attempts=2、只有 Redis 锁 TTL 无 DB 租约），以及 C8（恢复实现是 4 套以上，含 `lease IS NULL` 缺失与 `attempt+1 < max` 差一两个实质 bug）。
5. **路径**：**D1 决策 → P0 正确性 → P1 基线 →（P5 边界 ∥ P4 迁移）→ P2 适配层 → P3 任务运行时**。P3 的投入规模由 D1 与 D2 共同定档。
6. **验收用结构性判据，不用拍脑袋数值**：空闲态零写 DML、`database is locked` 归零、tick P95 < 轮询间隔、认领 P95 不劣化、节奏全可配。
7. 内存 / `memory://` / 普通 Run 问题见 [`architecture-assessment-memory-2026-09.md`](./architecture-assessment-memory-2026-09.md)。

---

## 附录 A. 节奏与租约配置全表（已核实）

### A.1 有配置项（`backend/app/core/config.py`）

| 配置键 | 默认 | 行 | 用途 |
| :--- | :--- | :--- | :--- |
| `database_connect_timeout_seconds` | 10.0 | :36 | ⇒ `busy_timeout` **10000ms** |
| `render_global_concurrency` | 1 | :60 | 渲染全局并发 |
| `render_workspace_concurrency` | 1 | :61 | 渲染工作空间并发 |
| `render_queue_size` | 64 | :62 | 渲染队列容量 |
| `render_workspace_queue_size` | 16 | :63 | 工作空间队列容量 |
| `render_request_timeout_seconds` | 120.0 | :64 | `wait_for_terminal` 总超时 |
| `render_max_attempts` | 3 | :65 | 渲染请求重试 |
| `render_scheduler_poll_interval_seconds` | **0.25** | :66 | render tick（下限 50ms） |
| `render_attempt_lease_seconds` | 180.0 | :67 | attempt 租约 |
| `render_unknown_reconcile_after_seconds` | 30.0 | :68 | unknown 态对账 |
| `ai_enabled` | True | :73 | 4 条 AI 队列的开关 |
| `ai_external_task_enqueue_timeout_seconds` | 30.0 | :82 | 入队超时 |
| `ai_model_catalog_sync_enabled` | True | :86 | catalog sync 开关 |
| `ai_page_mutation_concurrency` | 1 | :94 | 页面 + 组件 worker 数（**无 SQLite 分支**） |
| `ai_page_mutation_max_active_jobs` | 16 | :95 | |
| `ai_page_mutation_max_batch_size` | 16 | :96 | |
| `ai_page_mutation_poll_interval_seconds` | **0.5** | :97 | 页面 / 组件 / **external coordinator** 三处共用 |
| `runtime_preview_artifact_ttl_seconds` | 3600 | :101 | |
| `runtime_artifact_sweep_interval_seconds` | 30.0 | :102 | artifact sweeper |
| `runtime_build_state_ttl_seconds` | 604800 | :103 | |
| `durable_job_lease_seconds` | **300** | :104 | 页面 / 组件 / **截图（实际生效）** |
| `durable_job_heartbeat_seconds` | **30** | :105 | 同上 |
| `page_screenshot_batch_concurrency` | 2 | :112 | |
| `page_screenshot_queue_concurrency` | 1 | :113 | |
| `page_screenshot_queue_poll_interval_seconds` | 1.0 | :114 | |
| `page_screenshot_job_lease_seconds` | 180 | :115 | **死 fallback，永不生效**（C4 / Q11） |
| `page_screenshot_ai_wait_timeout_seconds` | 90.0 | :116 | |
| `asset_render_hint_backfill_queue_concurrency` | 1 | :117 | |
| `asset_render_hint_backfill_queue_poll_interval_seconds` | 1.0 | :118 | |
| `asset_render_hint_backfill_job_lease_seconds` | 180 | :119 | 实为 **Redis 锁 TTL**，非 DB 租约（N4） |
| `object_cache_sweep_interval_seconds` | 21600 | :126 | 非循环；请求内机会式清理（`object_storage_service.py:113-129`） |
| `mutation_job_lease_seconds` | **45** | :139 | api-mutation |
| `mutation_job_heartbeat_seconds` | **15** | :140 | api-mutation |
| `mutation_job_recovery_interval_seconds` | 30 | :141 | api-mutation sweeper |
| `mutation_job_max_attempts` | 3 | :142 | |
| `mutation_job_retention_days` | 7 | :143 | |

校验器：`durable lease ≥ 3× heartbeat`(:279-285)、`mutation lease ≥ 3× heartbeat`(:505-511)。**image queue 的 120s/30s 不受这两个校验器约束**（因为无配置项）。

### A.2 硬编码、无配置项（P3 步骤 8 的清理清单）

| 值 | 位置 | 说明 |
| :--- | :--- | :--- |
| poll 0.5s / heartbeat 30s / lease **120s** / max_attempts 3 | `ai/image_generation_queue.py:38-40,90` | Q10；lease 与 `durable_job_lease_seconds=300` 不一致 |
| 空闲 1.0s / 异常 2.0s | `services/mutation_job_service.py:891,897` | api-mutation-worker |
| 恢复重入队 +5s | `services/mutation_job_service.py:846` | |
| 重试 4 次 / base 25ms | `ai/platform_runtime.py:64-65` | S5 |
| 重试 3 次 / base 50ms | `services/page_screenshot_job_service.py:51,506` | S5 |
| 重试 3 次 / base 50ms | `ai/page_mutation_executor.py:445,455` | S5，第 4 份拷贝 |
| 退避表 `[0.05,0.1,0.2]` | `services/idempotency_service.py:28` | 读重试 |
| `wait_for_terminal` 100ms | `services/rendering/coordinator.py:168` | Q9 |
| tick 下限 50ms | `services/rendering/coordinator.py:120` | |
| poll 下限 50ms | `ai/external_task_queue.py:55`、`ai/page_mutation_queue.py:311`、`ai/component_mutation_queue.py:96` | |
| 清理窗口 60s（= 120 轮） | `ai/external_task_queue.py:63-64` | |
| 结果保留 7d / limit 100 | `ai/external_task_queue.py:449-483` | |
| audit grace `max(10.0, 2×poll)` = 10s | `ai/external_task_queue.py:248,323-332` | |
| 截图 in-loop 恢复 30s | `services/page_screenshot_queue_worker.py:79,89-91` | 与启动恢复并存 |
| 心跳 `min(30, lease//2)` = 30s | `services/page_screenshot_job_service.py:187-188` | |
| catalog 唤醒 3600s / `SYNC_INTERVAL` 24h / `LEASE_DURATION` 10min | `services/ai_model_catalog_service.py:346,29,30` | 空转周期不写库 |
| `_MAX_ATTEMPTS` 3（页面）/ 3（组件）/ **2**（asset backfill） | `ai/page_mutation_queue.py:41`、`ai/component_mutation_queue.py:27`、`services/asset_render_hint_backfill_job_service.py:37` | Q8 不一致 |
| render 恢复 limit 20 / `retry_after +2s` | `services/rendering/repository.py:461-517,549` | |
| Redis 锁键 `runtime:asset-render-hint-backfill-job-lock:{job_id}` | `services/asset_render_hint_backfill_job_service.py:377-388` | `memory://` 回落 `InMemoryRedis`（`redis_runtime_client.py:86-87`） |
