# 已拆分：本篇内容迁出

> 2026-09-23：原「SQLite 兼容债与定时任务」合并评估已按主题拆成两份，**请直接阅读**：
>
> - [`architecture-assessment-sqlite-2026-09.md`](./architecture-assessment-sqlite-2026-09.md) — SQLite 兼容、迁移分支、写锁/重试、定时任务写路径  
> - [`architecture-assessment-memory-2026-09.md`](./architecture-assessment-memory-2026-09.md) — 内存状态、`memory://`、进程内锁/订阅、普通 Run 绑进程  
>
> 下文仅保留原合并稿，便于对照；**以两份新文档为准**。

---

# 架构评估：SQLite 兼容债与定时任务不规范（旧稿）

> 评估日期：2026-09-23。对象为当前工作区 Backend / 部署模板 / 持久化任务实现。  
> 重点：**SQLite 兼容导致的架构不规范**，以及 **各类定时/后台任务**如何放大这些问题。  
> 判断标准：代码可确认的问题与尚未验证的风险分开；单机 Lite 与 PostgreSQL 部署的行为差异单独标出。  
> 前序材料：`docs/temp/architecture_review_report.md`、`architecture-assessment-2026-09.md`、`docs-temp-issue-status-2026-09.md`。本文不重复浏览器外移等已解决问题。

---

## 1. 结论摘要

平台在「一套代码同时支撑 SQLite Lite 与 PostgreSQL」上做了大量正确工程（WAL、busy_timeout、条件 UPDATE 认领、租约、空闲免写），但代价是：

1. **数据库层语义被多处方言特判切开**：时区、部分索引、JSON 类型、锁错误识别、事务探测、迁移脚本都有 `sqlite` / `postgresql` 分支。业务正确性依赖这些分支是否被维护者记住。
2. **把 SQLite 单写入者约束上浮进了业务代码**：进程内事件写锁、锁序反转判断、候选读取后强制 `commit()`、空闲恢复先只读后写——这些是 SQLite 工作区补丁，却写在通用领域服务里。
3. **后台任务以「高频轮询 + 心跳写库 + 周期恢复扫描」为主**，而不是事件驱动。空闲时仍持续产生 SELECT/UPDATE，与 SQLite 写锁模型直接冲突；心跳/恢复循环数量多、生命周期全部绑在同一个 FastAPI `lifespan` 上。
4. **Lite 还叠了 `memory://` 假 Redis**：进程内 artifact 与锁，重启即失，且和 SQLite 文件库的持久化语义不一致。

**总体判断**：SQLite 兼容不是「配置开一下 WAL」这么简单，它已经渗透进锁协议、类型系统、调度器和迁移。若 Lite 是长期一等公民，应把上述不规范收成**明确的持久化适配层 + 统一任务运行时**；若 Lite 只是过渡，应限缩 SQLite 能力范围（单进程、单 Backend、有限并发），避免继续往通用路径堆补丁。

---

## 2. 架构快照（为后文铺垫）

```text
Editor ──HTTP──► Gateway ──► Backend(FastAPI)
                               │
               ┌───────────────┼───────────────────┐
               ▼               ▼                   ▼
          业务库(SQLite/PG)  运行态(Redis/memory://)  Runtime(Vite)
               │                                       │
               │  render_requests / 租约队列            │ 预览/编译/构建
               ▼                                       ▼
          各类后台 asyncio 任务 ──────────────────► Renderer(单槽 Chromium)
```

Backend 进程内常驻任务（`main.py` lifespan）至少包括：

| 任务 | 角色 |
| :--- | :--- |
| `render-coordinator` | 渲染调度 tick：过期、派发、心跳探测、回收 |
| `api-mutation-worker` / `api-mutation-sweeper` | External API 异步 Mutation Job |
| `ai-page-mutation-queue`（N worker） | AI 页面变更执行 |
| `ai-image-generation-queue` | AI 图片生成 |
| `ai-component-mutation-queue` | 组件变更 |
| `ai-external-task-coordinator` | 外部任务状态同步 + Batch 续跑 |
| `page-screenshot-queue` | 截图领域任务 |
| `asset-render-hint-backfill-queue` | 资源渲染提示回填 |
| `runtime-artifact-sweeper` | 运行态 artifact TTL |
| `ai-model-catalog-sync` | 模型目录同步 |
| `AgentBackgroundRunManager` | 普通 AI Run（进程内，非可恢复） |

