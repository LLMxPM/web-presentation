# 架构评估：内存状态与 memory:// 运行态

> 评估日期：2026-09-23。对象为当前工作区 Backend、Runtime 运行态用法与 Lite 部署模板。  
> 本文只阐述**内存形态**导致的架构不规范：进程内全局状态、`memory://` 假 Redis、进程绑定执行、进程内唤醒与生命周期分裂。  
> SQLite 方言、写锁、轮询写放大等见姊妹篇 [`architecture-assessment-sqlite-2026-09.md`](./architecture-assessment-sqlite-2026-09.md)。两文在「锁序」「定时任务」处有交叉，会互相引用。

---

## 1. 结论摘要

Lite 与单实例部署大量依赖**进程内内存**：

1. **`memory://` 不是 Redis**，而是一套进程内模拟（String/Hash/Stream/TTL），却被当成正式运行态存储承接 preview artifact、任务锁和可选通知。
2. **进程内全局字典/锁**（事件订阅、Run 事件锁、Run 执行锁、代次唤醒）在单进程正确，跨进程或水平扩展时语义消失。
3. **普通 AI Run 绑定 Backend 进程**，重启即 `AI_RUN_PROCESS_STOPPED`；与可持久化的页面/图片/组件外部任务不是同一套可用性承诺。
4. **持久化事实源在 SQLite/PostgreSQL，瞬时事实源在内存**，任务恢复扫描与 artifact 生命周期脱节，失败模式变成复合故障。

**总体判断**：内存方案对「单机 Lite、可接受重启中断」是合理极简；问题是它**没有被收成明确的运行态适配边界**，而是与可恢复任务、多副本叙事混在同一套代码里。需要把「内存运行态」从「可持久化调度」中切开，并在部署承诺里写死单实例限制。

---

## 2. 内存形态全景

```text
                    ┌─────────────────────────────────────┐
                    │  Backend 进程地址空间                  │
                    │                                     │
                    │  _SUBSCRIBERS / _RUN_EVENT_LOCKS     │
                    │  _run_locks / GenerationWakeup       │
                    │  AgentBackgroundRunManager (asyncio) │
                    │  TokenService._private_key           │
                    │                                     │
                    │  InMemoryRedis  (REDIS_URL=memory://)│
                    │    ├─ preview artifact               │
                    │    ├─ 任务锁 / 可选 Stream 通知        │
                    │    └─ TTL 字典（purge_expired）        │
                    └─────────────────────────────────────┘
                                      │
                    进程重启 / 扩容 / 多副本 → 以上全部蒸发
```

| 内存形态 | 位置 | 存的是什么 | 重启后 | 跨实例 |
| :--- | :--- | :--- | :--- | :--- |
| `_SUBSCRIBERS` | `ai/platform_runtime.py` | SSE 订阅 Queue 集合 | 丢 | 不可见 |
| `_RUN_EVENT_LOCKS` | 同上 | run 级 asyncio.Lock | 丢 | 失效 |
| `_run_locks` | `ai/session_facade_pydantic.py` | (session, run) 锁 | 丢 | 失效 |
| `GenerationWakeup` | `ai/page_mutation_wakeup.py` | 代次 + Condition | 丢 | 不可见 |
| `AgentBackgroundRunManager` | `ai/background_run_manager.py` | 普通 Run 的 asyncio.Task | 中断 | 不可迁 |
| `InMemoryRedis` | `services/redis_runtime_client.py` | artifact / 锁 / Stream 模拟 | 丢 | 不可共享 |
| `TokenService._private_key` | `services/token_service.py` | 进程缓存的 RSA 密钥 | 从本地文件重载 | **副本密钥必须一致** |
| Runtime Vite 进程缓存 | `runtime/` | 预览 token、模块转换缓存 | 丢 | 见扩容规划 |

---

## 3. 不规范清单（内存维度）

### 3.1 `memory://` 假 Redis（核心）

**实现**：`redis_runtime_client.InMemoryRedis` 线程安全模拟 `set/get/incr/expire/hset/hget/xadd/xread/scan_iter/pipeline`，并自实现 Stream ID 比较与 `purge_expired`。

