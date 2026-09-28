<!-- 文件功能：docs/temp 2026-09-28 整理合并稿（含对 09-25 两稿的过期修正），已归档。 -->
# 架构评估（合并整理稿）：任务模型主轴确立之后（2026-09-28）

> **归档说明**：本稿为「合并 09-25 两稿 + 标过期实现层」的整理版本，已归档。**现行评估**只看 [`../architecture-assessment-2026-09-28.md`](../architecture-assessment-2026-09-28.md)（现状与问题，不作历史对照）。

> **评估日期**：2026-09-28。基线提交 `2d7858b`（分支 `dev`）。  
> **定位**：历史合并整理稿。执行计划见 [`../plans/remaining-work-2026-09-28.md`](../plans/remaining-work-2026-09-28.md)。  
> **整理说明**：本稿合并两份 09-25 评估的**仍然成立**结论，并修正其**已过期实现层判断**（见 §1）。原稿整体归档，不在其上续写。  
> **判断口径**：代码可确认的问题与尚未验证的风险分开；「已实施」不等于「门槛已达成」；产品可接受残留（R-*）只登记不进优先级。

---

## 0. 一页结论

1. **执行面与并发收口的改造主轴已落地**，不必再争论方向：浏览器执行出 Backend（远程 Renderer + `render-contracts`）、Runtime 并入主仓、页面校验单一谓词、SQLite 单实例守卫、运行态 `memory://` 窄接口、DB 并发原语 CP1–CP6、多部署 T0–T4 代码批次、构建持久领取 + attempt 围栏。
2. **真正的结构性债务是任务模型碎片化（P1-TaskModel）**，不是「loop 节奏」。claim 时序已收口到 `durable_job_lease_service.claim_rows_by_cas`，但领取/租约/心跳/恢复/错误码仍是多方言并存。**P3 统一任务运行时是剩余架构工作的主轴**（现行计划 WS-A）。
3. **「已实施」≠「可承诺多副本 / Lite 混合负载」**。跨副本演练未跑、D2 写路径基线未采集、分布式模板副本数=1。对外承诺保持单实例。
4. **低成本高收益项是死物清理与门禁搬家**（WS-B，1–2 天）：7 份布局脚本死副本、死契约测试（`manifest.capabilities`）、JSON Schema 死双源、架构级测试不在 PR 阻塞层。这些制造假安全感，应先于大重构。
5. **产品三问已拍板（2026-09-28）**：Run **承诺会丢**；Lite **5–10 人 / 预览并发约 3**；双库方言预算**从宽**（§4.1）。工程跟进改为文档/UI 与容量承诺落地，不再阻塞架构项。
6. **推荐顺序**：WS-B 死物与门禁 → WS-A 契约冻结（与 WS-D 基线并行）→ WS-C 多部署门槛与演练 → WS-E 契约机械化 → WS-F 巨石拆分 → WS-G 加固。多副本承诺严格最后。

---

## 1. 相对 09-25 两稿的修正（哪些已过期）

### 1.1 已过期、以本稿为准

| 09-25 旧判断 | 现状（`2d7858b`） |
| :--- | :--- |
| 构建仍走 `BackgroundTasks`，**根本没有租约**（平台演进稿 §1.2 / P1-Build / 架构快照） | **过期**。T2-2（`e156630`）+ CP4（`ccc8a18` 系列）后，`ProjectBuildJob.claim_job` 走 `claim_rows_by_cas`，有租约、attempt 围栏、过期回收。方言仍在，但不再是「无租约」。 |
| `runtime-multi-deployment-scaling-plan` 仍是未实施规划 | **过期**。T0–T4 已落地，C/M 多数已修；**门槛与跨副本演练未达成**，见 §3 / WS-C。 |
| `docs/temp` README 与计划状态漂移（lite-memory-adapter 写「未实施」） | **已修复**（2026-09-28 整理）。 |
| P1-Build 是 9 套方言里**最弱**的一套 | **过期**。最弱者已加固；最弱者更接近「进程内 AI Run」（P1-Run）或仍无 attempt 的长任务。 |
| 优先序第 3 项「构建持久领取」待做 | **已完成**，从优先序删除。 |
| 结构批判稿 §4.1「两套续跑路径」 | **已收敛**（该稿 09-25 已自注）；统一为 `ai-external-task-coordinator` → `AiAgentExternalBatch`。双记账（同一工作单元两套状态机）**仍在**。 |

