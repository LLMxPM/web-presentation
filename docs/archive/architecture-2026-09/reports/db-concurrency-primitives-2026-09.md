# 数据库并发原语收口规划（SQLite Lite / PostgreSQL Prod）

> **归档说明（2026-09-28）**：CP1–CP6 全部落地并完成验证面补强（见 §9），本计划移入 `archive/`。残留缺口已抽入 [`../plans/remaining-work-2026-09-28.md`](./remaining-work-2026-09-28.md)。
>
> 状态：**已实施（2026-09-28）**。CP1a / CP1b / CP2 / CP3 / CP4 / CP5 / CP6 全部落地，见 §9 实施记录。CP3 的度量门已在真实 PostgreSQL 16 上采集并复测（§9.4、§9.5），本文 §0-3 的「收益为零」措辞已被实测**部分证伪**，修正见 §0-3 与 §9.2。验证面补强见 §9.6（基准脚本入库、PG 认领用例、idempotency 读重试覆盖）。
> **编号警示**：本文 §4 CP3 曾把该度量门写作「D2」，但它与现行评估的 **D2 写路径基线门**（Lite 2C4G 空闲/混合两轮 + `/metrics/db-write`）不是同一件事。**现行评估的 D2 仍未采集，不因本文关闭**，本文的测量统一称「claim 竞争基线」。
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

   > **本条「收益为零」已被 §9.4 实测部分证伪。** 跨事务加 `SKIP LOCKED` 仍然消除候选集重叠（无效 CAS 从 75–90% 降到 0%），因此并非零收益；但它把「CAS 空转」换成「等锁阻塞」，吞吐天花板只到同事务形态的一半左右，且不再有行锁保证。准确表述是：**跨事务 `SKIP LOCKED` 治症状，同事务 `SKIP LOCKED` 才治成因。**

4. **模型/类型/索引层比外部评审以为的更结实：已有防漂移门禁。** `backend/tests/unit/test_db_adapter_layer.py` 锁住了四件事：写冲突判据单定义（`:87`）、`driver_connection` 下钻只允许在 `app/db/locks.py`（`:76`）、`with_variant(JSONB` 只在 `db/types.py` 与迁移 helper（`:100`）、model 不得写 `sqlite_where=`/`postgresql_where=`（`:110`）。对应历史步骤 **2a / 2c / 2e / 2f 已实施完毕**。

5. **「SQLite 锁语义泄漏到业务层」部分过时。** 驱动对象下钻已收口（见上）；仍留在 AI 层的是**调用与锁序决策**：`ai/platform_runtime.py:333-344` 依据 `_has_sqlite_write_transaction()`（`:464-470`）决定走进程锁还是重试路径。泄漏面比描述的小，但确实还在，归 **P2-Locks**。

6. **外部评审完全没提、但比它列的四点更贵的问题：claim 已经有第二份手写拷贝。** `services/project_build_service.py:237-321` 的 `claim_job` 自行实现了 SELECT→commit→CAS，并把同一条 SQLite 注释复制到 `:276`。它没有复用 `durable_job_lease_service.claim_pending_jobs`——后者已被 **5 个队列 / 6 个调用点**使用（`ai/page_mutation_queue.py:152`、`ai/component_mutation_queue.py:115`、`ai/image_generation_queue.py:129`、`services/page_screenshot_job_service.py:327,339`、`services/asset_render_hint_backfill_job_service.py:145`），而构建侧只复用了 `renew_running_job_lease` / `transition_owned_running_job`（见 CP4）。**这就是现行评估的 P1-TaskModel；不先折叠它，任何原语抽象都会立刻产生第三种方言。**

**因此本文的处方**：不建能力层、不建 Adapter 矩阵；做 **CP1（=2b）命名与重试收口**、**CP2（=2d）事务技巧语义化**、**CP5 部署 profile 一等化**三件低风险收口，再把 **CP3 事务形态分方言 claim** 与 **CP4 折叠构建 claim** 绑定到 P3 任务运行时契约冻结之后执行。

**对外部评审排序建议的修正**：它主张「先做 DB concurrency primitive 收口，再做 Agent Run lease」。**部分同意**——CP1/CP2/CP5 无契约影响，应当先做；但 CP3/CP4 改的就是 claim 契约本身，**先做等于把 P3 要冻结的东西先实现一遍再返工**。正确顺序是 CP1/CP2/CP5 → P3 契约冻结 → CP3/CP4 → Agent Run lease。

