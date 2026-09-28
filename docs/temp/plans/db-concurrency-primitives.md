# 数据库并发原语收口规划（SQLite Lite / PostgreSQL Prod）

> 状态：**部分实施（2026-09-28）**。CP1a / CP1b / CP2 / CP5 / CP6 已落地，见 §9 实施记录；**CP3 / CP4 仍未实施**，按 §5 排在 P3 契约冻结与 D2 基线之后。
> 基线提交：`4becd41`（分支 `dev`）。外部输入结论的基线是 `04d78bd`，两者差异只有 `4becd41`（构建链路评审修复），不影响本文结论。
> 编号：本文工作项用 **CP1–CP6**（Concurrency Primitive），避免与既有 `C0–C4`（`lite-memory-adapter.md` 步骤 / 多部署评审 Critical）冲突。
> 复用既有编号：**2b**（统一写重试，D1=A 后已重立）、**2d**（事务技巧语义化，有限重立）、**P1-TaskModel**、**P2-Dialect**、**P2-Locks**、**D1=A**、**D2**。
> 行数口径：本文引用 `wc -l` **总行数**；`docs/temp` 历史稿用的是非空行数，跨文档对比时注意（例：`platform_runtime.py` 总 2067 / 非空 1854）。

---

## 0. 一页结论

外部评审的核心判断——**「数据模型兼容干净，事务/并发语义兼容开始别扭」**——方向正确，但它开出的中心处方（新增 `DatabaseCapabilities` / `skip_locked` 布尔能力层，按方言分 Adapter）**不成立**，理由是可验证的：

1. **SQLAlchemy 已经按方言渲染并发子句，布尔能力层不会改变任何生成 SQL。** 实测（`.venv` 内编译同一 `select()` 到两个方言）：

   | 语句 | SQLite 方言 | PostgreSQL 方言 |
   | :--- | :--- | :--- |
   | `.with_for_update()` | `SELECT ... LIMIT ?`（**FOR UPDATE 被静默丢弃**） | `... LIMIT %(param)s FOR UPDATE` |
   | `.with_for_update(skip_locked=True)` | `SELECT ... LIMIT ?`（**同样静默丢弃**） | `... FOR UPDATE SKIP LOCKED` |

   也就是说：**「PG 用 SKIP LOCKED、SQLite 不用」这件事不需要能力层，写进共享查询即可，SQLite 自动忽略。** 新增 `skip_locked: bool` 只会增加一层不产生差异的间接。

2. **「代码在寻找 PG 与 SQLite 的最低公共并发原语」这个概括与现状不符。** 仓库里已有 **12 处** `with_for_update()` 走在共享代码路径上，PG 拿到真行锁、SQLite 退化为写者串行化，两侧同一份语句：
   `services/mutation_job_service.py:555,600,660,702,772`、`services/page_visual_edit_service.py:256`、`services/project_build_service.py:60`、`ai/page_mutation_executor.py:399,496`、`ai/page_mutation_queue.py:720`、`ai/tools/generic/archive.py:138`、`services/ai_model_catalog_service.py:234`。
   `rendering/repository.py:59` 的 `version += 1` 是**局部选择**，不是全仓被迫的妥协。

3. **真正被漏掉的分歧点不是「有没有 SKIP LOCKED」，而是事务边界。** `SKIP LOCKED` 只在「锁定 SELECT」与「claim UPDATE」**同一事务**内有效。现有实现故意在两者之间 `commit()`（`services/durable_job_lease_service.py:62`、`services/project_build_service.py:277`），目的是规避 SQLite 读事务升级写锁失败。**因此直接给现有候选查询加 `skip_locked=True`，在 PG 上能编译、能跑，但收益为零**——commit 已经把行锁释放了。要拿到收益，必须让 PG 走「单事务 claim」，SQLite 走「跨 commit CAS」。这是事务形态差异，SQLAlchemy 不会替我们表达，也正是唯一值得抽象的原语。

4. **模型/类型/索引层比外部评审以为的更结实：已有防漂移门禁。** `backend/tests/unit/test_db_adapter_layer.py` 锁住了四件事：写冲突判据单定义（`:87`）、`driver_connection` 下钻只允许在 `app/db/locks.py`（`:76`）、`with_variant(JSONB` 只在 `db/types.py` 与迁移 helper（`:100`）、model 不得写 `sqlite_where=`/`postgresql_where=`（`:110`）。对应历史步骤 **2a / 2c / 2e / 2f 已实施完毕**。

5. **「SQLite 锁语义泄漏到业务层」部分过时。** 驱动对象下钻已收口（见上）；仍留在 AI 层的是**调用与锁序决策**：`ai/platform_runtime.py:333-344` 依据 `_has_sqlite_write_transaction()`（`:464-470`）决定走进程锁还是重试路径。泄漏面比描述的小，但确实还在，归 **P2-Locks**。

