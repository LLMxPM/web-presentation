# 远程 MCP 首批实施交接

核对日期：2026-10-03。本记录冻结主仓可独立实施的 M1 身份边界和 M3 契约发现方式。OAuth 协议入口仍是候选设计，M0 整体尚未退出；本文不表示远程 MCP 已可用。

## 1. 核对基线与范围

| 仓库 | 核对基线 | 状态 |
| --- | --- | --- |
| web-presentation | `dcf91cbf7e02f0d14cfbf82f4e0911fdef238443` | External API 仅接受 PAT |
| web-presentation-agent-kit | `5f9489a` | MCP 为历史骨架，尚无首期 binding 注册表 |

从实际 FastAPI 路由、依赖和当前 OpenAPI 离线核对了 **87 个 HTTP 方法/路径组合**。包括主资源路由、附加读取视图、Mutation 别名路由和批量归档。请求路径、DTO、Scope 与幂等要求继续以主仓代码为准；A1/A4 必须依据完成后的 OpenAPI 对拍，不允许使用本文作为离线请求契约。

首期复用项目/页面/组件/文本资源/主题/样式查询与创作、规范、Runtime Kit、字体、Mutation 查询/取消/重试、组件发布和现有预览/截图。首期排除上传、批量归档、Restore、Build、图片生成和内部 Agent 会话。

### 已定位的响应缺口

| 真实入口 | 当前问题 | M3 修正 |
| --- | --- | --- |
| `GET /api/v1/auth/whoami` | user/token/workspaces 是任意字典 | 明确嵌套 DTO，保留旧 PAT 字段；增加 credential 来源 |
| `GET /api/v1/pages/{page_id}/source` | 成功响应仅声明通用 object | 完整源码、页面 ID/code、version_no 类型化 |
| `GET /api/v1/components/{component_id}/draft` | 通用 object，缺少编辑基线 | 完整 content/preview_schema，加 current_version_no、draft_base_version_no、draft_hash |
| `GET /api/v1/components/{component_id}/dependencies` | 成功响应为 Any | 复用已有 WorkspaceComponentCurrentDependencies |
| `POST /api/v1/assets/{asset_id}/content/preview` | 差异结果是通用 object | asset_id/name、changed、unified_diff 类型化 |
| 六类单项 `POST .../{id}/archive` | 仅声明 dict[str, str] | 复用 MessageResponse，响应 JSON 不变 |
| `GET /api/v1/pages/{page_id}/screenshot` | 200 没有 PNG 契约 | image/png binary、页面 ID/版本响应头；不改变等待行为 |

页面详情、源码、版本列表/版本内容共用 `page.get`；组件详情、草稿、版本列表/版本内容共用 `component.get`。每个视图必须从自己的 HTTP 路由取参数和响应，不能使用 operation 主路径代替。现有项目配置、路由树、预览和 Job 请求/响应已有 DTO，保留原契约。

## 2. M1 身份边界

外部请求主体保存用户、不可变 scopes/空间集合和来源明确的 credential。业务路由只读取公共主体，不持有 PAT ORM 记录。

| 来源 | 审计/兼容信息 | 约束 |
| --- | --- | --- |
| pat | token_id、public_id、name、expires_at | 保留现有 all_workspaces 行为与实时成员资格检查 |
| delegated | public_id、grant_id、client_id、service_id、issuer、audience、expires_at | 固定具体空间集合；不可使用 all_workspaces |

`delegated` 结构只供 M2 的验证器适配，不能凭 HTTP Header 或调用方声明构造身份。本批仍只接受 `wp_pat_` 凭证并沿用严格 PAT 校验；认证失败没有第二种规则兜底。M2 必须先验证 issuer、API audience、期限、用户/Grant/客户端/服务状态及授权范围，才允许构造委托主体。

whoami 的 `user`、`token`、`workspaces` 字段保持兼容。PAT 的 token 保留 id/name/token_public_id/scopes/expires_at/all_workspaces；委托身份 token 为 null，credential 明确使用 delegated 及授权/客户端/服务标识，不伪造 PAT ID。credential 只包含公共标识，不包含原始凭证。capabilities.operations 继续为字符串列表，Scope 的 all/any 语义保持现状。

M1 完成基础解耦并不代表委托认证验收完成；PAT/委托 HTTP 对等、错误 audience 和撤销等场景依赖 M2。

## 3. M3 操作元数据