> **本段排序已被 §5 修正 1、2 推翻，此处保留原文以便追溯。** 实测结论：CP3/CP4 对外签名不变、只改内部事务形态，与 P3 契约冻结无耦合；CP4 必须**先于** CP3。实际落地顺序为 CP1a/CP1b/CP2/CP5/CP6 → CP4 → claim 竞争基线 → CP3，全部已完成（§9）。仍受 P3 约束的是**认领语义**（批量协议形态），不是本原语的实现形态。

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
| 8 | Backend × 8 / 10000 jobs 下会大量 CAS 竞争失败、吞吐下降 | **成立，且比评审预估更严重（已实测）** | 原判定为「方向成立、数字未验证」。claim 竞争基线已在真实 PG 16 上采集（§9.4）：limit=1 时 8 个 worker 的认领吞吐只有单 worker 的 **1/4**（9.5 → 2.4 jobs/s），16 worker 进一步降到 2.0，无效 CAS 占比 75% → 90%。这不是「吞吐下降」而是**负缩放**：加副本反而变慢。修正后的正确表述是「竞争上界不受 `limit` 保护，因为所有 worker 都按 `created_at` 抢同一批头部候选」 |
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

**评估结论（§9.6）：PostgreSQL 不可跳过。** 进程锁串行化的是同一 `AsyncSession` 上的并发追加与重试 rollback（会话不可并发共用），不是跨进程互斥；跨进程游标已由 `allocate_run_event_index` 原子递增覆盖。与方言无关。仅当改为「每次追加独立会话」时才可在 PG 跳过，当前不改。

---

## 4. 后做批次：CP3 / CP4（已实施，见 §9.1、§9.4–§9.5）

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
5. **度量门（本文原写作「D2」）**：施工前必须采集 PG 侧 claim 竞争基线（无效 CAS 次数 / claim round trip / tick P95），施工后对比；无基线不得声称吞吐改善。**已满足**：见 §9.4（施工前）与 §9.5（施工后同口径复测）。注意这条度量门与现行评估的 **D2 写路径基线门**不是一件事，后者仍未采集，本文不代替它。打点入口 `db/metrics.py`（`record_write_conflict` / `record_sql`）服务于后者，本轮未使用。

**验收**：`tests/integration/test_multi_replica_coordination.py`（现有并发认领用例 `:149`）在 PG 与 SQLite 两侧均通过且断言值不变；新增用例断言 PG 分支下两个并发 claim 的候选集不相交；`tests/integration/test_ai_page_mutation_queue.py` 三处 `claim_pending_jobs`（`:124,384,528`）行为不变。

**实施结果（2026-09-28）**：

- 分支落在 `claim_rows_by_cas`（CP4 抽出的认领时序）内部，判据是新增的 `db/tx.row_locks_hold_until_commit`，而不是布尔能力开关。
- **实现与本文目标形态有一处偏差**：PG 侧仍是「逐条 CAS」，没有改成 `WHERE id IN (锁定集)` 的单条批量 UPDATE。原因是 `claim_cas` 必须支持逐候选取值（构建侧的租约裁剪按 `deadline_at` 逐行不同），批量形态无法表达。这不是瓶颈：§9.4 基准里的「同事务 SKIP LOCKED」变体用的正是**批量 UPDATE** 形态，而 §9.5 复测的 CP3 生产代码是**逐条 CAS** 形态，两者在全部并发档上一致（8 worker：35.2 vs 33.6；16 worker：36.8 vs 35.2，在复测偏差内），说明收益全部来自**事务边界**而不是语句合并。
- SQLite 分支的 SQL 与语义未变：`with_for_update(of=model, skip_locked=True)` 在 SQLite 方言编译后与收口前逐字相同（已用双方言编译对照验证），事务形态判据在 Lite 侧为假因此仍走 `commit_end_read`。Lite 的全部回归仍由现有 1074 条用例守住。
- `FOR UPDATE OF <目标任务表>` 显式限定加锁表，避免带 JOIN 的候选查询（`ai/page_mutation_queue.py`、`ai/component_mutation_queue.py` 都 JOIN `ai_agent_runs`）把 Run 行也锁住。
- **`claim_cas` 是同步回调不是疏忽**：类型上排除持锁窗口内 await 慢路径，等于把硬约束 2 固化进签名。
- 门禁三条：`skip_locked` 只出现在 `durable_job_lease_service.py`；`dialect.name` 只出现在 `app/db/` 与 Schema 播种脚本；SQLite 判据取值直接断言。
- **验收缺口**：本文要求的「PG 与 SQLite 两侧均通过且断言值不变」只在 SQLite 侧达成。`test_multi_replica_coordination.py` 与 backend 全部用例都强制跑 SQLite（`tests/fixtures/app.py:51` 覆写 `DATABASE_URL`），仓库没有 PG 侧的认领用例；PG 证据来自 §9.4 的独立基准脚本，其表结构是与标准队列同构的合成表，**不含业务谓词与 `AgentWriteGuardedAsyncSession` 写围栏**。

### CP4 折叠构建 claim

`services/project_build_service.py:237-321` 是第二份手写 claim，且已随 `4becd41` 继续增长（该提交给本文件 +89 行）。它复用了 `renew_running_job_lease` / `transition_owned_running_job`（`:342-345`、`:386-391`、`:445-446`，通过 `owner_attr="lease_owner"` / `heartbeat_attr="claimed_at"` 适配命名差异），**唯独 claim 自己写**。