6. **外部评审完全没提、但比它列的四点更贵的问题：claim 已经有第二份手写拷贝。** `services/project_build_service.py:237-321` 的 `claim_job` 自行实现了 SELECT→commit→CAS，并把同一条 SQLite 注释复制到 `:276`。它没有复用 `durable_job_lease_service.claim_pending_jobs`——后者已被 **5 个队列 / 6 个调用点**使用（`ai/page_mutation_queue.py:152`、`ai/component_mutation_queue.py:115`、`ai/image_generation_queue.py:129`、`services/page_screenshot_job_service.py:327,339`、`services/asset_render_hint_backfill_job_service.py:145`），而构建侧只复用了 `renew_running_job_lease` / `transition_owned_running_job`（见 CP4）。**这就是现行评估的 P1-TaskModel；不先折叠它，任何原语抽象都会立刻产生第三种方言。**

**因此本文的处方**：不建能力层、不建 Adapter 矩阵；做 **CP1（=2b）命名与重试收口**、**CP2（=2d）事务技巧语义化**、**CP5 部署 profile 一等化**三件低风险收口，再把 **CP3 事务形态分方言 claim** 与 **CP4 折叠构建 claim** 绑定到 P3 任务运行时契约冻结之后执行。

**对外部评审排序建议的修正**：它主张「先做 DB concurrency primitive 收口，再做 Agent Run lease」。**部分同意**——CP1/CP2/CP5 无契约影响，应当先做；但 CP3/CP4 改的就是 claim 契约本身，**先做等于把 P3 要冻结的东西先实现一遍再返工**。正确顺序是 CP1/CP2/CP5 → P3 契约冻结 → CP3/CP4 → Agent Run lease。

---

## 1. 逐条核对外部结论

判定口径：**成立** / **部分成立（已过时）** / **不成立**，全部给 `file:line` 证据。

### 1.1 「做得比较好的部分」

| 外部结论 | 判定 | 证据 |
| :--- | :--- | :--- |
| `db/types.py` 用 `JSON().with_variant(JSONB(), "postgresql")` | **成立，且已加门禁** | `db/types.py`；门禁 `tests/unit/test_db_adapter_layer.py:100`（P2-2e） |
| `UTCDateTime` 统一 naive / tz-aware | **成立** | `db/types.py:28` 按 `dialect.name == "sqlite"` 去 tzinfo |
| `partial_index()` 同时生成双方言谓词 | **成立，且已加门禁** | `db/indexes.py:26`；门禁 `test_db_adapter_layer.py:110`（P2-2f） |
| Model / Repository 没有到处写 `if postgres else sqlite` | **成立** | `grep -n "SQLITE\|sqlite" backend/app` 命中集中在 `db/`、`main.py`、4 个重试常量与注释；业务模型层无方言分支 |
| `session.py` 统一 `AsyncSession` | **成立** | `db/session.py:67` `get_session_factory()`；`:29` `AgentWriteGuardedAsyncSession` 统一提交期写围栏 |

补充：`db/session.py:134-156` 为 SQLite 统一设置 `foreign_keys=ON` / `busy_timeout` / 文件库 `WAL`，内存库不启 WAL（`:159`）。这部分属于「能自然共享的保持一套代码」，符合外部评审自己的原则，**不动**。

### 1.2 「别扭的部分」