**同一时刻至少 8–10 条循环**在空转或写库。这是 SQLite 兼容问题的主要放大器。

---

## 3. SQLite 兼容导致的不规范

### 3.1 连接与引擎层（合理，但边界未收口）

| 位置 | 行为 | 评价 |
| :--- | :--- | :--- |
| `db/session.py` `_configure_sqlite_engine` | 文件库启用 `foreign_keys=ON`、`busy_timeout`、`journal_mode=WAL` | **正确且必要**。内存库不启 WAL 也合理。 |
| `db/types.py` `UTCDateTime` | SQLite 存 naive UTC，读回补 `tzinfo`；PG 存 aware | **必要适配**，但把方言差异藏进 TypeDecorator，业务仍需用 `UTCDateTime`；绕过它就回归历史时区 bug。 |
| `AgentWriteGuardedAsyncSession.commit` | 提交前校验 Agent 写围栏 | 与 SQLite 无关，但是通用会话子类，职责混在同一文件。 |

**不规范点**：连接参数、PRAGMA、时区、围栏会话都堆在 `db/` 少数文件里，没有「方言能力矩阵」文档；新字段/新索引是否兼容 SQLite 靠测试（`test_sqlite_migration`）事后拦，而不是设计期约束。

### 3.2 类型与索引的双方言重复声明

**JSON**：`JSON().with_variant(JSONB(), "postgresql")` 出现在 `render_request`、`render_attempt`、`render_execution` 等。逻辑字段一份，物理类型两份。

**部分唯一/部分索引**必须同时写 `sqlite_where` 与 `postgresql_where`（内容相同）：

- `render_attempts`：`active_occupancy = 1` 槽位唯一
- `page_screenshot_jobs`：`status IN ('pending','running')`
- `ai_external_batches`：`resuming` / `collecting`
- `ai_agent_runs` / `ai_agent_requirements`：活跃状态子集
- `ai_llm` / `ai_image_model`：`scope = personal|global`

**不规范点**：

1. 同一谓词写两遍，漏改一处会导致某一库上的唯一性/查询计划静默失效。
2. `active_occupancy` 用 **Integer 0/1** 而不是 Boolean——SQLite 无原生布尔是常见约束，但模型层没有统一的「伪布尔」类型别名，靠约定。
3. 唯一约束本身在 SQLite 上依赖部分索引表达；若迁移里方言分支写错（见 3.3），唯一性保护会直接消失。

### 3.3 迁移脚本方言分支（高风险手工逻辑）

`backend/migrations/versions/` 中已出现：

- `20260818_0100_remove_self_delegation.py`：多处 `if op.get_bind().dialect.name == "sqlite":` 走不同 DDL/数据搬迁路径。
- `20260910_0100_remote_render_service.py`：`if bind.dialect.name in {"postgresql", "sqlite"}` 分支；含**离线转换**语义——清除无法证明新输入/profile 身份的当前有效截图指针。
- 集成测试 `test_sqlite_migration.py` 要求：「推理能力迁移不得用整数比较或写入布尔列」「文件源码必须出现方言分支」等——测试在**固化补丁形态**，而不是消灭补丁。

**不规范点**：迁移是跨方言数据转换的最后一道闸，却用字符串匹配方言、手写分支。双库测试存在，但**生产 Lite 只跑 SQLite、生产集群只跑 PostgreSQL**，实际是两套几乎不重叠的迁移验收面；「同一 migration 在两边语义等价」缺少机器证明。

### 3.4 错误识别与重试：两份几乎相同的 SQLite BUSY 探测

| 文件 | 内容 |
| :--- | :--- |
| `services/durable_job_lease_service.is_sqlite_lock_error` | 错误码 5/6 + 消息片段 |
| `ai/run_event_writer.is_sqlite_lock_error` | **同逻辑再抄一份** |

再叠加：

- `platform_runtime._append_event_with_retry`：纯追加路径 rollback + 指数退避（最多 4 次，base 25ms）。
- `idempotency_service.SQLITE_BUSY_RETRIES = 3`。
- 截图终写集成测试直接注入 `sqlite3.OperationalError("database is locked")` 验证重试。

**不规范点**：

