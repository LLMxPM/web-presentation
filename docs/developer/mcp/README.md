# MCP 服务落地规划

## 1. 文档状态

- 状态：规划稿
- 适用范围：`web-presentation` 对外提供 MCP Server
- 目标读者：Backend、平台架构、部署和测试维护者
- 规划基线：2026-08

本文规划把平台现有 External API v1 适配为 MCP 服务，供 Claude、Cursor、ChatGPT 及其他 MCP Client 调用。MCP Server 只负责协议适配、上下文约束和结果格式化，业务权限、数据校验和任务执行仍由 Backend 负责。

统一命名约定：对外 HTTP 接口的公共前缀为 `/api/v1`，能力名称称为 **External API v1**。`backend/app/api/routes/external/` 和 `external_operations` 是 Backend 内部实现命名，不作为对外 URL 的组成部分；MCP Server、CLI 和相关文档都必须遵循该公共前缀。

## 2. 结论与推荐方案

代码已放入同级独立仓库 `web-presentation-agent-kit/mcp-server/`，作为独立的 `mcp-server/` Python 服务，通过 HTTPS 调用 Backend 的 `/api/v1` External API：

```text
MCP Client
    |
    | MCP Streamable HTTP
    v
独立 mcp-server
    |
    | Bearer PAT/OAuth + X-Workspace-ID + Idempotency-Key
    v
Backend /api/v1
    |
    +-- PAT、Scope、成员状态和工作空间隔离
    +-- 页面/组件异步 Mutation Job
    +-- 校验、截图、构建和资源服务
```

不建议第一阶段把 MCP 工具直接接入 Backend 内部 Service 或数据库，原因是：

1. 复用现有 External API 的权限、幂等和错误契约，避免出现第二套安全边界。
2. MCP Server 可以独立部署、升级和限流，不影响 Editor 和 Backend 主链路。
3. CLI、MCP 和未来其他 Agent 接入都可以共享 `/api/v1` 契约。
4. 页面和组件重任务继续经过已有持久化队列，不在 MCP 请求线程内启动 Runtime 或 Chromium。

MCP 当前生产传输应优先使用 Streamable HTTP；旧的 HTTP+SSE 传输已被新规范替代。若只支持本机桌面 Agent，可以额外提供 stdio 启动方式。[MCP Transport 规范](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)

## 3. 当前基础与边界

### 3.1 已有能力

- External API v1 已覆盖工作空间、项目、页面、组件、资源、主题、样式、校验、构建和 Mutation Job。
- PAT 已具备哈希存储、过期、吊销、使用记录和失败限速机制。
- External API 已通过 Scope 和 `X-Workspace-ID` 约束访问边界。
- 写操作已使用 `Idempotency-Key`，页面/组件重任务已进入异步 Job。
- 页面和组件支持版本号、草稿 hash 等乐观锁约束。
- 平台采用归档语义，不向外部 Agent 暴露永久删除能力。

相关实现入口：

- [External API 路由聚合](../../../backend/app/api/routes/external/__init__.py)
- [External API 鉴权依赖](../../../backend/app/api/dependencies_external.py)
- [External 操作注册表](../../../backend/app/core/external_operations.py)
- [External API DTO](../../../backend/app/schemas/external_api.py)
- [CLI 技术方案](../cli/README.md)

### 3.2 当前缺口

- `web-presentation-agent-kit` 已引入 MCP Python SDK 和独立 MCP Server 目录，当前先提供只读 Tools/Resource 骨架。
- PAT 是平台自有 Bearer 凭证，并非完整 OAuth Authorization Server。
- External API 的工作空间上下文通过 HTTP Header 传递，MCP 工具需要显式承接该上下文。
- MCP 工具、资源、Prompt、错误码和异步任务结果仍处于只读契约收敛阶段。
- 尚未有 MCP Inspector、真实客户端连接和跨工作空间隔离测试。

### 3.3 非目标

第一阶段不包含以下内容：

- 将平台内部 Pydantic AI Agent 暴露为 MCP Tool。
- 通过 MCP 暴露模型供应商、API Key、AI 会话、Run 或 HITL 内部状态。
- MCP Server 直接访问数据库、Redis、Runtime 或对象存储。
- 自动把 External API 的全部操作无审核地生成 MCP 工具。
- 依赖 MCP Client 的确认弹窗代替服务端权限控制。

