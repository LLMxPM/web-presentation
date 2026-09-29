<!-- 文件功能：docs/temp 2026-09-28 整理后的残留问题与下一轮实施计划（承接已归档三份 plans 与多部署评审的未覆盖项）。 -->
# 残留问题与下一轮计划（2026-09-28）

> 整理日期：2026-09-28。基线提交 `2d7858b`（分支 `dev`）。  
> 输入材料：已归档的 [`lite-memory-adapter-2026-09.md`](../archive/lite-memory-adapter-2026-09.md)、[`runtime-multi-deployment-scaling-plan-2026-09.md`](../archive/runtime-multi-deployment-scaling-plan-2026-09.md)、[`db-concurrency-primitives-2026-09.md`](../archive/db-concurrency-primitives-2026-09.md)、[`review-multi-deployment-e2efe6c-head.md`](../archive/review-multi-deployment-e2efe6c-head.md) 的实施记录与未覆盖项，以及现行评估 [`../architecture-assessment-2026-09-28.md`](../architecture-assessment-2026-09-28.md)（继承自 09-25 平台演进稿与结构批判快照）。  
> **本文是 `docs/temp/plans/` 的现行计划**。已实施工作只在 `archive/` 留证据，不在本文复述完成勾选；「未覆盖项不得被完成勾选吃掉」是硬规则。

---

## 0. 一页结论

1. **三条已归档主线（运行态 `memory://`、多部署 T0–T4、DB 并发原语 CP1–CP6）代码均已落地**，但都不能关闭对应架构项：任务模型仍碎片化、多副本拓扑未就绪、D2 写路径基线仍未采集。
2. **下一轮主轴只有一条：P3 统一任务运行时（契约冻结 → 迁移）**。其余工作按「再补多部署门槛 → 再做契约机械化与巨石拆分」推进，不与 P3 抢同一片代码。
3. **产品三问已拍板（2026-09-28）**：Run 承诺「会丢」；Lite 推荐 5–10 人、预览并发约 3；双库方言预算从宽。跟进项转入 WS-G（文档/UI/容量/治理）。
4. ~~**可立即做的低成本项**（WS-B）~~ **已全部完成（2026-09-29）**：死副本/死契约测试/死 JSON Schema 清理，架构测试进 PR 阻塞层，ClaimGate 补强，跨用户 AI 工具写入矩阵，branch protection 启用。见 §3。

---

## 1. 工作流总览

| 工作流 | 名称 | 优先级 | 体量 | 依赖 |
| :--- | :--- | :--- | :--- | :--- |
| **WS-A** | P3 统一任务运行时 | **P0 主轴** | 大（多迭代） | 无（可先冻结契约） |
| **WS-B** | 死物清理 + 架构测试进门禁 | **已清（2026-09-29）** | 小 | 无 |
| **WS-C** | 多部署/多副本门槛补齐 | P1 | 中 | WS-A 部分语义 |
| **WS-D** | D2 写路径与容量基线 | P1 | 中 | 打点已就绪 |
| **WS-E** | 跨端契约机械化 | P1 | 中 | 无 |
| **WS-F** | AI 巨石与分层拆分 | P2 | 大 | WS-A（降低迁移面） |
| **WS-G** | Lite / 生产加固 | P2 | 中 | WS-D（规模承诺） |
| **WS-H** | 产品决策 | **已拍板（09-28）** | — | 跟进项 → WS-G |

并行建议：本周 **WS-B**；与之并行启动 **WS-A 契约冻结** 与 **WS-D 采集**；**WS-C** 在 WS-A 任务语义定稿后接上。

---

## 2. WS-A · P3 统一任务运行时（主轴，**A1–A4 已完成 2026-09-29**）

**问题**（现行评估 P1-TaskModel / 结构批判 P0）：至少 9 套并行的领取-租约-心跳-恢复-错误码方言（`external_task_queue` / `page|component mutation` / `image` / `screenshot` / `backfill` / `mutation_job` / `render coordinator` / 构建 `BackgroundTasks` / 进程内 AI Run）。CP4 只收口了 **claim 时序**，没有统一运行时。