1. **复制粘贴的方言错误分类**——判据（errorcode 掩码、消息子串）一旦要改（例如 SQLite 新错误码、驱动包装变化），两处必漏一处。
2. 重试策略散落：有的 4 次指数退避，有的 3 次，有的依赖 `busy_timeout=7s` 由驱动层扛。没有统一的「SQLite 写冲突执行器」。
3. 对 PostgreSQL 路径，这些补丁是死代码或 no-op，却增加了所有环境的控制流复杂度。

### 3.5 锁序反转防护（纯 SQLite 污染领域代码）

`platform_runtime.append_event`：

```text
if has_sqlite_write_transaction:
    直接 _append_event_once          # 已持 DB 写锁，不再进进程锁
else:
    async with _get_run_event_lock:  # 进程内 asyncio.Lock
        可选 rollback+retry
```

`_has_sqlite_write_transaction` 通过 **SQLAlchemy → sync_connection → driver_connection.in_transaction** 下钻 aiosqlite 驱动对象探测。

**不规范点**：

1. 为避免「先拿进程锁再抢 SQLite 写锁」与「已持写锁再等进程锁」死锁，把 **SQLite 驱动内部状态**暴露给 AI 运行时模块。换驱动（如 pysqlite 同步包装）即失效。
2. 进程内 `_RUN_EVENT_LOCKS` 本身就不能跨进程；在 PostgreSQL 多实例下这段锁序逻辑是**无效的复杂度**，在 SQLite 下又是**必须的补丁**。同一函数同时服务两种部署，却没有方言策略对象。
3. 测试 `test_ai_platform_runtime_concurrency.py` 专门测「持 SQLite 写锁后不得再申请进程锁」——再次把补丁测成了契约。

### 3.6 为 SQLite 写锁设计的「空闲免写 / 读写分离」补丁

| 补丁 | 位置 | 意图 |
| :--- | :--- | :--- |
| 候选 SELECT 后立即 `session.commit()` | `durable_job_lease_service.claim_pending_jobs` | 读事务不升级为写锁 |
| 空队列时先 SELECT 再决定是否 UPDATE | `recover_expired_running_jobs` | 空闲恢复不发起无命中 UPDATE |
| 诊断前 `_release_session_before_diagnostics` | `code_check_service` | 等 Runtime/Chromium 时不占 SQLite 锁 |
| 渲染调度「写锁状态行再 INSERT」 | `rendering/repository.lock_scheduler_state_for_queue_admission` | 在 SQLite 上用 UPDATE 提前拿写事务，串行化容量检查 |
| 各 partial index / claim 条件写 | 各 model | 减少全表锁与回表 |

**不规范点**：

- 这些是**正确的 SQLite 工程**，但全部内联在业务方法里，注释写「SQLite」原因。维护者在 PostgreSQL 上优化时容易「删掉多余 commit」而破坏 Lite。
- 没有统一的「短事务 / 只读探测 / 写优先」API；每个队列各写各的。
- `lock_scheduler_state_for_queue_admission` 用 `state.version += 1` 的假写来抢锁，在 PG 上是行锁 + 无意义版本递增，语义含混。

### 3.7 `memory://` Redis：Lite 的第二套不规范

`redis_runtime_client.InMemoryRedis` 是完整内存模拟（String/Hash/Stream/SCAN/expire/pipeline），Lite 用它承载：

- Runtime preview artifact（`RuntimeArtifactStore`）
- 部分任务锁（如 asset backfill `job_id` 锁）
- 可选唤醒通知（设计上）

**不规范点**：

1. **持久化分裂**：业务表在 SQLite 文件（重启保留），artifact/锁在进程内存（重启丢失）。`memory://lite` 文档已声明「不承诺跨重启」，但和「任务表恢复扫描」组合后，会出现「任务还在、artifact 已无」的复合失败，错误归因困难。
2. `sweep_expired` 依赖 `InMemoryRedis.purge_expired` 的 duck-typing（`getattr(..., "purge_expired")`）；真 Redis 返回 0。清理语义两套。
3. Stream 的 `xread`/`xadd` 自实现 ID 比较，仅够测试；若生产路径误用 Stream，Lite 与 Redis 行为不一致。

### 3.8 小结：不规范清单（去重）