### 1.2 仍然成立、继承自两稿

| 结论 | 来源 | 说明 |
| :--- | :--- | :--- |
| P3 统一任务运行时是主轴 | 平台演进稿 §0.4 / 结构批判 P0 | claim 子集收口**不关闭**此项 |
| D1=A 永久税，需成本预算与复审触发器 | 平台演进稿 §1.2-3 | 见 §4 决策表 |
| D2 写路径基线仍待实测，不挡 P3 设计 | 平台演进稿 | CP 的 claim 基线**不是** D2 |
| 死契约 / 死副本 / 门禁错位 | 结构批判 §4.2–4.4 | 已核实：`page_render_*_script.py` 仍在；`manifest.capabilities` 空转测试仍在 |
| 跨端契约纸面化、previewSchema 三份 | 结构批判 §4.2 | → WS-E |
| AI 巨石与 `ai↔services` 耦合 | 结构批判 §4.5 / P2-GodFiles | → WS-F |
| 截图环境身份产品可接受 | 平台演进稿定案 09-25 | R-Screenshot，非门禁 |
| 「删编译省 50%」「纯内存租约」「内外 API 机械合并」作废 | 平台演进稿 | 维持作废 |
| Browserless/CDP 作废 | 各稿一致 | 维持 |

---

## 2. 架构快照（2026-09-28 修正版）

```text
Editor (Vue) ──HTTP──► Gateway ──┬──► Backend (FastAPI 控制面)
                                 │       ├─ 领域服务 / AI Run（进程内）/ 工具规格
                                 │       ├─ 任务执行（多方言，claim 时序已收口）
                                 │       ├─ render_requests → RenderCoordinator
                                 │       └─ SQLite(单实例锁) | PostgreSQL
                                 │           + memory:// | redis://（窄接口）
                                 │
                                 ├──► Runtime (Vue3+Vite)
                                 │       预览 / 构建 / 编译诊断 / 视觉编辑
                                 │
                                 └──► Renderer (单槽 Chromium)
                                         packages/render-contracts

任务持久性（修正：构建已有租约）：
  durable + lease： external_batch / page|component mutation / image / screenshot
                    / backfill / render_request / ProjectBuildJob（T2-2+CP4）
  非持久：          普通 AI Run（进程内，重启 AI_RUN_PROCESS_STOPPED）
  仍待统一：        上述 durable 任务的领取/恢复/错误码多方言（P1-TaskModel）
```

| 边界 | 约束 | 锁强度 |
| :--- | :--- | :--- |
| 浏览器执行 | 只在 Renderer | 代码 + 配置拒绝旧 Playwright env |
| 校验通过 | 唯一谓词 `validation_result` | 单定义门禁 |
| SQLite | 文件库单进程/单容器 | 排他锁 + worker 数拒绝 + `BACKEND_MULTI_INSTANCE` 拒绝 |
| 运行态 | 业务只走窄命令 facade | 静态门禁禁 raw redis / `.client` |
| 认领时序 | `claim_rows_by_cas`；方言分支只在 `app/db/` | AST 门禁 |
| 普通 AI Run | 进程内，不承诺重启恢复 | **产品已定承诺「会丢」**；UI/文档待标注（WS-G7） |
| 截图身份 | 环境版本可不进指纹 | **产品接受** |
| 任务模型 | 应统一运行时 | **未锁**（多方言） |
| 多副本 | Lite 禁；分布式模板副本=1 | **不得宣称多副本可用** |

---

## 3. 仍在风险

### 可接受残留（登记不进优先级）

