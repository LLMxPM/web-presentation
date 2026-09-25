# 重资源队列与复用运行态

AI 一次创建或修改多页时，页面源码校验会同时触发 Runtime Vite 构建、远程渲染诊断、临时 artifact 写入和页面版本写入。为避免 SQLite 单写入者、磁盘复制和浏览器进程相互放大，平台把这些步骤拆为受控队列。

## 执行链路

```text
AI 页面写工具
  → ai_page_mutation_jobs（领域执行） + ai_agent_external_tasks（续跑控制面）
  → Runtime Vite 调度器与诊断工作区池
  → render_requests / RenderCoordinator
  → 远程 Renderer（单槽 Chromium）
  → 页面与 Job 原子提交，终态写穿 AiAgentExternalTask
  → ai-external-task-coordinator 一次性恢复 Pydantic AI run
```

- `create_project_page` 与 `apply_page_edits` 为顺序工具。同一模型步骤中的多个调用仍归入 `AiPageMutationBatch` 做业务分组与 `run_step` 序号，页面源码只保存在原始 AI tool call 中。页面 Batch 不再承载模型续跑。
- 页面 Job 使用数据库租约、心跳和拥有者条件更新；领域 Job 终态会同事务写穿到统一 `AiAgentExternalTask`。模型续跑只由 `ai-external-task-coordinator` 认领 `AiAgentExternalBatch`，每次认领递增 `lease_generation`，运行态写入嵌入同一条件，过期协调器即使仍拿到模型响应也不能覆盖新执行者。Backend 重启后仅重新认领租约已过期的领域任务，并把历史遗留的页面 Batch `resuming` 记录收敛为 `completed`；Run 的 `waiting_external` 恢复统一由 external coordinator 负责。`synchronize_external_task_states` 只作崩溃对账兜底，不是主写路径。
- 任务在 Runtime/Renderer 阶段不持有数据库事务；提交前会重新检查取消状态、权限和页面版本。
- Job 全部结束后，external coordinator 将多个 deferred result 一次性交回 Pydantic AI。用户关闭浏览器或登录会话过期不会中断已授权任务；撤销成员权限、停用用户或取消 run 会阻止后续页面写入。
- 页面代码检查使用 `page_diagnostics` 最小快照：只注入候选入口、递归组件/页面依赖和实际引用资产；无法安全解析的依赖继续按原校验错误或完整快照语义收敛，不得跳过 Vite 与远程渲染检查。
- Runtime 以每批最多 128 个路径读取 artifact 模块；滚动升级遇到旧 Backend 不支持批量接口时自动回退逐模块读取。
- 页面任务提交会通过进程内代次通知立即唤醒领域 Worker；续跑就绪由 external coordinator 轮询 `AiAgentExternalBatch` 兜底，多实例、重启与丢通知场景不依赖进程内唤醒。

截图继续使用独立的 `page_screenshot_jobs` 领域队列，执行阶段通过统一 `render_requests` 队列派发到远程 Renderer。截图任务组通过成员表关联，因此一个去重后的活跃截图任务可以属于多个批次。任务会固化页面版本、配置指纹和视口，截图对象使用不可变路径；页面或配置在捕获期间变化时任务收敛为 `skipped/PAGE_SCREENSHOT_JOB_STALE`，不会覆盖新截图指针。布局 warning 属于已完成诊断的内容结果；Renderer 离线或执行不可用时返回 `RENDER_*` 基础设施错误，不能映射为“源码有错”或“检查通过”。

页面校验结果携带 `stages: {compile, render}`：`render` 取值 `passed | warning | unavailable | failed | skipped`。render=`unavailable` 时顶层必须输出 `status=unavailable` 且 `success is not True`，写入门槛默认拒写；调用方显式传入 `skip_visual_verification=true` 时才允许写入，并在 job result 中留下 `skipped_visual_verification` 审计标记。