| # | 不规范 | 根因 | 主要影响面 |
| :--- | :--- | :--- | :--- |
| S1 | 时区双写语义藏在 TypeDecorator | SQLite 无 timestamptz | 所有时间字段 |
| S2 | 部分索引谓词双写 | 两库 DDL 语法 | 唯一性与查询 |
| S3 | JSON/JSONB with_variant 散落 | 类型能力差异 | 渲染/AI 载荷 |
| S4 | 迁移方言手工分支 | DDL/数据搬迁差异 | 升级与数据正确性 |
| S5 | SQLite BUSY 识别两份拷贝 | 无统一 IO 重试层 | 任务终写、事件追加 |
| S6 | 驱动级 `in_transaction` 下钻 | 锁序反转 | AI 事件写入 |
| S7 | 业务方法内联 SQLite 事务技巧 | 无持久化适配层 | 认领/恢复/调度 |
| S8 | 伪布尔 / 错误码字符串约定 | 缺类型与错误模块 | 模型与契约 |
| S9 | `memory://` 与 SQLite 持久化语义分裂 | Lite 极简依赖 | artifact/锁生命周期 |
| S10 | 定时任务写放大（见 §4） | 轮询 + 心跳模型 | 全库锁竞争 |

---

## 4. 定时任务与后台循环

### 4.1 任务全景

| 任务 | 默认节奏 | 空闲是否写库 | 心跳/租约 | 恢复扫描 | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RenderCoordinator.run_forever** | `render_scheduler_poll_interval_seconds`（未在默认配置块读到时用 tick 内逻辑；`run_forever` 下限 50ms） | **是**：每 tick `expire_requests` + `release_expired_attempt_leases` + `_sync_workers`（含 Worker heartbeat upsert） | Worker `last_heartbeat_at` 每次能力探测 | 同 tick 内回收 | 最重的空闲写源之一 |
| **Render wait_for_terminal** | 100ms 轮询 DB | 等待时驱动 `ensure_progress` | — | — | 同步「提交并等待」路径 |
| **api-mutation-worker** | 空闲 sleep **1.0s**；异常 2.0s | 认领 SELECT + 条件 UPDATE | 执行中 **15s** 心跳 UPDATE | — | 每任务一个 heartbeat task |
| **api-mutation-sweeper** | `mutation_job_recovery_interval_seconds=30` | 是（有孤儿才写） | — | 孤儿 running | |
| **ai-page-mutation worker** | 唤醒或 **0.5s** 轮询 | 认领；空闲时 `GenerationWakeup.wait(0.5s)` 兜底 | **30s** job/batch 心跳 | 启动一次 + coordinator 内 recovery | lite `concurrency=1` |
| **ai-external-task-coordinator** | **0.5s** | **每轮** `synchronize_external_task_states` + `recover_external_continuations` + `audit_external_state_consistency`（全量扫非终态 Task） | Batch 继承领域任务心跳 | 每轮 + 60s 清理结果 | **空闲写放大最严重** |
| **ai-image-generation-queue** | 同类 0.5s 级 | 认领 + 心跳 | 是 | 启动恢复 | |
| **ai-component-mutation-queue** | 同类 | 认领 + 心跳 | 是 | 启动恢复 | |
| **page-screenshot-queue** | `poll_interval_seconds=1.0` | 认领 | job lease 180s | 启动恢复 | |
| **asset-render-hint-backfill-queue** | **1.0s** | 认领；另有 Redis 锁 | lease 180s | 启动恢复 | |
| **runtime-artifact-sweeper** | **30s** | memory/Redis 过期扫描 | — | — | Lite 上扫内存 |
| **ai-model-catalog-sync** | 周期同步 | 写目录表 | — | — | 可关 |
| **AgentBackgroundRunManager** | 事件驱动为主 | 模型执行中写事件 | 进程内 | 启动 `AI_RUN_PROCESS_STOPPED` | 非持久执行 |

配置集中见 `core/config.py`：`ai_page_mutation_poll_interval_seconds=0.5`、`durable_job_heartbeat_seconds=30`、`durable_job_lease_seconds=300`、`mutation_job_heartbeat_seconds=15`、`mutation_job_lease_seconds=45`、`mutation_job_recovery_interval_seconds=30`、`runtime_artifact_sweep_interval_seconds=30`、`page_screenshot_queue_poll_interval_seconds=1` 等。

