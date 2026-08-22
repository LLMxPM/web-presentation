# External API v1 契约与外部 Agent 接入边界

## 1. 文档归属

本文是 `web-presentation` 主仓库维护的 External API v1 契约文档，服务于同级独立仓库 `web-presentation-agent-kit` 的 CLI、MCP Server 和 Skill。

本文只维护平台侧事实：

- External API v1 的公开边界、路径和版本策略；
- PAT、Scope、工作空间隔离和错误语义；
- 页面、组件、资源、主题、样式和 Mutation Job 的后端契约；
- `/guides`、`/standards/*`、`/capabilities` 等自省接口；
- 主仓库契约测试、兼容性和变更流程。

本文不维护以下内容：

- `wp` CLI 的 Click 命令、参数、终端输出和本地 Profile；
- MCP Tool、Resource、Prompt、传输和协议输出；
- Agent Skill 的工作流提示词；
- agent-kit 的 Python 模块结构、发布方式和本仓测试。

对应实现文档：

- CLI 实现：`web-presentation-agent-kit/docs/cli-capability-completion.md`
- MCP 实现：`web-presentation-agent-kit/docs/mcp-implementation-plan.md`
- Skill：`web-presentation-agent-kit/skills/web-presentation/SKILL.md`

如果本地两个仓库位于同级目录，可直接从主仓文档跳转到 `../../../../web-presentation-agent-kit/docs/cli-capability-completion.md`；远程镜像应使用 agent-kit 仓库的对应路径。

## 2. 唯一事实源

External API 契约的优先级如下：

1. Backend 实际路由、Pydantic 请求/响应模型和鉴权依赖；
2. `backend/app/core/external_operations.py` 中的 operation 注册表；
3. `tests/contracts/` 中的跨模块契约测试；
4. 本文的语义说明和变更记录。

当本文与代码或契约测试冲突时，先修正主仓契约，再通知 agent-kit 更新适配；不得由 CLI 或 MCP 猜测并绕过主仓事实。

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

### 4.2 规范和操作指南

```text
GET /api/v1/standards/page
GET /api/v1/standards/component
GET /api/v1/guides
GET /api/v1/guides/{operation_key}
```

`/guides` 返回带 `api_version=v1`、`guide_schema_version=1`、`operation_revision` 和 `detail_url` 的轻量索引；详情接口返回 method、path、Scope、必需 Header、幂等规则、成功状态、错误码及 External API 专属 DTO 生成的请求/响应 JSON Schema。两者只要求有效 PAT，不要求工作空间 Header，也不是 Backend 内部 AI `tool_specs.py` 的公开镜像。

规范和指南由 Backend 发布，agent-kit 不应复制为长期本地业务数据或静态提示词。

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

### 5.3 截图

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

## 6. 错误和状态

外部接入应保留 Backend 的业务错误码，不把所有失败压成通用异常。至少保持以下语义：

| 情况 | 外部客户端处理 |
|---|---|
| 401 | 未认证或 PAT 无效，不自动重试 |
| 403 | Scope 或工作空间授权不足 |
| 404 | 对象不存在或不属于当前空间 |
| 409 | 版本、草稿、状态或幂等冲突，重新读取后再决定 |
| 422 | 请求 Schema 或业务参数错误 |
| 429 | 仅按 `Retry-After` 和客户端策略有限重试 |
| 5xx/网络失败 | 仅对安全的幂等读操作有限重试 |
| Job 失败 | 保留 Job 状态、业务错误码和诊断摘要 |

Mutation 对外状态固定为 `pending | running | succeeded | failed | canceled`。`attempt_count` 表示已执行的自动重试次数，`max_attempts` 包含首次执行；自动重试沿用同一 `job_id`，人工重试创建新任务并通过 `retry_of_job_id` 关联原任务。running 取消是协作式取消，Worker 可以完成诊断，但必须在业务写入前收敛为 canceled。

## 7. 已知契约问题

页面/组件安全元数据 PATCH、版本化 Guides、Mutation 状态/取消/重试/幂等契约已冻结；首版明确排除 Build 执行、产物下载、Restore、图片能力和 Agent 运行。

## 8. 变更流程和测试归属

### 主仓变更

以下变更必须先在主仓完成：

- 路径、HTTP 方法、请求/响应 DTO；
- Scope、Header、幂等要求；
- 错误码、状态和取消语义；
- `/guides`、`/standards/*`、`/capabilities` 字段；
- 版本、归档和工作空间隔离规则。

主仓至少运行：

```powershell
pnpm run test:contracts
```

### agent-kit 变更

以下内容只在 agent-kit 维护：

- CLI 命令名、Click 参数、Profile 和终端输出；
- 共享 API Client 的传输适配和轮询封装；
- MCP Tool、Resource、Prompt、传输和结构化结果；
- Skill 工作流和调用检查点；
- CLI/MCP MockTransport、协议和适配测试。

agent-kit 至少运行：

```powershell
uv run pytest
uv run --project packages/cli wp --help
```

### 联动顺序

1. 主仓先修改并测试 External API 契约。
2. 主仓更新本文和对应 operation 注册表。
3. 主仓在 PR 或发布说明中标注需要升级的 agent-kit 适配。
4. agent-kit 更新 CLI/MCP 实现和本仓测试。
5. 联调目标主仓版本，确认旧客户端兼容或明确最低版本。

## 9. 相关文档

- 主仓 CLI 集成边界：`docs/developer/cli.md`
- 主仓 MCP 集成边界：`docs/developer/mcp.md`
- [CLI 实施](../../../../web-presentation-agent-kit/docs/cli-capability-completion.md)（本地同级工作区）
- [MCP 实施](../../../../web-presentation-agent-kit/docs/mcp-implementation-plan.md)（本地同级工作区）
- 主仓 AI 工具规格：`docs/developer/backend/ai-tool-specs.md`（仅平台内部 Agent，不作为 External API 契约）