**要求**：

1. 把 `claim_job` 的候选查询作为 `candidate_query` 传入 `claim_pending_jobs`（该参数已存在，`durable_job_lease_service.py:47`），保留构建侧特有谓词：绝对期限 `deadline_clause`（`:256-259`）、租约过期或为空（`:263-266`）、`job_id` 定向领取（`:268-269`）。
2. 保留构建侧特有的**租约裁剪**语义：`_cap_lease_expiry`（`:283-286`）使新租约不越过 `deadline_at`，剩余预算不足则跳过。共享 claim 目前用统一 `lease_seconds`（`:52`），需要新增可选的 per-candidate 租约裁剪钩子——**这是 CP3 之后才动的原因：钩子形状应由 P3 契约决定，不该由构建侧倒推。**
3. `attempt_id` 铸造（`:252`）与产物指针清空（`:311`）保留在构建侧，通过 `values` 扩展点传入。
4. **不得**丢失 `4becd41` 刚修的语义：终态需有效租约、`complete(success)` 对同一 `attempt_id` 幂等返回 200、产物提升失败时的对象回收需先复核该行是否仍引用同一 key。

**验收**：`tests/integration/test_project_build.py`（`4becd41` 新增 162 行）全绿且断言不改；`grep -c "候选读取不应维持 SQLite" backend/app` 从 2 降为 1（只剩 `durable_job_lease_service`）。

**实施结果（2026-09-28）——本项前提被证伪，交付形态与本文不同**：

本文要求「把候选查询作为 `candidate_query` 传入 `claim_pending_jobs`」即可折叠。**不成立**，实际核对后有三个障碍：

1. **两个模型的列词汇不相交。** `claim_pending_jobs` 硬编码 `model.cancel_requested_at` 谓词与 `error_code=None` 取值，而 `ProjectBuildJob`（`app/models/project_build_job.py`）**既没有 `cancel_requested_at` 也没有 `error_code` 列**——照原方案传入会直接抛 `AttributeError`。这才是构建侧当年自行实现 claim 的真实原因，不是偷懒。若强行合并，需要给共享函数加 `owner_attr`/`heartbeat_attr`/`cancel_attr`/`error_code_attr`/`extra_conditions`/`extra_values`/`lease_cap`/`max_claims` 共约 8 个可选参数。
2. **构建是「扫描多候选、只领取一个」的认领者。** 旧实现扫描 10 个候选但在第一次 CAS 成功后 `return`；直接复用会连着认领至多 10 个并只执行第 1 个，其余 9 个滞留在无人执行的 `running` 状态并持着有效租约。**这是原方案会引入的真实缺陷。**
3. 租约裁剪是**逐候选**计算，无法由统一的 `lease_seconds` 表达。

因此实际交付改为**只抽象真正会写错的部分**：新增 `claim_rows_by_cas` 收口「加锁读候选 → （按方言）结束读事务 → 逐条 CAS → rowcount 判定 → 统一提交」这一**时序**，由各服务自带自己的列词汇与领域取值。没有引入配置层，且默认形态下 5 个既有队列的调用完全不变。

顺带修掉旧实现的两个问题（均已在提交说明中记录）：

- 旧 `claim_job` 在一条也没抢到时直接 `return`，此时失败的 CAS 已经开启写事务却没有提交，SQLite 侧会把写锁带给调用方的下一次操作。现在无条件统一末尾提交。
- 旧实现没有「只领取一个」的约束（见上），现在由 `max_claims=1` 表达。

**门禁落地时发现的第三份手写 claim**：`ai/external_task_queue.py:510 _claim_ready_batch`。本文与外部评审都只数到两份。它**不并入**并列为显式例外，理由是共享助手不承诺它的三条语义：按业务主键 `batch_id` 认领、以 `lease_generation` 作为租约围栏条件、以及必须与 `AiAgentRequirement` 置 `resolving` 同事务原子完成且抢锁失败时 `rollback`（不是 commit）。硬套会丢掉围栏语义。

**验收结果**：`test_project_build.py`、`test_project_build_job_lease.py`、`test_project_build_worker_claim.py`、`test_multi_replica_coordination.py` 共 48 条全绿且断言未改；全部 6 个 claim 消费方相关用例 39 条全绿；backend 全量 1074 passed / 9 skipped。原验收里的 grep 判据已失效（CP2 阶段该注释被改写），改由 `test_claim_functions_must_delegate_cas_timing` 以 AST 精确判定「认领函数自己 execute 条件 UPDATE」。

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
| 7 | ~~CP3 claim 分方言~~ | 2、6、claim 竞争基线 | **已完成**（§9.4）。基线已实测；**对 6 的依赖已重新评估并解除**，理由见下 |
| 8 | ~~CP4 折叠构建 claim~~ | 7 | **已完成**，但交付形态与本文不同（§4 CP4 实施结果）；**实际先于 CP3 落地** |
| 9 | Agent Run lease / Backend × N | 7、8 | 外部评审担心的「再产生一套兼容逻辑」在此被前置消解 |

