# 架构评估：远程渲染落地后的控制面收口（2026-09-24）

> 评估日期：2026-09-24。基线提交 `023c95c`（分支 `dev`）。  
> 输入材料：`docs/temp/archive/` 下首轮评审与 2026-09-23/24 专项评估，以及 `e8afd67..023c95c` 提交区间的实现与文档。  
> 判断口径：代码可确认的问题与尚未验证的风险分开表述；单机 Lite 与 PostgreSQL 部署的行为差异单独标出。  
> 本文是 `docs/temp` 的**现行评估**；历史稿与问题状态表见 [`archive/`](./archive/)，未实施规划见 [`plans/`](./plans/)。

---

## 0. 一页结论

1. **本轮架构变更的主轴已经落地**：浏览器执行彻底出 Backend（远程 Renderer + `render-contracts`）、Runtime 并入主仓、双包管理器 workspace 收拢、页面校验跨阶段语义收口、SQLite 单实例边界与空闲写路径治理。从 `e8afd67`（渲染服务拆分设计）起算，到 `023c95c` 为止，是一条完整的「执行面外移 → 仓库/构建边界 → 正确性与调度收口」改造链。
2. **原 P0（Renderer 不可用却报 `passed` 并落库）已关闭**，判定收敛到 `services/validation_result.py` 单一谓词，并用跨阶段契约测试锁住。
3. **不能据此宣称「可水平扩展」或「Lite 已适配 2C4G」**。普通 AI Run 仍绑 Backend 进程；截图指纹不含运行时/浏览器环境版本；Lite 仍是 Backend+Runtime+Gateway 同容器；构建派发仍依赖 `BackgroundTasks`；容量/故障基线仍缺实测。
4. **D1 已定案（2026-09-24）：SQLite Lite 是长期一等公民**。P2 持久化适配层与 P3 任务运行时按「全做」立项，P4 迁移双方言等价与 P5 Lite 边界固化保持必做；此前「D1 未决 ⇒ 从裁剪」的统一写重试（2b）应重新立项，BoolInt 维持裁剪（见 §4 与 §7）。
5. **下一步优先序**：截图环境身份与失效（P1-Screenshot）→ 写路径基线实测与决策门 D2 → 重立 P2/P3 适配层与任务运行时 → Lite 故障域/构建持久领取 → 双入口契约矩阵。多 Runtime 副本应等 D2 与阶段 0 验收后再启动。**Browserless/CDP 路线已作废**，由远程 Renderer 承接，不再进入计划。

---

## 1. 近期架构变更总览（从哪些提交开始）

### 1.1 提交区间与阶段

改造起点取 **`e8afd67`（2026-09-21，渲染服务拆分设计）**，终点为 **`023c95c`（2026-09-24）**。更早的 `a806ec5`（SQLite 时区）是持久化正确性前置，可视为铺垫。

| 阶段 | 提交 | 日期 | 做了什么 |
| :--- | :--- | :--- | :--- |
| **A. 渲染执行面外移** | `e8afd67` → `bdfcdab` → `9edfd2d` | 09-21 ~ 09-22 | 设计并落地独立 Renderer；Backend 只经 `render_requests` 协调；修复状态机与 artifact 生命周期。 |
| **B. 仓库与交付边界** | `3fa414e` → `2c7420b` → `f981de1` → `0244a5b` → `75de051` → `262f398` → `75af01e` | 09-22 | Runtime 子模块合入主仓；目录结构调整；CI 门禁收敛、本仓构建 Runtime 镜像；`deploy/` 收拢为交付配置中心；Python `uv` workspace 与前端 `pnpm` 单锁；镜像构建修复；文档目录对齐。 |
| **C. 运行态与前端收口** | `b3a268e` → `c261054` → `6ee199d` → `0c6fcc8` → `44282d6` | 09-23 ~ 09-24 | 渲染时间入口统一；文件清理；开发文档对齐现状；Agent 会话状态按会话分片并拆分组合式逻辑。 |
| **D. 正确性与调度治理** | `5c459ae` → `a9dd2c1` → `023c95c` | 09-24 | 页面校验语义与持久化适配层；SQLite 单实例守卫、`/readyz`、写路径打点；空闲写放大治理与循环门禁。 |

### 1.2 分主题：更新了什么

#### A. 远程渲染服务拆分（`e8afd67` / `bdfcdab` / `9edfd2d`）

