# MCP 主仓集成边界

本文档只说明主仓库 `web-presentation` 对 MCP 的平台侧约束。MCP Server 的工具实现、协议适配和发布流程由同级仓库 `web-presentation-agent-kit` 负责。

## 1. 权责边界

| 范围 | 负责方 | 说明 |
| --- | --- | --- |
| Backend `/api/v1` External API v1 | 主仓库 | 资源、页面、组件、主题、样式、构建任务等平台接口契约 |
| MCP 工具、参数映射和 transport | agent-kit | 将 MCP 调用映射为主仓库 API 请求，并维护 MCP 运行态行为 |
| MCP Server 配置与发布 | agent-kit | 负责本地启动、远程部署和版本兼容说明 |
| 跨仓库契约测试 | 双方 | 主仓库验证 API 契约，agent-kit 验证工具到 API 的映射 |

主仓库的 API 事实源是[External API v1 契约](./reference/external-agent-api.md)，不要在此文档复制 MCP 工具清单、参数 Schema 或返回示例。

MCP 的实施细节见 agent-kit 的[实施计划](../../../web-presentation-agent-kit/docs/mcp-implementation-plan.md)；工具级说明以 agent-kit 的 MCP 文档和源码为准。

## 2. MCP 依赖的主仓能力

MCP Server 依赖以下平台能力，但不在主仓库登记 MCP 工具：

- 身份认证与工作空间边界：`/api/v1/auth/*`、`/api/v1/workspaces/*`。
- 项目、页面和源码：项目、页面查询，以及页面源码的创建、更新、归档。
- 资源、组件、主题和样式：列表、详情、导入、创建、更新和归档。
- 指导与规范：`/api/v1/guides`、`/api/v1/standards`。
- 构建与任务：预览/构建任务创建、状态查询、产物下载信息。

具体路径、请求体、响应体、权限和错误语义统一以[External API v1 契约](./reference/external-agent-api.md)为准。

## 3. 主仓库变更要求

当 Backend 调整 MCP 会调用的接口时：

1. 先更新[External API v1 契约](./reference/external-agent-api.md)，明确路径、入参、出参、权限、错误和幂等语义。
2. 补充主仓库的 API、契约或集成测试。
3. 在 agent-kit 更新 MCP 工具的映射、Schema、说明和测试。
4. 联调认证、工作空间隔离、确认语义、错误透传和长任务状态。
5. 发现接口与 MCP 实现不一致时，优先修复契约或实现，不在两份文档中长期保留不同口径。

主仓库只维护平台 API 的兼容性和服务端行为；不要为了 MCP 的单一调用场景，把 MCP 协议细节反向放入 Backend 的工具注册表。

## 4. 当前已知接口缺口

以下问题属于主仓库 External API 或其实现的待补齐项，agent-kit 应在实现计划中跟踪适配：

- 页面与组件更新接口的正式写入路径及请求体仍需稳定。
- `/guides` 的结构化 Schema 和版本策略仍需明确。
- 构建产物下载 URL、鉴权方式和过期语义需要统一。
- 长任务状态、取消、重试与幂等键的组合语义需要通过契约测试固定。

缺口补齐后，先改本文件引用的共享契约，再由 agent-kit 更新 MCP 实施文档和代码。