**对本文 §5 原排序的两处修正**：

1. **CP4 必须先于 CP3，不是后于。** 原文把 CP3 排在 CP4 之前。若在仍存在第二份手写 claim 时就给共享助手加分方言分支，结果是「共享实现被优化、构建 claim 保持旧形态」——恰好留下本文 §0-6 批评的分歧。实际执行顺序为 CP4 → claim 竞争基线 → CP3，CP3 的分方言因此只需落在一处。
2. **CP3 与 P3 契约冻结无耦合，门禁解除。** 原排序把 CP3 绑在 P3 之后，理由是「CP3/CP4 改的就是 claim 契约本身」。复核后：CP3 **对外签名不变**、只改内部事务形态，且实测收益（14.7x，§9.5）与正确性证据（重复认领恒为 0）都已到位；真正有契约形态问题的是 CP4 的钩子形状，而 CP4 最终以「时序收口 + 词汇留在本地」落地，没有新增跨模块契约。因此 P3 冻结不再是 CP3 的前置条件。仍受 P3 约束的是**认领语义**（例如是否需要 claim-one 之外的批量协议），那属于 P3 的议题而不是本原语的议题。

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

1. ~~**PG 侧 claim 竞争基线未采集**~~——**已在 §9.4 采集**（真实 PG 16、合成同构表、limit=1/4 × 1/4/8/16 worker，含复测）。仍未采集的是**真实业务谓词**下的基线：合成表不带 JOIN、绝对期限与写围栏。
   > **JOIN 业务谓词已补用例**（§9.6）：`test_pg_claim_contention.test_join_candidate_query_claims_without_locking_parent_rows` 覆盖「JOIN 过滤 + `FOR UPDATE OF` 不锁父表」。绝对期限（构建租约裁剪）与写围栏仍不在 PG 基准内；混合负载 D2 写路径基线见现行评估，不因本文关闭。
2. **Backend × N 从未联调**：现行评估 §5 列明的多实例共享对象存储、密钥一致、跨实例迁移与租约，全部未验收。CP5 的 profile 校验只保证「非法组合启动失败」，不证明「合法组合可横向扩展」。§9.4 的 8/16 worker 是**同进程多协程**并发，不等于多副本进程并发（后者另有连接池与 CPU 竞争），不得据此宣称多副本已验收。
3. **故障注入缺失**：`busy_timeout` 耗尽、PG 序列化失败风暴、Worker 掉线下的 claim 行为均无端到端验收；CP1 统一重试后尤其需要一次 SQLite BUSY 与 PG `40001` 的对拍演练。
   > **单元级对拍已补**（§9.6）：`tests/unit/test_db_write_retry_drill.py` 覆盖 SQLite BUSY、PG `40001`、PG `40P01` 走同一 `run_with_write_retry` 路径、尝试/rollback 次数一致、非冲突不重试、用尽后仍 rollback。**仍未覆盖**：真实 `busy_timeout` 耗尽风暴、Worker 掉线下的 claim 端到端——需联调/故障注入环境。
4. **`AgentWriteGuardedAsyncSession`（`db/session.py:29-42`）会在每次 `commit()` 前执行写围栏校验**——这一点已由 §9.2-3 实测确认（正是它使 `page_screenshot_job_service.py:110` 的 `rollback()` 不能替换为 `commit()`）。**仍未量化**的是：PG 单事务 claim 会把围栏校验挪到 claim 提交点，是否与 `SKIP LOCKED` 的持锁窗口互相放大等待。CP3 已落地但**基准用的是普通 `AsyncSession`**，写围栏侧未被覆盖。
   > 缩小后的风险面：认领调用点（5 个队列 Worker + 构建）都在队列循环里用 `session_factory()` 新建的普通会话，不是 Run 续跑期的受围栏会话；`claim_rows_by_cas` 的 `claim_cas` 为同步回调也不允许在持锁窗口内触发围栏查询。剩余可疑点是「受围栏会话是否可能进入 claim 路径」，需要一次调用点核对而非推测。
   >
   > **调用点核对已完成（2026-09-28 后补，§9.6）：结论是「不会」。** `agent_run_write_fence_scope` 只在 `pydantic_tools.py` 的工具包装器内生效；全部 `claim_pending_jobs` / `claim_rows_by_cas` / `claim_job` / `_claim_ready_batch` 调用点均在 lifespan 启动的队列 Worker（`page_mutation_queue` / `component_mutation_queue` / `image_generation_queue` / `page_screenshot_queue_worker` / `asset_render_hint_backfill`）或 `internal_runtime` 的 Build Worker HTTP 入口，这些上下文没有进入围栏 scope，`current_agent_run_write_fence()` 恒为 `None`，`AgentWriteGuardedAsyncSession.commit()` 不会触发围栏查询。工具层的 `claims` 是 JWT claims，与任务 claim 无关。**写围栏 × PG claim 放大的风险面可以关闭**；若未来在工具内直接认领，必须重新打开本条。