| # | 外部结论 | 判定 | 证据与修正 |
| :--- | :--- | :--- | :--- |
| 1 | `_RUN_EVENT_LOCKS` 进程锁 + `_has_sqlite_write_transaction()` + `holds_write_lock()` + `driver_connection.in_transaction`，业务层被迫关心 SQLite 写锁 | **部分成立（已过时一半）** | 驱动下钻**已**收口到 `db/locks.py:12`，`in_transaction` 读取在 `:36-37`，并有门禁 `test_db_adapter_layer.py:76` 断言 `driver_connection` 在 `app/db/locks.py` 之外出现次数为 0。仍泄漏的是**调用点与锁序决策**：`ai/platform_runtime.py:68`（锁表）、`:333-344`（分支）、`:464-470`（探测）、`:1717-1724`（`_get_run_event_lock`）。归 **P2-Locks** → CP6 |
| 2 | `claim_pending_jobs()` 的 SELECT→COMMIT→逐条 CAS 是被 SQLite 读事务升级问题塑形，PG 陪跑 | **成立** | `services/durable_job_lease_service.py:60-62`（含注释「候选读取不应维持 SQLite 读事务，否则并发认领时可能升级写锁失败」）、`:65-88` 逐条 CAS。同类形状在 `recover_expired_running_jobs:229-239`（只读探测后 commit，避免无命中 UPDATE 争抢 writer） |
| 2' | 应改为 `FOR UPDATE SKIP LOCKED` 或单条 UPDATE/CTE 原子 claim | **成立但需修正** | 见 §0-3：**必须先改事务边界**，否则加了 `skip_locked` 也是零收益。这是 CP3 的实质内容，不是「加个关键字」 |
| 3 | `lock_scheduler_state_for_queue_admission()` 用 `version += 1` + flush 找最低公共原语 | **部分成立** | `services/rendering/repository.py:59-67` 确实如此，注释也写明双侧语义；调用点 `services/rendering/request_service.py:121`。但「全仓都在找最低公共原语」被 §0-2 的 12 处 `with_for_update()` 反证。此处保留写、只做 CP2 的命名与注释归属 |
| 4 | `SQLITE_BACKOFF_DELAYS` 名字过时，`detect_transient_write_conflict()` 实际已覆盖 PG `40P01`/`40001` | **成立** | `db/errors.py:77` `_PG_RETRYABLE_SQLSTATES = {"40P01","40001"}`、`:80` 统一判据（含打点副作用 `:100-104`）。过时命名共 **4 组 + 1 条日志事件**，见 CP1 清单 |
| 5 | SQLite 与 PG 已是两个 deployment profile，不是两个平等后端 | **成立** | `db/sqlite_single_process.py:22`（排他锁）、`:111`（拒绝 `WEB_CONCURRENCY`/`UVICORN_WORKERS` > 1）、`:124`；`services/redis_runtime_client.py:277` 拒绝 PG + `memory://`、`:281-287` 拒绝 `memory://` + 多 worker、`:299` `is_postgresql_database_url`。**事实已存在，但被拆在 3 个模块、4 处校验里，没有单一概念** → CP5 |
| 6 | 不放弃 SQLite；明确「SQLite 不参与分布式语义」 | **成立且已定案** | 与 **D1=A**（2026-09-24 定案：SQLite Lite 长期一等公民）一致。本文不重开 D1 |
| 7 | `event_index = event_index + 1 RETURNING` 是应当保持的共享实现 | **成立** | `ai/run_event_writer.py:24-33`，并把写围栏条件并入同一条 UPDATE（`:37`）。**这是本仓最好的跨库并发样板，CP3 应对齐它的风格** |
| 8 | Backend × 8 / 10000 jobs 下会大量 CAS 竞争失败、吞吐下降 | **方向成立，数字未验证** | 现行评估 §5 明确 D2 写路径基线**仍未采集**。竞争上界受 `limit`（构建侧 `:275` 取 10）与并发配置约束，代价是 round trip 与无效 CAS，不是正确性。CP3 必须带 D2 度量门，不得凭推测施工 |
| 9 | 只拆「并发 primitive」5 类（job claim / leader / queue admission / write retry / process topology），95% 业务代码共用 | **成立** | 本文 CP1–CP6 与之一一对应，见 §2 映射表。其中 leader election 目前**无实现**（Lite 单进程不需要，PG 侧尚未做 Backend × N），列为 CP3 的可选延伸而非本轮范围 |

---

## 2. 改造项与既有编号映射

| 本文 | 既有编号 | 内容 | 契约影响 | 风险 |
| :--- | :--- | :--- | :--- | :--- |
| **CP1** | **2b**（D1=A 已重立） | 统一写重试，**session 工厂签名**；清理 `SQLITE_*` 过时命名 | 无 | 低 |
| **CP2** | **2d**（有限重立） | 事务技巧语义化：`end_read_before_write` / `acquire_admission_lock` | 无 | 低 |
| **CP3** | P1-TaskModel 子集 / P2-Dialect | claim 按**事务形态**分方言（PG 单事务 SKIP LOCKED，SQLite 跨 commit CAS） | **有**（claim 内部实现，签名不变） | 中 |
| **CP4** | P1-TaskModel | 折叠 `project_build_service.claim_job` 到共享 claim | 有 | 中 |
| **CP5** | P5 Lite 边界 / D1=A | 部署 profile 一等化 + 启动期拒绝非法组合 | 无（新增校验） | 低 |
| **CP6** | P2-Locks | 进程锁定位澄清：明确非分布式原语 | 无 | 低 |

外部评审的「5 类 primitive」映射：job claim → CP3/CP4；write conflict retry → CP1；queue admission → CP2；process topology → CP5；global leader → **本轮不做**（无实现、无需求，PG 多副本立项时再议，届时优先 `pg_advisory_lock` 而非新表）。

---

## 3. 先做批次：CP1 / CP2 / CP5 / CP6

这批不动任务契约，可独立于 P3 推进。

### CP1（=2b）统一写重试与命名收口

**现状：4 套重试、4 组过时命名，语义各不相同。**

| 位置 | 参数 | 形态 | 备注 |
| :--- | :--- | :--- | :--- |
| `ai/platform_runtime.py:65-66,346-369` | 4 次 / base 25ms 指数 | 复用同一 session，重试间 `rollback()` + `session.get(..., populate_existing=True)` 刷新实体 | 另有「仅当无 pending 变更才允许重试」前置判定（`:334-338`、`:454-462`） |
| `services/page_screenshot_job_service.py:51,437-516` | 3 次 / 50ms 指数 | 复用同一 session，重试内含快照校验与 `_mark_job_stale` 分支 | 日志事件名 `page.screenshot.job.sqlite_lock_retry`（`:510`）已名不副实 |
| `ai/page_mutation_executor.py:459-474` | 3 次 / 50ms 指数 | **每次尝试新建 session**（`self._session_factory()`），`finally` 关闭 | ← **这是 2b 要求的 session 工厂形态的在仓参考实现** |
| `services/idempotency_service.py:28,168-186` | 固定表 `[0.05,0.1,0.2]` | 只重试**读**；`for-else` 兜底再读一次（`:185-186`） | 常量名 `SQLITE_BACKOFF_DELAYS`、注释「SQLite 锁重试读取」均过时 |

