# 架构调整后评估：边界更清楚，正确性与发布证据仍不足

> 评估日期：2026-09-23。评估对象为当前工作区代码与部署模板，基线提交 `a84e88b`；工作区存在其他未提交改动，本文没有修改它们。输入材料为本地 `docs/temp/architecture_review_report.md`。本评估以静态代码追踪和现有文档为依据，未执行多实例、故障注入或性能压测。下文将“代码可确认的问题”和“尚未验证的风险”分开表述。

## 结论

这次调整解决了旧架构最明显的执行边界问题：Backend 不再直接运行 Chromium，截图和页面布局诊断经持久化渲染请求交给独立 Renderer；Runtime 编译任务和浏览器任务分别有容量控制。旧报告把 `PlaywrightBrowserPool`、Backend 内的 Chromium 与“三容器替代方案”当作待实施目标，已经不能作为当前改造计划。

但“执行进程分离”尚未等于“端到端正确且可扩展”。当前最严重的问题是**渲染不可用可被页面校验结果包装成通过**。其次，普通 AI Run 的执行仍以 Backend 进程为边界，轻量版仍把 Backend、Runtime、Gateway 放在同一容器，截图缓存没有绑定运行环境版本，生产健康检查也不能反映调度链路是否可用。项目设计文档还明确把真实多实例联调、数据转换副本演练和性能基线列为未完成验收项。因此，现阶段可以评价为“核心拆分已落地”，不能据此宣称“轻量版已被证明适配 2C4G”或“企业级无状态高可用已完成”。

## 评估范围与判断标准

- 跟踪页面候选源码从 Backend 校验、Runtime 编译到 Renderer 布局诊断，再到页面写入的实际数据流。
- 核对 AI Run、租约队列、渲染调度和四种 Compose 拓扑的真实边界。
- 将正确性、故障恢复、容量和维护成本分开评价；代码存在并不等于压力指标达标。
- 风险级别：**P0** 表示可能错误提交业务结果，应先修复；**P1** 表示发布或可用性边界不足；**P2** 表示可控但持续累积的扩展或维护成本。

## 对原评审报告的复核

