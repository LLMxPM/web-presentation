<!-- 文件功能：WS-A1 冻结的任务运行时契约；A2/A3 实现与迁移均以本文为单一事实源，禁止再发明字段/状态/错误码方言。 -->
# 统一任务运行时契约（WS-A1 冻结）

> **状态**：契约冻结（2026-09-29）。**本阶段只定契约，不写实现**。  
> **历史输入**：[09-28 计划（已归档）](../../temp/archive/remaining-work-2026-09-28.md) WS-A 及旧评估 P1-TaskModel / P1-Recovery / P2-VocabDrift；最新状态与后续验证见[现行评估与计划](../../temp/README.md)。
> **出口**：A2 统一执行器、A3 队列迁移、A4 跨表不变量，均不得偏离本文词汇；偏离须先改本文并登记理由。  
> **硬约束**（继承 CP 系列）：SQLite 分支语义字节级维持；PG 同事务 `SKIP LOCKED` 形态不得退回跨事务 CAS；`with_for_update(skip_locked=True)` 只允许出现在 `durable_job_lease_service`。

---

## 0. 一页契约

| 维度 | 冻结结论 |
| :--- | :--- |
| 角色 | **Worker / Lease / Attempt / Terminal** 四角色；Batch/Requirement 是业务聚合，不是任务角色 |
| 执行体 | **Job**（可领取可重试的持久化工作单元）与 **Attempt**（一次物理执行）分离 |
| 认领 | 统一委托 `claim_rows_by_cas`；方言只允许出现在「列名映射」与「领域取值」 |
| 租约 | `lease_expires_at` + `worker_id`（或 `lease_owner`）+ 可选 `lease_generation` 围栏 |
| 心跳 | `heartbeat_at`（或 `claimed_at` 别名）；**租约 ≥ 3× 心跳间隔** |
| 取消 | `cancel_requested_at` 协作取消；pending 直接终态，running 由执行者在安全边界确认 |
| 恢复 | 循环内过期恢复 + 启动恢复兜底；**禁止只在启动时恢复** |
| 终态 | 统一词汇 `succeeded / failed / cancelled`；迁移期允许别名，见 §3 |
| 错误码 | 四族前缀（§4）；基础设施错误可重试，内容/确定性错误直接终态 |
| Run | 普通 AI Run **不在**本契约内做可恢复语义；产品承诺「会丢」 |

---

## 1. 角色模型

```text
┌──────────┐  claim   ┌──────────┐  execute  ┌──────────┐
│  Queue   │────────►│  Worker  │─────────►│  Attempt │
│ (pending)│         │ (owner)  │          │ (物理执行)│
└──────────┘         └────┬─────┘          └────┬─────┘
                          │ heartbeat            │ complete
                          ▼                      ▼
                    ┌──────────┐          ┌──────────┐
                    │  Lease   │          │ Terminal │
                    │ (有效期)  │          │ (终态)   │
                    └──────────┘          └──────────┘
```

### 1.1 Worker（执行者）

- **定义**：持有租约、推进 Job 的进程内执行实体。
- **身份字段**：`worker_id`（推荐 `hostname:pid:uuid`，由 `build_durable_worker_id()` 生成）。
- **别名**：`lease_owner`（ProjectBuildJob 历史命名；语义等同 `worker_id`）。
- **职责**：认领、心跳续租、执行、写终态、响应取消。
- **禁止**：跨 Worker 移交执行体；旧 Worker 在租约过期后写回状态（必须被围栏拒绝）。

### 1.2 Lease（租约）

- **定义**：Worker 对 Job 的有限期独占权。
- **字段**：`lease_expires_at`（UTC）；认领时写入，续租时延长。
- **围栏代次**（可选）：`lease_generation`（int，认领/恢复时 +1）。用于「读到实体 → 按代次 CAS」的写围栏协议，阻断过期 Worker 把结果写回。
- **render 变体**：`claim_generation`（RenderRequest）与 `slot_generation` / `active_occupancy`（RenderAttempt 槽位）；语义映射见 §2。
- **比例硬约束**：`lease_seconds ≥ 3 × heartbeat_seconds`（配置校验已强制；新队列必须遵守）。
- **绝对期限**（可选）：`deadline_at`（ProjectBuildJob / RenderRequest）；续租与终态共用同一 wall-clock 上界，越过即拒绝续租。