## 4. 分阶段产品范围

### 阶段一：只读与校验 MVP

目标是让桌面 Agent 能理解平台结构、读取创作上下文并校验候选源码。

建议工具：

| MCP Tool | 能力 | Backend 映射 |
| :--- | :--- | :--- |
| `wp_list_workspaces` | 查询 Token 可访问工作空间 | `GET /api/v1/workspaces` |
| `wp_get_workspace` | 查询工作空间详情 | `GET /api/v1/workspaces/{workspace_id}` |
| `wp_get_workspace_capabilities` | 查询当前 Scope 和能力 | `GET /api/v1/workspaces/{workspace_id}/capabilities` |
| `wp_list_projects` | 查询项目列表 | `GET /api/v1/projects` |
| `wp_get_project` | 查询项目详情和路由 | `GET /api/v1/projects/{project_id}` |
| `wp_list_pages` | 查询项目页面 | `GET /api/v1/projects/{project_id}/pages` |
| `wp_get_page` | 查询页面元数据 | `GET /api/v1/pages/{page_id}` |
| `wp_get_page_source` | 查询页面源码 | `GET /api/v1/pages/{page_id}/source` |
| `wp_list_components` | 查询工作空间组件 | `GET /api/v1/components` |
| `wp_get_component` | 查询组件元数据 | `GET /api/v1/components/{component_id}` |
| `wp_get_component_draft` | 查询组件草稿源码 | `GET /api/v1/components/{component_id}/draft` |
| `wp_list_assets` | 查询资源元数据 | `GET /api/v1/assets` |
| `wp_get_asset` | 查询资源详情或文本内容 | `GET /api/v1/assets/{asset_id}` |
| `wp_get_page_standards` | 获取页面开发规范 | `GET /api/v1/standards/page` |
| `wp_get_component_standards` | 获取组件开发规范 | `GET /api/v1/standards/component` |
| `wp_get_operation_guide` | 获取操作手册和参数说明 | `GET /api/v1/guides` |
| `wp_validate_source` | 校验候选页面/组件源码 | `POST /api/v1/validate/code` |

估算：5～8 人日。

### 阶段二：受控写入与异步任务

目标是支持 Agent 创建和修改页面、组件，并能可靠获取任务结果。

建议增加：

- `wp_create_page_job`
- `wp_apply_page_edits_job`
- `wp_create_component_job`
- `wp_apply_component_edits_job`
- `wp_get_mutation_job`
- `wp_cancel_mutation_job`
- `wp_update_project`
- `wp_update_theme`
- `wp_update_style`
- `wp_archive_entity`

约束：

- MCP Server 必须为每个写请求生成稳定的 `Idempotency-Key`，并在重试时复用。
- 页面和组件源码写入必须携带 `base_version_no` 或 `base_draft_hash`。
- 创建/修改页面和组件只返回任务受理结果，不能绕过 Mutation Job 直接写库。
- 批量归档默认不作为第一批工具；若开放，必须保持整批原子语义。
- 工具返回 `job_id`、当前状态、目标对象和下一步建议，避免模型误以为任务已经完成。

估算：5～8 人日。

### 阶段三：视觉复核、构建与资源交付

目标是支持完整的“生成—校验—截图—构建”闭环。

建议增加：

- `wp_get_latest_screenshot`
- `wp_start_build`
- `wp_get_build_status`
- `wp_download_build_artifact`
- `wp_upload_asset`
- `wp_get_asset_content`

图片、截图和构建包不建议直接塞入普通 JSON 文本。优先返回受保护的短期下载地址或 MCP Resource Link；文本类资源才直接返回内容。资源下载仍必须经过 Backend 的 DeliveryAccessContext，不得暴露永久公开地址。

估算：4～8 人日，取决于是否需要图片内容在不同 MCP Client 中稳定展示。

### 阶段四：OAuth 与生态化接入

目标是让用户可以在远程 MCP Client 中完成标准授权，而不是手工复制 PAT。

需要建设：

- OAuth Authorization Server 或现有账户系统的 OAuth 适配层。
- Protected Resource Metadata 和 Authorization Server Metadata。
- Authorization Code + PKCE。
- MCP Server audience/resource 校验。
- OAuth Token 到平台用户、工作空间和 Scope 的映射。
- Token 撤销、刷新、审计和异常回收。
- 不同 MCP Client 的连接回归测试。