- **设计**：`e8afd67` 引入 `docs/developer/backend/remote-render-service-design.md`，明确 Backend 不跑 Chromium，截图与页面布局诊断经持久化渲染请求派发。
- **落地**：`bdfcdab` 新增独立 `renderer/` 与 `packages/render-contracts/` 纯契约包；Backend 启动 `RenderCoordinator`，按 Worker ID/epoch 定向调度；每 attempt 新建 Chromium/Context，单槽执行。
- **修复**：`9edfd2d` 收口渲染状态机与 `PreviewArtifact` 生命周期，避免「结果已回、状态未到」或 artifact 提前清理。
- **边界**：Renderer 不连业务库；浏览器网络不能打控制 API；组件远程渲染诊断保留在协议层，不进入内容助手校验链路。

#### B. 单仓化与构建/部署边界（`3fa414e` … `75af01e`）

- `3fa414e`：移除 `runtime` git submodule，合入 `runtime/` 原生目录（含 Runtime Kit 清单、Vite 插件与文档）。
- `2c7420b` / `75af01e`：顶层与 `docs/` 结构调整，`runtime-integration` 与 `runtime` 文档职责对齐。
- `f981de1`：CI 质量门禁收敛；Runtime 镜像改为本仓构建，不再依赖子仓产物。
- `0244a5b`：`deploy/compose` + `deploy/docker` + `deploy/scripts` 收拢为部署配置中心；Backend/Renderer/契约包落入根 `uv` workspace（唯一 `uv.lock`）。
- `75de051` / `262f398`：`editor` 与 `runtime` 并入根 `pnpm` workspace（唯一 `pnpm-lock.yaml`）；修复 `pnpm deploy` legacy 与 Runtime 根上下文镜像构建。
- **含义**：控制面、执行面、前端运行时、契约包在同一仓库内同步演进；跨模块改动可用根仓测试入口（`test:contracts` / `test:render-contracts` / `test:runtime:gate` 等）门禁。

#### C. Agent 会话与前端结构（`44282d6` 等）

- `44282d6`：`editor/src/stores/agent-session.ts` 改为**按会话分片的单一状态**（`runtime` + `ui`），消除树状/扁平双向同步；`AgentConversationPanel` 继续拆出 body/run-state 组合式逻辑。
- `0c6fcc8`：开发文档（架构总览、部署、测试、Runtime）按新结构改写，与实现对齐。
- `b3a268e`：渲染时间入口统一（`utc_now()`），Runtime 排障说明更新。

#### D. 校验语义、SQLite 边界与调度（`5c459ae` / `a9dd2c1` / `023c95c`）

**`5c459ae` 收口页面校验语义与持久化适配层**

- 页面校验输出 `stages={compile,render}`；`_render_stage_status` 改写顶层 `success/status/retryable`，禁止「编译通过 + 渲染不可用 ⇒ passed」。
- 通过判定唯一化到 `services/validation_result.py`（`is_validation_passed` / `is_render_unavailable` / `resolve_write_gate`），删除多份 `_is_validation_passed` 拷贝；`test_validation_predicate_definition_is_single` 作门禁。
- `skip_visual_verification` 为**显式逃生口**：仅 render=`unavailable` 且编译通过时放行，并留审计标记；写入 `tool_specs.py` 使用条件。
- 异步错误码区分 `RENDER_SERVICE_UNAVAILABLE`（可重试）与 `PAGE_VALIDATION_FAILED`（终态）。
- SQLite 兼容债收口（原评估 P2）：`db/errors.detect_transient_write_conflict` 单点写冲突判据；`db/locks` 限定 driver 下钻；`db/indexes.partial_index` 单源部分索引；`db/types.JSONPayload` + 迁移 helper 收敛 JSON 双方言。

**`a9dd2c1` SQLite 单实例边界与运行态就绪/打点**

- `db/sqlite_single_process.py`：启动对 `*.single-process.lock` 取排他锁，拒绝 `WEB_CONCURRENCY`/`UVICORN_WORKERS` > 1；换库时释放旧锁再绑定。
- 守卫在 `lifespan` 获取（避免 `import app` 期抢锁导致测试/脚本失败）。
- 新增 `/readyz`（DB 可连通 + 渲染 Worker 已配置）；`/healthz` 保持纯 liveness；lite compose healthcheck 接入。有意不探测 Renderer 存活，避免外部抖动打挂 Backend 就绪。
- SQLite 写路径打点（默认关）+ `/metrics/db-write` + 导出脚本（须 HTTP 读目标进程，进程内 import 得到全 0）。