**要求**：

1. 新建 `backend/app/db/retry.py`，以 **session 工厂**为参数（`Callable[[], AsyncSession]`），**不得**恢复历史稿的 `run_with_write_retry(session, fn)` 旧签名（`archive/architecture-assessment-2026-09-24.md:175` 明确禁止）。
2. 必须同时容纳现有四类语义，缺一即视为设计不合格：
   - 每尝试新建 session（`page_mutation_executor`）与复用传入 session（其余三处）两种生命周期；
   - 尝试之间刷新实体（`platform_runtime:364-367`）；
   - `for-else` 兜底再读（`idempotency_service:185-186`）；
   - 重试内结构化日志（`page_screenshot_job_service:507-515`）。
3. 各处**保留自己的次数与退避数值**作为参数传入，不在本项统一调参（调参属 D2 产出）。
4. 判据只用 `db/errors.detect_transient_write_conflict`，**不得**新增第二个谓词（门禁 `test_db_adapter_layer.py:87` 会红）。
5. 命名与日志收口（可独立提交，纯改名）：
   - `SQLITE_BACKOFF_DELAYS` → `WRITE_CONFLICT_BACKOFF_DELAYS`
   - `SQLITE_LOCK_RETRY_ATTEMPTS` → `WRITE_CONFLICT_RETRY_ATTEMPTS`
   - `_SQLITE_EVENT_WRITE_MAX_ATTEMPTS` / `_SQLITE_EVENT_WRITE_RETRY_BASE_SECONDS` → 去 `SQLITE_` 前缀
   - 日志事件 `page.screenshot.job.sqlite_lock_retry` → `page.screenshot.job.write_conflict_retry`
   - `db/errors.py:73-75` 的 `SQLITE_BUSY_ERROR_CODE` / `SQLITE_LOCKED_ERROR_CODE` / `SQLITE_LOCK_MESSAGES` **保留 SQLite 命名**——它们确实是 SQLite 专属常量，与 `:77` 的 `_PG_RETRYABLE_SQLSTATES` 对称，改名反而丢信息。

**验收**：`tests/unit/test_db_adapter_layer.py` 新增断言——`backend/app` 内 `except OperationalError` + `detect_transient_write_conflict` 的手写重试循环只允许出现在 `app/db/retry.py`；`grep -rn "SQLITE_BACKOFF_DELAYS\|SQLITE_LOCK_RETRY_ATTEMPTS\|_SQLITE_EVENT_WRITE" backend/app` 为空。既有行为测试（`test_page_screenshot_job_durability.py`、`test_ai_platform_runtime_concurrency.py`，含精确 rollback 次数断言）**不得修改断言值**。

### CP2（=2d）事务技巧语义化

**范围已比历史稿缩小**：`archive/architecture-assessment-sqlite-2026-09.md:536` 列出的 4 个调用点中，`services/code_check_service.py` 已不含该技巧（实测 grep `SQLite|sqlite|commit()` 无命中），**只剩 3 个**：

| 位置 | 现状 | 处理 |
| :--- | :--- | :--- |
| `services/durable_job_lease_service.py:61-62` | 裸 `await session.commit()` + SQLite 原因注释 | 改为 `await end_read_before_write(session)`，原因移入 helper docstring |
| `services/durable_job_lease_service.py:227-239` | 只读探测后 commit，空队列不发 DML | 同上，保留「空则不发 UPDATE」语义 |
| `services/rendering/repository.py:63-66` | `version += 1` + flush 当准入锁 | 改为 `acquire_admission_lock(state)`；**按历史稿 C5 结论保留写、只改名与纠正注释，禁止使用「假写」措辞** |

新建 `backend/app/db/tx.py`。**明确不做**：不引入 `read_probe` 之类零调用点别名（D1=A 复核结论「2d 仅有限重立」）。

**验收**：`backend/app/services` 与 `backend/app/ai` 下不再出现解释 SQLite 事务行为的注释（断言方式：grep 业务子树中同时含「SQLite」与「事务/读事务/writer」的注释行数为 0）；`rendering/repository.py` 的准入锁语义由既有 `tests/unit/test_render_control_plane.py:263` 的替身同步改名，**不得删测试**。

### CP5 部署 profile 一等化

**问题不是缺少校验，而是校验散落、没有单一概念。** 现状四处：