| 序 | 工作项 | 完成口径 | 估时 |
| :--- | :--- | :--- | :--- |
| A1 | **冻结任务运行时契约**：角色模型（Worker / Lease / Attempt / Terminal）、字段词汇（owner、heartbeat、attempt_id、cancel）、错误码族、恢复语义 | 一份契约文档 + 与现有 9 套方言的映射表；**不写实现** | **已完成（2026-09-29）**：[`docs/developer/architecture/task-runtime-contract.md`](../../developer/architecture/task-runtime-contract.md)；含 10 套任务模型映射、3 套认领方言对照、字段/状态/错误码/恢复语义冻结；未写实现 |
| A2 | **统一 claim/lease/heartbeat/recover 执行器**（扩展 `durable_job_lease_service.claim_rows_by_cas`，不建能力布尔层） | 新任务类型只注册列词汇与领域取值，不再手写 claim；门禁拒绝第 N+1 份手写 claim | **已完成（2026-09-29）**：`JobColumnVocabulary` + `DurableJobRuntime`；词汇化 claim/recover/cancel；`test_job_runtime_vocabulary.py` 14 例；门禁补注新队列注册口径。存量队列迁移归 A3 |
| A3 | **迁移队列**（建议顺序：构建 → 截图/回填 → 图片 → 页面/组件 mutation → external_task_queue） | 每迁一队：行为回归绿、方言份数 −1、旧代码删除 | **已完成（2026-09-29）**：构建迁移、页面/组件 L1、图片终态归一、MutationJob 词汇化 recover、external 认领 `claim_rows_by_cas`+`on_claimed`。证据见 task-runtime-contract §9 |
| A4 | **跨表不变量下沉**（如 `resolving` requirement ⇔ 有效租约的 `resuming` batch） | DB 约束或状态机库保证，审计函数降为兜底 | **已完成（2026-09-29）**：`app/ai/job_invariants.py` 强制 INV-1/3/5；claim 同事务复核；构建 attempt 围栏统一；审计降为兜底。见 task-runtime-contract §7 |
| A5 | ~~普通 AI Run 持久性语义落产品面~~ | **已定「承诺会丢」**；UI/文档标注改由 **WS-G7** 承接，不在任务运行时内做可恢复 Run | — |

**硬约束**：SQLite 分支语义字节级维持；PG 同事务 `SKIP LOCKED` 形态已实测（8 worker 14.7x），迁移时不得退回跨事务 CAS；`skip_locked` 只允许出现在租约服务。

**已关闭、不要重做**：claim 时序收口（CP3/CP4）、写重试统一（CP1b）、事务原语命名（CP2）、部署 profile（CP5）、`ai-external-task-coordinator` 单一续跑路径。

---

## 3. WS-B · 死物清理 + 架构测试进门禁（**已实施，2026-09-29**）

**问题**（结构批判 §4.2–4.4）：假安全感与门禁错位，成本极低、误导极大。

| 序 | 工作项 | 完成口径 | 状态 |
| :--- | :--- | :--- | :--- |
| B1 | 删 `backend/app/services/page_render_*_script.py` 7 份已漂移死副本（约 65KB，零 import） | 全仓 grep 无引用；Renderer 侧 `layout_scripts.py` 为唯一事实源 | **已完成**：7 份死副本已删；`page_render_diagnostics_service.py` 保留 |
| B2 | 修死契约测试 `runtime-kit-manifest.test.ts`（`capabilities` → `exports`） | 循环体真实执行，能红也能绿 | **已完成**：改为断言 `exports`，补非空清单与 `.vN` 命名契约 |
| B3 | `packages/render-contracts/schemas/*.v1.json`：补往返对拍测试，或删除死双源 | 二选一，禁止继续「文档声称对拍、实际零消费」 | **已完成**：新增 `test_schema_roundtrip.py`（required/type/enum 对拍 + DTO 往返） |
| B4 | 把架构级测试推进 PR 阻塞层：`test_unified_tool_specs_*`、render-contracts 往返、runtime-kit `exports` 真断言、多租户越权矩阵 | 进 `test:backend:unit` 或独立 gate job，不再只在 `inputs.full` | **已完成**：工具规格主测迁至 `tests/unit/test_unified_tool_specs.py`；contracts/render-contracts 本就在 PR；补跨用户 AI 工具写入矩阵 |
| B5 | 顺手：`test:repository` / `test:contracts` 文档断链保持绿（归档移动后复核） | 两入口全绿 | **已完成**：两入口 13+35 全绿 |
| B0 | 启用 branch protection / ruleset（评估 P0-MergeGate） | require PR + required checks | **已完成**：`main`/`dev` 均启用 classic protection（1 审 + `quality` check） |
| B-ClaimGate | CP4 认领门禁 AST 补强（评估 P0-ClaimGate） | 捕获变量间接 `execute(update)` 与 `reserve_*` 命名 | **已完成**：检测器补强；`claim_next_pending_job` 迁至 `claim_rows_by_cas`；`reserve_attempt` 登记例外 |
| B-AuthZ | 跨用户 AI 工具写入矩阵（评估 P2-AuthZGap） | A 用户不得写 B 用户实体 | **已完成**：补 `test_cross_user_ai_tool_write_should_be_denied`；写路径增加操作者成员校验 |