5. ~~**CP4 的租约裁剪钩子形状未定**~~——已解决，但答案与本文预期相反：不做 per-candidate 钩子参数，而是把**逐候选取值**留给调用方（`claim_cas` 回调自带 `_cap_lease_expiry`），共享层只保证时序。见 §4 CP4 实施结果。
6. ~~**`idempotency_service` 的读重试路径零测试覆盖**~~——**已补覆盖**（§9.6）：冲突退避、不可重试立即上抛、`for-else` 兜底再读、查无此行退避均有用例。顺带修掉「查无此行不 sleep 空转重查」的缺陷。仍**未**并入 `db/retry.py`（读重试语义不同，门禁 allow-list 保留）。
7. ~~**`rollback()` 会 expire ORM 实体**（§9.3）已在 SQLite 侧踩到一次；PG 侧单事务 claim 的 expire 时机尚未验证。CP3 的 `claim_rows_by_cas` 只返回**行的标量副本**（`row[0]`）不回读实体，构建侧的 `session.get` + `refresh` 发生在提交之后，因此设计上避开了该窗口——但没有测试固化这一不变量。~~——**不变量已固化**（§9.6）：`tests/integration/test_claim_scalar_and_expire.py` 断言 claim 返回标量 ID、rollback expire 后标量仍可用、重试钩子只用预先取出的标量。PG 侧单事务 claim 的 expire 时机仍依赖设计（不回读实体），无独立 PG 用例。
8. ~~**仓库没有 PG 侧认领用例**~~——**已有用例且已进 CI**（§9.6）：`tests/integration/test_pg_claim_contention.py` + `pnpm run test:backend:pg-claim`；CI job `pg-claim-contention` 起 PostgreSQL 16 服务并以 `P4_POSTGRES_REQUIRED=1` 强制执行（缺配置失败而非 skip）。基准脚本已入库（`app.scripts.measure_claim_contention`），§9.4 数字可用同口径复测，但历史绝对值仍以采集机记录为准。

---

## 8. 与既有文档的关系

| 文档 | 关系 |
| :--- | :--- |
| [`../architecture-assessment-2026-09-25.md`](./architecture-assessment-2026-09-25.md) | 现行评估。本文细化其 **P2-Dialect / P2-Locks / P1-TaskModel**；其 §7.3 优先序中 **P3 契约冻结对 CP3 的约束已在 §5 复核后解除**（对外签名不变），对 CP4 的语义议题仍然有效。**本文只关闭自己新立的「claim 竞争基线」门（§9.4、§9.5），不关闭现行评估的 D2 写路径基线门**，后者在评估文档中仍应保持「待实测」 |
| [`./architecture-assessment-sqlite-2026-09.md`](./architecture-assessment-sqlite-2026-09.md) | S1–S8 与 2a–2f 原始定义。**2a/2c/2e/2f 已实施**（证据见 §0-4）；本文承接其 **2b/2d**，并修正 2d 的调用点清单（`code_check_service.py` 已无该技巧） |
| [`./architecture-assessment-2026-09-24.md`](./architecture-assessment-2026-09-24.md) | D1=A 定案与 2b 重立约束（`:175` 禁止旧签名）来源 |
| [`./runtime-multi-deployment-scaling-plan-2026-09.md`](./runtime-multi-deployment-scaling-plan-2026-09.md) | T2-2 构建持久领取（`e156630`）是 CP4 的对象；其阶段 0 门禁与多副本 E2E 缺口仍然有效 |
| [`./lite-memory-adapter-2026-09.md`](./lite-memory-adapter-2026-09.md) | 运行态（`memory://`）与本文的持久化并发原语是**两条独立边界**；其核心不变量「DB 任务领取/租约/终态不得放运行态」约束 CP5 的 profile 派生不得读取运行态 |

---

## 9. 实施记录（2026-09-28）

基线 `4becd41`。第一批：CP1a / CP1b / CP2 / CP5 / CP6（§9.1–§9.3）。第二批：CP4 → claim 竞争基线 → CP3（§9.4–§9.5），第二批内部顺序与本文原排序不同，理由见 §5 修正 1、2。代码提交 `ccc8a18..4e42795`（`dev`），本文与 AGENTS.md 的边界规则收口在 `0376a63`。

### 9.1 已落地