### 1.3 Attempt（一次物理执行）

- **定义**：Job 在某一租约期内的具体执行尝试。Job 可有多次 Attempt；`attempt_count` 记录次数。
- **标识**：
  - 标准：`attempt_count`（int）+ `worker_id` + 本次 `lease_expires_at`。
  - 显式 Attempt 实体：`attempt_id` / `attempt_uid`（ProjectBuildJob / RenderAttempt）。
- **产物围栏**：产物对象键、限权令牌必须绑定当前 `attempt_id`（或等价代次）；迟到上传按围栏拒绝。
- **与 Job 的关系**：Job 状态机跨 Attempt；Attempt 状态机只覆盖单次物理执行（render 场景）。

### 1.4 Terminal（终态）

- **终态集合**：`succeeded` | `failed` | `cancelled`。
- **非执行失败的旁路终态**（Job 级可选）：`skipped`（内容陈旧等确定性跳过，如 `PAGE_SCREENSHOT_JOB_STALE`）。
- **终态写入条件**：拥有者匹配 + 租约未过期（或显式 attempt 围栏命中）+ 可选「未请求取消」。
- **终态幂等**：重复完成不得覆盖已有终态；以条件 UPDATE rowcount 判定。

---

## 2. 字段词汇（单一映射表）

下列是**契约标准名**。历史列名允许暂存，但新代码与迁移目标一律使用标准名；映射见 §5。

| 契约标准名 | 含义 | 类型 | 必填 | 历史别名 |
| :--- | :--- | :--- | :--- | :--- |
| `status` | 任务状态 | str | 是 | — |
| `worker_id` | 当前租约拥有者 | str? | 认领后 | `lease_owner` |
| `lease_expires_at` | 租约到期时刻 | UTC? | 认领后 | — |
| `lease_generation` | 租约/围栏代次 | int | 围栏协议必填 | `claim_generation`（RenderRequest） |
| `heartbeat_at` | 最近心跳 | UTC? | 认领后 | `claimed_at`（Build） |
| `attempt_count` | 已尝试次数 | int | 是 | — |
| `max_attempts` | 重试上限 | int | 可重试队列必填 | — |
| `attempt_id` | 本次物理执行标识 | str? | 显式 Attempt 场景 | `attempt_uid` |
| `cancel_requested_at` | 协作取消请求时刻 | UTC? | 支持取消时 | `cancel_requested` + `cancel_version`（Render） |
| `error_code` | 错误码 | str? | 失败时 | `last_error_code`（MutationJob） |
| `error_message` | 人类可读错误 | str? | 失败时 | — |
| `started_at` | 本次/最近执行开始 | UTC? | — | `claimed_at`（兼） |
| `finished_at` | 终态时刻 | UTC? | 终态时 | — |
| `next_attempt_at` | 下次可领取时刻（退避） | UTC? | 支持退避时 | `retry_after`（RenderRequest） |
| `deadline_at` | 绝对期限 | UTC? | 长任务 | — |

### 2.1 状态机（Job 级）

```text
                    ┌──────────── cancel_requested ────────────┐
                    ▼                                          │
┌─────────┐  claim  ┌─────────┐  complete  ┌───────────┐  ◄────┤
│ pending │────────►│ running │───────────►│ succeeded │       │
└────┬────┘         └────┬────┘            └───────────┘       │
     │                   │ fail / attempt 用尽                   │
     │ cancel            ▼                                      │
     │             ┌─────────┐            ┌───────────┐         │
     └────────────►│ failed  │            │ cancelled │◄────────┘
                   └─────────┘            └───────────┘
     （pending 被取消可直接 cancelled）
     （可选旁路）running → skipped（陈旧/条件不再满足）
```

**允许的旁路**（仅当业务需要，须在映射表登记）：

| 旁路 | 含义 | 现存使用者 |
| :--- | :--- | :--- |
| `waiting_provider` | 已提交外部供应商、轮询中；**不占用 Worker 租约** | AiImageGenerationJob |
| `collecting` / `waiting_tasks` / `ready` / `resuming` | Batch 聚合状态，不是 Job 状态 | AiAgentExternalBatch / AiPageMutationBatch |
| `queued` | 请求已入队、尚未被协调器派出 | RenderRequest（映射为 `pending`） |
| `executing` | 协调器已派出、Worker 执行中 | RenderRequest（映射为 `running`） |
| `expired` | 超过绝对期限/总预算 | RenderRequest / RenderAttempt |
| `unknown` | 执行状态不可知（Worker 失联） | RenderAttempt |
| `skipped` | 确定性跳过 | PageScreenshotJob |