**WS-B 证据**：删除 7 份死副本；`runtime-kit-manifest.test.ts` 5 条真断言；`packages/render-contracts/tests/test_schema_roundtrip.py`；`backend/tests/unit/test_unified_tool_specs.py`；`test_ai_generic_business_tools.py::test_cross_user_ai_tool_write_should_be_denied`；`test_db_adapter_layer.py` 假阴性对照；GitHub branch protection `main`/`dev`。

---

## 4. WS-C · 多部署 / 多副本门槛补齐

**问题**：T0–T4 代码已落地，但评审认定的门槛多数未达成；分布式模板副本数=1，**不得标记为可用**。C1–C3 / 多数 Major 已修，下列仍开放。

| 序 | 工作项 | 来源编号 | 完成口径 | 估时 |
| :--- | :--- | :--- | :--- | :--- |
| C1 | 代码侧 Run owner 过滤（现仅文档如实描述全局收敛） | M8 | 代码与文档一致，或明确降级承诺 | **已完成（2026-09-29）**：`ai_agent_runs.process_owner` + 启动按本机死进程/无主策略收敛；不碰其它副本。见 task-runtime-contract §6.3 |
| C2 | 检查指纹三处缺口：资源 / 组件主题 / 编译器版本 | M11 | 指纹覆盖三者，缓存不再返回陈旧检查结果 | **基本完成（2026-09-29）**：资源身份 token + 组件默认主题色板 + Kit 清单内容 hash；Runtime 副本 Vite/镜像版本回报并入指纹归 **C6** |
| C3 | preview 角色独立预算与调度（当前变量全是死配置） | #14 | plan 硬门槛：容器约束 + 内部执行预算配套 | 2–3 天 |
| C4 | preview 健康输出排队年龄与活跃数 | #15 | `/readyz` 或 metrics 可读 | 0.5 天 |
| C5 | 归档峰值内存移出主进程 | #16 | 归档 worker 子进程内存计入子进程 | 1 天 |
| C6 | 版本指纹强制（当前只报告） | #17 | 不匹配时拒绝或降级有明确策略 | 1 天 |
| C7 | `can_safely_remove_worker` 接入真实摘除路径（现为死代码） | #18 | 摘除前核对有可执行保证 | **已完成（2026-09-29）**：`check_render_worker_removal` CLI 门禁 + compose.md 指引 |
| C8 | T0-1 六阶段指标补 `workspace` 计时、统一 `archive` 口径、失败/超时计数 | #19 #20 | 指标可对账 | 1 天 |
| C9 | **§11 跨副本回归与故障演练**：两预览 / 两构建检查 / 两 Renderer、强制跨副本子请求、实例重启与摘流 | plan §11 | 演练记录入库；未过则模板仍标「单副本」 | 2–3 天 |
| C10 | AGENTS.md 全面同步：Runtime 角色、构建 attempt 围栏、检查指纹缓存、签名密钥环 | #13 | 与代码一致 | **已完成（2026-09-29）**：多部署约束小节写入 AGENTS.md |
| C11 | §4.2 Minor 清单批量处理（healthz、`sendHtml` 缺 `no-store`、票据校验欠规格等） | 评审 §4.2 | 建议并入 C 安全项一起做 | **安全三项已完成（2026-09-29）**：`sendHtml` no-store/Referrer-Policy、JWT RS256+exp、healthz 公网最小化；其余 Minor 视需要另开 |