| ID | 问题 | 处理 |
| :--- | :--- | :--- |
| **R-Screenshot** | 截图指纹不含环境身份 | 产品接受。可选发布说明提示手动刷新。 |
| **R-Profile** | `profile.v1` 手填 | 同上；多副本/缓存强一致时再开。 |
| **R-CP5** | `memory://` + `BACKEND_MULTI_INSTANCE` 不被拓扑拒绝 | 非真实部署形态。 |
| **R-CP6** | 事件追加进程锁保留 | PostgreSQL 不可跳过（同会话并发），与方言无关。 |

### P1 — 可用性与承诺边界

| ID | 问题 | 状态与出口 |
| :--- | :--- | :--- |
| **P1-TaskModel** | 任务模型碎片化 | **主轴**。claim 已收口；运行时未统一 → WS-A |
| **P1-Run** | 普通 AI Run 绑进程 | **产品已定：承诺「会丢」**；缺口改为 UI/文档如实标注 → 文档项 |
| **P1-Lite** | Lite 故障域合并、混合负载未验收 | → WS-G1 + WS-D |
| **P1-Health** | 队列/租约积压无对外指标 | → WS-G2 |
| **P1-MultiDeploy** | 多部署门槛未达成、跨副本演练未跑 | T0–T4 已落地但不得承诺多副本 → WS-C |

### P2 — 成本与维护性

| ID | 问题 | 出口 |
| :--- | :--- | :--- |
| **P2-Dialect** | 双库方言永久税 | → WS-G6 预算与复审触发器 |
| **P2-API** | 内外双入口无契约矩阵 | → WS-E |
| **P2-GodFiles** | AI 巨石 / 上帝文件 | → WS-F |
| **P2-Locks** | 进程内锁表 | 登记 R-CP6，不作扩展原语 |
| **P2-DeadGoods** | 死契约、死副本、门禁错位 | → WS-B（**先做**） |
| **P2-Docs** | docs/temp 第二事实源漂移 | **本轮已收口**；维护约定见 README |

---

## 4. 决策状态

| 决策 | 状态 | 成本 / 复审 |
| :--- | :--- | :--- |
| **D1** SQLite Lite 地位 | **A：长期一等公民**（维持） | 永久税：双方言迁移、CI 双轨、Lite 禁多副本。**预算（2026-09-28 定）**见下「D1 方言预算」。产品放弃 Lite 一等公民 → 重开 D1 |
| **D1 方言预算** | **已定（2026-09-28）** | **从宽**：正常双方言迁移/测试/CI 双轨视为固定税，不计入超支。触发复审须同时偏高——见 §4.1 |
| **D2** 写路径基线门 | **仍待实测** | 降为节奏参数来源，不挡 P3 设计。采集 → WS-D。CP 的 claim 竞争基线**不能**代替 D2 |
| **Lite 运行态 `memory://`** | **已实施** | 残留：构建产物下载、跨宿主基线 → WS-D |
| **Lite 推荐规模** | **已定（2026-09-28）：5–10 人小团队，预览并发约 3** | 写入用户承诺与容量说明 → WS-G1/G2 |
| **多部署 T0–T4** | **代码已落地** | 门槛多数未达成；跨副本演练未跑；**禁止标记多副本可用** → WS-C |
| **DB 并发原语 CP1–CP6** | **已实施** | PG claim 8 worker 14.7x；不关闭 P1-TaskModel / D2 |
| **CDP/Browserless** | **已作废** | — |
| **截图准确度** | **已定：现状可接受** | R-Screenshot；多副本强一致时再开 |
| **正常 Run 丢失语义** | **已定（2026-09-28）：承诺「会丢」** | 不立项可恢复 Run；须在 UI/文档标明。工程跟进 → 文档/UI 项（原 WS-A5 关闭） |

### 4.1 D1 方言预算与复审触发器（2026-09-28 定，从宽）