> **A3 迁移规则**：队列迁入统一运行时后，Job 级状态必须落在标准三态 + 显式登记的旁路；不得新增第四套「完成/失败」词汇。

### 2.2 取消语义

1. `request_job_cancellation`：`pending` → 立即 `cancelled` 并清租约；`running` → 只写 `cancel_requested_at`，由执行者在安全边界确认。
2. 执行者安全边界：阶段提交前、外部 IO 前、循环体顶点检查 `cancel_requested_at`。
3. 过期恢复时若 `cancel_requested_at` 非空 → 收敛为 `cancelled`，不重试。
4. 业务强依赖「父级取消」（如 Run cancelled）时，领域服务应在同一事务写穿子任务取消，不依赖轮询。

`request_job_cancellation(..., commit=False)` 允许领域服务把父 Job 与子任务取消合并提交，默认调用仍独立提交。截图取消在同一事务按工作空间、页面、版本、配置与视口关联到未终态 RenderRequest；每个活动截图执行另有短会话取消观察者，补偿「取消已提交、渲染请求随后才入队」的竞争。观察者只有当前 Job 拥有者及有效租约才可继续传播，执行结束即退出。

### 2.3 心跳与续租

| 队列 | lease 默认 | heartbeat 默认 | 比例 | 备注 |
| :--- | ---: | ---: | ---: | :--- |
| durable 标准队列 | 300s | 30s | 10× | 截图/回填/页面/组件 |
| MutationJob（External API） | 45s | 15s | 3× | 下限 |
| Image Generation | 300s | 30s | 10× | waiting_provider 不续租 |
| Project Build | 960s | （随进度） | — | `claimed_at` 别名 |
| Render Attempt | 180s | （Worker 心跳 5s 节流） | — | 槽位占用租约 |

**契约要求**：

- 心跳必须是**拥有者 + 未过期租约 + running** 的条件更新。
- 空闲期心跳不得变成写放大源（render worker 心跳 5s 节流是可接受实现）。
- `waiting_provider` 状态**不占用** Worker 租约；存活依据是 `next_poll_at`，不是 `lease_expires_at`。
- RenderAttempt 只有真实 `accepted/running/cleaning` 回执才续租；网络不可达保留原租约，由后续独立 tick 执行到期恢复。成功结果提交同时复核 attempt 占用、有效租约、请求取消标记与总期限；即使回收器尚未处理过期租约，也拒绝迟到结果。竞争失败整笔回滚，不留下孤立 RenderResult。
- Renderer 容器入口由 tini 承担 PID 1，转发信号并回收被接管的浏览器子进程；资源释放需同时检查槽位、临时文件和 `/proc`，僵尸残留不算完整回收。

---

## 3. 终态词汇对齐（P2-VocabDrift 出口）

| 契约标准 | 当前方言 | 所在 | A3 迁移动作 |
| :--- | :--- | :--- | :--- |
| `succeeded` | `succeeded` | MutationJob, ProjectBuild, Render | **保持** |
| `succeeded` | `completed` | ExternalTask, PageMutation, Image, ExternalBatch | 改名为 `succeeded`（或读侧归一 + 写侧改名，一次切换） |
| `failed` | `failed` | 多数队列 | **保持** |
| `failed` | `error` | AiImageGenerationJob | 改名为 `failed` |
| `cancelled` | `cancelled` | 多数队列 | **保持** |
| `cancelled` | `canceled` | ApiMutationJob | External API v1 兼容例外：共享恢复分类为 `cancelled`，领域持久化与响应继续使用 `canceled`；统一改名需另行迁移 API 契约与消费者 |
| `skipped` | `skipped` | PageScreenshotJob | **保持**（旁路终态） |

> 迁移期允许**读侧归一**（映射函数）作为过渡；**写侧**必须一次改到位，禁止长期双写两种拼写。

**兼容例外（2026-09-29 复核）**：ApiMutationJob 的取消拼写属于现有 External API v1 契约，本次租约修复不改客户端枚举。所有取消写路径继续只写 `canceled`；过期恢复优先处理取消，再判重试预算，同时撤销租约、递增围栏代次且不增加尝试次数。