- `db/sqlite_single_process.py:69` 文件库排他锁 + `:111` 拒绝多 worker 环境变量；
- `services/redis_runtime_client.py:277` 拒绝 `PostgreSQL + memory://`；
- `services/redis_runtime_client.py:281-287` 拒绝 `memory:// + 多 worker`；
- `services/signing_identity.py:18` 也独立引用 `read_explicit_worker_count`。

**要求**：

1. 新建 `backend/app/db/profile.py`，从 `database_url` + `redis_url` + 显式 worker 数派生**单一** profile 对象，字段只保留有消费者的：`is_lite`（SQLite 单进程）、`is_distributed`（PG + 真实 Redis）、`backend_multi_process_allowed`。**不加** `skip_locked` / `advisory_lock` 一类当前无分支消费者的能力布尔——见 §0-1，它们不产生 SQL 差异，加进来就是死配置。
2. 现有 4 处校验改为消费该 profile，**校验语义与错误消息不变**（避免动 compose 与文档）。
3. 新增一条拒绝：`is_lite` 且显式声明多 Backend 副本 → 启动失败。这是外部评审建议的「SQLite + BACKEND_MULTI_INSTANCE=true 直接拒绝」；当前 `_reject_multi_worker_env` 只覆盖进程内 worker 数，**不覆盖 compose 副本数**，是真实缺口。
4. **必须在 `lifespan` 内取值，不得放进 `create_app()`**：`main.py` 底部有模块级 `app = create_app()`，导入期副作用会让任何 `import app` 的脚本/测试失败——单进程守卫曾因此让 `tests/workspace/test_import_boundaries.py` 全红。

**验收**：`/readyz` 与 `main.py:266,466` 的健康详情暴露 profile 名；新增单测覆盖 4 个合法组合与 2 个非法组合（SQLite+多副本、PG+`memory://`）。

### CP6 进程锁定位澄清

`ai/platform_runtime.py:68` 的 `_RUN_EVENT_LOCKS` 是**进程内按 run 的事件追加串行化**，不是分布式原语；PG 下 `run_event_writer.allocate_run_event_index` 的 `UPDATE ... RETURNING` 已保证游标单调，进程锁只对「重试路径的 rollback 交错」有意义。

**要求**：不删锁（`test_ai_platform_runtime_concurrency.py` 固化了锁序行为），只把上述定位写进模块 docstring 与 `docs/developer/backend/`，并在 CP3 落地后评估 PG 分支是否可跳过进程锁。**禁止**把它当作 Backend × N 的互斥手段——多副本下它天然失效。

---

## 4. 后做批次：CP3 / CP4（绑定 P3 契约冻结）

### CP3 claim 的事务形态分方言

**唯一需要真正分方言的原语。** 目标形态：

```text
业务层（6 个队列 + 构建）
        │  签名不变：claim_pending_jobs(session, model, *, worker_id, limit, lease_seconds, ...)
        ▼
durable_job_lease_service.claim_pending_jobs
        ├── PostgreSQL：单事务内
        │     SELECT id ... FOR UPDATE SKIP LOCKED LIMIT n
        │     UPDATE ... WHERE id IN (锁定集) AND status='pending'
        │     COMMIT                     ← 全程不提前 commit
        └── SQLite：维持现状
              SELECT 候选 → COMMIT → 逐条 CAS UPDATE → COMMIT
```

**硬约束**：

1. **SQLite 分支字节级维持现状语义**。`end_read_before_write`（CP2）之后仍必须 commit，否则并发认领会撞上读事务升级写锁失败。CP3 对 Lite 的唯一可见变化是函数调用名。
2. **PG 分支必须证明「最多一个执行者取得同一任务」不被削弱**。`SKIP LOCKED` 改变的是候选集选取，不是围栏；`UPDATE` 的 `status='pending'` + `cancel_requested_at IS NULL` 谓词必须保留，作为兜底 CAS。
3. **不得把方言判断散到调用点**。分支只允许存在于 `durable_job_lease_service` 内部；新增门禁断言 `with_for_update(skip_locked=True)` 在 `backend/app` 中只出现于该文件（对齐 `test_db_adapter_layer.py` 既有风格）。
4. **`recover_expired_running_jobs`（`:212-316`）本轮不动**。它的只读探测是为了「空闲期不发无命中 UPDATE」，属写放大治理（现行评估 §3 已关闭项 `023c95c`），与 claim 竞争无关；改成单事务会重新引入空闲写放大。
5. **D2 度量门**：施工前必须采集 PG 侧 claim 竞争基线（无效 CAS 次数 / claim round trip / tick P95），施工后对比。D2 目前**仍未实测**（现行评估 §5、决策表「D2 仍待实测」），打点入口 `db/metrics.py`（`record_write_conflict` / `record_sql`）已就绪。**无基线不得声称吞吐改善。**

**验收**：`tests/integration/test_multi_replica_coordination.py`（现有并发认领用例 `:149`）在 PG 与 SQLite 两侧均通过且断言值不变；新增用例断言 PG 分支下两个并发 claim 的候选集不相交；`tests/integration/test_ai_page_mutation_queue.py` 三处 `claim_pending_jobs`（`:124,384,528`）行为不变。