| 项 | 落地内容 |
| :--- | :--- |
| **CP1a** | 改名 `SQLITE_BACKOFF_DELAYS`→`WRITE_CONFLICT_BACKOFF_DELAYS`、`SQLITE_LOCK_RETRY_ATTEMPTS`→`WRITE_CONFLICT_RETRY_ATTEMPTS`、`_SQLITE_EVENT_WRITE_*`→`_EVENT_WRITE_*`；日志事件 `page.screenshot.job.sqlite_lock_retry`→`.write_conflict_retry`；4 处「SQLite 锁/SQLite 重试」措辞改为写冲突口径。`db/errors.py:73-75` 的 SQLite 专属常量按计划**保留原名**。 |
| **CP1b** | 新建 `backend/app/db/retry.py`：`run_with_write_retry`（session 工厂签名）、`exponential_backoff_delays`、`WriteConflictContext`。收编 3 个写重试点：`ai/page_mutation_executor._run_final_write`、`ai/platform_runtime._append_event_with_retry`、`services/page_screenshot_job_service._finalize_captured_job`。各处次数与退避数值**原样保留**为参数。 |
| **CP2** | `db/tx.py` 扩展 `acquire_admission_lock`；4 个调用点改用命名原语：`durable_job_lease_service`（claim 候选读、recovery 空队列）、`rendering/repository.lock_scheduler_state_for_queue_admission`、`project_build_service.claim_job`。SQLite 事务机理移入 helper docstring。 |
| **CP3** | `claim_rows_by_cas` 内按方言选择**事务形态**：PostgreSQL 在同一事务里 `SELECT ... FOR UPDATE OF <队列表> SKIP LOCKED` + 逐条 CAS 后一次性提交；SQLite 仍走「候选读 → `commit_end_read` → 逐条 CAS → 提交」。分支只经由 `db/tx.row_locks_hold_until_commit()` 这一个出口，业务层不再比较 `dialect.name`。对外签名与 `claim_pending_jobs` 返回语义不变；`of=model` 是必需的，否则 JOIN 候选查询会把 `ai_agent_runs` 一并锁住。收益与实测见 §9.4、§9.5。 |
| **CP4** | 交付形态与本文不同：折叠的是**认领时序**不是词汇表。新增 `durable_job_lease_service.claim_rows_by_cas(session, model, candidate_query=…, claim_cas=…, max_claims=…)`，`ProjectBuildJob` 的列名、绝对期限谓词、`_cap_lease_expiry` 与 `attempt_id` 生成留在调用方本地（本文原设想复用 `claim_pending_jobs` 需要 8 个参数，见 §4 CP4 实施结果）。顺带修掉构建 claim 的两个既有缺陷：零候选时提前 `return` 留下未提交的写事务；复用批量循环后会多领任务却只执行 1 个（以 `max_claims=1` 固定）。 |
| **CP5** | 新建 `backend/app/db/profile.py`：`DeploymentProfile` + `resolve_deployment_profile`；`read_explicit_worker_count` 由 `db/sqlite_single_process.py` 迁入，`is_postgresql_database_url` 由 `services/redis_runtime_client.py` 迁入（无外部消费者，已从其 `__all__` 移除）。`sqlite_single_process`、`redis_runtime_client`、`signing_identity` 三处校验改为消费 profile，**错误消息逐字不变**。新增拒绝：SQLite 文件库 + `BACKEND_MULTI_INSTANCE=true` 启动失败。`/readyz` 与启动日志暴露 `deployment_profile` / `backend_multi_process_allowed`。 |
| **CP6** | 未删锁。定位写进 `_get_run_event_lock` docstring 与 `docs/developer/backend/ai-agent.md` 新增小节「事件追加的并发边界」。 |
| 门禁 | `tests/unit/test_db_adapter_layer.py` 第一批新增 2 条防漂移断言；第二批新增 5 条：认领函数不得自行 execute CAS（AST 检查，附带**正控用例**防门禁静默失效）、`skip_locked` 只允许出现在租约服务、`dialect.name` 分支只允许出现在 `app/db/` 与 `app/scripts/test_data.py`、`row_locks_hold_until_commit` 在 SQLite 上必须为假。新增 `tests/unit/test_deployment_profile.py`（9 例）；`AGENTS.md` backend 开发约束新增 `app/db/` 边界条目与认领时序条目。 |

**实测**：`pnpm run test:backend` 第一批后 **1069 passed / 9 skipped**，第二批后 **1074 passed / 9 skipped**（§9.5）；`pnpm run test:contracts` 10 files / 33 tests 全绿（含 `test:repository`）。认领相关 96 例、构建与多副本 48 例全绿，SQLite 侧既有断言未改。

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

### 9.4 PostgreSQL claim 竞争基线（施工前实测）

本文 §4 CP3 原把这一门写作「D2」，与现行评估的 **D2 写路径基线门**（Lite 2C4G + `/metrics/db-write`）重名但不是同一件事；后者仍未采集。本节只关闭 claim 竞争这一门。