**被当成正式存储的用途**：

| 用途 | 调用方 | Lite 默认 |
| :--- | :--- | :--- |
| Runtime preview / 诊断 artifact | `RuntimeArtifactStore` | `REDIS_URL=memory://lite` |
| 任务锁 | 如 `asset_render_hint_backfill_job_service` | 同上 |
| 事件唤醒 / 通知（设计可选） | 各队列 | 进程内代次为主 |

**不规范点**：

1. **接口像 Redis，持久性不是 Redis**  
   真 Redis 挂了有运维语义；`memory://` 则是「本进程堆上的字典」。`ensure_redis_runtime_available()` 对二者只做 `ping`，健康检查无法区分「真依赖可用」与「假实现永远 ok」。

2. **清理语义 duck-typing**  
   `sweep_expired` 用 `getattr(client, "purge_expired", None)`；真 Redis 返回 0，靠自身 TTL。空闲行为两套，监控无法对齐。

3. **Stream 子集是测试玩具**  
   自实现 `xadd/xread` 与 ID 比较，仅供测试/演示。生产路径若误用 Stream，Lite 与真实 Redis 的阻塞、裁剪、消费组语义都不等价。

4. **与持久化任务表生命周期分裂（与 SQLite/PG 文交叉）**  
   - 业务任务在数据库表里可恢复；  
   - artifact 在 `memory://` 中进程退出即无；  
   - 父任务恢复时找不到 artifact，只能走「明确失败或按既有规则重建」。  
   文档（`resource-queues.md` / 扩容规划）已声明不承诺跨重启，但**错误分类与用户可读恢复路径**仍偏弱：表现为「渲染 404 / 结果丢失」而非结构化的 `RUNTIME_ARTIFACT_LOST`。

5. **TTL 依赖惰性删除 + 周期 purge**  
   `runtime-artifact-sweeper` 默认 30s 调 `purge_expired`。热点 key 未触达时靠 sweeper；若 sweeper 停止（lifespan 退出异常），内存只增不减——Lite 与 Runtime 同容器时直接吃预览内存。

**建议**：

- 配置与启动日志显式区分 `runtime_store_driver = memory | redis`；`/healthz` 外的 readiness 标明 `artifact_store=memory (ephemeral)`。  
- artifact 丢失映射稳定错误码，供 AI 工具与 External API 统一展示。  
- 禁止业务代码直接 `xadd/xread`；唤醒统一走 §3.4 的 GenerationWakeup 抽象。  
- Lite 文档写死：**artifact 不可备份、不可多实例、重启后旧预览链接失效**。

---

### 3.2 进程内全局锁与订阅表

| 符号 | 文件 | 用途 |
| :--- | :--- | :--- |
| `_SUBSCRIBERS` | `platform_runtime.py` | run_id → SSE Queue 集合 |
| `_RUN_EVENT_LOCKS` | 同上 | run 事件追加互斥（WeakValueDictionary） |
| `_run_locks` | `session_facade_pydantic.py` | (session_id, run_id) 执行互斥 |

**不规范点**：

1. **双事实源「实时推送」**  
   SSE 正确路径是「进程内 Queue 推送 + 按 `event_index` 查库回放」。推送只是加速，回放才是正确性——这一点实现是对的。但命名与代码结构仍让人以为订阅表是唯一通道；多实例时只有 DB 回放活着，延迟与空轮询上升（见 SQLite 篇 §定时任务）。

2. **锁粒度与锁序和 SQLite 纠缠**  
   `_RUN_EVENT_LOCKS` 不仅是并发控制，还是 **SQLite 锁序补丁**的一部分：`append_event` 在「尚未持有 SQLite 写事务」时才进进程锁，避免与 DB 写锁死锁（详见 SQLite 篇 S6）。  
   → 内存锁对象因此**不能**简单换成 Redis/DB 锁；换锁必须与写锁顺序一起重设计。