**`023c95c` 空闲写放大与循环门禁**

- 终态清理 / `expire_requests` / 图片任务提升等改为「先探测命中集，无命中不发 UPDATE」；探测与更新共用条件对象，避免谓词漂移导致清理静默失效。
- 渲染 Worker 心跳 5s 节流；轮询间隔、图片任务租约/心跳、mutation job 退避全部配置化；删除 `page_mutation_queue` 中已被统一外部任务协调器取代的死代码续跑协调器。
- mutation job 租约回收与 `durable_job_lease_service` 口径对齐（`attempt_count < max_attempts`），并覆盖 `lease_expires_at` 为空的孤儿 `running`；回填任务恢复只收敛 `started_at` 缺失或已超租约者。
- 新增 `test_loop_gate`：`while True` + 亚秒 sleep 必须落在白名单，阻止再新增未登记空转循环。

---

## 2. 变更后的架构快照

```text
Editor (Vue) ──HTTP──► Gateway ──┬──► Backend (FastAPI 控制面)
                                 │       │
                                 │       ├─ 领域服务 / AI Run / 工具规格
                                 │       ├─ render_requests → RenderCoordinator
                                 │       ├─ 预览 artifact / 构建 snapshot
                                 │       └─ SQLite(单实例锁) 或 PostgreSQL + Redis/memory://
                                 │
                                 ├──► Runtime (Vue3+Vite，主仓 runtime/)
                                 │       预览 / 构建 / 编译诊断 / 视觉编辑
                                 │
                                 └──► Renderer (独立容器, 单槽 Chromium)
                                         经 packages/render-contracts 协议
                                         截图 / 页面布局诊断

部署形态（deploy/compose）：
  SQLite Lite：platform-lite(B+E+G) + renderer
  常规单实例 / 分角色 / 分布式：见 plans/runtime-multi-deployment-scaling-plan.md（后两档未落地）
```

关键边界（变更后应遵守）：

| 边界 | 约束 |
| :--- | :--- |
| 浏览器执行 | 只在 Renderer；Backend 不装 Playwright/Chromium。 |
| 校验通过语义 | 唯一谓词 `validation_result`；执行不可用 ≠ 检查通过；页面写入默认要求 render 阶段有结论。 |
| SQLite | 文件库单进程/单容器；启动守卫；多副本部署不得共用同一 SQLite 卷。 |
| 普通 AI Run | 进程内执行，不承诺重启恢复；页面/图片/组件外部任务走持久化租约队列。 |
| Runtime Kit | 只暴露清单内 `.vN` 路径；壳层能力不进公开能力目录。 |
| 循环门禁 | 新增后台循环须进 `test_loop_gate` 白名单并配置化节奏。 |

---

## 3. 已关闭项（相对 2026-09-23 评估）

| 原问题 | 关闭证据 | 提交 |
| :--- | :--- | :--- |
| P0：Renderer 不可用仍 `passed` 落库 | `validation_result.py` + `stages` 契约 + 跨阶段测试（`test_page_code_check_render_unavailable_must_not_report_passed` 等） | `5c459ae` |
| `_is_validation_passed` 多份拷贝 | 单一定义 + `test_validation_predicate_definition_is_single` | `5c459ae` |
| SQLite 写冲突判据/JSON 别名/部分索引双写 | `db/errors` / `db/types.JSONPayload` / `db/indexes.partial_index` | `5c459ae` |
| SQLite 可被多进程并发写 | `sqlite_single_process` 排他锁 + worker 数拒绝 | `a9dd2c1` |
| Backend 无 readiness | `/readyz` + lite healthcheck | `a9dd2c1` |
| 空闲态无条件 DML 放大 | 探测-命中再写、心跳节流、节奏配置化 | `023c95c` |
| 租约回收口径不一致 / 孤儿 running | mutation job 与 durable lease 对齐 | `023c95c` |
| 未登记亚秒空转循环可随意新增 | `test_loop_gate` 白名单 | `023c95c` |
| Agent Store 双向同步 | 按会话分片单一状态 | `44282d6` |
| Backend 内嵌 Chromium | 远程 Renderer + render-contracts | `bdfcdab` 起 |

---

## 4. 仍在风险（按优先级）

### P0

