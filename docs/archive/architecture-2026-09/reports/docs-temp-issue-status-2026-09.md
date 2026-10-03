# docs/temp 问题状态总览（2026-09 梳理）

> 梳理日期：2026-09-23。输入为 `docs/temp/` 下四份文档；对照当前工作区代码、部署模板与开发文档核对。  
> 本文只做状态归类与证据对齐，不替代任何设计文档，也不构成发布验收记录。

## 0. 四份源文档定位

| 文档 | 日期 | 性质 | 现在怎么用 |
| :--- | :--- | :--- | :--- |
| `architecture_review_report.md` | 2026-09-08 | 首轮架构/质量评审 | **部分过时**。浏览器外移、渲染远程化已落地后，若干判断不再适用；代码气味与双入口成本仍有参考价值。 |
| `architecture-assessment-2026-09.md` | 2026-09-23 | 对首轮报告的复核 + 当前风险清单 | **现行问题清单的主要来源**。P0/P1/P2 仍基本成立，个别细节已随代码变化需小幅修正。 |
| `cdp.md` | 2026-09-09 | Browserless / CDP 多用户横向扩展**方案** | **未实施的规划**。当前 Renderer 仍是本地 `chromium.launch()`，无 Browserless/CDP。 |
| `runtime-multi-deployment-scaling-plan.md` | 2026-09-23 | Runtime 多部署形态与扩容**规划草案** | **未实施的规划**。角色拆分、预览无状态化、构建持久领取均未开始。 |

下文按「已解决 / 仍在 / 文档外 / 不成立」四类归拢问题，而不是按源文档逐条复述。

---

## 1. 已解决（代码可确认）

| 问题 | 原出处 | 证据 |
| :--- | :--- | :--- |
| Backend 内嵌 Chromium / `PlaywrightBrowserPool` 与 API 同进程 | 首轮缺陷 1/2 | 已删除。`backend/app/main.py` 启动 `RenderCoordinator`；截图与页面诊断走 `render_requests` → 远程 Renderer。旧配置会被启动拒绝（`test_render_settings_reject_legacy_playwright_env`）。设计摘要见 `docs/developer/backend/remote-render-service-design.md`。 |
| 浏览器崩溃直接拖垮 Backend 进程 | 首轮缺陷 2（部分） | Renderer 已是独立容器（四套 Compose 均有 `renderer`）。Chromium OOM 不再杀 Backend。 |
| 组件远程渲染诊断混入内容助手校验 | 评估隐含边界 | 组件校验明确只做「契约 + Runtime 编译」；远程渲染诊断保留在协议层但不进入内容助手链路（`component_validation_service.py` 注释与 `resource-queues.md`）。 |
| Agent Store 树状 + 扁平映射双向同步（`syncFlatMaps` / `hydrateSessionFromFlatMaps`） | 首轮代码气味 2 | **已消除**。`editor/src/stores/agent-session.ts` 现为按会话分片的单一状态（`runtime` + `ui`），全文 234 行，无双向搬运。 |
| `AgentConversationPanel.vue` 2407 行巨石 | 首轮代码气味 1 | **部分拆解**：2407 → 1080 行，并抽出 `AgentConversationBody.vue`、`agent-conversation-panel.ts`、`agent-run-state.ts` 等。仍偏大，但反模式主因已去。 |
| 渲染失败被归类为「源码错误」 | 评估 P0 表述的一部分 | 基础设施故障已拆出：`PageRenderDiagnosticsService._build_unavailable_result` 返回 `status=unavailable / retryable / warning`，`test_page_unavailable_is_not_content_error` 等测试覆盖。 |
| **页面校验在 Renderer 不可用时仍 `passed` 并落库（原 P0）** | 评估 P0 / 本文旧 §2 P0 | **已修复（2026-09-24）**。`code_check_service._append_page_render_diagnostics` 现按 `_render_stage_status` 改写顶层 `success/status/retryable`，并输出 `stages={compile,render}`；`services/validation_result.py` 成为唯一通过判定谓词（`is_validation_passed` / `is_render_unavailable` / `resolve_write_gate`），页面写工具与 planner 全部改用它。跨阶段契约测试已补齐：`test_page_code_check_render_unavailable_must_not_report_passed`、`test_create_project_page_should_reject_when_render_unavailable`、`test_validate_entity_render_unavailable_must_not_report_valid`、`test_plan_apply_edits_should_reject_render_unavailable`。异步任务错误码区分 `RENDER_SERVICE_UNAVAILABLE`（可重试）与 `PAGE_VALIDATION_FAILED`（终态）。 |
| Backend 无 readiness 探针 | 本文旧 §2 P1-Health | **已补 `/readyz`**（数据库可连通 + 渲染 Worker 已配置），lite compose healthcheck 已接入；`/healthz` 保持纯 liveness。有意**不**探测 Renderer 存活，避免外部抖动把 Backend 打成 not_ready。 |
| SQLite 文件库可被多进程/多容器同时写 | S1 / Lite 边界 | **已加启动守卫**：`db/sqlite_single_process.py` 取 `*.single-process.lock` 排他锁，并拒绝 `WEB_CONCURRENCY`/`UVICORN_WORKERS` > 1。守卫在 lifespan 而非 `create_app()` 中获取——`main.py` 底部有模块级 `create_app()`，导入期抢锁会让任何 `import app` 的脚本/测试失败。 |
| 组件 Runtime 不可用被当成通过 | 类比 P0 | 组件侧正确：编译异常时 `success=false / status=unavailable / retryable=true`（`component_validation_service.py`），`_is_validation_passed` 不会放行。 |
| 单容器内 Chromium + 业务同故障域 | 首轮缺陷 2 | 轻量版已是 `platform-lite` + 独立 `renderer` 两容器；不能再写成「四进程含浏览器同容器」。 |

