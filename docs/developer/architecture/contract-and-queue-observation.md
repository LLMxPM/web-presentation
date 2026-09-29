# 契约生成与队列观测

## API 与 previewSchema

Backend OpenAPI 是 HTTP DTO 的事实源。`editor/src/types/api.ts` 中的工作空间、项目、页面、组件、主题、样式、资源、预览响应和用户类型直接引用 `api.generated.ts`；相应路由、构建扩展资源和资产分析摘要也使用生成类型。其它尚未迁移的视图、请求与查询类型继续保留在兼容层，不能据此宣称全部 Editor 类型已经单源化。

```powershell
pnpm run codegen:editor-api
pnpm run codegen:preview-types
pnpm run test:contracts:generated
pnpm run test:contracts
pnpm run test:editor:check
```

OpenAPI 导出使用独立进程，清除应用配置环境覆盖、禁读 `.env`，使用内存数据库地址及临时对象存储目录。仅读取应用路由，不进入 lifespan、不连接业务服务。CI 从当前 Backend 重新导出，完整比较 OpenAPI 与生成类型；不会把仓库里两份同时过时的静态文件对比当作充分证据。默认字段在 OpenAPI 中可能可选，消费处须显式处理缺省值，不应靠手写类型将其强制变成必填。

组件结构的事实源为 `backend/app/core/component_preview_schema.v1.json`。Backend 生产入口先使用 Draft 2020-12 校验，再执行 Runtime Kit 和工作空间组件 import 边界检查；结构合法不代表引用已获授权。Editor 与 Runtime 从同一 Schema 生成类型，再各自附加视图状态。

共享样本为 `tests/fixtures/preview-schema-cases.json`：Backend 运行生产校验器，Editor/Runtime 使用真实 TypeScript 语义检查。覆盖必填、字段类型、枚举及递归节点；JSON Schema 的长度、数值范围等约束仍由 Backend 运行时校验，TypeScript 不替代运行时验证。Schema 目前允许额外属性，以保留扩展能力。

双入口 Top 操作测试完整核对 HTTP 方法与路径段，只允许参数名不同。删除目标方法或路径但保留同前缀路由必须失败。页面列表、读取、更新和两种预览对齐响应模型；创建的 200/202 及 Internal 无校验端点的差异单独锁定。全业务 API 矩阵和真实权限联调仍由相关 API/E2E 测试覆盖。

## 队列快照 v2

`snapshot_job_queue_metrics()` 输出 `schema_version: 2`。它是某一时刻的积压与存活观测，不是吞吐量或请求延迟统计。每个集合执行一次按状态聚合的 SQL，不读取源码、提示词、结果或业务标识。各队列采样使用同一 UTC 时间，但并不承诺跨语句、跨数据库的全局原子快照。

| 集合 | 口径 | pending / running |
| :--- | :--- | :--- |
| 页面修改、图片、组件修改、截图、构建、资产回填、API mutation | 领域任务行 | pending / running |
| external_task | 领域状态投影；组件按 kind 另列 | pending / running |
| external_batch | 一次模型 step 的续跑批次 | collecting、waiting_tasks、ready / resuming |
| render_request | 渲染请求 | queued、retry_wait / executing |
| render_attempt | `active_occupancy=1` 的物理槽位占用 | 无 pending / 契约定义的占用状态 |

`totals.unit=domain_job_rows`，`included_queues` 列出参与汇总的领域集合。页改/图片 Job 对应的 ExternalTask、Batch、RenderRequest、RenderAttempt 均不重复加入 totals。组件没有独立执行 Job，其 ExternalTask 中 `kind=component_mutation` 的行只计一次。一个用户操作仍可能产生多个领域任务，所以 totals 不能命名为“用户请求总量”。

- `states` 保留各状态的原始计数，便于发现未知状态或与 DB 对账。
- `oldest_pending_age_seconds` 从 `age_origin` 指定的创建时间起算；重试请求包括之前尝试的时间。它不是 ready 后等待时长，也不是 P95。
- `expired_lease_running` 只统计运行状态中租约到期的行；`missing_lease_running` 单独统计缺租约。RenderRequest 没有租约列，`lease_supported=false`，相关值为 `null`；租约统计应看 RenderAttempt。
- 图片 `waiting_provider` 不占 Worker 租约。`overdue_provider_polls` 统计 `next_poll_at <= checked_at`，`missing_provider_poll` 统计缺少下次轮询时间；逾期年龄从 `next_poll_at` 起算。
- Batch 的 collecting/waiting_tasks 属于前置等待，ready 才可续跑；不能将 pending 合计误作立即可执行量。
- 没有待执行任务时最老年龄为 `null`，不是零。

本地非空数据集覆盖排队、重试、执行、缺失/过期租约、终态和供应商等待，并验证 totals 排除重复投影。真实 PG 对账、混合负载采样开销及容量结论属于现行计划 M03，尚未验收。
