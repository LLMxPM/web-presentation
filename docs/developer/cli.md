# CLI 主仓集成边界

## 1. 文档归属

本文由 `web-presentation` 主仓维护，只描述 Backend 对外 CLI 接入必须遵守的 External API v1 契约和协作边界。

本文不维护 `wp` CLI 的具体命令实现、Click 参数、Profile 文件、终端格式、MCP Tool 或 Skill 工作流。那些内容属于同级独立仓库 `web-presentation-agent-kit`：

- [CLI 实施文档](../../../web-presentation-agent-kit/docs/cli-capability-completion.md)（本地同级工作区）
- CLI 源码：`web-presentation-agent-kit/packages/cli/`
- 共享客户端：`web-presentation-agent-kit/packages/api-client/`
- Skill：`web-presentation-agent-kit/skills/web-presentation/SKILL.md`

主仓统一契约正文见：[External API v1 契约与外部 Agent 接入边界](./reference/external-agent-api.md)。

## 2. 责任分工

| 内容 | 负责仓库 | 权威入口 |
|---|---|---|
| External API 路径、DTO、Scope、错误码 | `web-presentation` | `backend/app/api/routes/external/`、`backend/app/schemas/external_api.py` |
| operation 注册表和幂等要求 | `web-presentation` | `backend/app/core/external_operations.py` |
| 工作空间隔离和权限校验 | `web-presentation` | External API 鉴权依赖、契约测试 |
| Mutation Job 语义 | `web-presentation` | External API 路由、任务模型和契约测试 |
| CLI 命令和参数 | `web-presentation-agent-kit` | `packages/cli/src/wp/commands/` |
| CLI Profile、输出和退出码 | `web-presentation-agent-kit` | `packages/cli/` |
| HTTP、PAT、Header、幂等和轮询适配 | `web-presentation-agent-kit` | `packages/api-client/` |
| CLI 单元/适配测试 | `web-presentation-agent-kit` | `packages/cli/tests/`、`packages/api-client/tests/` |

原则是：主仓改变服务契约，agent-kit 适配实现；agent-kit 不通过复制主仓内部代码建立第二套业务事实。

## 3. CLI 的平台侧边界

CLI 是 External API v1 的外部客户端：

- 使用 `/api/v1`，禁止使用旧的 `/api/external/v1`；
- 使用 PAT Bearer 和 `X-Workspace-ID`；
- 由 Backend 最终校验用户、Scope、工作空间和对象归属；
- 页面、组件源码重任务必须进入持久化 Mutation Job；
- 写操作遵守 `Idempotency-Key` 和版本/hash 乐观锁；
- 外部接入只使用归档，不提供永久硬删除；
- 不直接访问数据库、Redis、Runtime、Chromium 或 Backend 内部 Service。

完整公共契约、错误语义、自省接口和已知契约问题统一维护在 [External API v1 契约文档](./reference/external-agent-api.md)。

## 4. 当前 CLI 接入范围

以下只是平台侧的能力边界索引，不是 CLI 命令清单；命令是否已实现以 agent-kit 实施文档和 `wp --help` 为准。

### 4.1 自省和基础能力

```text
GET /api/v1/auth/whoami
GET /api/v1/workspaces
GET /api/v1/workspaces/{workspace_id}
GET /api/v1/workspaces/{workspace_id}/capabilities
GET /api/v1/standards/page
GET /api/v1/standards/component
GET /api/v1/guides
GET /api/v1/guides/{operation_key}
GET /api/v1/system/version
GET /api/v1/system/health
GET /api/v1/runtime-kit
GET /api/v1/runtime-kit/{item}
GET /api/v1/fonts
```

### 4.2 核心资源

```text
/api/v1/projects
/api/v1/projects/{project_id}/pages
/api/v1/pages
/api/v1/components
/api/v1/assets
/api/v1/themes
/api/v1/styles
GET  /api/v1/projects/{project_id}/configuration
PUT  /api/v1/projects/{project_id}/configuration
GET  /api/v1/projects/{project_id}/route-tree
PUT  /api/v1/projects/{project_id}/route-tree
POST /api/v1/projects/{project_id}/apply-style
PUT  /api/v1/projects/{project_id}/build-assets
POST /api/v1/pages
POST /api/v1/pages/{page_id}/copy
POST /api/v1/pages/{page_id}/edits
GET  /api/v1/pages/{page_id}/dependencies
POST /api/v1/components/{component_id}/edits
GET  /api/v1/components/{component_id}/dependencies
POST /api/v1/assets/content
GET  /api/v1/assets/{asset_id}/content
PUT  /api/v1/assets/{asset_id}/content
POST /api/v1/assets/{asset_id}/content/preview
POST /api/v1/assets/{asset_id}/copy
GET  /api/v1/assets/tags
```

### 4.3 校验、截图和重任务

```text
POST /api/v1/validate/entity
GET  /api/v1/pages/{page_id}/screenshot
POST /api/v1/jobs/mutations/pages
POST /api/v1/jobs/mutations/pages/edits
POST /api/v1/jobs/mutations/components
POST /api/v1/jobs/mutations/components/edits
GET  /api/v1/jobs/mutations/{job_id}
POST /api/v1/jobs/mutations/{job_id}/cancel
POST /api/v1/jobs/mutations/components/metadata
POST /api/v1/components
POST /api/v1/components/{component_id}/validate
POST /api/v1/pages/{page_id}/validate
```

`POST /api/v1/styles` 的创建请求同时兼容规范的 `configuration.presentation` 嵌套配置和 CLI/样式详情使用的顶层完整展示字段（如 `page_width`、`theme_key`、`style_spec_markdown`）；两种写法最终归一化为同一份样式快照。

页面和组件实体校验支持 `current | content | edits` 三种模式；复杂 CLI 参数统一由 JSON 文件或 UTF-8 内容文件承载。Agent Session/Run/HITL、图片能力、Build 执行、产物下载和 MCP 不属于本期外部接口范围。

具体 operation、Scope、请求字段和响应字段以主仓代码和契约测试为准，不在本文复制完整 Schema。

## 5. CLI 适配变更流程

### 5.1 只改 agent-kit

以下变化不需要修改主仓文档：

- 增加或调整 Click 命令别名；
- 修改表格列、Rich 文案和本地退出码；
- 增加 Profile 命令或本地配置选项；
- 调整 API Client 的重试、超时和文件落盘实现，但不改变 HTTP 契约；
- 增加 CLI/MCP 本地测试。

### 5.2 必须先改主仓

以下变化必须先修改主仓 External API 契约并运行契约测试：

- API 路径、HTTP 方法、请求/响应字段；
- Scope、Workspace Header、幂等要求；
- 错误码、Job 状态、取消语义；
- 归档、工作空间隔离和文件大小限制；
- `/guides`、`/standards/*`、`/capabilities` 返回结构。

主仓完成后，再由 agent-kit 更新 CLI 实施文档、适配代码和测试。

## 6. 已知契约问题

页面/组件安全元数据 PATCH、版本化 Guides 详情，以及 Mutation 取消、人工重试和幂等组合语义已经冻结。首版不暴露 Build 执行、产物下载或 Restore 入口。

这些问题的详细记录和 agent-kit 阻塞关系见 [External API v1 契约文档](./reference/external-agent-api.md)。

## 7. 验证入口

主仓：

```powershell
pnpm run test:contracts
```

agent-kit：

```powershell
uv run pytest
uv run --project packages/cli wp --help
```

两边联调时，先锁定目标主仓版本，再运行 agent-kit 的 CLI 适配测试和真实 External API smoke；不要只依据单边文档判断兼容性。
