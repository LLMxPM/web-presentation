# MCP 主仓集成边界

本文档说明主仓库 `web-presentation` 对 MCP 的平台侧约束与集成规划。

> [!NOTE]
> 2026-10-05 首期 MCP 已实现十五个工具/75 分支，并完成 TLS 网关下真实页面/组件创作和 PNG、SQLite/PG 消费者联测。当前本地证据见[域名前本地验收](./testing/mcp-local-acceptance.md)；公网部署、ChatGPT consent 和 Linux 镜像实机尚未完成，不能宣称生产交付。

MCP Server 的工具实现、协议适配和发布流程由同级独立仓库 [web-presentation-mcp](https://github.com/LLMxPM/web-presentation-mcp) 负责。

## 1. 权责边界

| 范围 | 负责方 | 说明 |
| --- | --- | --- |
| Backend `/api/v1` External API v1 | 主仓库 | 资源、页面、组件、主题、样式、Mutation Job 等平台接口契约 |
| MCP 工具、参数映射和 transport | MCP 仓库 | 将 MCP 调用映射为主仓库 API 请求，并维护 MCP 运行态行为 |
| MCP Server 配置与发布 | MCP 仓库 | 负责本地启动、远程部署和版本兼容说明 |
| 跨仓库契约测试 | 双方 | 主仓库验证 API 契约，MCP 仓库验证工具到 API 的映射 |

主仓库的 API 事实源是[External API v1 契约](./reference/external-agent-api.md)，不要在此文档复制 MCP 工具清单、参数 Schema 或返回示例。

MCP 的远程认证、通用业务工具和分期安排见 MCP 仓库的[实施规划](https://github.com/LLMxPM/web-presentation-mcp/blob/main/docs/mcp-implementation-plan.md)；工具级说明以 MCP 仓库的 MCP 文档和源码为准。

主仓可执行清单见[远程 MCP 主仓实施计划](./mcp-implementation-plan.md)：按 M0～M7 拆分授权、External Principal、契约自省、任务与幂等、媒体、Gateway 和验收；包含拟新增接口、跨仓依赖、测试命令和完成定义。候选契约在实施并验收前不替代现行 External API。

## 2. MCP 依赖的主仓能力

MCP Server 依赖以下平台能力，但不在主仓库登记 MCP 工具：

- 身份认证与工作空间边界：OAuth 发行/自省/委托、`/api/v1/whoami`、`/api/v1/capabilities` 和工作空间接口。
- 项目、页面和源码：项目、页面查询，以及页面源码的创建、更新、归档。
- 资源、组件、主题和样式：列表、详情、导入、创建、更新和归档。
- 规范与契约：`/api/v1/standards`、`/openapi.json`。
- 任务：页面/组件 Mutation 创建、状态查询、取消和人工重试。

具体路径、请求体、响应体、权限和错误语义统一以[External API v1 契约](./reference/external-agent-api.md)为准。

## 3. 主仓库变更要求

当 Backend 调整 MCP 会调用的接口时：

1. 先更新[External API v1 契约](./reference/external-agent-api.md)，明确路径、入参、出参、权限、错误和幂等语义。
2. 补充主仓库的 API、契约或集成测试。
3. 在 MCP 仓库更新 MCP 工具的映射、Schema、说明和测试。
4. 联调认证、工作空间隔离、确认语义、错误透传和长任务状态。
5. 发现接口与 MCP 实现不一致时，优先修复契约或实现，不在两份文档中长期保留不同口径。

主仓库只维护平台 API 的兼容性和服务端行为；不要为了 MCP 的单一调用场景，把 MCP 协议细节反向放入 Backend 的工具注册表。

## 4. 当前契约状态

页面/组件安全元数据 PATCH，以及 Mutation 状态、取消、人工重试和幂等组合语义已经冻结并由 MCP 仓库适配。构建产物下载 URL、鉴权方式、过期语义和持久化 Worker 契约仍未冻结，MCP 仓库不注册 Build 工具。

## 5. 远程多用户方案的平台待办

授权协议、真实委托认证、工具适配和本地创作闭环已实现。PAT 兼容、whoami 类型化来源、87 个路由的操作元数据与内容响应 Schema 的早期交接见[实施交接记录](./mcp-contract-handoff.md)；当前跨仓、PG、Gateway 和渲染证据见[域名前本地验收](./testing/mcp-local-acceptance.md)。OAuth 默认关闭，真实宿主与生产部署仍待验收。

本期优先交付基于现有 External API 的 MCP。内部助手迁移标准 API、统一业务操作层与合并工具注册表不属于前置工作；主仓只补远程多用户接入和 MCP 创作闭环必需的能力。统一访问主体仅涉及外部认证，不扩展为内部 Agent 运行态重构。

- **外部授权**：基于平台登录提供客户端授权、工作空间/Scope 授权、短期凭证和撤销。MCP 作为 OAuth 资源服务器，以面向 Backend 的委托凭证调用 API；不能用一枚服务端 PAT 代表所有用户。
- **统一访问主体**：ExternalPrincipal 把用户、不可变授权范围与凭证来源从 PAT ORM 解耦；已接入真实 OAuth 委托，保留实时成员资格、Grant 和对象归属检查。
- **契约自省**：MCP 工具 Schema 来自 External API；版本 1 的 `x-wp-operation` 从 `external_operations.py` 及真实鉴权依赖派生，覆盖多视图与动态 Job 权限；75 binding / 70 HTTP 路由已对拍当前生产生成物。
- **任务边界**：外部页面/组件继续使用 Mutation Job，不接入内部 AgentRun、Deferred 或 ExternalBatch 模型续跑；MCP 断连不等于业务取消。
- **批量确认**：跨客户端、跨副本确认需要的平台记录或票据，须定义主体、目标绑定、期限和一次性消费语义；模型布尔值不代替用户确认，不重用内部 AgentRun/HITL。
- **远程媒体**：先适配文本、资产 ID、短期预览与 PNG；二进制上传通道或异步截图契约另行冻结，不能沿用 CLI 本地路径或内部会话附件 ID。

新增接口先明确路径、入参、出参、Scope、错误与撤销语义，再实施 Backend 和 MCP 仓库。授权页遵循 `DESIGN.md`；HTTP DTO、External API 或 Gateway 改动执行已有 codegen、权限隔离和真实 Nginx 契约门禁。主仓不登记 MCP 工具，也不维护 MCP 传输和工具清单。

首期 P0～P2 默认支持单项归档、文本资源、现有预览和截图；批量确认、二进制上传、Resources 和正式多副本支持列为 P3 扩展。截图实测若不能满足宿主预算，异步截图契约需先补齐才能验收该首期能力。