MCP HTTP 授权规范要求使用 Bearer Token，并以 OAuth 2.1、RFC 8414、RFC 7591、RFC 8707 和 RFC 9728 等机制完成发现与资源约束。[MCP Authorization 规范](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)

估算：5～10 人日；若账户体系没有可复用的 OAuth 能力，需单独评审。

## 5. 认证和工作空间设计

### 5.1 MVP：PAT 模式

面向内部部署、开发环境和支持手工配置 Header 的 MCP Client，第一版可采用：

```text
Authorization: Bearer wp_pat_...
X-Workspace-ID: 123
```

MCP Server 不解析或复制平台用户权限逻辑，只把 PAT 和工作空间上下文传给 `/api/v1`，由 Backend 负责最终校验。

对于 stdio 模式，凭证通过环境变量或本地配置注入：

```text
WP_API_BASE_URL=https://presentation.example.com
WP_PAT=wp_pat_...
WP_WORKSPACE_ID=123
```

Token 不得出现在工具返回、异常消息、日志、MCP Resource URI 或 telemetry 事件中。

### 5.2 工作空间上下文

第一版要求以下二选一，并且服务端只能选择一种模式，不能静默混用：

1. **显式模式**：每个工具参数包含 `workspace_id`，适合一个 Token 授权多个空间。
2. **绑定模式**：MCP 进程或连接只绑定一个工作空间，工具参数不重复传递。

推荐第一版使用显式模式，原因是更容易审计、重试和防止上下文漂移。所有项目、页面、组件和资源 ID 都必须再次由 Backend 校验其工作空间归属。

### 5.3 Scope 映射

MCP 工具不新增第二套权限命名，直接复用 External API Scope：

| 能力 | Scope |
| :--- | :--- |
| 工作空间读取 | `workspace:read` |
| 项目读取/写入 | `project:read` / `project:write` |
| 页面读取/写入 | `page:read` / `page:write` |
| 组件读取/写入 | `component:read` / `component:write` |
| 资源读取/写入 | `asset:read` / `asset:write` |
| 主题和样式 | `design-system:read` / `design-system:write` |
| 源码校验 | `page:read` 或 `component:read` |
| 构建和预览 | `build:run` / `preview:run` |

## 6. MCP 工具契约原则

### 6.1 命名和说明

- 工具名使用 `wp_` 前缀，避免与其他 MCP Server 冲突。
- 工具描述必须写清工作空间、对象归属、版本基线、是否产生写入和是否返回异步任务。
- 工具输入 Schema 优先从现有 Pydantic DTO 派生，不能在 MCP 层复制一套不一致的业务校验。
- 不把内部表名、Redis Key、Agent Run ID 或 Runtime 内部类型暴露给模型。

### 6.2 返回结构

工具返回应同时提供适合模型阅读的文本摘要和机器可读的结构化结果：

```json
{
  "summary": "页面源码校验通过，没有发现错误。",
  "data": {
    "valid": true,
    "errors": [],
    "warnings": [],
    "imports": []
  },
  "request_id": "..."
}
```

长源码、长日志和大列表必须支持分页、字段裁剪或按需读取，避免一次工具调用把完整工作空间上下文注入模型。

### 6.3 错误映射

MCP 层不吞掉 Backend 错误码。建议保留：

- `code`：原始业务错误码。
- `message`：面向模型的简洁说明。
- `retryable`：是否适合自动重试。
- `details`：版本冲突、缺失 Scope、任务状态等结构化信息。

典型处理：

| Backend 情况 | MCP 行为 |
| :--- | :--- |
| 401 | 返回未认证错误，不自动重试 |
| 403 | 返回缺少 Scope 或工作空间授权错误 |
| 404 | 返回对象不存在；不得泄露其他工作空间对象存在性 |
| 409 | 返回版本冲突或幂等键冲突，要求模型重新读取 |
| 429 | 标记可重试，并尊重 `Retry-After` |
| 5xx/网络失败 | 仅对幂等读操作自动有限重试 |
| 异步任务失败 | 返回任务错误码和诊断摘要，不伪装为 MCP 协议错误 |

## 7. 服务目录和代码结构

建议新增独立 Python 包：