---

## 4. 错误码族

错误码是机器可判定的稳定字符串；`error_message` 仅供人读，不参与逻辑分支。

| 族 | 前缀/模式 | 语义 | 可重试？ | 示例 |
| :--- | :--- | :--- | :--- | :--- |
| **LEASE** | `*_LEASE_*`, `LEASE_TIMEOUT_*`, `*_INTERRUPTED` | 租约丢失、进程中断、过期恢复 | **是**（退避后重新入队） | `LEASE_TIMEOUT_RECOVERED`, `AI_PAGE_MUTATION_INTERRUPTED`, `PAGE_SCREENSHOT_JOB_INTERRUPTED` |
| **INFRA** | `RENDER_*`, `RUNTIME_*`, `*_UNAVAILABLE`, `*_TIMEOUT` | 下游/基础设施不可用或超时 | **是**（须在 `RETRYABLE_ERROR_CODES`） | `RENDER_SERVICE_UNAVAILABLE`, `RENDER_DEADLINE_EXCEEDED`, `RUNTIME_VITE_QUEUE_FULL` |
| **CONTENT** | `*_VALIDATION_*`, `*_FAILED`（内容结果）, `*_STALE` | 源码/内容确定性失败或陈旧 | **否**（直接终态） | `PAGE_VALIDATION_FAILED`, `PAGE_SCREENSHOT_JOB_STALE` |
| **CANCEL** | `*_CANCELLED`, `*_RUN_CANCELLED`, `*_RUN_NOT_ACTIVE` | 请求取消或父级已终止 | **否**（收敛 `cancelled`） | `AI_RUN_CANCELLED`, `RENDER_CANCELLED`, `AI_RUN_NOT_ACTIVE` |
| **FENCE** | `*_LEASE_LOST`, `*_LEASE_OWNER_*`, `*_STATE_INCONSISTENT` | 围栏拒绝、状态机不一致 | **否**（对旧 Worker）；系统侧可重入 | `AI_PAGE_MUTATION_LEASE_LOST`, `BUILD_LEASE_OWNER_MISMATCH`, `AI_EXTERNAL_STATE_INCONSISTENT` |
| **LIMIT** | `*_QUEUE_FULL`, `*_MAX_ATTEMPTS`, `*_ADMISSION_*` | 容量或重试预算耗尽 | 视配置；默认否 | `RENDER_QUEUE_FULL`, `LEASE_TIMEOUT_MAX_ATTEMPTS` |

**硬规则**：

1. 基础设施错误**不得**伪装为内容错误（否则短暂离线会把可恢复故障固化为「源码有错」）。
2. 新增错误码必须归入上表之一，并更新本表；禁止无前缀自由发挥。
3. 重试判定以错误码族为准，不以 `error_message` 文本为准。

---

## 5. 现有任务模型映射表（10 套 → 契约）

> **历史迁移基线（W08 已对齐当前实现）**：下表保留 A1 冻结时的 10 套任务模型、3 套认领方言映射框架。**恢复列已按当前实现更新为「循环内过期恢复 + 启动兜底」**；普通 AI Run 启动恢复为 hostname/pid 过滤，不再描述为全局扫杀。剩余差距以[现行评估](../../temp/architecture-assessment-2026-09-30.md)与[计划](../../temp/plans/architecture-improvement-plan-2026-09-29.md)为准。

### 5.1 总表