执行不可用不得复用内容错误码：异步页面任务在此场景必须输出 `RENDER_SERVICE_UNAVAILABLE`（已纳入 `RETRYABLE_ERROR_CODES`，按退避重试），而不是 `PAGE_VALIDATION_FAILED`（确定性失败，直接终态）。否则 Renderer 短暂离线会把可恢复的基础设施故障固化成「源码有错」。

Backend 不再安装或持有 Playwright/Chromium。截图与页面诊断统一进入 `RenderRequestService` → `RenderCoordinator` → 远程 Renderer Worker；占用释放以 attempt 租约与条件更新为准。组件远程渲染诊断协议保留在 Renderer/契约层，内容助手组件校验本迭代只覆盖契约与 Runtime 编译。

## 资源上限

SQLite/lite 推荐保持所有重资源并发为 1。SQLite 文件库为**单实例边界**：Backend 禁止 `uvicorn --workers > 1`，禁止多容器挂同一数据卷；启动时获取 `*.single-process.lock` 排他锁，冲突则拒绝启动并打印 `sqlite_single_process=true`。就绪探针使用 `/readyz`（数据库可连通、渲染 Worker 已配置），不探测 Renderer 存活以免外部抖动把 Backend 打成 not_ready；`/healthz` 保持纯 liveness。

| 资源 | lite 默认 | 常规部署默认 |
| :--- | ---: | ---: |
| AI 页面变更 Worker | 1 | 2 |
| Runtime Vite 调度槽 | 1 | 2 |
| Renderer 执行槽（每 Worker） | 1 | 1（可横向加 Worker） |
| `RENDER_GLOBAL_CONCURRENCY` | 1 | 2 |
| Runtime 等待队列 | 16 | 16 |
| `RENDER_QUEUE_SIZE` | 64 | 64 |

Runtime 诊断与正式构建共享调度槽，默认按诊断:正式构建 `3:1` 加权领取。渲染调度按交互诊断:后台截图 `3:1` 类别轮转，并在同类别内按 workspace 轮转。队列满或 Runtime 等待超时会返回 `RUNTIME_VITE_QUEUE_FULL` / `RUNTIME_VITE_QUEUE_TIMEOUT` 或 `RENDER_QUEUE_FULL`，不会伪装成页面源码错误。

## 复用与清理

- 每个 Runtime 诊断槽只复制一次 Runtime 基础源码；任务使用 `.runtime-task/<uuid>` 隔离。
- 长期诊断 Node Worker 每 25 个任务、30 分钟或达到 heap 上限的 75% 后轮换；可用 `RUNTIME_DIAGNOSTICS_WORKER_REUSE_ENABLED=false` 临时回退为一次性 Worker。
- Renderer 每个 attempt 新建 Chromium 与 Context，不跨请求复用浏览器；终态产物按 `RENDER_RESULT_TTL_SECONDS` 回收，Backend 确认消费后可提前删除临时产物。
- attempt 占用使用 `lease_expires_at`；租约超时由 `RenderCoordinator` 收敛释放，避免 unknown/悬挂执行永久占用容量。
- 应用关闭时，截图队列先停止认领，再等待领域任务收敛；渲染链路由协调器与 Renderer 负责回收。HTTP 断连也不会提前释放正在执行的槽位。
- Runtime 诊断和正式构建分别使用 120 秒、600 秒端到端 deadline；渲染阶段默认总预算 `RENDER_REQUEST_TIMEOUT_SECONDS=120`。网络拉取、Vite Worker 与上传共享同一取消信号，超时作为基础设施错误重试而非源码错误。
- Runtime artifact 在编译和渲染检查结束后主动删除。`memory://` 运行态还会按 `RUNTIME_ARTIFACT_SWEEP_INTERVAL_SECONDS` 扫描过期 key，防止 lite 容器持续积累内存。两种适配器的边界见 [运行态存储适配器](./runtime-state-adapter.md)。
- 资源比例回填任务与截图队列同口径：领取用数据库条件更新抢占 `pending`，执行者写入 `worker_id`、`lease_expires_at`、`heartbeat_at`，提交终态与资源比例时复核 attempt 身份与有效租约。旧 attempt 的迟到成功/失败会被围栏拒绝，运行态被清空不影响领取结果。