### 4.2 共性设计模式（以及为何在 SQLite 上不规范）

**模式 A：0.5s 数据库轮询认领**

- 实现：`while True: claim → empty? sleep(poll)`。
- 页面队列额外有 `GenerationWakeup`（进程内 Condition + 代次），避免通知早于等待；**跨进程仍靠轮询**。
- 问题：Lite 单进程时唤醒有效；多实例或重启丢通知时，所有实例以 2Hz 打写库/读库。空闲 CPU 与 SQLite 锁探测被多个队列叠乘。

**模式 B：独立心跳协程定期 UPDATE**

- 实现：`_heartbeat_job_lease` / `_heartbeat_batch_lease` / `MutationJobService._heartbeat_loop` / external batch heartbeat。
- 间隔 15s 或 30s；**每个执行中任务一条**。
- 问题：纯续租写。空闲无任务时没有；有 N 个长诊断任务时，每 15–30s 产生 N 条 UPDATE，与事件追加、页面终写抢 SQLite 单写锁。首版评审「消灭高频心跳」的方向部分正确——但不能删租约，只能**合并心跳或改为租约惰性延长**。

**模式 C：周期恢复扫描（sweeper）**

- api-mutation-sweeper 30s；external coordinator 每 0.5s 就跑 recover；page/image/component 启动时 recover；render tick 每轮 release expired。
- 问题：
  1. **external coordinator 把 recover/audit 绑进 0.5s 主循环**，与「页面 Job 独立 worker」的分工不一致，空闲成本最高。
  2. 多个 recover 对同一张租约表语义重叠（`durable_job_lease_service` vs `mutation_job_service.recover_expired_running_jobs` vs render `release_expired_attempt_leases`），过期阈值与 max_attempts 各自为政。
  3. 首版「只在启动时恢复一次」不安全（多实例/长运行），但「每 0.5s 恢复」过度。缺少**基于租约到期时间的退避唤醒**。

**模式 D：全生命周期绑 lifespan，无独立部署单元**

- 任一 worker 崩溃：`except Exception → sleep → 继续`（多数循环有）；但 OOM/取消整个 loop task 依赖 lifespan shutdown。
- Lite `platform-lite`：Backend 多任务 + Runtime Vite + Nginx 同容器；**定时任务的内存与锁压力与预览请求同预算**。
- 没有「队列 Worker 可独立进程」的入口（Renderer 有，Backend 任务没有）。

**模式 E：等待型 API 自旋**

- `RenderCoordinator.wait_for_terminal` 100ms 查库直到终态。
- 长诊断时同步 HTTP 客户端占用连接 + 反复 SELECT，加重读负载；与 SSE 的 DB 回放轮询同类问题。

### 4.3 定时任务 × SQLite 的具体冲突场景

| 场景 | 冲突机制 | 后果 |
| :--- | :--- | :--- |
| 外部协调器 0.5s 全量 sync + 页面 worker 0.5s claim | 双写者频繁拿 `BEGIN IMMEDIATE`/UPDATE | `database is locked`、认领延迟抖动 |
| 长页面诊断期间 15–30s 心跳 × 多 job | 续租 UPDATE 插进事件追加事务 | 事件 append 触发 S5/S6 重试路径；偶发延迟尖峰 |
| Render tick 每轮 upsert Worker heartbeat + expire | 与截图终写、Mutation finalize 交错 | 空闲也写；Lite busy_timeout 7s 排队 |
| 启动时多个 recover_* 同时跑 | 并发 UPDATE 同租约表 | 启动风暴写锁；曾靠「先 SELECT 后写」缓解 |
| `wait_for_terminal` 自旋 + sweeper | 只读风暴仍占 WAL 读锁/页缓存 | 混合负载 P95 不稳定 |
| memory:// sweep 30s 与真实 Redis | 仅内存实现清理 | 两库两套空闲行为 |

**尚未量化的**：空闲态每秒 SQL 读写数、锁等待次数、`busy_timeout` 耗尽比例。评估材料多次要求基线，至今缺失；因此下文优先级按**结构风险**而非实测排名。

---

## 5. 风险分级（聚焦本主题）

### P0 — 正确性 / 锁协议