**当前无代码可确认的 P0。** 原「渲染不可用却报通过」已关闭。  
但注意：**契约-实现对齐依赖测试锁**；后续改 `code_check_service` / planner / 外部任务错误码时，不得绕开 `validation_result` 或删跨阶段测试。

### P1 — 发布与可用性边界

| ID | 问题 | 现状 |
| :--- | :--- | :--- |
| **P1-Screenshot** | 截图指纹不含 Runtime/Renderer/字体/Chromium 环境版本 | `page_screenshot_fingerprint_service` 只哈希尺寸/主题/字体修订等配置；`RENDER_PROFILE_DIGEST` 多为运维标签 `profile.v1`。镜像升级后旧截图仍可能复用。**建议**：指纹纳入环境摘要，发布时定向失效。 |
| **P1-Run** | 普通 AI Run 绑定 Backend 进程 | `background_run_manager` 进程内 asyncio；退出收敛 `AI_RUN_PROCESS_STOPPED`。已是明示约束，不可宣称滚动升级无中断。 |
| **P1-Lite** | Lite 故障域与内存预算仍合并 | `platform-lite` 同容器 Backend+Runtime+Nginx，任一子进程退出即整平台退出。Renderer 已隔离。无 2C4G 混合负载实测。 |
| **P1-Build** | 构建派发依赖 FastAPI `BackgroundTasks` | 进程故障后任务接管与迟到结果处理不足。扩容规划已指出，未实施。 |
| **P1-Health** | `/readyz` 不反映 Renderer 与调度 loop 健康 | 有意不探 Renderer（避免抖动）；loop 积压/租约年龄仍无对外指标（写路径打点已具备采集入口）。 |

### P2 — 成本与维护性

| ID | 问题 | 簡述 |
| :--- | :--- | :--- |
| **P2-Queue** | 调度写路径仍偏轮询 | 空闲写已治理；13 条 loop 节奏未收敛到统一运行时；4 套租约恢复实现仍在。**D1=A 后**：统一任务运行时（P3）与写重试收口（2b 重立）进入正式范围，不再从裁剪。 |
| **P2-API** | 内外 API 双入口 | 领域服务已共享；仍缺「同一操作两入口」防漂移矩阵（权限/错误码/字段/事务语义）。 |
| **P2-Locks** | 进程内订阅/锁表 | SSE 有序列号 DB 回放；限制在 Run 生命周期，而非事件通道本身。`memory://` 已定为 Lite 正式适配器；进程内锁仍不得当作可扩展原语。 |
| **P2-GodFiles** | 超大文件 | 后端 ≥1000 行仍约 10 个；Editor 视图层普遍偏大。AGENTS.md 要求「控制行数、职责过多优先拆分」。 |
| **P2-Profile** | `profile.v1` 写死在 Compose/示例 | 与 P1-Screenshot 同根：发布身份未自动生成、未强制一致。 |

### 决策状态

| 决策 | 状态 | 影响 |
| :--- | :--- | :--- |
| **D1**：SQLite Lite 产品地位 | **已定案（2026-09-24）——长期一等公民**（选项 A） | P2 **全做**、P3 **全做**、P4/P5 **必做**。统一写重试（2b）按 D1=A **重新立项**；2d 仅有限重立（不恢复零调用点别名）；BoolInt **维持裁剪**。实现沿用 6.3.1 技术结论，见下表。 |
| **D2**：是否触发写路径基线门 | **仍待实测** | 需 2C4G 空闲/混合两轮（`DATABASE_WRITE_PATH_METRICS_ENABLED` + `/metrics/db-write`）；未达标前不启动 Runtime 角色拆分。D1=A **不替代** D2：基线决定调度节奏怎么收，不决定 Lite 是否一等。 |
| **Lite 运行态** | **已定案（2026-09-24）：正式支持 `memory://` 适配器** | 与真实 Redis 双后端同契约；Lite 不强制上 Redis。契约见 [`docs/developer/backend/runtime-state-adapter.md`](../../developer/backend/runtime-state-adapter.md)，实施计划见 [`plans/lite-memory-adapter.md`](./plans/lite-memory-adapter.md)。 |
| **CDP/Browserless 路线** | **已作废（2026-09-24）** | 由远程 Renderer（`renderer/` + `render-contracts`）承接浏览器执行边界。`archive/cdp.md` 仅作历史对照，**不再作为实施计划或路线图**。 |