## 关键配置

Backend：

- `AI_PAGE_MUTATION_CONCURRENCY`、`AI_PAGE_MUTATION_MAX_ACTIVE_JOBS`、`AI_PAGE_MUTATION_MAX_BATCH_SIZE`
- `DURABLE_JOB_LEASE_SECONDS`、`DURABLE_JOB_HEARTBEAT_SECONDS`
- `RENDER_WORKERS_CONFIG`、`RENDER_SERVICE_CREDENTIAL` / `RENDER_SERVICE_CREDENTIAL_FILE`
- `RENDER_GLOBAL_CONCURRENCY`、`RENDER_WORKSPACE_CONCURRENCY`
- `RENDER_QUEUE_SIZE`、`RENDER_WORKSPACE_QUEUE_SIZE`
- `RENDER_REQUEST_TIMEOUT_SECONDS`、`RENDER_MAX_ATTEMPTS`、`RENDER_PROFILE_DIGEST`
- `RENDER_RUNTIME_NAVIGATION_BASE_URL`、`RENDER_RUNTIME_ASSET_BASE_URL`、`RENDER_PLATFORM_ASSET_BASE_URL`
- `RUNTIME_DIAGNOSTICS_REQUEST_TIMEOUT_SECONDS=180`、`RUNTIME_BUILD_REQUEST_TIMEOUT_SECONDS=900`

Renderer：

- `RENDER_WORKER_ID`、`RENDER_SERVICE_CREDENTIAL` / `RENDER_SERVICE_CREDENTIAL_FILE`
- `RENDER_PROFILE_DIGEST`、`RENDER_CLEANUP_GRACE_SECONDS`、`RENDER_RESULT_TTL_SECONDS`

Runtime：

- `RUNTIME_VITE_TASK_CONCURRENCY`、`RUNTIME_VITE_TASK_QUEUE_SIZE`、`RUNTIME_VITE_TASK_QUEUE_WAIT_TIMEOUT_MS`
- `RUNTIME_DIAGNOSTICS_WORKER_REUSE_ENABLED`、`RUNTIME_DIAGNOSTICS_WORKER_MAX_TASKS`
- `RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB=1024`（lite）或 `2048`（常规部署）

## 排障

1. 先使用 `diagnose_ai_run` 查看 run 是否处于 `waiting_external`、对应 Job 是否有有效租约，以及是否收到 `tool.progress`。
2. Runtime 返回 429 时优先查看队列深度和正在运行的正式构建；不要让模型反复修改页面源码。
3. 渲染任务长期不结束时查看 `render.coordinator.*` / `render.worker.*` 事件，以及 attempt 的 `lease_expires_at` 是否被持续延长；Renderer 侧看 `renderer.started` 与单槽 `slot_state`。
4. SQLite 出现 `BUSY/LOCKED` 时确认没有绕过队列的批量截图/页面写入，并保持 lite 部署的三类并发都为 1。

结构化日志可直接用于采集队列指标：`render.request.created`、`render.reserve.conflict`、`render.dispatch.*`、`render.coordinator.tick.failed` 提供调度与派发事件；`page.screenshot.job.*` 与 `ai.page_mutation.job.execution_finished` 提供任务耗时、重试、取消和租约恢复事件。心跳本身不会写入 AI 事件表，避免把监控变成 SQLite 写放大来源。

单页延迟基线以任务成功入队到页面与 Job 原子提交为主指标，不包含模型生成时间。`preview.artifact.created` 分别记录快照和 artifact 存储耗时，`runtime.diagnostics.compile.finished`、`runtime.diagnostics.render.finished`、`diagnostics.modules.ready`、`diagnostics.workspace.validated`、`diagnostics.vite.finished` 与 `ai.page_mutation.save.finished` 用于拆分检查阶段。固定夹具预热两次后至少运行十次，比较 P50/P95；首期目标为 P50 降低 25%，P95 不劣化超过 10%。