| ID | 问题 | 为何 P0 |
| :--- | :--- | :--- |
| P0-A | **页面校验跨阶段结果语义**（前序已述）仍可能把 Renderer 不可用报成通过 | 与定时任务无关，但是当前最高正确性缺陷；任务队列会在「错误通过」后继续写库。 |
| P0-B | **迁移方言分支无等价证明** | Lite 升级与 PG 升级数据语义可能分叉；远程渲染迁移还带截图指针清除，属数据不可逆操作。 |

### P1 — 可用性与可运维性

| ID | 问题 |
| :--- | :--- |
| P1-A | 多循环 × 0.5s 轮询 × 心跳写在 SQLite Lite 上叠加，空闲与混合负载缺少容量/锁等待基线 |
| P1-B | external coordinator 每轮全量 synchronize/recover/audit，与其它队列恢复职责重叠且过频 |
| P1-C | 锁序探测下钻 aiosqlite 驱动对象，驱动升级即脆弱 |
| P1-D | `memory://` artifact 与 SQLite 任务表生命周期分裂，失败模式复合 |
| P1-E | 全部后台任务与 HTTP 同进程同 lifespan；Lite 与 Backend CPU/内存预算耦合，无独立伸缩 |

### P2 — 维护成本与演进阻塞

| ID | 问题 |
| :--- | :--- |
| P2-A | BUSY 识别、重试次数、退避策略多处拷贝 |
| P2-B | 部分索引/JSON/伪布尔双方言约定分散 |
| P2-C | 业务方法内联 SQLite 事务技巧，缺少持久化适配层 |
| P2-D | sweeper/租约恢复三套实现语义不统一 |
| P2-E | 等待型 API 与 SSE 均用 DB 轮询，无完成通知通道（跨进程） |

---

## 6. 整改建议（按顺序，可验证）

### 6.1 先收正确性与可观测性（1–2 天量级可起步）

1. **修 P0-A**（页面 merge 语义）：`compile_status` / `render_status` 分离；unavailable 不得 `passed`。补 AI 写入 + External API 双路径契约测试。  
2. **采集 SQLite 运行基线**（Lite 目标机）：空闲 10 分钟与「5 页面变更 + 截图 + 预览」混合负载下记录：SQL/s、`database is locked` 次数、`busy_timeout` 命中、最长写等待、各循环 tick 耗时 P95。  
3. **打点心跳/恢复/认领**：每次 UPDATE 是否实际写（rowcount）、空轮询比例。用于决定 6.2 要不要砍频率。

### 6.2 统一「任务运行时」与「持久化适配」（结构债，按队列渐进）

**任务运行时（建议一个模块，例如 `app/jobs/`）：**

| 能力 | 现状 | 目标 |
| :--- | :--- | :--- |
| 认领 | 各队列复制 `claim_pending_jobs` 调用 | 单一 claim 策略（FIFO + 代次条件） |
| 心跳 | 多份 `_heartbeat_*` | 惰性续租：执行阶段边界 + 最小保活间隔；合并同类 job 心跳 |
| 恢复 | durable / mutation / render 三套 | 统一 `recover_expired(lease_table, policy)`；**按最近 lease_expires_at 定时**，而非固定 0.5s/30s |
| 唤醒 | `GenerationWakeup` 仅页面队列 | 统一进程内唤醒 + DB 轮询兜底；间隔指数退避到 2–5s |
| 生命周期 | 全绑 lifespan | 允许 `QUEUE_WORKERS_ENABLED` 拆到独立进程（后期） |

**持久化适配（`app/db/`）：**

| 能力 | 目标 |
| :--- | :--- |
| `is_transient_write_error(exc)` | 合并 S5 两份拷贝；PG 映射死锁/serialization failure |
| `run_with_write_retry(...)` | 统一退避与最大次数 |
| `session.read_probe()` / `commit_end_read()` | 表达「读事务尽早结束」而不是散落 `session.commit()` |
| `holds_write_lock(session)` | 收口 S6，禁止业务下钻 driver_connection |
| `PartialIndex` / `JSONPayload` / `BoolInt` | 收口 S2/S3/S8 |
| 迁移 | 方言差异收进显式 helper + 双库 contract test；禁止业务 migration 里裸 `dialect.name` |

### 6.3 定时任务具体调法（在有基线后）