**禁止事项**：在 C9 通过前，`compose.runtime-roles.yml` 不得宣称多副本可用；不得把「代码已落地」写成「门槛已达成」。

---

## 5. WS-D · D2 写路径与容量基线

**问题**：现行评估 **D2 写路径基线门仍待实测**（与 claim 竞争基线不是同一件事）。打点入口 `db/metrics.py` 已就绪，采集未执行。

| 序 | 工作项 | 完成口径 | 估时 |
| :--- | :--- | :--- | :--- |
| D1 | Lite 2C4G 两轮基线：空闲 + 混合负载；读 `/metrics/db-write` | 锁等待、队列年龄、P50/P95、RSS/OOM 成文 | 1–2 天 |
| D2 | 真实 `busy_timeout` 风暴联调（写重试对拍的遗留） | 双库在风暴下写路径可解释、可恢复 | 1 天 |
| D3 | 构建成功产物在 Lite 真实容器可下载（`memory://` 计划未覆盖项 2） | E2E 或 drill 覆盖成功下载路径 | 1 天 |
| D4 | 不同宿主资源基线复测入口（未覆盖项 3） | 文档写明换机型需重跑的命令 | 0.5 天 |
| D5 | 两阶段校验耗时拆分基线 | 有数字；「删编译省 50%」继续作废 | 1 天 |

产出直接回填：WS-A 的 sleep/租约参数、WS-G 的 Lite 规模承诺、D1 方言成本预算。

---

## 6. WS-E · 跨端契约机械化

**问题**（结构批判 §4.2 / 现行评估 P2-API）：`editor/src/types/api.ts` 170 个手写 interface；previewSchema 三份手写；内外双入口无契约矩阵；根契约测试大量 `toContain` 子串匹配。

| 序 | 工作项 | 完成口径 | 估时 |
| :--- | :--- | :--- | :--- |
| E1 | 双入口对拍（Top 操作先行：页面读写、校验、预览、归档） | 契约矩阵文档 + 自动化对拍，不要求全矩阵 | 3–5 天 |
| E2 | 从 `/openapi.json` 生成 `editor/src/types/api.ts`（或等价 codegen） | 手写镜像层删除或降为生成物 | 1 周 |
| E3 | previewSchema 抽单一源，三端引用 | 三处手写收敛为一处 + 对拍 | 3–5 天 |
| E4 | HTTP 状态映射并入契约包（消灭 `rendering/errors.py` 第二事实源） | 错误码单源 | 2 天 |
| E5 | Runtime Kit 构建端第二道闸（manifest 白名单解析，拒绝 `internal/`） | Backend 写路径 + Runtime 构建端双侧强制；删或消费 `runtime_kit_exports` 死配置 | 2–3 天 |

---

## 7. WS-F · AI 巨石与分层拆分

**问题**（结构批判 §4.5 / 现行评估 P2-GodFiles）：`platform_runtime.py` 2067 行、`session_facade_pydantic.py` 1687、`page_mutation_queue.py` 1384、`asset_service.py` 1336；`ai ↔ services` 双向耦合；仓储层名存实亡。

| 序 | 工作项 | 完成口径 | 估时 |
| :--- | :--- | :--- | :--- |
| F1 | `platform_runtime.py` 按持久化 / 事件投影 / SSE / 锁拆分 | 单文件职责单一；WS-A 迁移面下降 | 1 周 |
| F2 | `session_facade_pydantic.py` 拆分 | 同上 | 3–5 天 |
| F3 | 依赖方向门禁：禁止 `services/` import `app.ai` 新增、路由层直查 ORM | AST/导入门禁 + 清单 | 2–3 天 |
| F4 | Editor：`AssetsView` / AI 侧边栏按域拆分；状态三轨收敛 | 可测性恢复；**不挡正确性** | 1–2 周 |

