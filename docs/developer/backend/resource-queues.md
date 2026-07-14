# 重资源队列与复用运行态

AI 一次创建或修改多页时，页面源码校验会同时触发 Runtime Vite 构建、Chromium 渲染检查、临时 artifact 写入和页面版本写入。为避免 SQLite 单写入者、磁盘复制和浏览器进程相互放大，平台把这些步骤拆为受控队列。

## 执行链路

```text
AI 页面写工具
  → ai_page_mutation_batches / ai_page_mutation_jobs
  → Runtime Vite 调度器与诊断工作区池
  → Backend 共享 Chromium 池
  → 页面与 Job 原子提交
  → 自动恢复 Pydantic AI run
```

- `create_project_page` 与 `apply_page_edits` 为顺序工具。同一模型步骤中的多个调用会生成一个 Batch，Batch 序号由平台在同一 run 内持久化递增，避免 Pydantic AI continuation 重置内部步骤号后误复用已完成批次；页面源码仍只保存在原始 AI tool call 中。
- 页面 Job 与 Batch 使用数据库租约、心跳和拥有者条件更新。Batch 每次认领都会递增 `lease_generation`；运行态事件、消息历史和终态提交将该代次嵌入同一条条件写入，过期协调器即使仍拿到模型响应也不能覆盖新执行者。Backend 重启后仅重新认领租约已过期的任务，并把中断的 `running` run 恢复为 `waiting_external`，不干扰其他实例仍在执行的任务。
- 任务在 Runtime/Chromium 阶段不持有数据库事务；提交前会重新检查取消状态、权限和页面版本。
- Job 全部结束后，后台协调器将多个 deferred result 一次性交回 Pydantic AI。用户关闭浏览器或登录会话过期不会中断已授权任务；撤销成员权限、停用用户或取消 run 会阻止后续页面写入。

截图继续使用独立的 `page_screenshot_jobs` 领域队列，但与 AI 渲染诊断共享 Chromium 池。截图任务组通过成员表关联，因此一个去重后的活跃截图任务可以属于多个批次。任务会固化页面版本、配置指纹和视口，截图对象使用不可变路径；页面或配置在捕获期间变化时任务收敛为 `skipped/PAGE_SCREENSHOT_JOB_STALE`，不会覆盖新截图指针。

## 资源上限

SQLite/lite 推荐保持所有重资源并发为 1：

| 资源 | lite 默认 | 常规部署默认 |
| :--- | ---: | ---: |
| AI 页面变更 Worker | 1 | 2 |
| Runtime Vite 调度槽 | 1 | 2 |
| Chromium 浏览器槽 | 1 | 2 |
| Runtime 等待队列 | 16 | 16 |

Runtime 诊断与正式构建共享调度槽，默认按诊断:正式构建 `3:1` 加权领取。浏览器池也按交互渲染诊断:后台截图 `3:1` 调度。队列满或 Runtime 等待超时会返回 `RUNTIME_VITE_QUEUE_FULL` 或 `RUNTIME_VITE_QUEUE_TIMEOUT`，不会伪装成页面源码错误。

## 复用与清理

- 每个 Runtime 诊断槽只复制一次 Runtime 基础源码；任务使用 `.runtime-task/<uuid>` 隔离。
- 长期诊断 Node Worker 每 25 个任务、30 分钟或达到 heap 上限的 75% 后轮换；可用 `RUNTIME_DIAGNOSTICS_WORKER_REUSE_ENABLED=false` 临时回退为一次性 Worker。
- Chromium 固定在专属线程中复用，每次任务创建并关闭独立 BrowserContext；50 个任务或 30 分钟后轮换。
- 应用关闭时，截图队列先停止认领，再等待已经认领的 BrowserContext 关闭和 Job 终态提交，最后才关闭 Chromium 池；HTTP 断连也不会提前释放正在执行的槽位。
- Runtime 诊断和正式构建分别使用 120 秒、600 秒端到端 deadline；网络拉取、Vite Worker 与上传共享同一取消信号，超时作为基础设施错误重试而非源码错误。
- Runtime artifact 在编译和渲染检查结束后主动删除。`memory://` 运行态还会按 `RUNTIME_ARTIFACT_SWEEP_INTERVAL_SECONDS` 扫描过期 key，防止 lite 容器持续积累内存。

## 关键配置

Backend：

- `AI_PAGE_MUTATION_CONCURRENCY`、`AI_PAGE_MUTATION_MAX_ACTIVE_JOBS`、`AI_PAGE_MUTATION_MAX_BATCH_SIZE`
- `DURABLE_JOB_LEASE_SECONDS`、`DURABLE_JOB_HEARTBEAT_SECONDS`
- `PLAYWRIGHT_BROWSER_POOL_SIZE`、`PLAYWRIGHT_TASK_QUEUE_SIZE`、`PLAYWRIGHT_BROWSER_REUSE_ENABLED`
- `RUNTIME_DIAGNOSTICS_REQUEST_TIMEOUT_SECONDS=180`、`RUNTIME_BUILD_REQUEST_TIMEOUT_SECONDS=900`

Runtime：

- `RUNTIME_VITE_TASK_CONCURRENCY`、`RUNTIME_VITE_TASK_QUEUE_SIZE`、`RUNTIME_VITE_TASK_QUEUE_WAIT_TIMEOUT_MS`
- `RUNTIME_DIAGNOSTICS_WORKER_REUSE_ENABLED`、`RUNTIME_DIAGNOSTICS_WORKER_MAX_TASKS`
- `RUNTIME_BUILD_WORKER_MAX_OLD_SPACE_MB=1024`（lite）或 `2048`（常规部署）

## 排障

1. 先使用 `diagnose_ai_run` 查看 run 是否处于 `waiting_external`、对应 Job 是否有有效租约，以及是否收到 `tool.progress`。
2. Runtime 返回 429 时优先查看队列深度和正在运行的正式构建；不要让模型反复修改页面源码。
3. Chromium 任务长期不结束时查看 `playwright.browser.*` 日志事件；关闭复用开关可作为短期故障隔离手段。
4. SQLite 出现 `BUSY/LOCKED` 时确认没有绕过队列的批量截图/页面写入，并保持 lite 部署的三类并发都为 1。

结构化日志可直接用于采集队列指标：`playwright.task.queued/finished` 提供队列长度、等待和执行时长；`page.screenshot.job.*` 与 `ai.page_mutation.job.execution_finished` 提供任务耗时、重试、取消和租约恢复事件。心跳本身不会写入 AI 事件表，避免把监控变成 SQLite 写放大来源。