| 原报告判断或建议 | 当前证据 | 复核意见 |
| :--- | :--- | :--- |
| Backend 中的 `PlaywrightBrowserPool` 与 Uvicorn 共进程，应外移浏览器 | [应用启动](../../../../backend/app/main.py)启动 `RenderCoordinator`；[页面渲染业务入口](../../../../backend/app/services/page_render_diagnostics_service.py)调用远程渲染；[Renderer 设计实施摘要](../../developer/backend/remote-render-service-design.md#16-实施落地摘要2026-09)列出旧池删除 | **已过时。** 浏览器执行已外移。当前应审查跨进程结果语义、租约、产物与发布一致性。 |
| Node/Vite 编译与 Chromium 渲染是无意义的“双重构建”，跳过编译可节省 50% | [代码检查](../../../../backend/app/services/code_check_service.py)先调用 Runtime 编译，成功后才追加页面渲染诊断；[组件校验](../../../../backend/app/services/component_validation_service.py)只覆盖契约与 Runtime 编译 | **问题存在，结论不成立。** 两阶段检查的失败集合不同。浏览器访问预览仍依赖 Runtime/Vite；删除显式编译检查可能改变错误归类与组件保障。50% 的收益没有基线。应按真实阶段耗时与等价测试判断是否合并。 |
| 单容器容纳 Chromium，任一子进程失效都会带崩全站 | [SQLite Lite Compose](../../../../deploy/compose/compose.sqlite-lite.yml)已有独立 `renderer`，但 `platform-lite` 仍集成 Backend、Runtime、Gateway；[启动脚本](../../../../deploy/docker/entrypoints/start_lite.sh)发现任一平台子进程退出会结束其余进程 | **部分仍成立。** Chromium 已隔离；轻量平台内的三个服务仍共享故障域与内存预算。不能照旧报告写成“四进程含浏览器同容器”。 |
| 数据库租约队列应换成纯进程内队列、固定租约、只在启动时恢复 | [页面变更队列](../../../../backend/app/ai/page_mutation_queue.py)采用进程内唤醒加数据库轮询兜底，运行时续租；[租约服务](../../../../backend/app/services/durable_job_lease_service.py)用拥有者条件更新 | **不应照搬。** 纯内存通知会丢失重启及跨实例唤醒；固定租约无法安全覆盖长时间模型或渲染步骤。SQLite 写放大仍值得测量，但优化对象应是轮询与心跳频率、事务量，而非删除持久化事实源。 |
| 内外 API 是两套完全重复的业务实现，应让 Editor 全部改用 `/api/v1` | [路由装配](../../../../backend/app/api/router.py)确有两套入口；内部与外部[页面路由](../../../../backend/app/api/routes/pages.py)、[External 页面路由](../../../../backend/app/api/routes/external/pages.py)已共用 `PageService`，外部写入还承载任务和幂等语义 | **边界风险真实，重复程度被夸大。** 先核查权限、错误码、字段和写入语义的漂移，再决定哪些 DTO/服务可合并；机械统一 URL 会把不同事务语义混成一套接口。 |
| 进程内事件字典使多实例 SSE 完全失效 | [运行态事件流](../../../../backend/app/ai/platform_runtime.py)有进程内订阅者，但 SSE 也会按事件序号从数据库轮询回放；[普通 Run 管理器](../../../../backend/app/ai/background_run_manager.py)仍为进程内任务 | **表述过度。** SSE 有跨进程兜底，普通 Run 的模型执行却确实不能跨进程恢复；扩容的限制在执行生命周期与代价，而非“事件立即击穿”。 |
| 核心文件职责过多、Agent Store 维护双向状态 | [会话面板](../../../../editor/src/components/agent/AgentConversationPanel.vue)、[资产视图](../../../../editor/src/views/AssetsView.vue)、[AI 运行态](../../../../backend/app/ai/platform_runtime.py)、[会话门面](../../../../backend/app/ai/session_facade_pydantic.py)、[Agent Store](../../../../editor/src/stores/agent-session.ts) | **仍成立。** Store 同时保存树状状态和扁平映射，并显式双向同步；这是有证据的维护风险。原报告的行数和“1000 行硬限制”并非当前规范的准确表述，不能用行数本身证明性能问题。 |
| CLI 的部分叶子命令 `--help` 依赖在线 OpenAPI | 同级 `web-presentation-agent-kit/packages/cli/src/wp/openapi_help.py` 及 `tests/test_openapi_help.py` 可验证离线失败；该代码不在本仓 | **属实但归属错误。** 应在 Agent Kit 独立仓提出体验和契约策略，不能作为本仓 Backend 重构的前置理由。 |

## 当前架构风险

### P0：Renderer 故障时页面校验可能“通过”并落库

**代码可确认。** [渲染诊断服务](../../../../backend/app/services/page_render_diagnostics_service.py)把若干 Renderer 基础设施异常转换成 `status="unavailable"` 和一条 `severity="warning"` 诊断。[代码检查的结果合并](../../../../backend/app/services/code_check_service.py)把 warning 与布局分析合入 Runtime 编译结果，却没有把 `unavailable`、`retryable` 或 `success=false` 覆盖到最终状态。Runtime 编译成功时，最终结果因而仍可能是 `success=true/status=passed`。[页面变更规划器](../../../../backend/app/services/mutation_planners/page_mutation_planner.py)与 [AI 页面变更执行器](../../../../backend/app/ai/page_mutation_executor.py)调用 `_is_validation_passed()` 决定是否继续写入；该谓词接受 `success=true` 或 `status=passed`。

这意味着 Renderer 离线、结果丢失或超时等场景，可能被报告为“代码检查通过，附带基础设施 warning”，并允许创建或更新页面。用隔离的结果合并调用复现了这一点：输入 Runtime `success=true/status=passed` 与 Renderer `status=unavailable/retryable=true`，输出仍为 `success=true/status=passed`，`retryable` 丢失。这里不是要求布局 warning 阻止保存，而是**没有产生布局事实时，不能宣称完整校验已通过**。现有[渲染控制面单测](../../../../backend/tests/unit/test_render_control_plane.py)检查了不可用结果和 artifact 清理，却未覆盖“不可用结果合并后最终状态及页面写入”的组合边界。

**建议**：在页面结果合并处显式区分 `compile_status` 与 `render_status`；渲染 `unavailable` 时，最终 `success=false/status=unavailable/retryable=true`，保留基础设施错误码和独立摘要。页面写入消费者应对未知或不完整阶段状态拒绝提交，或若产品允许“跳过视觉诊断保存”，提供显式、可审计的用户选择，不能借 `passed` 隐式放行。补一条跨服务契约测试：Runtime 编译通过 + Renderer 不可用，断言页面与版本不新增，返回的错误仍归类为基础设施故障。

### P1：普通 AI Run 仍绑定 Backend 进程，不能按“无状态控制面”承诺

**代码与文档均确认。** [后台 Run 管理器](../../../../backend/app/ai/background_run_manager.py)用进程内 `asyncio.Task` 保存执行，进程关闭时取消；[AI Agent 文档](../../developer/backend/ai-agent.md)明确正常退出写 `AI_RUN_PROCESS_STOPPED`，异常退出由空闲超时收敛，不自动重跑。SSE 的数据库回放解决了观察问题，并未保存可恢复的模型执行栈。页面、图片等 external job 的持久化恢复也不能代表普通 Run 的恢复。

如果产品目标是单实例创作工作台，这可以是明示约束；如果目标包含 Backend 滚动升级、多副本或无中断长会话，它是发布边界。建议在部署规格中写明可用性承诺，并对滚动重启中的普通 Run 失败率和用户恢复路径设门禁。需要真正跨进程续跑时，应先设计 Run 的可恢复检查点与幂等工具副作用，再考虑把普通 Run 移到独立执行服务；仅替换锁提供者不足以解决。

### P1：截图“当前”判断未包含 Runtime/Renderer 环境版本

**代码可确认，影响需通过升级演练量化。** [截图配置指纹](../../../../backend/app/services/page_screenshot_fingerprint_service.py)只哈希页面尺寸、主题与字体修订等配置；[页面服务](../../../../backend/app/services/page_service.py)和[截图服务](../../../../backend/app/services/page_screenshot_service.py)用页面版本、配置 hash、视口判定现有截图可复用。Runtime 组件实现、Renderer 镜像或 Chromium 字体环境更新后，如果页面与配置不变，旧截图仍可能被视为当前结果。[渲染请求服务](../../../../backend/app/services/rendering/request_service.py)虽将 `render_profile_digest` 放入渲染请求身份，[部署模板](../../../../deploy/compose/compose.sqlite-lite.yml)和[配置默认值](../../../../backend/app/core/config.py)却长期使用人工填写的 `profile.v1`；Renderer 能力回执也是同一个配置值，并未自动证明镜像、浏览器或字体真实身份。

建议给截图有效性身份加入发布时生成的 Runtime/Renderer/字体版本指纹，并在发布切换时定向失效或重新生成既有截图。不同镜像却共用同一 profile 时应让发布门禁失败。不要把 `profile.v1` 当成不可变内容摘要；它目前是运维配置标签。

### P1：轻量版资源和故障域仍合并，容量结论缺实测

**拓扑已确认，容量指标未证实。** [轻量 Compose](../../../../deploy/compose/compose.sqlite-lite.yml)设置 AI 页面变更、Runtime Vite 和渲染的并发各为 1，但 `platform-lite` 中仍同时运行 Backend、Vite 与 Nginx；[启动脚本](../../../../deploy/docker/entrypoints/start_lite.sh)以其中任一进程退出作为整个平台重启条件。模板没有容器级内存或进程数上限。Renderer 作为单独容器，已经避免浏览器崩溃直接杀死 Backend 进程，但这并不能自动保证整机内存峰值、排队时延或 SQLite 写入稳定。

建议以 2C4G 和实际目标机器做混合负载测量：五个并发页面变更、截图、预览和构建同时到达；记录各容器 RSS 峰值、OOM 事件、SQLite BUSY/LOCKED、排队最长时间及 P95。根据测量结果决定是否拆出 Runtime 或调整并发、队列和内存限额。原报告的“1.5GB 以下”“延迟降低 40%”应视为未验证假设，而非验收基线。

### P1：存活探针不能反映调度链路是否可用

**代码可确认。** [Backend `/healthz`](../../../../backend/app/main.py)固定返回 `ok`，有意不探测数据库或外部服务；这适合作为 liveness。[生产 Compose](../../../../deploy/compose/compose.prod.yml)却用它作为 Backend `service_healthy` 条件，Runtime/Gateway 的启动又依赖此状态。即使渲染协调器持续报错、Renderer profile 不匹配或队列停止推进，平台仍可能被编排层视为健康。

建议保留轻量的 liveness，增加独立 readiness/运行状态探针，至少覆盖数据库可读写、必要运行态存储、协调器最近成功推进时间、Renderer 能力匹配和队列积压；对“Renderer 离线但编辑仍可用”定义明确的降级状态。告警应依据积压年龄和终态错误率，而不是只看 HTTP 200。

### P2：持久化调度的空闲成本需要量化，不能用内存队列替换正确性

**代码可确认的成本**：[渲染协调器](../../../../backend/app/services/rendering/coordinator.py)默认每 0.25 秒执行一次 `tick()`，包括 Worker 能力 HTTP 探测与心跳写入；[页面变更队列](../../../../backend/app/ai/page_mutation_queue.py)默认 0.5 秒轮询，并以进程内代次通知提前唤醒。SQLite 单写入者下，这种固定频率可能放大空闲写入和争用，但现有材料没有证明它已造成原报告所称的“频繁 database is locked”。

建议先采集空闲/混合负载每秒 SQL 读写数、锁等待、心跳延迟、事件到认领延迟。优化优先级是减少无变化的心跳更新、按负载自适应退避并保持持久化兜底；任意方案都必须通过进程崩溃、跨实例通知丢失、租约代次转移和重复结果消费测试。

### P2：入口与前端状态仍有维护成本，但不宜用“大一统”重写

内部 API 和 External API 的页面读写已经共享部分领域服务，却仍有不同的认证、幂等、任务返回和错误语义。真正要防的是同一业务规则在两个入口呈现不同结果。建议维护一张“同一操作的两个入口”契约矩阵，覆盖权限、工作空间隔离、版本冲突、错误码与字段含义；只合并相同的领域行为，不强迫 Editor 直接承担 External API 的异步任务协议。

Agent Store 的树状状态与多个扁平映射通过 `syncFlatMaps()` / `hydrateSessionFromFlatMaps()` 双向同步，确实存在遗漏和状态覆盖风险。可以先选一个会话生命周期做单一事实源试点，比较事件顺序、重连、HITL 与多会话切换结果；再拆分面板和大型服务文件。行数应作为定位复杂度的信号，不应直接充当性能结论或重构完成标准。

## 建议的处理顺序与验收门槛

| 顺序 | 工作 | 可验证的完成条件 |
| :--- | :--- | :--- |
| 1 | 修正页面校验的跨阶段结果语义 | 编译通过但 Renderer 不可用时，页面/版本不写入；响应明确为可重试基础设施故障；补覆盖 AI 与 External API 写入路径的契约测试。 |
| 2 | 固定真实发布身份与截图失效规则 | 同一页面在 Runtime/Renderer/字体版本改变后旧截图不再被判定为当前；不匹配的 profile 拒绝派发，并有升级回归。 |
| 3 | 明确服务健康和普通 Run 的运行承诺 | readiness 能识别 DB、协调器和 Renderer 降级；滚动重启对普通 Run 的失败与恢复行为经过故障演练并写入部署说明。 |
| 4 | 建立容量基线后优化调度与拓扑 | Lite 目标硬件上有混合负载 P50/P95、RSS、OOM、SQLite 锁等待和队列年龄记录；按实测决定是否拆 Runtime 或降低空闲轮询。 |
| 5 | 做多实例与迁移发布验收 | 两个 Backend 协调器竞争、Renderer 失联/重启、迟到结果、权限撤销及数据转换副本演练均有记录；与 Agent Kit 的契约同步发布。 |
| 6 | 收敛 API 与状态管理维护成本 | 同一领域规则的双入口契约测试通过；Agent Store 改动前后事件回放、HITL 和多会话切换行为一致。 |

原报告按 1～4 周给出三阶段交付和固定收益率，缺少工作量、负载与故障数据，不宜直接用作排期。当前更合理的决策门槛是：**先保证失败不会被报告为成功，再证明发布与恢复行为，最后依据容量基线决定是否继续拆分。**