---

## 2. 仍在的问题（按优先级）

### P0 — 可能把失败报成成功

**已全部关闭。** 原 P0「页面校验在 Renderer 不可用时仍可能 `passed` 并落库」已于 2026-09-24 修复，事实链与证据见 §1。收口要点：

- 单一判定谓词落在 `services/validation_result.py`；`_is_validation_passed` 的三份拷贝（`project_pages` / `apply_page_edits` / `component_library`）与 `code_check_service._is_runtime_diagnostics_passed` 均已删除，`test_validation_predicate_definition_is_single` 门禁全仓只允许一处定义。
- 阶段结论 `stages={compile,render}` 成为契约的一部分，`resource-queues.md` 与 `remote-render-service-design.md` §10.2 已同步。
- `skip_visual_verification` 是**显式逃生口**：仅在 render=`unavailable` 且编译已通过时放行，并在 job result 与 AI 事件中留 `skipped_visual_verification` 审计标记；`tool_specs.py` 的 page create/update `error_recovery` 已写明使用条件（默认拒写、先重试、不得据此重写源码）。

### P1 — 发布与可用性边界

| ID | 问题 | 状态摘要 |
| :--- | :--- | :--- |
| P1-Run | 普通 AI Run 绑定 Backend 进程 | **仍在，且已是明示约束**。`background_run_manager` 进程内 `asyncio.Task`；退出写 `AI_RUN_PROCESS_STOPPED`（`run_recovery.py`）。不能宣称无状态控制面或滚动升级无中断。 |
| P1-Screenshot | 截图「当前」判断不含 Runtime/Renderer/字体环境版本 | **仍在**。`page_screenshot_fingerprint_service` 只哈希页面尺寸、主题与字体修订等配置；`RENDER_PROFILE_DIGEST` 全库默认 `profile.v1`，是运维标签不是内容摘要。镜像升级后旧截图仍可能被复用。 |
| P1-Lite | 轻量版资源与故障域仍合并 | **仍在**。`platform-lite` 同容器跑 Backend + Runtime Vite + Nginx；任一子进程退出触发整平台退出（`start_lite`）。Renderer 已隔离，但内存预算与故障域未拆。无 2C4G 混合负载实测。 |
| P1-Health | 存活探针不反映调度链路 | **部分解决**。Backend 已有 `/readyz`（数据库可连通 + 渲染 Worker 已配置），lite compose healthcheck 已接入；`/healthz` 仍是有意的纯 liveness。**仍在**的部分：`/readyz` 不探测 Renderer 存活（有意为之，避免外部抖动导致 not_ready），因此「Renderer 全挂但 Backend ready」仍然可能；调度链路各 loop 的健康仍无可观测出口。 |
| P1-Build | 项目构建派发依赖 FastAPI `BackgroundTasks` | **仍在**（评估未单列，扩容规划已指出）。`build_jobs.py` 用 `background_tasks.add_task`；进程故障后任务接管与迟到结果处理不足。 |