```text
mcp-server/
├── pyproject.toml
├── src/web_presentation_mcp/
│   ├── main.py                 # stdio / Streamable HTTP 启动入口
│   ├── settings.py             # API 地址、凭证、超时和限流配置
│   ├── auth.py                 # PAT/OAuth 上下文解析
│   ├── client/
│   │   ├── backend_client.py   # httpx 请求、错误和重试
│   │   └── job_client.py       # Mutation/Build 状态轮询
│   ├── tools/
│   │   ├── workspace.py
│   │   ├── project.py
│   │   ├── page.py
│   │   ├── component.py
│   │   ├── asset.py
│   │   ├── validation.py
│   │   └── jobs.py
│   ├── resources.py             # 规范、指南和受控资源引用
│   ├── prompts.py               # 可选的创作流程 Prompt
│   ├── schemas.py                # MCP 输入输出模型
│   └── errors.py
└── tests/
    ├── unit/
    ├── contract/
    └── e2e/
```

目录中的每个源代码文件应包含中文功能描述，函数补充职责、输入输出和关键约束注释；依赖使用 `uv` 管理。

工具注册采用显式 allowlist，不使用“扫描所有 API 路由并自动暴露”的方式。工具说明可以从 `external_operations.py` 和对应 Pydantic DTO 生成基础内容，但最终披露列表必须经过人工审核。

## 8. 传输和部署

### 8.1 stdio

适用场景：本机 Claude Desktop、Cursor、内部开发和单用户使用。

- MCP Client 启动 `mcp-server` 子进程。
- stdout 只能输出 MCP JSON-RPC 消息。
- 日志写 stderr 或文件。
- Token 从环境变量、系统凭据库或 MCP Client 配置注入。
- 默认只允许绑定一个工作空间。

### 8.2 Streamable HTTP

适用场景：团队共享服务、远程客户端、云部署和多实例部署。

- 独立暴露 `/mcp` 端点。
- 生产环境使用 HTTPS。
- 校验 `Origin`，防止 DNS rebinding。
- 使用请求级认证，不把认证状态仅绑定在进程内存会话上。
- 需要明确负载均衡、超时、限流、审计和健康检查策略。
- 若使用 SDK 的有状态会话能力，必须评估多实例下的会话存储；MVP 优先采用无状态请求和 Backend 持久化任务。

