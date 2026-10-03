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