### P2 — 成本与维护性

| ID | 问题 | 状态摘要 |
| :--- | :--- | :--- |
| P2-Queue | 持久化调度空闲写放大 | **部分收敛，仍需量化**。已做：终态清理 / `expire_requests` / `_promote_due_provider_jobs` 改为「先探测命中集、空闲态不发 UPDATE」；渲染 Worker 心跳 5s 节流；`synchronize_external_task_states` / `audit_external_state_consistency` 空闲不 commit；图片队列租约与轮询间隔配置化；`db/metrics.py` 写路径打点（默认关闭）+ `/metrics/db-write`。**未做**：13 条循环的轮询频率本身未收敛（`test_loop_gate.py` 只登记白名单、禁止新增亚秒循环）；SQLite busy 判据已合并为 `db/errors.detect_transient_write_conflict` 单点，但 4 套重试循环仍各自实现（P2-2b 已裁剪，理由见 `architecture-assessment-sqlite-2026-09.md` §6.3.1）。仍无「频繁 database is locked」实测证据 ⇒ §6.2 决策门 D2 未触发。 |
| P2-API | 内外 API 双入口维护成本 | **仍在，但重复被首轮夸大**。内部 `/api` 与 External `/api/v1` 共用 `PageService` / `MutationJobService` 等领域服务；差异在认证、幂等、202 任务语义与错误码。仍缺「同一操作两入口」契约矩阵。 |
| P2-Locks | 进程内全局锁/订阅表 | **仍在**。`platform_runtime._SUBSCRIBERS` / `_RUN_EVENT_LOCKS`、`session_facade_pydantic._run_locks`。SSE 有序列号 DB 回放兜底，跨进程「事件立刻失效」被夸大；真正限制是普通 Run 执行生命周期。 |
| P2-GodFiles | 超大文件 / 上帝类 | **部分改善，远未收敛**。后端 ≥1000 行仍有 10 个；Editor 还有 `AssetsView` 1791、`PageDetailView` 1422、`PagesView` 1410 等。AGENTS.md 要求「控制行数」并优先拆分，并非「1000 行硬门禁 = 性能结论」。 |
| P2-Profile | `profile.v1` 写死在所有 Compose/示例 | **仍在**。与 P1-Screenshot 同根：发布身份未自动生成、未强制一致（仅有 env 一致性检查脚本）。 |

---

## 3. 文档外的问题（本轮核对新发现或未入清单）

1. **实现与已文档化契约不一致（P0 的伴生问题）**  
   `resource-queues.md` / `remote-render-service-design.md` 已写清「不可用 ≠ 通过」，组件侧也做到了，页面合并层没做到。这是契约漂移，不只是缺测试。

2. **`_is_validation_passed` 多份拷贝**  
   至少 `apply_page_edits.py`、`project_pages.py`、`component_library.py` 各有一份，语义都是 `success is True or status == "passed"`。页面/组件/工具/规划器改判定时极易漏改一处。

3. **超大文件范围比首轮清单更宽**  
   首轮点了 5 个文件；实际后端 ≥1000 行还有 `page_mutation_queue.py`(1418)、`asset_service.py`(1336)、`component_share_package_service.py`(1334)、`ai_llm_service.py`(1141)、`business_tools.py`(1112)、`agents.py`(1094)、`tool_specs.py`(1064)。Editor 则是视图层普遍超限，不只是 `AssetsView`/`AgentConversationPanel`。

4. **CLI 帮助策略与项目现行政策冲突**  
   首轮要求 `--help` 离线可用；但 `AGENTS.md` 现行规定是「CLI 请求契约失败直接报错，**不引入离线契约或缓存降级**」。体验问题可以提，但不能再当作「本仓 Backend 重构前置」或「必须内嵌 Schema」；若要改策略，应先改协作规范与 agent-kit 边界。

5. **容量/故障基线始终缺位**  
   首轮的「1.5GB / 延迟降 40% / 2C4G 流畅」与评估的验收门槛都依赖实测，至今没有可复现基线（队列年龄、RSS、OOM、SQLite 锁等待、P50/P95）。任何扩容或拓扑拆分决策都还不能用数据拍板。

