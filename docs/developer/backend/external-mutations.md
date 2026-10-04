# External Mutation 的身份、幂等与版本边界

本文记录主仓现有行为及 M4 回归边界。请求/响应与权限以当前 OpenAPI 和 `core/external_operations.py` 为准，本文不作为离线请求契约。远程 MCP 发布仍需真实 Gateway、PostgreSQL、Renderer 和宿主验收。

## 1. 受理与领域执行

页面创建/edits、组件创建/edits/重元数据返回 HTTP 202 和持久 `ApiMutationJob`。页面/组件轻元数据 PATCH、组件发布、单项归档保持同步。MCP 不创建另一条队列，也不把 HTTP 202 当成实体已写入。

Job 对外状态为 `pending | running | succeeded | failed | canceled`。查询到 failed 仍是 HTTP 200，错误在 `error` 中。running 的取消返回 202、仍为 running，并填写 `cancel_requested_at`；Worker 在提交实体前检查取消并收敛为 canceled。完成先提交后，取消返回 `MUTATION_JOB_NOT_CANCELABLE`，不会撤回已完成数据。

已受理 Job 不因请求响应丢失、MCP 断连、凭证到期或 Grant 撤销自动取消。领域 Worker 继续使用任务用户、当前成员权限、原基线和租约约束；后续查询、取消和 retry 必须重新认证及授权。凭证失效不能取回旧幂等响应。

动态 Job 鉴权从数据库 `job_type` 派发：status 需要对应 page/component 读取 Scope；cancel/retry 需要对应写入 Scope。真实 `job.workspace_id` 决定空间权限，调用方的 `resource_type` 或伪造空间 Header 不能改派。

## 2. 幂等存储命名空间

唯一边界保持 `user_id/workspace_id/operation/idempotency_key`；指纹包含 HTTP method、实际 path 和规范化业务 payload，不包含 Token、Grant 或 MCP 服务 ID。同一用户在权限有效且记录未过期时，重新交换、刷新或使用 PAT 可以重放原受理响应；同键异载荷返回 `IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD`。重放返回首次保存的响应，最新 Job 状态应使用 GET 查询。

以下前缀均为 `/api/v1`，动态 `entity` 取真实 Job 的 page/component 类型。

| 实际请求 | 公共 operation key | 幂等记录 operation |
| --- | --- | --- |
| `POST /pages` | `page.create` | `page.create` |
| `POST /pages/{id}/edits` | `page.edit` | `page.edit` |
| `POST /components` | `component.create` | `component.create` |
| `POST /components/{id}/edits` | `component.edit` | `component.edit` |
| `POST /jobs/mutations/pages` | `jobs.mutation.page.create` | `jobs.mutation.page.create` |
| `POST /jobs/mutations/pages/edits` | `jobs.mutation.page.edit` | `jobs.mutation.page.edit` |
| `POST /jobs/mutations/components` | `jobs.mutation.component.create` | `jobs.mutation.component.create` |
| `POST /jobs/mutations/components/edits` | `jobs.mutation.component.edit` | `jobs.mutation.component.edit` |
| `POST /jobs/mutations/components/metadata` | `jobs.mutation.component.metadata` | `jobs.mutation.component.metadata` |
| `POST /jobs/mutations/{id}/cancel` | `jobs.mutation.{entity}.cancel` | `jobs.mutation.{entity}.cancel` |
| `POST /jobs/mutations/{id}/retry` | `jobs.mutation.{entity}.retry` | `jobs.mutation.{entity}.retry` |
| `PATCH /pages/{id}` | `page.update` | `page.update` |
| `PATCH /components/{id}` | `component.update` | `component.update` |
| `POST /components/{id}/publish` | `component.publish` | `component.publish` |
| `POST /pages/{id}/archive` | `page.archive` | `page.archive` |
| `POST /components/{id}/archive` | `component.archive` | `component.archive` |
| `POST /projects/batch-archive` | `project.archive` | `operations.batch_archive` |
| `POST /pages/batch-archive` | `page.archive` | `operations.batch_archive` |
| `POST /components/batch-archive` | `component.archive` | `operations.batch_archive` |
| `POST /assets/batch-archive` | `asset.archive` | `operations.batch_archive` |
| `POST /themes/batch-archive` | `theme.archive` | `operations.batch_archive` |
| `POST /styles/batch-archive` | `style.archive` | `operations.batch_archive` |

其余现有幂等写入口的存储 operation 与公共 key 一致：`project.create/update/archive/configuration.update/route.update/apply_style/build_assets.update`、`page.copy`、`asset.content.create/content.update/upload/copy/update/archive`、`theme.create/copy/update/archive`、`style.create/copy/update/archive`。没有幂等写入的读取、预览和校验入口不产生该记录。

实体入口与 `/jobs/mutations` 别名具有不同命名空间，切换路径会创建另一任务。六类 batch 虽共享存储 operation，指纹仍包含不同实际 path；跨类型复用同键会冲突。不得无迁移地改名、合并别名或将 Grant/Token 添加到唯一边界。首期 MCP 不开放 batch，本表仅记录已有平台兼容行为。

页面/组件单项归档在幂等检查前允许定位已归档目标并复核当前权限，因此原有效 key 能恢复原成功响应。新 key 仍走既有未归档写入约束并返回 404，普通详情读取也返回 404。页面当前使用软删除时间，组件使用 archived 状态；没有硬删除或恢复动作。

## 3. 组件隐式基线与历史兼容

页面 edits 要求 `base_version_no`。组件 edits 的版本字段遵守 External DTO，省略 `base_draft_hash` 时首次受理补当前源码 hash；组件重元数据可省略版本/hash，首次受理补齐二者。

同键重放时仅为省略的字段沿用原 Job 的不可变基线，显式版本/hash 不改写，其他参数仍参与指纹比较。草稿或发布版本在受理后变化，不会改变原请求身份，也不会生成新 Job。

历史指纹顺序保持：实体 component edits、重元数据在补齐后计算；`/jobs/mutations/components/edits` 在补齐前计算。实现不重算历史记录、不改变 operation，也不要求数据库迁移。过期记录不沿用旧 Job 基线；超出保留期不承诺恢复原结果。

规划结束后提交仍复核原版本和草稿 hash。冲突以 `PAGE_CONCURRENT_MODIFIED` / `COMPONENT_CONCURRENT_MODIFIED` 确定性失败，不自动升版本或覆盖源码。人工 retry 仅适用于 failed 且 `error.retryable=true`，创建新公开 Job ID，通过 `retry_of_job_id` 关联原任务，并保留原 payload、版本和草稿 hash。

## 4. 回归证据范围

`tests/fixtures/oauth_mutations.py` 使用每例专属 SQLite/PG 测试库，预置已批准 Grant 后通过真实授权码 HTTP 兑换、服务 Basic 交换和 External Bearer 校验；不注入 ExternalPrincipal，不写开发库。API 专题分别覆盖重放、动态权限、人工 retry、同步入口和响应丢失。

`tests/integration/test_oauth_mutation_commit.py` 从真实 HTTP 入队、真实认领到独立 Session 提交，使用受控规划产物验证冲突、取消/完成的两种提交顺序及凭证失效。它不运行诊断阶段、Chromium 或真实 Renderer；顺序验证不能替代两个 Backend 实机并发演练。未配置专属 PostgreSQL 时用例明确跳过。

接续验收包括：专属 PG 和两个 Backend 进程竞争、真实 Gateway 响应丢失/断连、MCP binding 对拍，以及 Renderer→Runtime 实际诊断与 PNG 链路。