**D1=A 对已裁剪项的重立约束**（承接 [`archive/architecture-assessment-sqlite-2026-09.md`](./archive/architecture-assessment-sqlite-2026-09.md) §6.3.1）：

| 原步骤 | 重立结论 | 说明 |
| :--- | :--- | :--- |
| **2b 统一写重试** | **重立为 P3 前置 / D2 加速项** | 不得恢复 `run_with_write_retry(session, fn)` 旧签名；以 **session 工厂**为参数重新设计，兼容「每尝试新建 session」「尝试间刷新实体」「for-else 兜底再读」「重试内结构化日志」四类现有语义。若 D2 观测到 `database is locked`，本项升为 P3 必做阻塞。 |
| **2d 事务语义 helper 剩余** | **有限重立** | `read_probe` / `acquire_admission_lock` 仍不应恢复为零调用点别名；应把 `durable_job_lease_service` 与 rendering 准入锁的 SQLite 内联语义**就地文档化或并入 `db/tx` 有调用点 API**，禁止再散落方言注释。 |
| **2e BoolInt** | **维持裁剪** | `active_occupancy=1` 已由 `partial_index` 谓词约束，`int` 别名无运行时/DDL 保证；D1=A 不改变这一事实。 |
| **P3 统一任务运行时** | **全量立项** | 不得再按「过渡形态」只做空闲零写+死代码清理；目标是租约恢复口径统一、loop 节奏可配、空闲零写 DML 的可门禁运行时（对应 Q1/Q2/Q8–Q12）。 |
| **P4 迁移双方言等价** | **保持必做** | D1=A 使 Lite 长期共存，迁移分支必须有双库行为证明；历史迁移不改写，只约束新迁移。 |
| **P5 Lite 边界** | **保持必做** | 单实例守卫已有；还需把「Lite 能力范围」写进部署承诺（并发、故障域、不可多副本共用 SQLite 卷）。 |

---

## 5. 尚未验证（不可当作已有能力）

- **容量基线**：RSS、OOM、SQLite 锁等待、队列年龄、P50/P95——打点入口已有，目标机两轮采集未完成（模板见 [`archive/baseline-sqlite-2026-09.md`](./archive/baseline-sqlite-2026-09.md)）。
- **多实例联调**：共享对象存储、JWKS/签名密钥一致、AI 凭证密钥、迁移与租约跨实例——规划有清单，未验收。
- **故障注入**：Renderer 全挂、Worker 掉线、busy_timeout 耗尽、构建进程被杀后的端到端行为。
- **性能等价**：两阶段（编译+渲染诊断）耗时拆分；「删编译省 50%」类结论无基线，**不应采纳**。

---

## 6. 明确不要再当真的判断

沿用 2026-09-23 状态总览的「不成立/过时」清单，本轮补充：

| 判断 | 为何作废 |
| :--- | :--- |
| 含 Chromium 的三容器 / `PlaywrightBrowserPool` 改造路线 | 已被远程 Renderer 方案取代。 |
| 删 Runtime 编译阶段可省 50% | 失败集合不同，无基线。 |
| 纯内存租约队列 + 固定租约 | 丢重启/跨实例唤醒，盖不住长步骤。 |
| 内外 API 机械合并 URL | 事务语义不同；先做契约矩阵。 |
| 固定 1.5GB / 降延迟 40% 当验收 | 未验证假设。 |
| Browserless/CDP 当作待办路线 | **已作废**。远程 Renderer 已覆盖该边界；`archive/cdp.md` 仅历史对照，不进入计划。 |
| Runtime 多副本/角色拆分当已有 bug 清单 | 见 [`plans/runtime-multi-deployment-scaling-plan.md`](./plans/runtime-multi-deployment-scaling-plan.md)，属未实施路线图。 |

---

## 7. 建议处理顺序

> D1 已定为「SQLite Lite 长期一等公民」（选项 A）。下列顺序在原优先级上重排：P2/P3 不再等待 D1，但仍受 **D2 基线**调度节奏定档。