6. **多实例发布一致性前提未满足**  
   扩容规划已列出（共享对象存储、签名密钥/JWKS、AI 凭证密钥、迁移与租约边界），现状仍是单 Backend 假设：Token 私钥本地文件、Lite 用 `memory://lite` 与 SQLite。这是「分布式」文案与真实能力之间的缺口。

7. **External API 与内部 API 仍缺防漂移矩阵**  
   页面读写已共享领域服务，但权限、版本冲突、错误码、字段含义的双入口对拍测试不完整；契约漂移风险还在。

---

## 4. 不成立 / 过时 / 表述过度的问题

| 原判断 | 为何不成立或需降级 |
| :--- | :--- |
| 「双重重度构建无意义，跳过 Node 编译可省 50%」 | **结论不成立**。编译与渲染失败集合不同；浏览器访问仍依赖 Runtime/Vite。50% 无基线。两阶段应保留，按真实耗时决定是否优化，不能删编译。 |
| 「SQL 租约队列应换成纯内存队列 + 固定租约」 | **不应照搬**。纯内存通知丢重启/跨实例唤醒；固定租约盖不住长模型/渲染步骤。SQLite 写放大值得测，但正确性事实源必须留在持久层。 |
| 「内外 API 是两套完全重复业务实现，应让 Editor 全改 `/api/v1`」 | **重复程度被夸大**。已共享领域服务；机械统一 URL 会把同步/异步事务语义混成一套。应先做契约矩阵，再合并相同行为。 |
| 「进程内事件字典使多实例 SSE 完全失效」 | **表述过度**。SSE 有按事件序号的 DB 轮询回放。真正不能跨进程的是普通 Run 模型执行栈。 |
| 「1000 行硬限制 / 行数证明性能问题」 | **不准确**。AGENTS.md 是「控制行数、职责过多优先拆分」；行数是复杂度信号，不是性能结论或重构完成标准。 |
| 「Phase 1 验收：总内存 &lt;1.5GB、诊断延迟降 40%」 | **未验证假设，不能当验收基线**。 |
| 「Backend 内 `PlaywrightBrowserPool` / 三容器替代含 Chromium 方案」 | **目标已过时**。浏览器已外移；该改造计划不能再当 roadmap。 |
| 「CLI 离线 Schema 是本仓 Backend 重构前置」 | **归属与策略都不对**。代码在 agent-kit；本仓现行规范明确不做离线契约降级。 |
| 「单容器 = Nginx+Vite+Uvicorn+Chromium 一死全死」 | **Chromium 部分已不成立**。Lite 仍是 Backend+Runtime+Nginx 同容器共享故障域，但不能写成含浏览器。 |
| 首轮三阶段 1–4 周排期与固定收益率 | **不宜直接当排期**。缺工作量、负载与故障数据；评估文档的决策顺序更合理。 |
| `cdp.md` 中 Browserless 多节点公平调度、会话隔离容量等 | **尚未发生的问题/能力**。当前无 Browserless；文档是目标方案，不能写成「现状缺陷清单」。 |
| 扩容规划中的 `runtime-preview/build/check` 角色、预览多副本、构建持久领取 | **规划项，非缺陷**。现状只有单 Runtime 角色；在角色拆分落地前谈「路由/亲和性 bug」不成立。 |

---

## 5. 规划类文档状态（cdp.md / runtime scaling）

### 5.1 `cdp.md`（Browserless CDP）

| 规划项 | 现状 |
| :--- | :--- |
| 移除 Backend 内嵌 Chromium | **已通过远程 Renderer 做到**（路径不同：本地 Chromium Worker，不是 Browserless）。 |
| 独立渲染 Worker + 持久化渲染任务 + 租约 | **已有等价物**：`render_requests` / `RenderCoordinator` / Renderer 单槽。 |
| Browserless 多节点、CDP 会话容量、用户公平配额 | **未实施**。 |
| `browser_render_jobs` 三类型统一任务表 | **未实施**（当前是 `render_requests` 通用请求，业务侧另有截图/页面任务表）。 |
| 生产镜像删除 Chromium、迁到 Browserless 镜像 | **未实施**；Renderer 镜像仍自带 Chromium。 |
| 真实 CDP / 多 Worker 故障 / 性能对比测试 | **未做**（文档自述亦如此）。 |

