# CLI OAuth 主仓实施计划

规划日期：2026-10-05。状态：计划已建立，CLI OAuth 尚未实现。本计划以主仓 `mcp` 分支的 `45678f3` 为评估基线，CLI 基线为 `481a586`，开发分支为 `oauth`；这些版本用于追溯评估，不代表最终兼容版本。

本文负责平台侧授权契约、Backend、Editor 和跨仓验收。[CLI 仓库计划](https://github.com/LLMxPM/web-presentation-cli/blob/oauth/docs/oauth-implementation-plan.md)负责命令、Profile、同步客户端和 Skill。两份计划目前保存在本地工作树，跨仓 GitHub 链接在相应分支推送后可用。已实现的公共业务接口继续以 [External API v1 契约](./reference/external-agent-api.md)为准；下列候选认证契约须完成 P0 后才可作为实现依据。

## 1. 目标与首期范围

让官方 CLI 通过系统浏览器登录平台，由用户批准具体工作空间和 Scope，取得面向 External API 的短期 access token 与轮换 refresh token。CLI 直接调用现有 `/api/v1`，无需部署 MCP 或持有 MCP 服务密钥。

首期采用公开客户端、授权码和 PKCE S256；保留 PAT 接入供 CI、无人值守和既有客户端使用。CLI OAuth、ChatGPT/MCP OAuth 和 PAT 共用业务权限及任务语义，但凭证验证路径与 audience 必须明确区分。

设备码登录、任意第三方客户端动态登记、OIDC 身份声明和内部助手认证重构不纳入首期。服务端启用与客户端默认切换分别验收，不能因添加计划或登录 UI 宣称 OAuth 已交付。

## 2. 已核对的基础与缺口

| 环节 | 当前代码 | 平台侧工作 |
| --- | --- | --- |
| 客户端与确认 | `services/oauth/chatgpt_client.py`、`consent_service.py` 仅接受 ChatGPT，确认名称和 resource 固定 | 增加官方 CLI 登记与受限客户端解析，不扩大任意 CIMD 获取范围 |
| 回调验证 | `services/oauth/snapshots.py` 精确匹配登记 URI | 对已登记 CLI 增加 loopback 动态端口规则，其他客户端维持精确匹配 |
| 发行和授权状态 | `oauth_repository.py`、`persistence.py`、`grant_service.py` 固定 MCP resource | 支持明确的 API resource，联动授权码、刷新、围栏、撤销和账户 Grant 查询 |
| 业务鉴权 | `api/dependencies_external.py` 只分派 `wp_pat_` / `wp_dlg_` | 增加直接 API OAuth access 验证，继续拒绝 MCP access、refresh 和服务 Basic |
| 公共身份 | `external_principal.py`、`schemas/external_identity.py` 只有 PAT / delegated | 增加已验证的 OAuth 凭证快照、whoami DTO 和日志来源 |
| Editor | `editor/src/utils/oauth.ts` 只允许 ChatGPT 回调 | 支持服务端确认后的 CLI loopback 回调与通用客户端文案 |

已有 Authlib 协议核、授权存储、一次性消费、刷新轮换/重放撤销、审计和空间权限可复用。现有表包含 client、resource、audience 和刷新家族；P0 根据客户端类型及回调策略确定是否需要迁移，不能预先承诺无迁移。

## 3. P0 候选契约与约束

以下是实施建议，P0 完成时记录最终名称、DTO、配置和错误语义；CLI 不自行维护另一份服务端契约。

| 契约面 | 候选行为 |
| --- | --- |
| 客户端 | 预登记官方公开客户端，建议 ID 为 `web-presentation-cli`，`auth_method=none`；不分发共享 client secret |
| 发现 | 复用 `GET /.well-known/oauth-authorization-server`；明确 issuer、endpoint、S256、支持的 resource 和 CLI 能力发现方式；旧服务或 OAuth 关闭时明确报错 |
| 授权 | 复用 `GET /oauth/authorize` 与 Cookie consent；传入 client_id、redirect_uri、resource、scope、state 和 S256 challenge |
| 回调 | 建议 `/oauth/callback`，只允许 `http://127.0.0.1:{port}` 或 `http://[::1]:{port}`；严格验证 IP、路径和端口，拒绝 userinfo、查询及片段；仅端口允许动态变化 |
| 兑换/刷新 | 复用 `POST /oauth/token`；API resource 使用显式 `OAUTH_API_AUDIENCE`，兑换时精确匹配本次原始完整 redirect_uri，刷新不得改变 resource 或扩大 Scope |
| 直接 access | 建议使用独立 `wp_aat_` 命名空间；只有真实 API audience 凭证能访问业务 API，不能放开现有 `wp_oat_` MCP access |
| 撤销 | 复用 `POST /oauth/revoke` 和本人账户 Grant 管理；按原客户端、issuer、resource 撤销整条授权与刷新家族 |
| whoami | 保留 PAT 的 token 字段；直接 OAuth 的 token 为 null，credential 明确区分 OAuth / delegated，提供公共客户端、Grant、issuer、audience、期限和权限信息 |
| 配置 | 保持显式 HTTPS issuer、API audience、Editor origin 和安全 Cookie；按能力校验 MCP 配置，不从 Host 推导身份 |
| 错误 | OAuth 端点保持标准 OAuth 错误；业务认证失效返回 401，权限/空间不足保持现有 403/404，不以刷新修复业务越权 |

回调端口例外只属于已登记的原生 CLI 客户端，不能退化为所有客户端的 URI 前缀匹配。授权码仍绑定本轮完整 URI、state 与 PKCE；客户端校验返回的 state、iss 和接收地址。原生客户端流程参考 [RFC 8252](https://www.rfc-editor.org/rfc/rfc8252.html)。

API 直接凭证与 MCP 凭证的 issuer、audience、客户端、用户、Grant、刷新家族、期限、Scope 和实时空间成员资格都必须完成验证后才构造 `ExternalPrincipal`。自省和 RFC 8693 交换保持仅面向已登记 MCP 服务及其 resource，不能通过通用化仓储扩大其放行范围。鉴权按命名空间单次分派，失败不得回退 PAT、Cookie 或其他来源。

## 4. 分阶段工作包

| 阶段 | 工作内容 | 完成证据 | CLI 依赖 |
| --- | --- | --- | --- |
| P0 契约冻结 | 固定客户端、loopback 策略、直接 access 类型、发现、DTO、配置、期限与迁移决定 | 候选表转为已冻结契约，记录主仓完整 commit 和生成物摘要 | C0；完成后 C1/C2 可消费 |
| P1 客户端与确认 | 预登记/停用 CLI，解析受信客户端，通用化 consent，绑定完整回调和 API resource | 真实 Cookie 批准/拒绝、S256、跨用户/会话、错误回调、动态端口和停用负例通过 | C2 浏览器登录 |
| P2 资源发行与生命周期 | 将授权、发行、刷新、Grant 围栏、撤销及查询按受信资源收口；校验清理与重放证据 | SQLite/PG 的授权码竞争、刷新竞争、重放整链失效、提交失败和撤销通过 | C1/C3 凭证管理 |
| P3 API 身份与 Editor | 新增直接 access 验证与公共主体；同步 whoami/日志/DTO；扩展受限回调和授权管理文案 | PAT/OAuth/delegated 对拍、Editor 类型/行为检查、生成物一致通过 | C3/C4 业务调用与诊断 |
| P4 跨仓业务验收 | 固定双方版本，真实 CLI 调用规范、资源、Mutation、预览与 PNG；回归现有 MCP | 权限隔离、同键恢复、长任务跨刷新、真实截图、Gateway 和双 Backend 证据 | C5 集成测试 |
| P5 发布与回退 | 公网 HTTPS 下真实浏览器登录与打包 CLI 验收，更新配置、用户文档和兼容矩阵 | 记录双方版本、平台升级与 CLI 降级/PAT 使用路径；完成后再切换用户默认流程 | C6 分发与 Skill |

P1 与 P2 完成后才能声明授权生命周期可联调；P3 完成后才能让 CLI 使用新凭证访问业务 API。P4/P5 未完成前不修改用户文档为“已支持 OAuth”。涉及数据库迁移时增加双库升级/降级与既有 PAT/MCP 数据保留测试。

## 5. 业务与安全回归要求

- 直接 OAuth 与相同用户/空间/Scope 的 PAT、MCP 委托共享业务行为；不得增加第二套资源路由、业务 Scope 或工具目录。
- OAuth 只授权具体工作空间，不隐式覆盖未来加入的空间；用户、客户端、授权或成员状态失效后拒绝后续访问。
- 幂等边界继续使用 user/workspace/operation/key。刷新、重新登录和同用户 PAT 重放不产生重复 Job；原幂等键与基线不得因 Token 更换被替换。
- 已接受 Job 不随 CLI 退出、access 到期或 Grant 撤销自动取消；后续查询、取消和 retry 仍需要当前权限。
- 所有 OAuth 成功凭证与用户响应保持 private, no-store；日志和审计只保存公共标识，不记录 code、verifier、access、refresh 或完整授权 URL。
- Editor 复用既有确认 UI 与 `DESIGN.md`，默认只读范围，写权限及具体空间由用户显式确认；nonce 保持仅在当前组件生命周期内。
- 保持 ChatGPT 固定 CIMD / 回调规则和 MCP 服务 Basic / audience 隔离，补充“直接 API access 无法在 MCP 自省或交换”负例。

## 6. 验证入口与证据边界

先运行改动范围对应的最小测试，再按阶段完成下列门禁：

```powershell
uv run --locked --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_oauth_protocol.py backend/tests/unit/test_oauth_chatgpt.py backend/tests/api/test_oauth_http.py backend/tests/api/test_oauth_external_http.py
pnpm run codegen:editor-api
pnpm run test:contracts:generated
pnpm run test:editor:gate
pnpm run test:contracts
pnpm run test:contracts:gateway
pnpm run test:repository
```

实施时补充 CLI OAuth 专题测试，覆盖原生回调、API audience 和直接身份；以上现有入口不是新能力的完整验收。PostgreSQL 使用独立 `wp_oauth_test_*` 数据库，缺配置跳过必须报告。双 Backend、Redis、Runtime、Renderer 和 Gateway 使用专属资源；按已有 [Docker 架构演练](./testing/docker-architecture-drill.md)约束组织，CLI 联测入口在 P4 落地，不把 MCP 测试直接算作 CLI 通过。

当前可复用的 MCP 本地 SQLite/PG、TLS 创作、PNG 与双 Backend 证据见 [域名前本地验收（`mcp` 分支）](https://github.com/LLMxPM/web-presentation/blob/mcp/docs/developer/testing/mcp-local-acceptance.md)。它们不替代 CLI 原生回调、跨进程刷新或公网浏览器登录验收。

2026-10-05 本轮评估运行现有 OAuth 定向回归：65 passed、29 个 PG 分支因缺专用数据库跳过。该结果仅说明当前基础回归通过，不说明候选 CLI OAuth 契约已实现。本轮计划文档的链接/围栏与 diff 检查单独记录在交付说明。

## 7. 文档与交接

> [!NOTE]
> 本节引用的 MCP OAuth 基础与外部授权工作流文档目前只在 `mcp` 分支维护，短期不合入本分支，因此使用指向该分支的绝对链接。`mcp` 分支合入后应改回仓内相对链接，避免链接随分支重写失效。

P0 的服务端契约在主仓维护；CLI 计划只引用冻结版本。实现落地时同步 [CLI 集成边界](./cli.md)、External API 契约、[OAuth 基础（`mcp` 分支）](https://github.com/LLMxPM/web-presentation/blob/mcp/docs/developer/backend/oauth-foundation.md)、配置和运维文档。HTTP DTO 改动必须生成 Editor 类型并检查一致性；凭证分派约束变化时同步根 `AGENTS.md`。

P5 同步顶层 README、[外部授权工作流（`mcp` 分支）](https://github.com/LLMxPM/web-presentation/blob/mcp/docs/user/workflows/external-authorization.md)和发布检查表；现有 MCP 计划作为独立范围继续维护。证据记录双方完整 commit、CLI wheel/Skill 版本、OpenAPI 摘要、环境、测试命令、跳过项和未完成事项，不能仅用“登录成功”作为业务闭环。

## 8. 当前进度

- [x] 核对现有 OAuth、External API 与 CLI 缺口。
- [x] 建立主仓与 CLI 仓库分工计划，CLI 创建本地 `oauth` 分支。
- [ ] P0 候选契约冻结。
- [ ] P1 客户端与确认。
- [ ] P2 资源发行与生命周期。
- [ ] P3 API 身份与 Editor。
- [ ] P4 跨仓业务验收。
- [ ] P5 发布与回退。