3. **多实例语义为空**  
   两个 Backend 时：订阅互不相通、Run 锁可重复进入、`_run_locks` 各自为政。SSE 能靠回放「看起来在工作」，**普通 Run 执行不能**。

**建议**：

- 类型/命名上区分 `LocalOnlyLock` / `LocalPubSub`，禁止与「分布式锁」混用 API。  
- 多 Backend 前置条件写入部署清单：共享存储 + 密钥一致 + **明确普通 Run 不可跨实例续跑**（已是文档语义，需变成发布门禁）。  
- 锁序策略（§ SQLite S6）收口到持久化适配层后，进程内锁只剩「减少同进程重复写」的优化，可删可留。

---

### 3.3 普通 AI Run 绑定进程

**实现**：`AgentBackgroundRunManager` 用进程内 `asyncio.Task` 跑 Pydantic AI；关闭时 cancel；启动时 `recover_interrupted_agent_runs_on_startup` 把遗留 running 收敛为 `AI_RUN_PROCESS_STOPPED`。

**与外部任务对比**：

| | 普通 Run（模型对话步） | 页面/图片/组件外部任务 |
| :--- | :--- | :--- |
| 执行载体 | Backend 进程内 Task | 持久化 Job + 租约队列 |
| 重启 | 终态中断，不自动续跑 | 租约过期后重入队/恢复 |
| 用户可见 | `AI_RUN_PROCESS_STOPPED` | 可恢复的 waiting_external |

**不规范点**：

1. **可用性承诺分裂未产品化**  
   文档承认「不承诺跨进程恢复」，但 UI/工具层对两种失败的引导不同强度；用户容易把外部任务的「可恢复」误以为对话 Run 也可恢复。

2. **工具副作用与模型步不同寿命**  
   一次 Run 内工具已写页面（外部任务成功），模型步随进程死亡——出现「页面已改、对话中断」的半完成状态。围栏（`AgentRunWriteFence`）防止租约丢失后误写，但**不提供对话级补偿**。

3. **锁与 Task 都在 app.state**  
   测试、多 app 实例、`uvicorn --workers` 均需额外约定；当前默认单 worker 是隐含前提。

**建议**：

- 部规格与用户文案固定三句话：外部任务可恢复；普通 Run 停机即失败；页面已写不自动回滚。  
- 发布门禁：滚动重启演练记录普通 Run 失败率与用户恢复路径。  
- 若产品要求长会话无中断，另立「可恢复执行」项目；不要用替换锁提供者冒充解决。

---

### 3.4 进程内唤醒（`GenerationWakeup`）

**实现**：`page_mutation_wakeup.py` 代次 + `asyncio.Condition`；生产者 `notify()`，消费者 `wait(observed_generation, timeout)`，超时回落数据库轮询。

**评价**：模式正确（通知不丢代次 + 轮询兜底），但：

1. **仅页面 Job/Batch 有**，图片/组件/截图/External 协调器仍靠纯 `sleep` 轮询。  
2. **通知范围仅本进程**；Lite 单进程收益完整，多实例仅剩轮询。  
3. 与 `memory://` Stream 通知能力重叠，两套「事件推动」叙事。

**建议**：抽成通用 `JobWakeup`，所有队列共用；跨进程需求明确不做或改 Redis Pub/Sub，不与 `InMemoryRedis.publish`（现在是 no-op）混用。

---

### 3.5 密钥与配置的进程缓存

`TokenService._private_key` 进程内缓存，从本地 PEM 加载或首次生成。

**不规范点**（偏部署/扩展）：

1. 多副本若各自生成，JWKS 不一致，预览令牌全体失效。  
2. 生成后写回本地路径，在容器只读层或不可写卷上会失败/重复生成。  
3. 这是「本地文件 + 进程内存」模型，不是 `memory://` 问题，但同属**单实例假设**。

**建议**：多 Backend 必须挂载同一密钥文件或 Secret；启动时禁止「生成并写回」除非显式 `ALLOW_GENERATE_SIGNING_KEY=true`。

---

### 3.6 Lite 共享地址空间（与内存预算）

`platform-lite` 同容器：Backend 各 asyncio 任务 + Runtime Vite + Nginx。