F1–F2 建议在 WS-A 契约冻结后、队列迁移前做，避免在 1800 行文件里改运行时。

---

## 8. WS-G · Lite / 生产加固

**问题**（结构批判 §5.5 / 现行评估 P1-Lite、P1-Health、P2-Dialect）。

| 序 | 工作项 | 完成口径 | 估时 |
| :--- | :--- | :--- | :--- |
| G1 | Lite 故障域评估与承诺文档化（Backend+Runtime+Nginx 同容器）；**含 H2a 推荐规模：5–10 人、预览并发约 3** | 先写清「合并故障域」+ 规模承诺，再决定是否拆容器 | 2 天 |
| G2 | `/readyz` 或 metrics 暴露 loop 队列年龄 / 租约年龄（P1-Health）；按 H2 规模给观测口径 | 积压可观测 | 1 天 |
| G3 | 密钥治理：去掉 `.env.example` 真实格式密钥、弱默认口令、compose 密钥内联 | secrets 化 + 启动拒绝占位密钥（部分已做，补齐） | 1–2 天 |
| G4 | PostgreSQL 备份/恢复脚本与演练（现仅 SQLite demo） | 恢复能力可验证 | 2 天 |
| G5 | Renderer 网络隔离（现同 bridge + Playwright route 拦截） | 容器级隔离或明确风险接受 | 2–3 天 |
| G6 | **D1 方言预算与复审触发器**写入治理文档（口径见评估 §3，2026-09-28 从宽已定）+ 每季粗记账模板 | 超预算才重开 D1；日常双方言不计入超支 | 0.5 天 |
| G7 | **H1a/H1b Run「会丢」标注**：Agent 会话/Run 状态提示 + 用户文档持久性说明 | 用户能区分「Run 会丢」与「external 任务可恢复」 | 1 天 |

> **专项输入（2026-09-29，规划/未实施）**：G1 的镜像层事实、G3 的渲染凭证自动生成、G5 的「容器内 root 启动 Chromium」前置验证，已单独成文——证据见 [`../image-delivery-research-2026-09-29.md`](../image-delivery-research-2026-09-29.md)，工作项见专项子计划 [`./deployment-image-consolidation-2026-09-29.md`](./deployment-image-consolidation-2026-09-29.md)（IMG0–IMG12、决策 D-Img1）。**G1 的「再决定是否拆容器」在动手前先读调研 §7.3（边界的三个层级）与 §9（已被推翻的论点，含体积与故障域两条）**；已发布的 lite 镜像实测 645.4 MiB 且自带 225.3 MiB 浏览器层，而 `deploy/compose/` 全部 5 个模板引用的 renderer 镜像从未发布、当前不可拉取。

---

## 9. WS-H · 产品决策（**已全部拍板，2026-09-28**）

| # | 决策 | 结论 | 转成的工程项 |
| :--- | :--- | :--- | :--- |
| H1 | 普通 AI Run 丢失语义 | **承诺「会丢」**。不立项可恢复 Run；进程退出/重启导致的 Run 中断是产品接受的边界 | **H1a** UI/帮助文案标明「AI 长任务在服务重启后可能中断，不自动续跑」（会话/Run 状态处）；**H1b** 用户文档补「持久性说明」（Run 会丢 / external 任务可恢复）。原 WS-A5 关闭 |
| H2 | Lite 推荐规模 | **5–10 人小团队，预览并发约 3**（项目规模：常规演示文稿工作区，非海量资产库） | **H2a** 用户/Lite 部署文档写入推荐规模与并发承诺；**H2b** 与 WS-G1/G2 对齐：容量阈值、`/readyz`/metrics 按此规模给观测口径 |
| H3 | 双库方言维护预算 | **从宽**（兼容代价预算放大）。正常双方言成本为固定税；触发器见评估 §3：单季计入 >12 人周，或连续两季 >8 人周/季，或方言阻塞发版 ≥3 次/季，或放弃 Lite 一等公民 | **H3a**（即 WS-G6）把预算与复审触发器写入治理文档；每季粗记账 |
| H4 | ~~截图缓存策略~~ | **已定（2026-09-25）**：现状可接受 | 仅低成本顺手硬化，不进优先级 |