选择单个版本化扩展 `x-wp-operation`，版本为 1。扩展从真实路由鉴权依赖所持有的 `ExternalOperationSpec` 派生；不得维护另一份 route→scope 映射。

静态操作字段：`version`、`key`、`public`、`required_scopes`、`scope_mode`、`workspace_header_required`、`idempotency_key_required`。workspace_header_required 取实际路由/依赖的 Header 必填约束，不能把注册表中“非豁免”误当成所有详情路由都必须带 Header；实体和 Job 的空间仍由服务端复核。

通用 `/jobs/mutations/{job_id}`、`/cancel`、`/retry` 使用动态结构：`version`、`resolution=mutation_job_type`、`action`、`candidates`、`workspace_header_required=false`、`idempotency_key_required`。candidates 按 page/component 分别给出对应 operation key、required_scopes 和 scope_mode；候选不能合并成同时需要或任一满足的静态权限。执行时只按数据库真实 job_type 决定。

元数据是公开契约，不是用户可用能力。客户端执行前仍使用空间 capabilities，服务端每请求继续鉴权。规范与 capabilities 保持用户相关，不能进入共享公共缓存。旧客户端可以忽略新增扩展；不新增内部 guides 镜像。

## 4. OAuth 选型和未退出项

优先验证 Authlib。官方提供授权服务器与 PKCE/刷新/撤销扩展，但文档中的授权服务器框架集成主要为 Flask/Django，不能把 FastAPI 客户端集成误认成可直接使用的授权服务器。发布记录已列出 1.8.0；本批仅完成候选调查，尚未锁定依赖或宣称最小验证通过。[官方授权服务器说明](https://docs.authlib.org/en/stable/oauth2/authorization-server/)、[发布记录](https://github.com/authlib/authlib/releases)、[许可源码](https://github.com/authlib/authlib/blob/v1.8.0/LICENSE)。

M2 开工前需完成适配验证：框架无关协议核接入 FastAPI、平台用户/登录、SQLAlchemy 持久化、PKCE S256、resource 绑定、刷新轮换/重放、撤销、自省与受控 RFC 8693 交换。异步事务和 CAS 应由主仓数据库适配层处理；无内置支持的扩展不能算库已实现。验证失败应重新选型，不能手写整套协议弥补。

| 未冻结/未验收项 | 影响的工作包 | 下一步证据 |
| --- | --- | --- |
| 授权库版本/许可证确认及最小适配验证 | M0/M2 | 固定版本可复现 PoC，数据库并发消费正反例 |
| 首批真实宿主名称、版本和注册机制 | M0/M2/M7 | 与 A0 联合验证；SDK 测试不替代宿主 |
| 公网 origin/issuer/resource/API audience | M2/M6 | 明确配置及启动校验，不能从 Host 推导 |
| OAuth 错误、claim/opaque DTO、刷新最长时限/清理期 | M2/A3 | 两仓共同消费同一版本契约 |
| 全部 MCP binding 与请求/响应对拍 | M3/A1/A4 | agent-kit 建立首期 binding 后验收 |
| PAT/委托业务对等、轮换后幂等、撤销 | M1/M4 | M2 完成后的 API 和并发测试 |
| 真实宿主截图预算与 PNG 链路 | M5/M7 | 宿主时限、实际耗时和真实产物 |

已接受的持久 Job 不因 MCP 断连、Token 到期或撤销自动取消。查询、取消和 retry 仍需当前权限；重放维持 user/workspace/operation/key 边界。主仓本批不修改内部助手与领域队列，不启动或发布 MCP 服务。

## 5. 分步实施证据

### 批次 1：M0 独立边界核对

提交 `83b09c0`：冻结 M1/M3 首批边界、登记两仓基线与具体缺口。`pnpm run test:repository`：4 个文件、16 项通过。M0 整体仍待授权 PoC 与真实宿主矩阵。

### 批次 2：M1 基础身份解耦

新增不可变 ExternalPrincipal、来源明确的 PAT/委托快照和 PAT 适配器。业务上下文不再持有 PAT ORM；whoami 增加类型化 credential 并保留旧 token 字段，HTTP 仍只接受 PAT。

验证：外部主体/身份专题、PAT API、External API/契约缺口、PAT 服务、幂等与 Mutation 服务共 **73 项通过**；Editor API 重新生成及生成物一致性通过；真实 Nginx OpenAPI、上游 503 与 SPA 边界回归通过。委托对等测试只注入已验证主体，真实 Token 验证、audience、撤销与轮换仍待 M2。数据库结构未变，无迁移要求。