### CP4 折叠构建 claim

`services/project_build_service.py:237-321` 是第二份手写 claim，且已随 `4becd41` 继续增长（该提交给本文件 +89 行）。它复用了 `renew_running_job_lease` / `transition_owned_running_job`（`:342-345`、`:386-391`、`:445-446`，通过 `owner_attr="lease_owner"` / `heartbeat_attr="claimed_at"` 适配命名差异），**唯独 claim 自己写**。

**要求**：

1. 把 `claim_job` 的候选查询作为 `candidate_query` 传入 `claim_pending_jobs`（该参数已存在，`durable_job_lease_service.py:47`），保留构建侧特有谓词：绝对期限 `deadline_clause`（`:256-259`）、租约过期或为空（`:263-266`）、`job_id` 定向领取（`:268-269`）。
2. 保留构建侧特有的**租约裁剪**语义：`_cap_lease_expiry`（`:283-286`）使新租约不越过 `deadline_at`，剩余预算不足则跳过。共享 claim 目前用统一 `lease_seconds`（`:52`），需要新增可选的 per-candidate 租约裁剪钩子——**这是 CP3 之后才动的原因：钩子形状应由 P3 契约决定，不该由构建侧倒推。**
3. `attempt_id` 铸造（`:252`）与产物指针清空（`:311`）保留在构建侧，通过 `values` 扩展点传入。
4. **不得**丢失 `4becd41` 刚修的语义：终态需有效租约、`complete(success)` 对同一 `attempt_id` 幂等返回 200、产物提升失败时的对象回收需先复核该行是否仍引用同一 key。

**验收**：`tests/integration/test_project_build.py`（`4becd41` 新增 162 行）全绿且断言不改；`grep -c "候选读取不应维持 SQLite" backend/app` 从 2 降为 1（只剩 `durable_job_lease_service`）。

---

## 5. 执行顺序与门禁

| 序 | 工作 | 依赖 | 说明 |
| :--- | :--- | :--- | :--- |
| 1 | ~~CP1 命名收口（纯改名部分）~~ | — | **已完成**（§9.1） |
| 2 | ~~CP2 `db/tx.py`~~ | — | **已完成**，实际 4 个调用点（§9.2-2） |
| 3 | ~~CP5 `db/profile.py`~~ | — | **已完成**；残留缺口见 §9.2-7 |
| 4 | ~~CP1 `db/retry.py` 统一重试~~ | 1 | **已完成**，3 套写重试收口、读重试例外见 §9.2-4 |
| 5 | ~~CP6 文档与定位澄清~~ | 3 | **已完成** |
| 6 | **P3 任务运行时契约冻结** | — | 现行评估 §7.3 序 1，**本文不代替它**；未开始 |
| 7 | CP3 claim 分方言 | 2、6、D2 基线 | 带度量门；**未开始**，先回答 §7-4 |
| 8 | CP4 折叠构建 claim | 7 | **未开始** |
| 9 | Agent Run lease / Backend × N | 7、8 | 外部评审担心的「再产生一套兼容逻辑」在此被前置消解 |

每步最小验证：

```powershell
uv run --project backend pytest backend/tests/unit/test_db_adapter_layer.py
pnpm run test:backend:unit
pnpm run test:backend:integration
```

CP3/CP4 追加 `pnpm run test:backend:api` 与（PG 侧）`tests/integration/test_multi_replica_coordination.py`。

**门禁现状（2026-09-28 实测，基线 `4becd41` + 本文）**：`pnpm run test:repository` 4 files / 13 tests 全绿，`pnpm run test:contracts` 10 files / 33 tests 全绿。此前记录的 `documentation.test.ts` 46 条断链（`archive/` 历史稿深度错误 + 09-24 稿移入 archive 未改链接）**已修复**，不再是既有红。本文 6 条相对链接已逐条验证可解析；后续实施不得引入新断链。

---

## 6. 明确不做

| 项 | 理由 |
| :--- | :--- |
| `DatabaseCapabilities` / `db_profile.skip_locked` 一类能力布尔层 | §0-1：SQLAlchemy 已按方言渲染，布尔不改变生成 SQL；加了就是死配置 |
| 按方言拆 Adapter / 两套 Repository | 与 D1=A「不维护两套 Backend」冲突；12 处 `with_for_update()` 证明共享路径可行 |
| 放弃 SQLite 或把 Lite 降为「开发用」 | D1=A 已定案（2026-09-24），本文不重开 |
| `BoolInt` 伪布尔收口 | D1=A 复核结论「维持裁剪」，不重立 |
| 全局 leader election / `pg_advisory_lock` | 当前无实现、无消费者；Backend × N 立项时再议 |
| `recover_expired_running_jobs` 改单事务 | 会重新引入空闲写放大（`023c95c` 已治理） |
| 历史迁移改写双方言 | P4 只约束**新**迁移 |
| 调重试次数/退避数值 | 属 D2 产出，本轮只搬参数不改值 |