**环境**：本地 Docker PostgreSQL 16.14（`localhost:5432`），一次性测量库，`asyncpg`，同进程多协程并发。测量表是与标准队列模型同构的合成表（`id/status/worker_id/lease_expires_at/heartbeat_at/attempt_count/error_code/error_message/cancel_requested_at/started_at/finished_at/created_at`），刻意避开外键播种噪声。脚本 `.tmp/d2/measure_claim_baseline.py`，`created_at` 单调递增以使全部 worker 竞争同一批头部候选。认领后模拟 10 ms 执行以近似真实队列节奏。

**判据**：吞吐（jobs/s）、无效 CAS 占比（发出的 UPDATE 数 − 实际认领数）、每认领一次的任务数据库往返数、tick 延迟 P50/P95、重复认领数（正确性）。

**三种形态的口径**（§9.5 的对比依赖这段，勿混用）：「收口前」= 当时生产代码 `claim_pending_jobs`（跨事务 + 逐条 CAS）；「同事务 SKIP LOCKED」= 单事务内加锁读 + **一条 `WHERE id IN (锁定集)` 批量 UPDATE**（CP3 设想形态之一，实际未采用）；「跨事务 SKIP LOCKED」= 外部评审的字面处方（保留 commit，只加关键字）。

3000 条 pending、10 s 窗口，`limit=1`（对应 `page_mutation_queue`、`image_generation_queue`、`component_mutation_queue` 的真实形态）：

| worker 数 | 收口前（跨事务 CAS） | 同事务 SKIP LOCKED | 跨事务 SKIP LOCKED（字面处方） |
| :--- | :--- | :--- | :--- |
| 1 | 9.5 /s，无效 0% | 15.0 /s | 9.0 /s |
| 4 | 4.3 /s，无效 **74.9%** | 30.8 /s | 16.4 /s |
| 8 | 2.4 /s，无效 **87.4%** | 33.6 /s | 18.4 /s |
| 16 | 2.0 /s，无效 **89.7%** | 35.2 /s | 19.2 /s |

`limit=4`（对应截图/资源回填队列的 `limit=concurrency` 形态）：

| worker 数 | 收口前 | 同事务 SKIP LOCKED | 跨事务 SKIP LOCKED |
| :--- | :--- | :--- | :--- |
| 4 | 16.4 /s，无效 75.0% | 122.0 /s | 62.4 /s |
| 8 | 12.8 /s，无效 82.0% | 140.8 /s | 70.4 /s |
| 16 | 8.8 /s，无效 88.9% | 153.6 /s | 76.8 /s |

**四条结论**：

1. **收口前是负缩放，不是「吞吐下降」。** 8 worker 相对 1 worker 反而慢 4 倍，16 worker 再降到 2.0 /s；每认领一个任务要付出 15.9 次数据库往返（limit=1、8 worker）。原因：候选按 `created_at` 排序且不加锁，所有 worker 拿到**同一批头部候选**，CAS 只能排队等锁后失败重试。外部评审第 8 条的方向由此从推测变为实测，且严重程度高于其描述。
2. **收益几乎全部来自事务边界，不来自 `SKIP LOCKED` 关键字。** 同事务形态在 1 worker 时就比收口前快 1.58 倍（9.5 → 15.0），此时**完全没有竞争**——差异纯粹是少一次 COMMIT 往返。这支持本文 §0-1「不要建能力布尔层，要改事务形态」。
3. **本文 §0-3 的「直接加 `skip_locked` 收益为零」措辞过强，已修正。** 跨事务形态确实把无效 CAS 从 75–90% 打到 0%，吞吐约为收口前的 7.7 倍（8 worker，18.4 vs 2.4）。但它的天花板只有同事务形态的一半，且 tick P50 随 worker 线性增长（222 → 425 → 828 ms）——它把「空转 CAS」换成了「等锁阻塞」，串行点没有消失。**准确结论：跨事务 `SKIP LOCKED` 治症状，同事务才治成因。**
4. **正确性始终未被削弱。** 全部 24 组运行（3 形态 × 7 并发档 × 2 limit）重复认领数恒为 0，包括收口前的 CAS 形态。这与 §4 CP3 硬约束 2 一致：`SKIP LOCKED` 改变候选集选取，围栏仍由 CAS 谓词保证。

**测量边界（不得超出解读）**：合成表不含业务谓词（绝对期限、JOIN、`AgentWriteGuardedAsyncSession` 写围栏）；同进程多协程 ≠ 多副本进程；单轮采样（8 worker 复测两次为 2.4 与 2.8 /s，同事务 33.6 与 34.1，偏差约 ±15% 内）；模拟执行时长 10 ms 是人为设定，只影响绝对吞吐不影响形态间相对关系。**基准脚本未入库**：`.tmp/` 被根 `.gitignore` 忽略，`measure_claim_baseline.py` 只存在于采集机。因此本文数字**不能从仓库复现**，也不进 CI；需要复测时必须重写脚本，或先把脚本正式纳入版本控制（建议 `backend/scripts/` 下的只读基准入口）。

