# External 与 OAuth 请求关联日志

主仓复用 `main.py` 的 `X-Request-ID` 上下文与响应头。启用 `LOG_FORMAT=json`、`LOG_LEVEL=INFO` 时，授权、委托交换和业务调用输出以下事件；数据库审计仍是独立的持久记录。日志为尽力输出，不能替代权限检查或作为恢复凭证的存储。

## 1. 事件与关联字段

| 事件 | 触发位置 | 固定公共字段 |
| --- | --- | --- |
| `oauth.audit.committed` | 确认、代码兑换、刷新/重放撤销、客户端/账户撤销、服务登记/轮换/停用的事务提交之后 | request_id、audit_event/audit_event_id、user_id、client_id、service_id、grant_id、credential_id；无对应身份时为 null |
| `oauth.request.completed` | `/oauth/token`、`/oauth/introspect`、`/oauth/revoke` 完成协议处理 | request_id、固定 endpoint、status_code、库生成的 error_code；不输出错误描述 |
| `external.request.completed` | `ExternalAPIRoute` 完成原鉴权和响应序列化，或原路由抛出业务/校验异常 | request_id、method、route 模板、operation、status_code、duration_ms、error_code；认证成功后附加公共身份 |

External 身份字段为 `credential_source=pat/delegated`、`credential_id` 与 `user_id`；委托另外携带 grant/client/service ID。`credential_id` 是可公开的凭证标识，不是原始 Bearer 或哈希。认证完成后立即提取标量，幂等回滚或提交导致 ORM 过期后不再读取实体属性。认证失败不采信请求中的用户、来源或空间声明。

OAuth 审计在提交前保存公共标量快照，成功提交后才输出。日志的 `audit_event_id` 对应 `oauth_audit_events.event_id`；发行、交换和业务通过 grant/client/service/credential ID 串联，每次 HTTP request ID 可以不同。数据库未增加 request ID 列。进程若在提交后、输出前退出，可能存在审计而没有日志；Handler 故障不触发重试已提交事务。

## 2. 操作、空间与 Job

静态 operation 取真实鉴权依赖持有的规格，动态 Mutation 取数据库 job_type 与实际 action，沿用当前 OpenAPI 元数据，不另建 route→operation 清单。

- `workspace_context_id` 只在范围/成员检查通过后记录，表示已经验证的 `X-Workspace-ID` 上下文，不宣称它是详情目标所在空间。
- `workspace_id/job_id` 来自完成空间校验的动态 Job，或成功的 `ExternalMutationJobResponse`。后者只读取不超过 64 KiB 的已序列化响应，提取两个标量；大结果跳过提取，动态依赖已绑定的字段继续保留。
- 无 Header 的详情/预览、非 Job DTO 和被拒绝的空间不会猜测目标空间，允许缺少对应字段。
- 幂等重放记录每次请求但共享 Job ID。202 表示受理，200 的 Job 查询也可能返回 failed；请求日志不代表领域任务已完成。

`duration_ms` 测量路由鉴权、执行与响应对象构造/序列化的耗时，不代表完整代理传输、流式下载或 ChatGPT 宿主耗时。Renderer/Runtime 产物与冷/热/繁忙/并发预算仍需 M5/M7 专属拓扑验收。

## 3. 日志与部署边界

只使用固定字段，不记录 Authorization/Basic/Cookie、授权码、刷新/访问/委托原值、密钥/哈希、幂等键、原始 query、源码、领域 result/error 正文、图片 Base64 或带签名 URL。JSON formatter 继续脱敏，协议错误只记录库错误码；未处理异常的既有应用错误日志仍由全局规则管理。

MCP 每次平台调用应携带可关联的 `X-Request-ID`，并保存平台返回的请求 ID。Backend 会规范化输入；请求 ID 不作为身份。Gateway 已转发 Header，但非法/超长 ID 的 Gateway/Backend 规范化一致性和实际跨服务传输仍需真实 Gateway 回归。无 HTTP 上下文的运维调用可能没有 request ID。

本批没有数据库迁移、HTTP DTO、MCP Worker 或领域状态变更。OAuth 默认关闭，Scope、幂等、缓存和原异常语义保持现状。Backend 事件通过不表示 `/mcp` 入口或真实宿主已交付。

## 4. 验证入口

```powershell
uv run --locked --project backend pytest -c backend/pyproject.toml backend/tests/api/test_oauth_audit_http.py backend/tests/api/test_oauth_request_logging.py backend/tests/integration/test_oauth_audit_logging.py backend/tests/unit/test_external_request_logging.py
pnpm run test:contracts:generated
pnpm run test:repository
```

HTTP 测试使用真实 Cookie/授权码/服务交换/Bearer 和独立 SQLite/PG 夹具，request ID 通过生产上下文函数绑定，不启动 Gateway 或量测网络。缺专用 OAuth PostgreSQL 库时 PG 用例跳过；实机退出条件见 [MCP 主仓计划](../mcp-implementation-plan.md)。