官方 SDK 支持将 Streamable HTTP MCP App 挂载到已有 ASGI 应用，但本项目第一阶段仍推荐独立服务，以便隔离 MCP 的连接、限流和部署生命周期。[官方 Python SDK：ASGI 挂载](https://github.com/modelcontextprotocol/python-sdk)

## 9. 安全设计

上线前必须完成以下安全约束：

- Backend 继续作为最终鉴权点，MCP 层不能自行判断“看起来属于当前空间”就放行。
- 读写 Scope 分离，默认 Token 只开读取和校验权限。
- 工作空间 ID、项目 ID、页面 ID、组件 ID 交叉校验。
- 所有写操作必须使用幂等键；重试不能产生重复页面、组件或资源。
- 页面/组件源码写入必须做版本复核，拒绝覆盖其他 Agent 或用户的新版本。
- 永久删除、数据库操作、任意 Runtime/Chromium 调用不进入 MCP 工具目录。
- 限制工具参数大小、源码大小、分页大小、轮询次数和单请求耗时。
- 限制资源下载地址有效期，日志脱敏 Authorization 和 Token。
- 记录 `request_id`、用户、Token public id、工作空间、工具名、目标对象、结果状态和耗时。
- 对异常工具调用、跨工作空间访问、Scope 失败和高频写操作提供告警。

MCP Client 的工具确认只能作为用户体验层提示，不能作为服务端安全控制。远程 HTTP MCP 若采用标准授权，还需校验 Token 是否专门签发给当前 MCP Server，避免 Token 转发和 confused deputy 风险。

## 10. 测试计划

### 10.1 单元测试

- MCP 输入 Schema 到 External API DTO 的转换。
- `workspace_id` 注入和冲突拒绝。
- PAT/OAuth 上下文解析和日志脱敏。
- Backend 错误到 MCP 结构化错误的映射。
- 幂等键生成、重试和超时策略。
- 异步 Job 状态归一化。

### 10.2 协议和契约测试

- `initialize`、能力协商、`tools/list`、`tools/call`。
- 工具说明、输入 Schema 和结构化输出稳定性。
- Streamable HTTP 的 POST、GET、断开重连和不支持版本处理。
- MCP Inspector 连接和工具调用。
- External API Scope、DTO、错误码变化触发 MCP 契约失败。

### 10.3 安全测试

- 缺少 Token、Token 过期、吊销、错误 Token。
- Token 缺少读/写 Scope。
- Token 授权工作空间与请求工作空间不一致。
- A 空间资源 ID 访问 B 空间。
- 版本冲突和重复幂等键。
- Origin 校验、CORS、请求体大小、速率限制和敏感信息日志检查。

### 10.4 端到端测试

至少覆盖以下闭环：

1. 连接 MCP Server。
2. 查询授权工作空间和能力。
3. 查询项目、页面、组件和规范。
4. 读取页面源码并调用 `wp_validate_source`。
5. 提交页面创建或源码修改 Job。
6. 轮询 Job 到成功或失败。
7. 使用旧版本再次修改，确认返回版本冲突。
8. 启动构建并读取构建状态。
9. 尝试跨工作空间读取和写入，确认被拒绝。

建议命令：

```powershell
uv run --project mcp-server pytest
pnpm run test:backend:api
pnpm run test:contracts
pnpm run test:e2e:run
```

## 11. 里程碑和工作量

| 里程碑 | 交付物 | 估算 |
| :--- | :--- | ---: |
| M0 方案冻结 | 工具 allowlist、鉴权模式、工作空间模式、错误契约 | 1～2 人日 |
| M1 只读 MVP | 独立服务、stdio、17 个左右只读/校验工具、单元测试 | 4～6 人日 |
| M2 远程接入 | Streamable HTTP、部署配置、PAT、限流、Inspector 验证 | 2～4 人日 |
| M3 受控写入 | 页面/组件 Job、幂等、版本冲突、任务查询和取消 | 5～8 人日 |
| M4 视觉交付 | 截图、构建、资源引用和大文件策略 | 4～8 人日 |
| M5 生态化 | OAuth、标准授权发现、多客户端回归和运维指标 | 5～10 人日 |

建议先完成 M0～M2，再根据真实客户端和用户场景决定是否马上进入 M3。只读版本预计 1～2 周可交付；完整生产版预计 4～8 周，具体取决于 OAuth、图片资源和部署要求。

## 12. 验收标准

### MVP 验收

- 本地 stdio MCP Client 可连接并完成 `initialize`、`tools/list`、`tools/call`。
- 远程 Streamable HTTP 端点可通过 HTTPS 访问。
- Token、Scope 和工作空间隔离行为与 External API 一致。
- 至少覆盖项目、页面、组件、资源、规范和源码校验能力。
- 工具错误包含稳定业务错误码，不泄露内部堆栈和凭证。
- MCP Server 不直接依赖 Backend 数据库、Redis、Runtime 或 Chromium。
- 现有 Backend API、契约和 E2E 测试不回归。

### 生产版验收

- 页面/组件写操作具备异步任务、幂等重试和乐观锁冲突处理。
- 截图、构建和资源交付具备短期授权和大文件保护。
- 远程客户端可通过 OAuth 完成授权，或明确记录仅支持手工 PAT 的客户端范围。
- 具备请求审计、失败告警、速率限制和健康检查。
- 完成至少两种真实 MCP Client 的连接和创作闭环测试。

## 13. 待决策事项

实施前需要确认：

1. 首发目标是本地 stdio，还是公网 Streamable HTTP？
2. 是否要求 Claude/ChatGPT 等客户端出现标准 OAuth 授权页面？
3. MCP Server 是单独域名部署，还是与 Backend 同域？
4. 第一版是否需要写入能力，还是先只读和源码校验？
5. 多工作空间 Token 是否允许一个 MCP 连接切换空间？
6. 图片、截图和构建产物是返回短期 URL，还是只提供元数据？
7. 是否需要把规范和操作指南作为 MCP Resources/Prompts 暴露，还是先作为普通 Tools？

默认建议：首发使用“独立服务 + Streamable HTTP + PAT + 显式 workspace_id + 只读/校验工具”，验证真实客户端和调用方式后，再投入 OAuth 和全量写入。
