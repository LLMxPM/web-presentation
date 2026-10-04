# ChatGPT 网页端首批 OAuth 接入

首批客户端确定为 ChatGPT 网页端生产版本。网页端没有本仓可固定的客户端语义版本；本批以 2026-10-04 的 [OpenAI 授权文档](https://developers.openai.com/plugins/build/auth)和实际 CIMD 文档读取为依据，真实账户、浏览器和部署验收仍待联调。此处是远程 MCP 连接授权。

## 客户端边界

- 首批使用受限 CIMD：唯一客户端 ID 为 `https://chatgpt.com/oauth/client.json`。
- 唯一回调为 `https://chatgpt.com/connector_platform_oauth_redirect`。启用 Authlib RFC 9207 issuer 扩展，成功及错误回调中的 `iss` 与发现文档精确相同。
- CIMD 仅使用 `none + PKCE S256`。当前生产文档同时公布数组 `token_endpoint_auth_methods_supported=[none, private_key_jwt]` 与旧单值偏好 `private_key_jwt`；数组声明优先，不能将旧偏好误当成唯一能力。
- 元数据获取不接受任意用户 URL，不跟随跳转，5 秒超时、16 KiB 上限，失败闭合。客户端禁用不能因再次访问元数据自动恢复。
- 本批不发布 DCR 注册入口、不接受 callback-ID-specific 客户端、不声明 OIDC 身份或邮箱。

## 配置

`OAUTH_ENABLED` 默认 `false`。启用时必须同时提供：

| 环境变量 | 含义 |
| --- | --- |
| `OAUTH_ISSUER` | 公开授权服务 HTTPS origin，不带路径或尾斜杠 |
| `OAUTH_MCP_RESOURCE` | MCP 仓库的规范化公开 MCP URL，精确匹配 |
| `OAUTH_API_AUDIENCE` | 面向 External API 的独立 audience，不能等于 MCP resource |
| `OAUTH_EDITOR_ORIGIN` | 承载授权确认页的公开 HTTPS origin |
| `SESSION_SECURE` | 必须为 `true` |

独立 Editor origin 必须列入 `CORS_ORIGINS`。配置在应用装配时校验；不可从请求 Host、Forwarded 或客户端参数选择发行身份。

MCP 服务 Basic Secret 通过受控文件登记、轮换和停用，见 [MCP OAuth 维护](../../deployment/operations/oauth.md)。服务停用与交换共用数据库围栏并撤销已有委托，重新启用不会恢复旧委托；已接受业务 Job 保持原生命周期。

主仓负责授权服务和确认界面；MCP 受保护资源元数据、`WWW-Authenticate`、工具认证声明、MCP transport 与逐请求交换归属 MCP 仓库。主仓测试通过不能替代 ChatGPT 实际连接验收。

## 已装配的 HTTP 契约

| 路径 | 身份与行为 |
| --- | --- |
| `GET /.well-known/oauth-authorization-server` | 公开发现；关闭时 JSON 404；issuer 与所有 endpoint 均来自配置 |
| `GET /oauth/authorize` | 验证受限 CIMD / 精确回调 / resource / Scope / S256 后转 Editor `/oauth/consent`，不自动批准 |
| `POST /oauth/token` | urlencoded 授权码、刷新或受控交换；协议错误为标准 OAuth JSON |
| `POST /oauth/introspect` | 已注册 MCP 服务 Basic 身份；实时用户 access 验证 |
| `POST /oauth/revoke` | 原用户客户端认证；撤销本人客户端所属授权 |
| `POST /api/v1/account/oauth/consents` | Cookie + 精确 Editor Origin，提交原始 authorization_query，返回单次 nonce 和实时空间选项 |
| `POST /api/v1/account/oauth/consents/{id}/decision` | 同一 Cookie 会话 + Origin + nonce；只能缩小权限，批准须选择当前成员具体空间 |
| `GET /api/v1/account/oauth/grants` | Cookie 下本人最近 100 条公共授权；关闭时 enabled=false |
| `POST /api/v1/account/oauth/grants/{id}/revoke` | Cookie + Origin，本人整链幂等撤销；他人/未知同为 404 |

Token、自省、撤销拒绝 URL 参数与表单混合、重复参数、非 urlencoded 和超过 16 KiB 的表单。所有凭证与用户相关成功响应为 private, no-store；确认 nonce/含授权码的回调排除在 DTO repr 外。nonce 只存摘要，不进入 URL 或前端持久存储。

确认请求 TTL 最长 10 分钟，每用户最多 10 个未消费且未过期待确认。批准/拒绝首先 CAS 消费当前 user/session/nonce 绑定，批准在同一事务插入 Grant、60 秒 Code 摘要与审计，提交后才交付回调。拒绝保留 state 和 iss，不创建 Grant。登录失效、客户端停用、空间成员丢失、重复确认均不能签发。

Gateway 配置显式把发现文档与四个协议端点转 Backend，`/oauth/consent` 保留 Editor SPA。受控真实 Nginx 回归已增加发现、授权 Location、OAuth 错误透传和确认页 SPA 断言；当前机器 Docker 引擎不可用，该回归尚未通过本批实机验收。公共 OAuth 不纳入业务 `x-wp-operation` 目录；账户 DTO 纳入生成的 Editor OpenAPI 类型。

## Editor 确认与管理

独立 `/oauth/consent` 使用现有 Cookie 登录守卫，登录后返回原始请求；默认只选择服务端返回的读取 Scope，写入 Scope 和具体空间必须显式选择。nonce 只在组合式逻辑的组件生命周期内保存；查询切换、卸载和成功决定后清空，迟到响应不能导航已经离开的页面。过期或无空间/权限选择时禁用批准，拒绝不要求空间选择。

`/settings/account/grants` 使用生成 DTO，显示本人授权和当前可见工作空间名称。成员资格丢失时仅显示空间 ID 的失效提示，不泄漏非成员空间名称。撤销确认说明整链失效与已接受任务继续运行，成功后重取服务端状态。用户操作见 [外部授权工作流](../../user/workflows/external-authorization.md)。

## External API 凭证分派

`/api/v1` 业务认证按不混用的命名空间分派：`wp_pat_` 走原 PAT 验证，`wp_dlg_` 仅在 OAuth 启用时走完整委托链验证。`wp_oat_` MCP access、`wp_ort_` refresh、服务 Basic、未知来源和重复 Authorization 头均不能作为业务身份；任何分支失败都不尝试另一认证规则。

委托每请求重新读取 Grant、用户/客户端/服务、源 access、audience、到期与具体空间成员状态，无正向放行缓存。受信服务本身没有业务权限。whoami 中旧 token 为 null，credential 明确包含委托公共身份；相同 user/workspace/Scope 的 PAT 和真实委托共享业务读取与 capabilities。页面/组件写入、Job 与幂等的完整委托对拍仍归 M4。