结论：`cdp.md` 适合作为「多用户浏览器池」目标设计；其中一部分目标已被远程 Renderer 方案以不同形态覆盖。若继续走 Browserless，应先对照 `remote-render-service-design.md` 做增量，而不是重开一套任务模型。

### 5.2 `runtime-multi-deployment-scaling-plan.md`

| 阶段 | 现状 |
| :--- | :--- |
| 0. 基线与正确性（含「不可用≠通过」） | **未完成**。P0 页面合并语义仍未修；容量基线未采。 |
| 1. Runtime 角色拆分（all/preview/build/check） | **未开始**。仍是单 `runtime-all`。 |
| 2. 预览无状态化 | **未开始**。预览 token/artifact 仍进程内缓存。 |
| 3. 构建/检查扩容（持久领取、attempt 围栏） | **未开始**。构建仍 `BackgroundTasks`。 |
| 4. 分布式发布 | **未开始**。 |
| 5. Backend 多副本 | **未开始**。受 P1-Run 与共享密钥/存储前提约束。 |

结论：该文是合法路线图，但**阶段 0 的 P0 尚未关闭**，不应提前启动阶段 1+ 的扩容承诺。

---

## 6. 建议处理顺序（与评估文档一致，并补文档外项）

1. **先修页面跨阶段结果语义（P0）**：合并时显式输出 `compile_status` / `render_status`；渲染 `unavailable` 时最终不得 `passed`；写入路径拒绝不完整校验，或提供显式可审计的「跳过视觉诊断保存」。补 AI 写工具 + External API 双路径契约测试。顺手合并 `_is_validation_passed` 单一实现。
2. **固定发布身份与截图失效（P1-Screenshot / P2-Profile）**：指纹纳入 Runtime/Renderer/字体/Chromium 版本；`profile` 不匹配拒绝派发；发布时定向失效旧截图。
3. **健康与普通 Run 承诺写清（P1-Health / P1-Run）**：Backend 增加 readiness（DB、协调器、Renderer 能力、队列积压）；部署文档写明普通 Run 停机语义与恢复路径。
4. **建容量基线再调拓扑（P1-Lite / P2-Queue / 扩容阶段 0）**：2C4G 混合负载记录 RSS、OOM、SQLite 锁等待、队列年龄、P50/P95；用数据决定是否拆 Runtime、是否降轮询。
5. **多实例与迁移验收**（在 1–4 之后）。
6. **收敛 API 双入口契约与大文件拆分**（P2，持续）；CLI 体验问题移交 agent-kit，并先对齐「是否允许离线契约」的规范立场。

---

## 7. 一页结论

- **真正修掉的**：浏览器出 Backend、渲染远程化、Agent Store 双事实源、会话面板巨石部分拆解、组件链路 unavailable 语义、**页面校验 Renderer 不可用误报 passed（原 P0）**、校验谓词多处拷贝、Backend 无 readiness、SQLite 文件库多进程写入无守卫。
- **最危险的仍在项**：截图环境版本身份缺失（P1-Screenshot / P2-Profile 同根）；Lite 故障域未拆（P1-Lite）；普通 AI Run 绑定 Backend 进程（P1-Run）；构建派发依赖 `BackgroundTasks`（P1-Build）。
- **文档外**：契约与实现不一致、超大文件范围更大、CLI 策略冲突、容量基线缺失。
- **不要再当真的**：删编译省 50%、纯内存租约队列、API 全量合 URL、SSE 多实例全挂、行数=性能、固定 1.5GB/40% 验收、含 Chromium 的三容器目标、CLI 离线 Schema 绑本仓重构。
- **两份规划文档**：cdp 与 Runtime 扩容都未实施；远程 Renderer 已覆盖其中一部分目标。P0 已关，**下一步是 §6.2 基线采集与决策门 D2**，再谈 Browserless/多副本。
- **未决**：**D1**（SQLite Lite 是长期一等公民还是过渡形态）仍未答。P2 已按「D1 未决 ⇒ 从裁剪」收口（见 `architecture-assessment-sqlite-2026-09.md` §6.3.1）；若 D1 答「长期一等公民」，2b（统一重试）与 2d 剩余项应重新立项，P3 也不应裁剪。