| # | 队列 / 模型 | 表 | 认领方言 | 心跳/恢复 | 终态词汇现状 | 契约差距（A3 要做的） |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **构建 ProjectBuildJob** | `project_build_jobs` | **A** 共享 CAS（`claim_rows_by_cas`）自定义列名 | `claimed_at` / 启动+循环恢复 | `succeeded`/`failed` | 列名别名归一（`lease_owner`→`worker_id`）；补 `error_code` 族 |
| 2 | **截图 PageScreenshotJob** | `page_screenshot_jobs` | **A** `claim_pending_jobs` | 标准 / 循环+启动 | `pending/running/succeeded/failed/cancelled/skipped` | 已接近契约；`skipped` 保持旁路 |
| 3 | **回填 AssetRenderHintBackfillJob** | `asset_render_hint_backfill_jobs` | **A** `claim_pending_jobs` | 标准 / 循环+启动 | 同上（无 skipped） | 已接近契约 |
| 4 | **图片 AiImageGenerationJob** | `ai_image_generation_jobs` | **A** 标准列 + `waiting_provider` | 标准 / 启动恢复 | `error`≠`failed`；`completed` | `error`→`failed`，`completed`→`succeeded`；`waiting_provider` 登记旁路 |
| 5 | **页面变更 AiPageMutationJob** | `ai_page_mutation_jobs` | **A** 标准列（Batch 用 generation 围栏） | 标准 / 循环+启动 | `completed`/`cancelled` | `completed`→`succeeded`（若尚未统一） |
| 6 | **组件变更 AiComponentMutationTask** | `ai_component_mutation_tasks` + `ai_agent_external_tasks` | **A**（挂在 ExternalTask） | 标准 / 循环+启动 | 经 ExternalTask 穿透 | 同上；领域详情表保持 |
| 7 | **ExternalTask 统一控制面** | `ai_agent_external_tasks` | **A** 标准列 | 标准 / 对账兜底 | `succeeded`（已是） | 统一为契约 Job；Batch 聚合不进 Job 状态机 |
| 8 | **ExternalBatch 续跑聚合** | `ai_agent_external_batches` | **B** `lease_generation` CAS | generation 围栏 / coordinator 轮询 | `collecting/waiting_tasks/ready/resuming/completed/failed/cancelled` | **不是 Job**；保留为聚合/续跑角色，字段映射 §5.3 |
| 9 | **MutationJob（External API）** | `api_mutation_jobs` | **B** `lease_generation` CAS（经 `claim_rows_by_cas`） | 15s 心跳 / 循环恢复 | `canceled`/`succeeded`/`failed` | `canceled` 是 §3 的 v1 兼容别名；`last_error_code` 通过列词汇映射 |
| 10 | **渲染 RenderRequest + RenderAttempt** | `render_requests` / `render_attempts` | **C** `claim_generation` + `reserve_attempt` | Attempt 租约 / 协调器收敛 | `queued/executing/succeeded/failed/cancelled/expired` | `queued`→`pending`，`executing`→`running`；Attempt 状态机保留 |
| — | **进程内 AI Run** | `ai_agent_runs` | **无**（非租约队列） | 进程内；启动按 hostname/pid 收敛本机死进程 | `running/waiting_external/paused/cancelling/completed/cancelled/failed` | **契约外**：产品承诺「会丢」；见 §6 与[兼容矩阵 §5](../deployment/compatibility-matrix.md#5-run-收敛边界hostname--pid) |

### 5.2 认领方言对照（3 套 → 1 套）

| 方言 | 代表实现 | 机制 | 契约归宿 |
| :--- | :--- | :--- | :--- |
| **A 共享 CAS** | `claim_rows_by_cas` + `claim_pending_jobs` | 加锁读候选（PG `SKIP LOCKED`）→ 逐条条件 UPDATE → 统一提交 | **唯一合法认领时序**；A2 扩展此入口 |
| **B lease_generation 围栏** | `mutation_job_service.claim_next_pending_job`、ExternalBatch 续跑 | 读实体记下 generation → 以该 generation 为 CAS 条件 UPDATE | **保留围栏语义**，但认领时序仍走 A；generation 作为 `claim_cas` 的谓词 |
| **C render claim_generation** | `rendering/repository.reserve_attempt` | 请求级 `claim_generation` + Attempt 创建同事务 | **保留**为渲染专用；`reserve_attempt` 为已登记例外，不得再出现第三份手写 claim |

> **门禁**（继承 CP4 / B-ClaimGate）：除 `durable_job_lease_service` 与已登记例外（`external_task_queue` 围栏协议、`reserve_attempt`）外，禁止手写 claim 时序。A2 完成后新增队列只注册**列词汇**与**领域取值**。

### 5.3 Batch / 聚合角色（非 Job）

| 角色 | 表 | 职责 | 与契约关系 |
| :--- | :--- | :--- | :--- |
| ExternalBatch | `ai_agent_external_batches` | 聚合同一 step 的外部任务；独占一次模型续跑；`lease_generation` 阻断过期协调器写回 | 用 Lease + generation 围栏；状态机独立（collecting→waiting_tasks→ready→resuming→completed/failed/cancelled） |
| PageMutationBatch | `ai_page_mutation_batches` | 页面写工具业务分组 + `run_step`；续跑已迁 ExternalBatch | 遗留 `resuming` 收敛为 `completed`；不再承载续跑 |
| ScreenshotJobGroup | `page_screenshot_job_groups` | 批次关联；成员表允许一任务属多批 | 纯关联，无租约 |
| Requirement | `ai_agent_requirements` | 模型 step 的 deferred 结果槽 | 与 Batch 绑定：`resolving` ⇔ 有效租约的 `resuming` Batch（A4 不变量） |

### 5.4 字段映射明细

| 契约标准名 | ProjectBuild | Screenshot/Backfill/Image/Page | ExternalTask | MutationJob | RenderRequest | RenderAttempt |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `worker_id` | `lease_owner` | `worker_id` | `worker_id` | `worker_id` | （协调器） | `worker_id` + `worker_epoch` |
| `heartbeat_at` | `claimed_at` | `heartbeat_at` | `heartbeat_at` | `heartbeat_at` | — | Worker `last_heartbeat_at` |
| `lease_expires_at` | 同名 | 同名 | 同名 | 同名 | — | 同名（槽位占用） |
| `lease_generation` | — | — | Batch 上有 | `lease_generation` | `claim_generation` | `slot_generation` |
| `attempt_count` | 同名 | 同名 | 同名 | 同名 | 同名 | `attempt_no` |
| `attempt_id` | `attempt_id` | — | — | — | — | `attempt_uid` |
| `cancel` | （deadline） | `cancel_requested_at` | `cancel_requested_at` | `cancel_requested_at` | `cancel_requested` + `cancel_version` | — |
| `error_code` | （仅 `error_message`） | 同名 | 同名 | `last_error_code` | 同名 | 同名 + `dispatch_error_code` |
| `next_attempt_at` | — | — | — | `next_attempt_at` | `retry_after` | — |
| `deadline_at` | 同名 | — | — | — | 同名 | — |

---

## 6. 恢复语义

### 6.1 分层恢复（契约要求）

| 层 | 触发 | 行为 | 谁必须实现 |
| :--- | :--- | :--- | :--- |
| **L1 循环内** | Worker 空闲/每次 tick 前 | `recover_expired_running_jobs`：过期 `running` → 未用尽重试回 `pending`，用尽→`failed`，有取消→`cancelled` | **所有**持久化 Job 队列（A3 迁移完成的判定条件之一） |
| **L2 启动** | 进程启动 | 同 L1，外加本进程 owner 前缀的遗留清理 | 所有队列 |
| **L3 对账兜底** | 定时/低频 | `synchronize_external_task_states` 等跨表对账 | 仅跨表控制面 |
| **L4 父级穿透** | Run/会话取消 | 同事务写穿子任务 `cancel_requested_at` 或直接终态 | 领域服务 |

### 6.2 现状缺口（P1-Recovery，A3 必须关闭）

| 队列 | L1 循环内 | L2 启动 | 缺口 |
| :--- | :---: | :---: | :--- |
| ProjectBuild | ✅ | ✅ | — |
| Screenshot | ✅ | ✅ | — |
| Backfill | ✅ | ✅ | — |
| Image | ✅（含 waiting_provider 对账） | ✅ | — |
| **PageMutation** | ❌ | ✅ | **运行中租约过期滞留到重启** |
| **ComponentMutation** | ❌ | ✅ | 同上 |
| ExternalTask | 部分（对账） | 部分 | 领域 Job 终态写穿为主 |
| MutationJob | ✅ | ✅ | — |
| Render | ✅（协调器收敛 unknown/expired） | ✅ | — |
| **AI Run** | 进程实例心跳 | 普通执行 owner 过期 CAS；历史 owner 启动过滤 | 见 §6.3；终态收敛不恢复模型执行，实机 M04 待验 |

### 6.3 契约外：普通 AI Run

- **产品决策（H1，2026-09-28）**：普通 AI Run **承诺「会丢」**。进程退出/重启导致的中断是接受的边界，**不做**可恢复 Run。
- W05b 新实例按 `process_owner = hostname:pid:uuid` 登记 `ai_agent_process_owners`，心跳不依赖模型事件；`process_reaper` 复用 `claim_rows_by_cas`，同事务解除失效 owner、写终态与事件。普通执行/工具传播实例写围栏，过期实例不能续期复活；人工继续重新绑定实际 owner，自动外部续跑仍用 Batch 围栏。paused、waiting_external 和未完成外部 Batch 交接不由普通收敛器接管。
- 默认 owner TTL 90 秒、心跳/扫描各 10 秒，TTL 至少为心跳周期三倍；在数据库可用、时钟同步且无额外调度/写重试延迟时，最后有效心跳后约 TTL + 扫描周期收敛，实机上界需按环境预算验 M04。历史未登记 owner 不自动回填租约，仍按 hostname/PID 启动过滤，跨容器历史遗留由 `force_cancel` 处理；升级前排空旧 Run。模型不自动续跑，SSE 只观察，不能把存活心跳表称为可恢复 Run 队列。
- Run 状态机：`running / waiting_external / paused / cancelling → completed / cancelled / failed`；进程停止 → `AI_RUN_PROCESS_STOPPED`。
- UI/文档标注（区分「取消」与「进程停止、不续跑」）归 **WS-G7**。

---

## 7. 不变量（A4 已下沉，2026-09-29）

不变量由 **`app/ai/job_invariants.py` 状态机库**在写路径强制；`audit_cross_table_invariants` 与 `audit_external_state_consistency` 降为兜底。

| ID | 不变量 | 强制方式 | 状态 |
| :--- | :--- | :--- | :--- |
| **INV-1** | `requirement.status = resolving` ⇔ `batch.status = resuming` 且租约有效 | `claim_rows_by_cas(validate_claimed=...)` 在提交前调用 `assert_inv1_requirement_batch`；关联缺失或 Requirement 更新未命中时拒绝整批认领 | **已下沉** |
| **INV-2** | 同一 `run_id` 至多一个 `resuming` / 一个 `collecting` Batch | ✅ 部分唯一索引 | 保持 |
| **INV-3** | Job 终态 ⇒ ExternalTask 写穿相同终态 | `finalize_external_backed_job` + `sync_external_task_from_domain_job` 同事务投影；页面启动/循环恢复共用 `page_mutation_recovery`，在恢复提交前投影 | **已下沉** |
| **INV-4** | `active_occupancy = 1` 的 (worker_id, worker_epoch) 至多一条 | ✅ 唯一索引 | 保持 |
| **INV-5** | 产物 `attempt_id` 必须等于 Job 当前 attempt | `assert_inv5_attempt_fence`（构建/产物 complete 唯一入口） | **已下沉** |
| **INV-6** | `cancel_requested_at` 非空 ⇒ 不得再从 pending 认领 | ✅ 认领谓词 | 保持 |
| **INV-7** | 终态行不得再被认领 | ✅ 状态谓词 | 保持 |

**实现位置**：`backend/app/ai/job_invariants.py`；单测 `backend/tests/unit/test_job_invariants.py`。

**事务回归**：`backend/tests/integration/test_task_runtime_invariants.py` 使用关联完整的数据库记录验证认领校验失败、恢复投影失败时两侧都回滚，以及正常恢复无需对账即可同步 Task。INV-3 审计覆盖页面、图片终态不一致，兼容历史图片 `completed/error` 别名，保持只读。

---

## 8. A2 统一执行器（已落地，2026-09-29）

A2 扩展 `durable_job_lease_service`，对外提供**列词汇注册 + 领域取值**，不再手写 claim：

| 交付物 | 位置 |
| :--- | :--- |
| 列词汇 | `app/services/job_runtime_vocabulary.py`（`JobColumnVocabulary` + 标准/Build/Mutation/Render 预置） |
| 运行时门面 | `app/services/durable_job_lease_service.DurableJobRuntime` |
| 词汇化恢复 | `recover_expired_running_jobs(..., vocabulary=, recover_values=)` |
| 词汇化认领 | `claim_pending_jobs(..., vocabulary=, claim_values=, extra_claim_conditions=)` |
| 单测 | `backend/tests/unit/test_job_runtime_vocabulary.py` |
| 门禁 | `test_db_adapter_layer.test_claim_functions_must_delegate_cas_timing`（拒绝手写 claim） |

新任务类型只注册：

```python
runtime = DurableJobRuntime(
    model=MyJob,
    vocabulary=JobColumnVocabulary(owner="lease_owner", heartbeat="claimed_at"),  # 或复用预置
    claim_values=...,            # 可选：领域认领取值
    extra_claim_conditions=...,  # 可选：领域认领谓词（deadline 等）
    recover_values=...,          # 可选：领域恢复写入
)
await runtime.claim/renew/transition/cancel/recover(...)
```

`claim(limit=..., max_claims=...)` 分别限制候选扫描数量与成功认领数量，互不替代。`claim_rows_by_cas` 的 `validate_claimed` 与 `recover_expired_running_jobs` 的 `on_recovered` 都在共享事务提交前执行；回调只允许使用当前 Session 做数据库校验/投影，不得执行外部 IO 或自行提交。回调异常（含取消）使本批写入全部回滚；恢复回调只接收 CAS 确实更新的任务 ID。

**验收口径**：

1. 新任务类型只注册列词汇与领域取值，不手写 claim 时序。**已满足**（API 就绪；存量队列迁移归 A3）。
2. 门禁拒绝第 N+1 份手写 claim。**已满足**（`test_db_adapter_layer`）。
3. 不建「能力布尔层」；方言分支仍只在 `app/db/`。**已满足**。

---

## 9. 迁移顺序与完成口径（承接计划 A3）

建议顺序（计划原文）：**构建 → 截图/回填 → 图片 → 页面/组件 mutation → external_task_queue**。

每迁一队必须：

1. 行为回归绿（含取消、过期恢复、围栏拒绝迟到结果）。
2. 方言份数 −1（映射表「现状」列收敛）。
3. **旧代码删除**（不留双轨）。
4. 终态词汇改为契约标准（或读侧归一 + 写侧改名一次完成）。
5. L1 循环内恢复具备（尤其页面/组件队列）。

**迁移进度（A3 完成，2026-09-29）**：

| 队列 | 状态 | 证据 |
| :--- | :--- | :--- |
| 构建 ProjectBuildJob | **已迁** | `claim_job` 走 `claim_pending_jobs` + `PROJECT_BUILD_VOCABULARY` + 领域取值；`recover_expired_build_jobs` 走 `recover_expired_running_jobs` + classify/`recover_values`；手写 claim_cas 已删 |
| 截图 / 回填 | **已在统一入口** | `claim_pending_jobs` 标准词汇 + L1/L2 恢复 |
| 图片 | **终态已归一** | `error`→`failed`，`completed`→`succeeded`（Job.status 与 result_json） |
| 页面/组件 mutation | **L1 已补** | Worker 循环内过期恢复；组件恢复带 `kind` 过滤 |
| external_task_queue | **认领已归一** | `_claim_ready_batch` 走 `claim_rows_by_cas` + `on_claimed`（Requirement 同事务）；generation 围栏保留；门禁例外撤销 |
| MutationJob | **恢复已词汇化** | `MUTATION_JOB_VOCABULARY` + generation CAS + `next_attempt_at` 退避 |

每迁一队完成口径：行为回归绿、方言份数 −1、旧代码删除、终态词汇对齐、L1 恢复具备。

**硬约束重申**：SQLite 分支语义字节级维持；PG 同事务 `SKIP LOCKED` 不得退回跨事务 CAS；`skip_locked` 只允许出现在租约服务。

---

## 10. 已关闭、不要重做

| 项 | 结论 |
| :--- | :--- |
| claim 时序收口（CP3/CP4） | 已收口到 `claim_rows_by_cas` |
| 写重试统一（CP1b） | `app/db/retry` |
| 事务原语命名（CP2） | `app/db/tx` |
| 部署 profile（CP5） | `app/db/profile` |
| `ai-external-task-coordinator` 单一续跑路径 | 保持；页面 Batch 不再承载续跑 |
| Run 可恢复语义（原 A5） | **关闭**；产品承诺「会丢」，标注归 WS-G7 |
| WS-B 死物/门禁/ClaimGate | 已关闭（2026-09-29） |

---

## 11. 维护约定

1. 本文是任务运行时**唯一契约**；字段/状态/错误码/恢复语义变更必须先改本文。
2. A2/A3/A4 的实现 PR 应引用本文对应章节编号。
3. 新发现的方言或旁路状态追加到 §5 映射表，**不得**另开文档或静默扩表。
4. 产品边界（Run 会丢、Lite 规模、方言预算）不进本契约，见[现行评估 §6](../../temp/architecture-assessment-2026-09-30.md#6-决策与承诺边界)。
