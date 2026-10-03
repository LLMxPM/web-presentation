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
| `OAUTH_MCP_RESOURCE` | agent-kit 的规范化公开 MCP URL，精确匹配 |
| `OAUTH_API_AUDIENCE` | 面向 External API 的独立 audience，不能等于 MCP resource |
| `OAUTH_EDITOR_ORIGIN` | 承载授权确认页的公开 HTTPS origin |
| `SESSION_SECURE` | 必须为 `true` |

独立 Editor origin 必须列入 `CORS_ORIGINS`。配置在应用装配时校验；不可从请求 Host、Forwarded 或客户端参数选择发行身份。

主仓负责授权服务和确认界面；MCP 受保护资源元数据、`WWW-Authenticate`、工具认证声明、MCP transport 与逐请求交换归属 agent-kit。主仓测试通过不能替代 ChatGPT 实际连接验收。

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
