# 远程 MCP OAuth 授权基础

实施状态：2026-10-04，协议核与授权存储基础已落地。生产 FastAPI 尚未装配 OAuth 路由，登录确认页、账户 Grant 管理、服务自省/交换、Gateway 和真实宿主验收仍需后续批次。现有 External API 继续只接受 PAT。

## 协议与事务分层

主仓锁定 Authlib 1.8.0（BSD-3-Clause），复用框架无关 AuthorizationServer、AuthorizationCodeGrant、RefreshTokenGrant 和 PKCE 验证。[官方授权服务器文档](https://docs.authlib.org/en/stable/oauth2/authorization-server/)、[PKCE 扩展](https://docs.authlib.org/en/stable/oauth2/specs/rfc7636.html)。

- `services/oauth/request.py` 接受 HTTP 层已经异步读取的参数，保留重复值；首期仅接受一个 resource，重复参数统一拒绝。
- `repositories/oauth_repository.py` 查询注册信息、用户、Grant、Scope 和全部选定空间的当前成员资格，生成不可变快照。
- `services/oauth/protocol.py` 为每请求创建独立 Authlib 协议核，生成标准 OAuth 错误或暂存发行意图。同步钩子不访问 ORM、不阻塞异步 Session、不持有跨请求用户状态。
- `services/oauth/token_service.py` 先验证协议，再开启独立写事务，首先 UPDATE Grant 行取得互斥，重读全部状态、重新验证，然后 CAS 消费来源并插入新凭证。只有 commit 成功才交付成功响应。
- `services/oauth/grant_service.py` 只管理平台已认证用户自己的 Grant，撤销先取得同一 Grant 写锁；后台领域 Job 不随授权撤销取消。

认证方式必须精确匹配登记值：公开客户端 `none`，机密客户端 `client_secret_basic`。回调 URI 精确匹配，显式指定 resource 和 S256，禁止隐式默认回调、plain PKCE、Scope 扩大或在同一请求混用客户端认证方式。`issuer`、MCP resource 和 API audience 必须显式配置 HTTPS 地址；MCP 与 API audience 必须不同，不能从 Host 推导。

不透明凭证使用 `wp_oat_`（MCP access）和 `wp_ort_`（refresh）前缀，包含 48 字节随机输入，只持久化 SHA256 摘要。原始凭证仅在提交后的协议响应中出现。Authlib DEBUG 发行日志使用脱敏 dict repr；审计模型没有可存放原始 HTTP payload 的任意 JSON 字段。

## 持久化契约

新增迁移 `20261004_0100`，接续 `20261002_0100`；不预置客户端或服务密钥。

| 表 | 保存内容 |
| --- | --- |
| oauth_clients | 预注册客户端、精确回调列表、Scope 上限、resource、认证方式及密钥哈希 |
| oauth_mcp_services | 预注册服务身份、密钥哈希、MCP resource 与 API audience；业务交换实现后启用 |
| oauth_grants | user/client、issuer/resource、固定具体空间集合、Scope、事务版本与撤销原因 |
| oauth_consent_requests | 待确认请求、平台 user/session、回调/PKCE/state、CSRF 摘要与消费时间；后续确认流程接入 |
| oauth_authorization_codes | 摘要、Grant、精确回调、PKCE、Scope、期限与消费时间 |
| oauth_refresh_families | Grant、家族 ID、绝对到期时间和撤销时间 |
| oauth_tokens | 摘要及公共 ID、access/refresh/delegated 来源、Scope、audience、family/parent/source/service、期限和消费/撤销时间 |
| oauth_audit_events | 固定事件、公共 user/client/grant/token ID、时间；没有原始 Token |

用户停用、客户端停用、Grant 撤销、原 Scope 不再被允许、任一已选空间成员失效或空间归档，均阻止后续发行。未来加入空间不会扩大原 Grant。已消费授权码返回 `invalid_grant`；已消费刷新凭证只有被原客户端认证后才触发 `refresh_replay`，撤销整个 Grant 和刷新家族。其他客户端不能利用这条规则撤销他人授权。

并发刷新按严格重放处理：只允许一个响应成功，竞争失败会撤销整链，因而成功响应中的新 Token 也可能随即失效。客户端必须把同一刷新链的刷新请求串行化，不能盲目并发重试。下一代 access/refresh 的 Scope 沿用刷新时缩小后的集合，期限不晚于家族绝对期限。

首期上限：code 60 秒、MCP access 900 秒、delegated 60 秒、待确认请求 600 秒、刷新家族 30 天。凭证清理保留期上限 7 天、审计保留期上限 30 天；清理任务尚未接入，不能宣称已自动清理。服务自省、委托源链检查和 API 接入完成之前，不宣称实时业务撤销已验收。

## 验证入口与证据边界

```powershell
uv run --locked --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_oauth_protocol.py backend/tests/unit/test_oauth_policy.py backend/tests/integration/test_oauth_storage.py backend/tests/integration/test_oauth_migration.py
```

SQLite 使用每例一次性数据库并启用外键，PG 使用专属测试数据库内的随机独立 schema。仅接受 `OAUTH_TEST_POSTGRES_DATABASE_URL=postgresql+asyncpg://.../wp_oauth_test_<名称>`；`OAUTH_TEST_POSTGRES_REQUIRED=1` 可强制缺配置失败。测试结束只删除自己创建的 schema，不访问开发库。

FastAPI 测试入口只在测试模块装配。并发用两个独立服务对象、Session 和 ASGI app，覆盖错误 PKCE 后再次兑换、授权码竞争、刷新竞争/重放、Scope 缩减、期限、用户/客户端/成员状态、跨用户撤销及提交故障。它验证数据库共享事务边界，不能替代两个真实 Backend 进程、Gateway 或真实宿主 OAuth 联调。