| 优先级 | 动作 |
| :--- | :--- |
| 1 | **external coordinator**：synchronize/recover 从 0.5s 主循环拆出；改为「有非终态 external task 时短间隔，否则 2–5s 或按 lease 到期」；audit 降为 30–60s。 |
| 2 | **RenderCoordinator**：Worker heartbeat 与 expire 不必每 tick；按 `heartbeat_interval` / `lease_slack` 合并；tick 空闲时 sleep 自适应到 0.5–1s。 |
| 3 | **心跳合并**：同一 worker 的多个 job 一次 UPDATE `WHERE worker_id=?` 批量续租，或延长租约到「阶段超时 + 余量」，取消 15s 细粒度心跳。 |
| 4 | **认领轮询退避**：空队列连续 N 次后 sleep 从 0.5s 退避到 2s，有 `notify` 立即恢复。 |
| 5 | **恢复扫描**：sweeper 只处理「lease_expires_at 已过」集合，启动时一次全量 + 运行中按最近到期时间 sleep。 |
| 6 | **等待 API**：`wait_for_terminal` 改为条件唤醒（进程内）+ 200ms–1s 轮询，避免 100ms 自旋。 |

### 6.4 Lite 拓扑边界（明确承诺，减少补丁理由）

在文档与启动校验中固化：

- SQLite URL ⇒ **仅允许 1 个 Backend 进程 / 1 个 app 实例**（拒绝多 worker uvicorn 或多容器共享同一 db 文件）。
- `memory://lite` ⇒ 明确 artifact 丢失时的任务失败语义（已有文档，建议变成启动日志与健康状态）。
- 定时任务并发上限：Lite 默认全部 `*_CONCURRENCY=1`（compose 已部分如此），并**禁止**再增加新的 0.5s 级循环而不配退避。
- 若未来要 2C4G 长期支持：优先拆 **Runtime 与 Backend 容器**（P1-E），而不是先上 Browserless。

### 6.5 明确不做 / 误方向

| 不做 | 原因 |
| :--- | :--- |
| 删除持久化租约，改纯内存队列 | 丢重启/跨实例正确性 |
| 删掉 Runtime 编译阶段只留 Chromium | 失败集合不同（前序已论证） |
| 在 SQLite 上引入分布式锁中间件 | 过度；先减少写者数量 |
| 为每条 SELECT 加缓存掩盖轮询 | 问题在任务模型，不在缺缓存 |

---

## 7. 与前序文档的关系

| 前序判断 | 本文修正/加深 |
| :--- | :--- |
| 「SQL 租约队列 + 多轮询 Worker 导致 database is locked」 | **方向对，程度未证**。结构上多循环叠写属实；缺基线，不能断言已是主故障源。补丁（空闲免写、WAL、busy_timeout）说明团队已在止血，但补丁碎片化本身成为新债。 |
| 「应事件化调度、消灭心跳」 | **保留事件化 + 轮询兜底**；心跳应**合并/惰性化**而非简单删除。external coordinator 的 0.5s 全量扫描应优先开刀。 |
| 「内存全局锁阻断水平扩展」 | 在 SQLite 主题下另有一面：进程内锁是**锁序补丁**的一部分；多实例前必须先收口 S5/S6/S7。 |
| 容量验收 1.5GB / 降延迟 40% | 仍不成立；用 §6.1 基线替代拍脑袋阈值。 |

---

## 8. 一页结论

1. **SQLite 兼容债是真实的架构分叉**：时区、索引、JSON、迁移、错误重试、锁序、事务结束时机共 **10 类**不规范；其中 S5（BUSY 双份）、S6（驱动下钻）、S7（内联事务技巧）、S4（迁移分支）优先。  
2. **定时任务是放大器**：≥10 条后台循环，默认 0.5–1s 轮询 + 15–30s 心跳写 + 多套 sweeper；`ai-external-task-coordinator` 空闲成本最高。  
3. **P0 仍是页面校验语义**；P0-B 是迁移双方言数据语义。两者都要在「继续堆调度补丁」之前处理。  
4. **正确演进路径**：统一任务运行时与持久化适配层 → 按基线砍轮询/合并心跳 → 固化 Lite 单实例边界 → 再谈 Runtime 拆容与多实例。  
5. **不要**用纯内存队列删租约、用缓存藏轮询、或在无基线时用固定 GB/% 当验收。