---

## 7. 尚未验证（不得当作已有能力）

1. **PG 侧 claim 竞争基线未采集**（D2 仍待实测）——CP3 的收益目前只有推理，没有数字。
2. **Backend × N 从未联调**：现行评估 §5 列明的多实例共享对象存储、密钥一致、跨实例迁移与租约，全部未验收。CP5 的 profile 校验只保证「非法组合启动失败」，不证明「合法组合可横向扩展」。
3. **故障注入缺失**：`busy_timeout` 耗尽、PG 序列化失败风暴、Worker 掉线下的 claim 行为均无端到端验收；CP1 统一重试后尤其需要一次 SQLite BUSY 与 PG `40001` 的对拍演练。
4. **`AgentWriteGuardedAsyncSession`（`db/session.py:29-42`）会在每次 `commit()` 前执行写围栏校验**——这一点已由 §9.2-3 实测确认（正是它使 `page_screenshot_job_service.py:110` 的 `rollback()` 不能替换为 `commit()`）。**仍未量化**的是：PG 单事务 claim 会把围栏校验挪到 claim 提交点，是否与 `SKIP LOCKED` 的持锁窗口互相放大等待。CP3 施工前必须先回答。
5. **CP4 的租约裁剪钩子形状未定**，取决于 P3 契约；本文只给约束，不给接口。
6. **`idempotency_service` 的读重试路径零测试覆盖**（§9.2-4）。它的冲突退避、`None` 重试与 `for-else` 兜底再读目前完全靠代码审查保证；这也是它未被并入 `db/retry.py` 的直接原因。补覆盖是收口它的前置条件。
7. **`rollback()` 会 expire ORM 实体**（§9.3）已在 SQLite 侧踩到一次；PG 侧单事务 claim 的 expire 时机尚未验证。

---

## 8. 与既有文档的关系

| 文档 | 关系 |
| :--- | :--- |
| [`../architecture-assessment-2026-09-25.md`](../architecture-assessment-2026-09-25.md) | 现行评估。本文细化其 **P2-Dialect / P2-Locks / P1-TaskModel**，不改变其 §7.3 优先序；P3 契约冻结仍排在 CP3/CP4 之前 |
| [`../archive/architecture-assessment-sqlite-2026-09.md`](../archive/architecture-assessment-sqlite-2026-09.md) | S1–S8 与 2a–2f 原始定义。**2a/2c/2e/2f 已实施**（证据见 §0-4）；本文承接其 **2b/2d**，并修正 2d 的调用点清单（`code_check_service.py` 已无该技巧） |
| [`../archive/architecture-assessment-2026-09-24.md`](../archive/architecture-assessment-2026-09-24.md) | D1=A 定案与 2b 重立约束（`:175` 禁止旧签名）来源 |
| [`./runtime-multi-deployment-scaling-plan.md`](./runtime-multi-deployment-scaling-plan.md) | T2-2 构建持久领取（`e156630`）是 CP4 的对象；其阶段 0 门禁与多副本 E2E 缺口仍然有效 |
| [`./lite-memory-adapter.md`](./lite-memory-adapter.md) | 运行态（`memory://`）与本文的持久化并发原语是**两条独立边界**；其核心不变量「DB 任务领取/租约/终态不得放运行态」约束 CP5 的 profile 派生不得读取运行态 |

---

## 9. 实施记录（2026-09-28）

基线 `4becd41`，实施范围 CP1a / CP1b / CP2 / CP5 / CP6。**CP3 / CP4 未实施**，门禁条件（P3 契约冻结 + D2 基线）均未满足。

### 9.1 已落地

| 项 | 落地内容 |
| :--- | :--- |
| **CP1a** | 改名 `SQLITE_BACKOFF_DELAYS`→`WRITE_CONFLICT_BACKOFF_DELAYS`、`SQLITE_LOCK_RETRY_ATTEMPTS`→`WRITE_CONFLICT_RETRY_ATTEMPTS`、`_SQLITE_EVENT_WRITE_*`→`_EVENT_WRITE_*`；日志事件 `page.screenshot.job.sqlite_lock_retry`→`.write_conflict_retry`；4 处「SQLite 锁/SQLite 重试」措辞改为写冲突口径。`db/errors.py:73-75` 的 SQLite 专属常量按计划**保留原名**。 |
| **CP1b** | 新建 `backend/app/db/retry.py`：`run_with_write_retry`（session 工厂签名）、`exponential_backoff_delays`、`WriteConflictContext`。收编 3 个写重试点：`ai/page_mutation_executor._run_final_write`、`ai/platform_runtime._append_event_with_retry`、`services/page_screenshot_job_service._finalize_captured_job`。各处次数与退避数值**原样保留**为参数。 |
| **CP2** | `db/tx.py` 扩展 `acquire_admission_lock`；4 个调用点改用命名原语：`durable_job_lease_service`（claim 候选读、recovery 空队列）、`rendering/repository.lock_scheduler_state_for_queue_admission`、`project_build_service.claim_job`。SQLite 事务机理移入 helper docstring。 |
| **CP5** | 新建 `backend/app/db/profile.py`：`DeploymentProfile` + `resolve_deployment_profile`；`read_explicit_worker_count` 由 `db/sqlite_single_process.py` 迁入，`is_postgresql_database_url` 由 `services/redis_runtime_client.py` 迁入（无外部消费者，已从其 `__all__` 移除）。`sqlite_single_process`、`redis_runtime_client`、`signing_identity` 三处校验改为消费 profile，**错误消息逐字不变**。新增拒绝：SQLite 文件库 + `BACKEND_MULTI_INSTANCE=true` 启动失败。`/readyz` 与启动日志暴露 `deployment_profile` / `backend_multi_process_allowed`。 |
| **CP6** | 未删锁。定位写进 `_get_run_event_lock` docstring 与 `docs/developer/backend/ai-agent.md` 新增小节「事件追加的并发边界」。 |
| 门禁 | `tests/unit/test_db_adapter_layer.py` 新增 2 条防漂移断言；新增 `tests/unit/test_deployment_profile.py`（9 例）；`AGENTS.md` backend 开发约束新增 `app/db/` 边界条目。 |

