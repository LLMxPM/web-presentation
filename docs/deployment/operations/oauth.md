# MCP OAuth 服务身份与记录维护

实施日期：2026-10-04。主仓提供服务登记、轮换、停用及过期记录清理入口，默认关闭的 OAuth HTTP 配置保持不变。本文命令用于 Backend 运维；MCP 服务部署和真实 ChatGPT 连接仍须按[主仓实施计划](../../developer/mcp-implementation-plan.md)联合验收。

## 迁移与配置

先备份数据库，再由独立迁移器执行 `alembic upgrade head`。本批新增 `20261004_0101`，接续授权基础表迁移 `20261004_0100`：增加可空 `oauth_audit_events.service_id`，以及 Token 的 parent/source/service 三个索引。旧授权、凭证和业务数据保持兼容；迁移后再部署本批 Backend。

在根仓运行本地迁移命令：

```powershell
uv run --locked --project backend alembic -c backend/alembic.ini upgrade head
```

服务运维进程要求 `OAUTH_ENABLED=true` 以及完整的 issuer、MCP resource、API audience、Editor origin 和安全 Cookie 配置，见[首批 OAuth 配置](../../developer/backend/oauth-chatgpt.md)。应用配置自动读取根仓与 `backend/.env`，进程环境变量优先；容器运维应使用其真实数据库和 Secret 注入。服务的源/目标地址固定取自部署配置，CLI 不提供任意地址覆盖。

## 登记、轮换和停用

服务 ID 为小写字母开头的 1～128 字符，可包含数字、点、下划线和连字符。服务名称最长 128 字符。Secret 使用密码学随机来源，至少 32、至多 512 个可打印 ASCII 字符，不含空白；通过受控 Secret 管理器注入文件，只允许读取进程访问。文件末尾允许一个 LF/CRLF。下面 `/run/secrets/*` 为部署侧 Secret 文件示例，必须换成所在环境的实际路径。

```powershell
uv run --locked --project backend python -m app.scripts.oauth_services list
uv run --locked --project backend python -m app.scripts.oauth_services create --service-id presentation-mcp --name "演示文稿 MCP" --secret-file /run/secrets/mcp-service
uv run --locked --project backend python -m app.scripts.oauth_services rotate --service-id presentation-mcp --secret-file /run/secrets/mcp-service-next
uv run --locked --project backend python -m app.scripts.oauth_services disable --service-id presentation-mcp
```

`create` 仅创建，不覆盖重复 ID，也不占用已有用户客户端 ID。成功输出公共 ID、名称、resource、API audience 和启用状态，密钥仅持久化哈希。命令不接收 `--secret`；失败输出异常类型和固定排障提示，退出码为 1，不能以原始异常或 SQL 参数诊断凭证。命令返回 0 后再核对实际自省/交换，不能只凭登记成功宣称远程接入可用。

轮换提交后旧 Basic 密钥立即失效，所有 MCP 实例须协调更换。轮换保持服务启用/停用状态，既有短期委托继续按来源链验证。停用与交换共用服务行 UPDATE 围栏，提交时一并撤销该服务已签发委托；交换先提交的结果也会被停用事务撤销。停用不撤销用户 Grant、其他服务或已接受业务 Job。

重新启用必须再次提供新 Secret 并明确 `--enable`：

```powershell
uv run --locked --project backend python -m app.scripts.oauth_services rotate --service-id presentation-mcp --secret-file /run/secrets/mcp-service-next --enable
```

重新启用后旧委托仍保持撤销状态，需要从仍有效的用户 MCP access 重新交换。服务元数据不允许更改信任地址；地址变更应登记新的服务 ID。`service_created`、`service_secret_rotated`、`service_disabled`、`service_enabled` 审计和状态变更同事务提交，只记录公共服务 ID。

## 过期记录清理

Backend lifespan 启动 `oauth-cleanup`，每五分钟执行一个有界批次，正常关闭时取消并等待退出。关闭 OAuth 后继续清理历史记录。单轮失败只输出固定日志，下个周期重试；不打印数据库参数。日志事件 `oauth.cleanup` 含各类删除数量，失败事件为 `oauth.cleanup.failed`。

- 待确认请求、授权码到期后保留七天。
- access/delegated 到期或撤销、所属 Grant 撤销后，保留七天；存在 parent/source 后代引用时继续保留。
- 已消费 refresh 在家族绝对期限内继续保留重放证据；家族到期或整链撤销后保留七天，再按子到父回收。这保留了 [RFC 9700 的刷新轮换关系要求](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14.2)。
- 刷新家族终止超过七天且已无 Token 引用才删除；审计按创建时间保留三十天。
- 注册、用户 Grant 历史、业务数据和 Job 不参与本清理。

每类默认最多 200 条（delegated/access/refresh 分别计数），整轮单事务提交，多个清理进程可以重复执行。来源图层数和积压可能使实际删除晚于保留期限；这里的七/三十天是进入回收资格的时间，不承诺精确到时删除。可用 CLI 加速处理积压，批次必须为 1～1000：

```powershell
uv run --locked --project backend python -m app.scripts.oauth_cleanup
uv run --locked --project backend python -m app.scripts.oauth_cleanup --apply --batch-size 200
```

默认预检不修改数据，只统计当前可删除叶节点的本批数量；实际执行先删除后代，可能在同轮释放更多父节点，因此预检数不等于最终执行数，也不表示总积压。执行和预检都仅输出数量。需要继续处理时再次执行，每轮重新判断资格，不能通过手工全表删除缩短重放证据期限。

## 回滚与证据边界

先关闭 MCP 入口或停用其服务，再停止/替换本批 Backend，最后视需要降级至 `20261004_0100`。仅关闭 `OAUTH_ENABLED` 不会停止清理任务，不能据此在新 Backend 仍运行时删除新审计列。此降级只删除本批三个索引和服务审计字段，保留授权基础表、凭证和业务结果；已清理的过期记录及该审计字段不能凭降级恢复，需要备份。

SQLite 真实外键、并发运维/交换、刷新重放、清理来源链和迁移往返均有测试。PostgreSQL 用例需要 `OAUTH_TEST_POSTGRES_DATABASE_URL` 指向独立 `wp_oauth_test_*` 数据库，缺配置时跳过。协议和隔离数据库证据不代替真实 PostgreSQL、两个生产 Backend 进程、Gateway 或 ChatGPT 联调。

```powershell
uv run --locked --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_oauth_operations_cli.py backend/tests/integration/test_oauth_operations_cli.py backend/tests/integration/test_oauth_service_registry.py backend/tests/integration/test_oauth_cleanup.py backend/tests/integration/test_oauth_migration.py
```