### 9.5 CP4 / CP3 落地后的同口径复测

CP3 落地后以**同一脚本、同一表、同一参数**复跑，此时基准脚本里的 `current` 变体即生产代码 `claim_pending_jobs` 本身（脚本直接导入它），因此对比是同口径的：

| 形态 | limit=1，1 / 4 / 8 / 16 worker | limit=4，4 / 8 / 16 worker |
| :--- | :--- | :--- |
| 收口前 | 9.5 / 4.3 / 2.4 / 2.0 | 16.4 / 12.8 / 8.8 |
| CP3 后 | 14.5 / 29.2 / 35.2 / 36.8 | 110.4 / 131.2 / 147.2 |
| 倍率 | 1.5x / 6.8x / **14.7x** / **18.4x** | 6.7x / **10.3x** / **16.7x** |
| 无效 CAS | 0% / 0% / 0% / 0%（原 0 / 74.9 / 87.4 / 89.7%） | 0%（原 75.0 / 82.0 / 88.9%） |
| 每任务往返 | 2.0（原 2.0 / 7.95 / 15.92 / 19.4） | 1.25（原 5.0 / 6.95 / 11.25） |
| tick P50（8 worker） | 211.75 ms（原 390.76 ms） | 225.53 ms（原 417.06 ms） |
| 重复认领 | 恒为 0 | 恒为 0 |

缩放曲线由负转正（limit=1：14.5 → 29.2 → 35.2 → 36.8）。CP3 后实测值与 §9.4 中「同事务 SKIP LOCKED」预测值一致（35.2 vs 33.6、36.8 vs 35.2，在复测偏差内），说明 §4 CP3 记录的「逐条 CAS 而非批量 UPDATE」没有损失收益。

**回归**：`pnpm run test:backend` **1074 passed / 9 skipped**（CP4 后 1071，CP3 新增 3 条门禁），SQLite 侧认领用例断言未改。

### 9.6 验证面补强（2026-09-28 之后）

针对 §7 尚未验证项中「可仓库内闭合」的三块补齐：

| 项 | 落地 |
| :--- | :--- |
| claim 基准可复现 | 新增 `app.scripts.measure_claim_contention`：只读测量 CLI，在可丢弃库上自建合成队列表，对比 `current`（生产 `claim_rows_by_cas`）与 `cross_commit_cas`（收口前跨 commit 逐条 CAS）。刻意不复现「跨事务 + SKIP LOCKED」字面处方；对照形态也不写 `skip_locked`，以免绕过「`skip_locked` 只允许出现在租约服务」门禁。用法见脚本 docstring。 |
| PG 侧认领回归 | 新增 `tests/integration/test_pg_claim_contention.py`：配置 `P4_POSTGRES_DATABASE_URL` 时验证 `row_locks_hold_until_commit` 为真、并发 `claim_pending_jobs` 不重复认领、`claim_rows_by_cas` 候选集不相交、多轮并发吃完 pending；未配置则 skip。与迁移对拍共用同一环境变量。 |
| PG 认领进 CI | 根仓新增 `pnpm run test:backend:pg-claim`；`reusable-quality.yml` 新增 `pg-claim-contention` job（PostgreSQL 16 服务 + `P4_POSTGRES_REQUIRED=1`），并纳入 e2e 前置。缺连接串时显式失败，不以 skip 冒充通过。 |
| `idempotency` 读重试 | `tests/unit/test_idempotency_service.py` 新增 4 例：可重试冲突退避后命中、不可重试立即上抛、`for-else` 兜底再读次数、查无此行也退避。`_handle_existing_record` 在「重查为 `None`」时原先不 sleep 紧循环，已修为与冲突路径同一退避表。 |
| 围栏 × claim 调用点核对 | 见 §7-4 核对结论：claim 不在 `agent_run_write_fence_scope` 内，写围栏放大风险关闭。 |
| 写重试双库对拍 | `tests/unit/test_db_write_retry_drill.py`：SQLite BUSY / PG 40001 / PG 40P01 同路径、同尝试与 rollback 次数；非冲突不重试；用尽后仍 rollback。真实 `busy_timeout` 风暴仍待联调。 |
| claim 标量 / expire 不变量 | `tests/integration/test_claim_scalar_and_expire.py`：claim 返回标量 ID，rollback expire 后标量仍可用，重试钩子只用预先取出的标量。 |
| CP6 进程锁评估 | 结论写入 `docs/developer/backend/ai-agent.md` 与本文 CP6：**PostgreSQL 不可跳过**（锁保护同一 AsyncSession 上的并发追加/重试，与方言无关）。 |
| JOIN 业务谓词认领 | `test_pg_claim_contention` 新增 JOIN 候选用例：只认领 `waiting_external` 父行下任务，`FOR UPDATE OF` 不锁父表。 |