**实测**：`pnpm run test:backend` **1069 passed / 9 skipped**；`pnpm run test:contracts` 10 files / 33 tests 全绿（含 `test:repository`）。

### 9.2 与规划的偏差（均为实测后修正）

1. **`db/tx.py` 已存在**，含 `commit_end_read`（唯一消费者 `code_check_service.py:523`）。因此**沿用该名字**，未引入规划里写的 `end_read_before_write`——两个同义名字比一个差。`acquire_admission_lock` 为本次新增。
2. **CP2 调用点是 4 个不是 3 个**：`project_build_service.claim_job` 的候选读提交与 `durable_job_lease_service` 完全同形，顺手一并收口（只换原语，**不动 claim 算法**，CP4 的折叠仍未做）。
3. **`page_screenshot_job_service.py:110` 刻意未转换**。该处是 `rollback()` 而非 `commit()`：`AgentWriteGuardedAsyncSession.commit()`（`db/session.py:32-42`）在每次提交前执行写围栏校验，换成 `commit_end_read` 会凭空多一次围栏查询并可能抛 `AgentRunWriteFenceLost`。**这把 §7-4 从「未验证」变成了「已确认的真实约束」**，CP3 设计时必须处理。
4. **CP1b 排除了 `idempotency_service`（原第 4 套）**。它是**读**重试：不 rollback、结果为 `None` 也继续重试、`for-else` 兜底再读一次。强行并入需要 3 个只为它存在的开关；更关键的是它跑在请求级 session 上，**加 rollback 有可能丢弃调用方未提交的占位写入**，而该路径当前**零测试覆盖**，属不可验证风险。已在门禁中显式 allow-list 并写明理由，不得以它为模板新增第三套重试。
5. **统一采用「先 rollback，再判可重试/是否用尽」**（原 A/C 顺序），而非 B 的「先判可重试再 rollback」。差异只在**不可重试**错误上：B 原来不 rollback。被 pin 的断言 `rollback_count == before + 2` 只覆盖可重试路径，两种顺序都通过；选 A/C 顺序是因为 C 复用请求 session，失败后还要写任务终态，留在脏事务里更危险。B 仅在 `_session_has_pending_changes()` 为假时才进入重试路径，多一次 rollback 无副作用。
6. **CP5 未把 `redis_url` 纳入 profile 派生**（规划原文写了）。`resolve_runtime_state_profile` 已是 redis scheme 的单一判据，在 `db/profile.py` 再解析一次会造出第二事实源；改为 `redis_runtime_client` 消费 `profile.is_distributed`。
7. **CP5 残留缺口**：拓扑拒绝仍在 `ensure_sqlite_single_process` 的内存库 early-return **之后**，因此「SQLite `memory://` + `BACKEND_MULTI_INSTANCE=true`」不被拒。刻意如此——把检查前移会让 `test_sqlite_memory_url_skips_guard` 在开发者 shell 恰好设了 `WEB_CONCURRENCY` 时误红。该组合也不是真实部署形态（Lite 用文件库），列为已知残留而非静默扩大范围。

### 9.3 实施中发现的新约束（后续必做项需继承）

**`rollback()` 会 expire 会话内全部 ORM 实体**，因此 `on_conflict` 钩子里读取实体属性会触发同步懒加载并抛 `MissingGreenlet`。原 `platform_runtime` 代码把 `run_id` 在循环**之前**取成标量，正是规避此问题；首次改写时踩中并被 `test_append_event_should_retry_clean_sqlite_transaction_after_lock` 拦住。已把该约束写进 `WriteConflictContext` docstring 与调用点注释。**CP3 的单事务 claim 同样在事务内持有 ORM 实体，设计时必须显式考虑 expire 时机。**