- `InMemoryRedis` 与 Vite 编译缓存、Node 诊断 Worker 堆、事件缓冲**共享容器内存**。  
- artifact sweeper 不及时 = 内存只涨；Vite 大编译 = 挤掉 Backend 任务。  
- 任一子进程退出，入口脚本结束其余进程——内存 OOM 与逻辑崩溃同级放大。

**建议**（拓扑）：Lite 中期拆 Runtime 容器；短期给 `memory://` 与 Vite 设硬顶（max keys / max bytes），OOM 前可预期失败。

---

## 4. 内存 × 定时任务（交叉摘要）

定时任务详细清单在 SQLite 篇 §3；此处只记**内存导致的不规范**：

| 现象 | 内存根因 |
| :--- | :--- |
| 跨实例/重启后唤醒丢失，只能 sleep 轮询 | `GenerationWakeup` 仅进程内；`InMemoryRedis.publish` 为 no-op |
| SSE 依赖查库回放，空轮询 | `_SUBSCRIBERS` 跨进程无效 |
| 恢复扫描与 artifact 存活窗口不一致 | artifact 在 memory，任务在 DB |
| 心跳任务无法迁到独立 Worker 进程 | 状态与锁在 Backend 进程 |
| 多副本扩容假象 | 全局锁/订阅/Run Task 不可分片 |

---

## 5. 风险分级（仅内存）

| 级别 | ID | 问题 |
| :--- | :--- | :--- |
| **P1** | M1 | `memory://` 与 DB 任务生命周期分裂，复合失败难归因 |
| **P1** | M2 | 普通 Run 进程绑定，产品承诺与外部任务不一致 |
| **P1** | M3 | Lite 共享内存无硬顶，artifact/Vite/任务互相挤压 |
| **P2** | M4 | 进程内锁/订阅被误读为可扩展原语 |
| **P2** | M5 | 唤醒/通知实现分裂（Wakeup vs 假 Stream vs 纯 sleep） |
| **P2** | M6 | 签名密钥进程缓存 + 可自动生成，多副本不安全 |
| **P2** | M7 | `InMemoryRedis` 清理/Stream 语义与真 Redis 不对齐 |

---

## 6. 整改建议（内存专项）

1. **运行态驱动收口**  
   `RuntimeArtifactStore` / 锁 / 通知只依赖窄接口：`get/set/delete/expire/try_lock/publish_local`；`memory` 与 `redis` 两实现 + 能力矩阵文档。禁止业务直接摸 `InMemoryRedis`。

2. **错误码与生命周期**  
   artifact 缺失/过期 → `RUNTIME_ARTIFACT_LOST` / `RUNTIME_ARTIFACT_EXPIRED`；父任务与 AI 工具统一处理；健康状态暴露 `artifact_store_ephemeral=true`。

3. **内存配额**  
   Lite：artifact max entries/bytes、sweeper 失败告警；与 `RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB` 分列监控。

4. **普通 Run 承诺产品化**  
   UI/`diagnose_ai_run`/部署文档三处一致；滚动重启演练入门禁。

5. **统一 JobWakeup**  
   全部队列进程内通知 + 轮询退避；明确「无跨进程通知」或另接 Redis Pub/Sub，删除 no-op `publish` 假实现。

6. **密钥**  
   只读挂载、启动校验多副本一致、关闭默认自动生成。

**明确不做**：用 `memory://` 支撑多 Backend；用进程内锁宣称分布式互斥；把普通 Run 静默改成可恢复而不设计检查点。

---

## 7. 一页结论

- **内存问题的本质**是「瞬时状态被当成可恢复架构的一部分」。  
- 优先：artifact 生命周期与错误码、Lite 内存硬顶、普通 Run 承诺写死、统一唤醒。  
- 锁序与写重试细节见 **SQLite 篇 §2**；调度频率与写放大见 SQLite 篇 §3，整改计划见 §6。  
- 单实例 Lite 下当前实现可用；**多副本叙事必须先假切割这三块**：`memory://`、进程内锁/订阅、进程内 Run。