| 项 | 口径 |
| :--- | :--- |
| **计入** | 因 SQLite/PG 方言差异产生的额外设计、分支实现、双方言测试/迁移证明、因方言踩坑的排查修复 |
| **不计入** | 正常业务功能在双库上跑通的成本；通用写重试/事务原语（`app/db/`）一次收口后的常规使用；纯 PG 优化 |
| **正常区间** | ≤ **8 人周/季** 不视为超支（从宽；日常预期远低于此） |
| **复审触发**（满足其一） | ① 单季计入 > **12 人周**；或 ② 连续两季计入 > **8 人周/季**；或 ③ 方言问题导致发版阻塞 ≥ **3 次/季**；或 ④ 产品放弃 Lite 一等公民 |
| **复审动作** | 重开 D1：评估（a）继续 A + 收缩 Lite 能力面、（b）Lite 降级为非承诺形态、（c）收敛 PG-only。**不**因一次尖峰就推翻 A |
| **记账** | 每季在开发文档记一次粗账（人周量级 + 阻塞次数即可），不逼精确到小时 |

---

## 5. 尚未验证（不可当作已有能力）

- **D2 容量基线**：SQLite 锁等待、队列年龄、P50/P95、混合负载 RSS/OOM。`memory://` 的运行态 2C4G 数据不能替代。
- **故障注入**：Renderer 全挂、Worker 掉线、busy_timeout 耗尽、构建进程被杀、滚动升级中断 Run。
- **多实例联调**：共享对象存储、密钥一致、迁移与租约跨实例、§11 跨副本演练。
- **Lite 成功构建产物可下载**。
- **两阶段校验耗时拆分**（「删编译省 50%」继续作废）。

---

## 6. 处理顺序

| 序 | 工作 | 为何 |
| :--- | :--- | :--- |
| 1 | **WS-B 死物清理 + 架构测试进门禁** | 小时级；先消灭假安全感 |
| 2 | **WS-A1 任务运行时契约冻结** | 主轴设计可先行 |
| 3 | **WS-D 基线采集**（与 2 并行） | 打点已就绪 |
| 4 | ~~WS-H 产品拍板~~ | **已定（2026-09-28）**；跟进项转入文档/UI 与 WS-G |
| 5 | **WS-C 多部署门槛 + 跨副本演练** | 不过则继续标单副本 |
| 6 | **WS-E 契约机械化**（Top 操作先行） | 降低人肉对齐 |
| 7 | **WS-F 巨石拆分**（宜在 A2/A3 前） | 降低 P3 迁移面 |
| 8 | **WS-A2/A3 统一执行器与队列迁移** | 主轴落地 |
| 9 | **WS-G Lite/生产加固** | 承诺文档化优先于拆容器 |
| 10 | 多副本对外承诺 | **严格最后** |

---

## 7. 与历史文档的关系

| 文档 | 位置 | 关系 |
| :--- | :--- | :--- |
| [`./architecture-assessment-2026-09-25.md`](./architecture-assessment-2026-09-25.md) | `archive/` | 平台演进复核稿。**实现层判断已过期**（§1.1）；决策与优先序主轴由本稿继承。 |
| [`./architecture-assessment-critical-2026-09-25.md`](./architecture-assessment-critical-2026-09-25.md) | `archive/` | 结构批判证据快照（量化基线、死物、门禁）。开放项仍有效，出口见本稿 §3 与 WS-B/E/F/G。 |
| [`../plans/remaining-work-2026-09-28.md`](../plans/remaining-work-2026-09-28.md) | `plans/` | **现行计划**（WS-A…H）。 |
| 其余 `archive/*` | `archive/` | 专项证据库；结论以本稿为准。 |

---

## 8. 附录 · 代码锚点（2026-09-28）

```text
backend/app/services/durable_job_lease_service.claim_rows_by_cas   认领时序单源
backend/app/services/project_build_service.claim_job              构建领取（已有租约/attempt）
backend/app/services/runtime_state/                               运行态窄接口
backend/app/services/validation_result.py                         校验唯一谓词
backend/app/db/{retry,tx,profile,sqlite_single_process}.py        方言收口边界
backend/app/ai/*_queue.py + external_task_queue.py                任务方言集合（待统一）
backend/app/services/page_render_*_script.py                      死副本（待删，WS-B）
tests/contracts/runtime-backend/runtime-kit-manifest.test.ts      死契约测试（capabilities）
```