1. **P1-Screenshot / P2-Profile**：截图指纹纳入 Runtime/Renderer/字体/Chromium 版本；`profile` 不匹配拒绝派发；发布定向失效旧截图。这是当前最高残留正确性风险。
2. **D2 基线采集**（打点已就绪）：Lite 2C4G 空闲 10 分钟 + 混合负载各一轮。产出写路径结论后，直接喂给第 3 步的任务运行时节奏设计。
3. **P3 任务运行时 + 2b 写重试（D1=A 重立）**：按 [`archive/architecture-assessment-sqlite-2026-09.md`](./archive/architecture-assessment-sqlite-2026-09.md) §6.4 立项；2b 以 session 工厂签名设计，不恢复旧抽象。目标验收仍用结构性判据：空闲零写 DML、`database is locked` 归零或可重试闭环、tick P95 < 轮询间隔。
4. **P5 Lite 边界固化**：部署文档写死 Lite 能力范围（单进程、单 Backend、SQLite 卷禁止多实例）；评估 `platform-lite` 是否拆 Runtime 或至少独立重启。**运行态半边**按 [`plans/lite-memory-adapter.md`](./plans/lite-memory-adapter.md) 执行（`memory://` 契约、双后端对拍、可观测）。
5. **P1-Build**：构建任务改持久化领取 + attempt 围栏，与页面/截图队列对齐。
6. **P4 迁移双方言等价**：新迁移双库行为证明；与 3 并行可接受，不可无限期推迟。
7. **P2-API 契约矩阵**：同一操作双入口对拍（权限、错误码、字段、同步/异步语义）。
8. 多 Runtime 副本 / 角色拆分：**排在 1–3 与 D2 之后**，按 [`plans/runtime-multi-deployment-scaling-plan.md`](./plans/runtime-multi-deployment-scaling-plan.md) 增量，不重开任务模型。**不要再规划 Browserless/CDP**。

**D1=A 的长期含义（产品与工程）**

- SQLite Lite 不是「能跑就行」的演示档：CI 与发布门禁须长期覆盖 Lite 路径（单实例锁、迁移双方言、空闲写、校验语义）。
- 「一套代码两库」的方言分支是**长期成本**，收口目标是 `app/db/` 适配层而不是删掉 SQLite。
- 文档与对外能力声明不得写「Lite 仅过渡/请尽快迁 PostgreSQL」；应写清 Lite 适用边界与推荐规模。

---

## 8. 与历史文档的关系

| 文档 | 位置 | 关系 |
| :--- | :--- | :--- |
| `architecture_review_report.md`（09-08） | `archive/` | 首轮评审；浏览器内嵌、双重重度构建等结论已过时；代码气味清单仍有部分参考。 |
| `architecture-assessment-2026-09.md`（09-23） | `archive/` | 对首轮的复核；P0/P1/P2 框架被本文继承并更新状态。 |
| `architecture-assessment-sqlite-*.md` / `*-memory-*.md` | `archive/` | 专项债清单；Q0 与多数 P2 已在 `5c459ae`/`023c95c` 处理，细节证据仍可追溯。 |
| `docs-temp-issue-status-2026-09.md` | `archive/` | 问题状态表（含 09-24 修复标注）；以本文 §3/§4 为准。 |
| `baseline-sqlite-2026-09.md` | `archive/` | 采集模板；打点入口已在 `a9dd2c1` 落地，执行采集时仍可参照口径。 |
| `cdp.md` | `archive/` | **已作废**。Browserless/CDP 路线由远程 Renderer 取代，不再作为计划。 |
| `runtime-multi-deployment-scaling-plan.md` | `plans/` | **未实施规划**；阶段 0 门禁见 §7。 |

---

## 附录 A. 变更提交速查

```text
e8afd67  渲染服务拆分设计
bdfcdab  落地远程渲染服务拆分
9edfd2d  修复远程渲染状态与 artifact 生命周期
3fa414e  将 runtime 子模块合入主仓原生目录
2c7420b  调整仓库结构
f981de1  收敛 CI 质量门禁并改为本仓构建 Runtime 镜像
0244a5b  收拢 deploy 配置中心并落地 Python uv workspace
75de051  合并 editor/runtime 为根级 pnpm workspace 单锁
262f398  修复 workspace 下的镜像构建
75af01e  仓库结构调整
b3a268e  统一渲染时间入口并更新 Runtime 排障说明
c261054  清理文件
6ee199d  bug 修复
0c6fcc8  更新开发文档
44282d6  重构 Agent 会话状态：按会话分片并拆分组合式逻辑
5c459ae  收口页面校验语义与持久化适配层
a9dd2c1  加 SQLite 单实例边界与运行态就绪/打点入口
023c95c  降低持久化调度空闲写放大并补齐循环门禁
```

铺垫：`a806ec5` 修复 sqlite 时区问题（`docs/developer/backend/time-handling.md`）。