---

## 10. 产品可接受残留（不进计划，仅登记）

| ID | 问题 | 处理 |
| :--- | :--- | :--- |
| R-Screenshot | 截图指纹不含环境身份；升级后可复用旧图 | 产品接受。可选：发布说明提示手动刷新。 |
| R-Profile | `profile.v1` 手填 | 同上；多副本/缓存强一致成为目标时再开。 |
| R-CP5 | SQLite `memory://` + `BACKEND_MULTI_INSTANCE=true` 不被拓扑拒绝 | 非真实部署形态；保持已知残留。 |
| R-CP6 | 事件追加进程锁保留 | PostgreSQL 不可跳过（保护同一 AsyncSession），与方言无关。 |

---

## 11. 建议排期（两迭代）

**迭代 1（本周起）**

1. ~~WS-B 全部（死物 + 门禁）~~ **已清（2026-09-29）**
2. ~~WS-A1 契约冻结草案~~ **已完成（2026-09-29）**：`docs/developer/architecture/task-runtime-contract.md`
3. WS-D1/D3/D5 基线采集 — 可并行
4. ~~WS-H 产品拍板~~ **已定（2026-09-28）**；H1a/H1b/H2a/H2b 并入 WS-G7 / G1 / G2
5. WS-C 安全与正确性项：C1、C2、C7、C11（含 `no-store`/票据）
6. WS-G7 Run「会丢」UI/文档标注 + WS-G1/G2 规模承诺（小，可本周）

**迭代 2**

1. WS-A2 统一执行器 + WS-A3 先迁构建/截图队列（与 WS-F1 并行拆 `platform_runtime`）；契约与迁移口径见 [`docs/developer/architecture/task-runtime-contract.md`](../../developer/architecture/task-runtime-contract.md)
2. WS-C 其余门槛 + C9 跨副本演练（不过则继续标单副本）
3. WS-E1 双入口 Top 操作对拍
4. WS-G3/G6 密钥与方言预算

---

## 12. 与现行评估的对应（[`../architecture-assessment-2026-09-28.md`](../architecture-assessment-2026-09-28.md)）

| 现行评估 ID | 归属工作流 | 状态 |
| :--- | :--- | :--- |
| P1-TaskModel | WS-A | claim 子集已收口，运行时未统一 |
| P1-Run | WS-G7（原 WS-A5/H1） | **已定承诺「会丢」**；待 UI/文档标注 |
| P1-Build | WS-A3（构建队列优先迁） | T2-2/CP4 已加固，方言仍在 |
| P1-Lite | WS-G1 + WS-D | 规模承诺 **5–10 人/并发 3**；故障域与混合负载未验收 |
| P1-Health | WS-G2 | 待做 |
| P2-Dialect | WS-G6 + WS-D | **预算已定（§评估 4.1）**；待写入治理文档 |
| P2-API | WS-E | 待做 |
| P2-GodFiles | WS-F | 待做 |
| P2-Locks | 登记为 R-CP6 | 定位澄清已写入文档 |
| P2-Docs | 本次整理 | README 与正文状态已对齐；维护约定见 README |
| D2 基线门 | WS-D | **仍未采集** |
| 结构批判 P0 死物/门禁 | WS-B | **已清（2026-09-29）** |
| 结构批判 P0 双记账 | 已收敛续跑双轨；统一 runtime 见 WS-A | 部分关闭 |
| P0-MergeGate / P0-ClaimGate / P0-Gates / P2-AuthZGap | WS-B0 / ClaimGate / B4 / AuthZ | **已关闭（2026-09-29）** |

---

## 13. 维护约定（承接 README）

1. 本文是**现行计划**；单项完成后在对应表就地勾选并写证据提交，不新开完成清单。
2. 某工作流整体完成后，把该节移入 `archive/`（或拆出实施记录），并在 README 降级。
3. 新发现的未覆盖项追加到对应工作流表格，**不得**因「大项已交付」被吞掉。
4. 产品决策（WS-H）**已全部落地（2026-09-28）**并写入现行评估决策表；后续只跟进 H1a/H1b/H2a/H2b/H3a 工程项，不再重开决策（除非产品主动改口径）。
