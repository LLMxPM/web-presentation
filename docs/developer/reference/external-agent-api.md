# External API v1 契约与外部 Agent 接入边界

## 1. 文档归属

本文是 `web-presentation` 主仓库维护的 External API v1 契约文档，服务于独立 `web-presentation-cli` 的 CLI/Skill，以及 `web-presentation-mcp` 的远程协议服务。两端分别维护同步与异步客户端，不依赖共享 SDK。

本文只维护平台侧事实：

- External API v1 的公开边界、路径和版本策略；
- PAT、Scope、工作空间隔离和错误语义；
- 页面、组件、资源、主题、样式和 Mutation Job 的后端契约；
- `/standards/*`、`/capabilities` 和 OpenAPI 等自省接口；
- 主仓库契约测试、兼容性和变更流程。

本文不维护以下内容：

- `wp` CLI 的 Click 命令、参数、终端输出和本地 Profile；
- MCP Tool、Resource、Prompt、传输和协议输出；
- Agent Skill 的工作流提示词；
- CLI/MCP 各仓的 Python 模块结构、发布方式和测试。

对应实现文档：

- CLI 实施矩阵：[web-presentation-cli/docs/cli-capability-completion.md](https://github.com/LLMxPM/web-presentation-cli/blob/master/docs/cli-capability-completion.md)
- MCP 规划参考：[web-presentation-mcp/docs/mcp-implementation-plan.md](https://github.com/LLMxPM/web-presentation-mcp/blob/main/docs/mcp-implementation-plan.md)
- Skill 知识库：[web-presentation-cli/skills/web-presentation/SKILL.md](https://github.com/LLMxPM/web-presentation-cli/blob/master/skills/web-presentation/SKILL.md)

远程 MCP 主仓已实现默认关闭的 OAuth 协议、Cookie 授权确认/管理及真实委托 Bearer 验证。首批客户端为 [ChatGPT 网页端](../backend/oauth-chatgpt.md)。MCP 仓库、公开部署与真实宿主仍待[实施计划](../mcp-implementation-plan.md)验收，不把主仓 ASGI 测试当作客户端可用证明。

## 2. 唯一事实源

External API 契约的优先级如下：

1. Backend 实际路由、Pydantic 请求/响应模型和鉴权依赖；
2. `backend/app/core/external_operations.py` 中的 operation 注册表；
3. `tests/contracts/` 中的跨模块契约测试；
4. 本文的语义说明和变更记录。

当本文与代码或契约测试冲突时，先修正主仓契约，再通知 CLI/MCP 仓库更新适配；不得由 CLI 或 MCP 猜测并绕过主仓事实。

主仓实现入口：

```text
backend/app/api/routes/external/
backend/app/core/external_operations.py
backend/app/schemas/external_api.py
tests/contracts/
```

## 3. 公共边界

### 3.1 HTTP 前缀

所有外部接入统一使用：

```text
/api/v1
```

禁止重新引入 `/api/external/v1`。Endpoint 配置值只保存 Backend 根地址，公共前缀由客户端拼接。

### 3.2 认证和工作空间

MVP 使用 PAT Bearer：

```http
Authorization: Bearer wp_pat_...
X-Workspace-ID: <workspace_id>
```

工作空间 Header 是资源访问上下文，不是权限替代品。Backend 必须同时校验：

- PAT 用户身份和有效期；
- PAT 所有者的工作空间授权；
- 目标对象的工作空间归属；
- 当前 operation 所需 Scope。

无权对象统一按平台错误契约隐藏其存在性，外部接入不得通过错误差异探测其他工作空间。

### 3.3 Scope

外部接入直接复用以下 Scope，不新增 CLI 或 MCP 私有权限名：

| Scope | 责任范围 |
|---|---|
| `workspace:read` | 工作空间详情和能力矩阵 |
| `project:read` / `project:write` | 项目读取、创建、修改和归档 |
| `page:read` / `page:write` | 页面读取、创建、编辑和归档 |
| `component:read` / `component:write` | 组件读取、创建、编辑、发布和归档 |
| `asset:read` / `asset:write` | 资源读取、上传、内容/元数据更新和归档 |
| `design-system:read` / `design-system:write` | 主题、样式读取和维护 |
| `preview:run` | 页面截图和预览相关能力 |

具体 operation 使用的 Scope 以 `external_operations.py` 和 `/capabilities` 返回为准。

## 4. 自省接口

### 4.1 身份和能力

```text
GET /api/v1/auth/whoami
GET /api/v1/workspaces
GET /api/v1/workspaces/{workspace_id}
GET /api/v1/workspaces/{workspace_id}/capabilities
```

`capabilities` 返回当前 Token 在指定空间可用的 Scope 和 operation。CLI 可以用它决定命令提示，MCP 可以用它决定工具是否披露；两者都不能把客户端判断当作最终授权。

`whoami` 明确返回用户公共信息、PAT 兼容 `token`、公共凭证来源 `credential` 与实时有效的授权空间列表。PAT 的 token 字段保留 `id/name/token_public_id/scopes/expires_at/all_workspaces`，credential.type 为 `pat`，另含 public_id 和 expires_at，不返回原始令牌。External 业务主体已与 PAT ORM 解耦；委托 DTO 预留独立的 Grant/客户端/服务来源，但当前 HTTP 认证仍只接受 PAT，OAuth 接入尚未开放。

### 4.2 规范和 OpenAPI

```text
GET /api/v1/standards/page
GET /api/v1/standards/component
GET /openapi.json
```

页面和组件规范由 Backend 发布；CLI 使用公开 OpenAPI 获取当前服务端的路径、参数和请求 Schema。CLI 仓库不复制 Backend DTO 或维护第二份静态 Schema。

公开 OpenAPI 的 External 路由包含版本 1 的 `x-wp-operation` 扩展，由实际鉴权依赖派生。静态操作声明 `key/public/required_scopes/scope_mode/workspace_header_required/idempotency_key_required`，同一操作的附加视图保留各自参数和响应。通用 Mutation status/cancel/retry 声明 `resolution=mutation_job_type`、action 与按 page/component 区分的 candidates，不提供一个可代替动态鉴权的静态 Scope。完整字段约定见[首批契约交接](../mcp-contract-handoff.md#3-m3-操作元数据)。

需要认证的 External 成功响应统一使用 `Cache-Control: private, no-store`，包括身份、规范、capabilities 和业务数据。公开 OpenAPI 可共享，但不能将用户相关能力和内容写入公共缓存。

页面源码响应为完整 `source_code` 加 `page_id/page_code/version_no`。组件 draft 返回完整 content/preview_schema 与 `current_version_no/draft_base_version_no/draft_hash`；编辑使用 current_version_no 作为 base_version_no、draft_hash 作为 base_draft_hash。依赖与资源差异复用已有响应 DTO。截图 200 明确为 image/png binary，携带 X-Page-ID 与 X-Page-Version-No；仍可能等待队列刷新，新增 Schema 不表示已经满足宿主时限。

## 5. 资源和任务契约

### 5.1 资源接口

主仓维护下列资源的路由、DTO、Scope 和错误语义：

```text
/api/v1/workspaces
/api/v1/projects
/api/v1/projects/{project_id}/pages
/api/v1/pages
/api/v1/components
/api/v1/assets
/api/v1/themes
/api/v1/styles
```

资源具体视图包括详情、源码/草稿、历史版本、资源内容、配置和路由树；是否公开某个视图以实际路由和 operation 注册表为准。

首版 CLI 使用的结构化资源接口包括：

```text
GET/PUT  /api/v1/projects/{project_id}/configuration
GET/PUT  /api/v1/projects/{project_id}/route-tree
POST     /api/v1/projects/{project_id}/apply-style
PUT      /api/v1/projects/{project_id}/build-assets
POST     /api/v1/pages
POST     /api/v1/pages/{page_id}/copy
POST     /api/v1/pages/{page_id}/edits
GET      /api/v1/pages/{page_id}/dependencies
GET      /api/v1/components/{component_id}/dependencies
POST     /api/v1/components/{component_id}/edits
POST     /api/v1/assets/content
GET/PUT  /api/v1/assets/{asset_id}/content
POST     /api/v1/assets/{asset_id}/content/preview
POST     /api/v1/assets/{asset_id}/copy
GET      /api/v1/assets/tags
GET      /api/v1/runtime-kit
GET      /api/v1/runtime-kit/{item}
GET      /api/v1/fonts
POST     /api/v1/validate/entity
```

`validate/entity` 的 `entity_type` 为 `page | component`，`mode` 为 `current | content | edits`。项目配置、路由树、主题、样式和资源内容写入均由 Backend Schema 最终校验。

样式创建 `POST /api/v1/styles` 同时接受规范的 `configuration.presentation` 嵌套配置和顶层完整展示字段；OpenAPI 请求 Schema 与该接口保持一致。

### 5.2 页面和组件重任务

页面、组件源码创建和编辑不得在外部接入层直接写数据库或启动 Runtime。必须使用持久化 Mutation Job：

```text
POST /api/v1/jobs/mutations/pages
POST /api/v1/jobs/mutations/pages/edits
POST /api/v1/jobs/mutations/components
POST /api/v1/jobs/mutations/components/edits
POST /api/v1/jobs/mutations/components/metadata
GET  /api/v1/jobs/mutations/{job_id}
POST /api/v1/jobs/mutations/{job_id}/cancel
POST /api/v1/jobs/mutations/{job_id}/retry
```

页面编辑必须携带当前版本基线；组件编辑必须携带草稿 hash 或主仓规定的等价乐观锁字段。外部客户端不得在 409 后静默覆盖重试。

组件省略的基线在首次受理时冻结，同键重放沿用原 Job 的值；显式基线变化仍是异载荷冲突。实体写入口与 `/jobs/mutations` 别名的幂等 operation 不同，响应丢失后应保持原 method/path/payload/key 恢复。命名空间映射及历史指纹兼容见 [External Mutation 边界](../backend/external-mutations.md)。

### 5.3 预览地址

```text
POST /api/v1/projects/{project_id}/preview-artifact
POST /api/v1/pages/{page_id}/preview-artifact
```

两条接口都创建短期 preview artifact，并返回复用统一字段的 `ExternalPreviewArtifactResponse`，其中
`preview_url` 是可直接交给浏览器打开的预览地址。项目接口可以传入可选请求体
`{"route": "/overview"}` 指定入口路由；不传时使用项目默认入口。页面接口不要求
CLI 拼接源码模块路径，Backend 会根据页面当前的 `code` 和 `file_type` 解析单页面入口。

项目预览要求 `project:read + preview:run`，页面预览要求 `page:read + preview:run`。
预览地址和其中的签名上下文均为短期有效，客户端不应持久化或当作永久发布地址。

成功响应必含 UTC ISO 8601 `expires_at`，与 URL 中票据的 `exp` 相同，且不晚于 artifact 缓存期限或原有一小时票据上限。客户端直接读取该字段，无需解析签名 URL；缓存清理或运行态失效可能使链接提前失效，该字段不承诺到期前持续可用。创建后元数据缺失/已到期返回 `410 PREVIEW_ARTIFACT_EXPIRED`，元数据损坏返回 `503 PREVIEW_ARTIFACT_METADATA_INVALID`，不猜测默认期限。

### 5.4 截图

```text
GET  /api/v1/pages/{page_id}/screenshot
```

截图任务由主仓通过预览队列完成；首版不暴露 Build 执行、构建状态、产物下载或 Restore operation。

### 5.4 幂等和归档

- 所有会改变业务数据或创建、取消、人工重试任务的请求必须遵守 operation 注册表中的 `Idempotency-Key` 要求。相同 key、operation 和请求指纹重放首次响应；不同请求复用 key 返回 409；首个请求仍在执行时返回 409、`Retry-After` 和可重试标记。
- 校验等纯只读请求不应伪造写入幂等语义。
- 外部 Agent 只使用归档，不提供永久硬删除。
- 单对象归档和批量归档的确认、原子性、数量上限由主仓契约定义。
- 归档后的对象退出默认查询和操作边界；首版不提供 Restore operation。
- 页面/组件单项归档允许原有效 key 恢复原成功响应，重放仍检查当前用户、Scope 和空间权限；新 key 不恢复已归档对象。

## 6. 错误和状态

外部接入应保留 Backend 的业务错误码，不把所有失败压成通用异常。至少保持以下语义：

| 情况 | 外部客户端处理 |
|---|---|
| 401 | 未认证或访问凭证无效，不自动重试 |
| 403 | Scope 或工作空间授权不足 |
| 404 | 对象不存在或不属于当前空间 |
| 409 | 版本、草稿、状态或幂等冲突，重新读取后再决定 |
| 422 | 请求 Schema 或业务参数错误 |
| 429 | 仅按 `Retry-After` 和客户端策略有限重试 |
| 5xx/网络失败 | 仅对安全的幂等读操作有限重试 |
| Job 失败 | 保留 Job 状态、业务错误码和诊断摘要 |

Mutation 对外状态固定为 `pending | running | succeeded | failed | canceled`。`attempt_count` 表示已执行的自动重试次数，`max_attempts` 包含首次执行；自动重试沿用同一 `job_id`，人工重试创建新任务并通过 `retry_of_job_id` 关联原任务。running 取消是协作式取消，Worker 可以完成诊断，但必须在业务写入前收敛为 canceled。

running 取消的 202 响应仍为 running，通过 `cancel_requested_at` 表示请求已登记。failed 查询仍返回 HTTP 200；人工 retry 仅允许可重试失败并保留原编辑基线。已受理 Job 不因客户端断连、凭证到期或 Grant 撤销自动取消，后续管理请求仍需有效授权。

## 7. 已知契约问题

页面/组件安全元数据 PATCH、Mutation 状态/取消/重试/幂等契约已冻结；首版明确排除 Build 执行、产物下载、Restore、图片能力和 Agent 运行。

## 8. 变更流程和测试归属

### 主仓变更

以下变更必须先在主仓完成：

- 路径、HTTP 方法、请求/响应 DTO；
- Scope、Header、幂等要求；
- 错误码、状态和取消语义；
- `/standards/*`、`/capabilities` 和 OpenAPI 字段；
- 版本、归档和工作空间隔离规则。

主仓至少运行：

```powershell
pnpm run test:contracts
```

### CLI / MCP 仓库变更

以下内容分别由 CLI 与 MCP 仓库维护：

- CLI 命令名、Click 参数、Profile 和终端输出；
- 各仓专用客户端的传输适配和轮询封装；
- MCP Tool、Resource、Prompt、传输和结构化结果；
- Skill 工作流和调用检查点；
- CLI/MCP MockTransport、协议和适配测试。

CLI 仓库至少运行：

```powershell
uv run pytest
uv run --project packages/cli wp --help
```

MCP 仓库独立运行 `uv run pytest`、`uv run wp-mcp --help` 和构建；完整协议、OAuth 与媒体门禁以 MCP 实施计划为准。

### 联动顺序

1. 主仓先修改并测试 External API 契约。
2. 主仓更新本文和对应 operation 注册表。
3. 主仓在 PR 或发布说明中标注需要升级的 CLI/MCP 适配。
4. CLI/MCP 仓库分别更新自己的实现与契约测试。
5. 联调目标主仓版本，确认旧客户端兼容或明确最低版本。

## 9. 相关文档

- 主仓 CLI 集成边界：[docs/developer/cli.md](../cli.md)
- 主仓 MCP 集成边界：[docs/developer/mcp.md](../mcp.md)
- CLI 实施矩阵：[web-presentation-cli/docs/cli-capability-completion.md](https://github.com/LLMxPM/web-presentation-cli/blob/master/docs/cli-capability-completion.md)
- MCP 规划参考：[web-presentation-mcp/docs/mcp-implementation-plan.md](https://github.com/LLMxPM/web-presentation-mcp/blob/main/docs/mcp-implementation-plan.md)
- 主仓 AI 工具规格：[docs/developer/backend/ai-tool-specs.md](../backend/ai-tool-specs.md)（仅平台内部 Agent，不作为 External API 契约）
