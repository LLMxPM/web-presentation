# 独立 MCP wheel 消费者联测

2026-10-05 实现 review 修复：新增 `backend/tests/integration/test_mcp_review_regressions.py`，覆盖同一用户同时授权两个空间时的对象/任务归属、委托交换后真实撤销 Grant 的读写挑战，以及 128/129 字符幂等键边界。Backend 公共主体绑定请求空间，未授权目标仍保留原 403，已授权但未选定的目标返回 404 `WORKSPACE_CONTEXT_MISMATCH`。旧日志测试改为拒绝伪造任务 Header，成功日志只关联已验证上下文；对象权限测试的 edits 字段同步当前 Schema。

读取/写入/媒体与新增修复消费者四组在 SQLite **17 项通过**、独立 PostgreSQL **17 项通过**；PG 同批空间/任务权限另 **10 项通过**。MCP 完整回归为 **307 passed**，当前 75 binding/70 路由契约门禁、主仓 OpenAPI 生成物检查及携带完整契约的真实 Nginx 门禁通过。此批使用独立 MCP wheel，不修改主仓依赖或 lock；临时 PG 容器与专用测试库完成后清理，开发服务不重启。

最终复跑将主体单测、双数据库空间/日志/新增消费者回归，以及原对象权限失败场景一起执行，使用 `.tmp/final-fix-dist` 中当前 MCP wheel，**40 passed、无跳过**。扩大回归首次出现的两个失败已解决：保留凭证未授权空间的 403；日志测试要求拒绝伪造任务 Header，并更新对象权限测试过期的 edits 字段。修复无需数据库迁移；请求空间绑定与 Header Schema 需要 Backend 和 MCP 同步升级。

2026-10-05 当前结果：四组消费者 SQLite 15 项、PG 15 项通过；新增 TLS 网关下真实 Runtime/Renderer 的两协议页面/组件创作与 PNG，见[域名前本地验收](testing/mcp-local-acceptance.md)。下文保留 2026-10-04 的历史证据范围。

2026-10-04 已增加[真实 TLS Gateway 基线](mcp-gateway-baseline.md)。四个消费者文件合跑为 13 项 SQLite 通过、13 项 PG 暂未执行；SDK 最大 20 秒 Job wait 经真实 Nginx 验证。该新增记录不包含 Renderer 成功链。

日期：2026-10-04。测试源码：`backend/tests/integration/test_mcp_consumer.py`、`test_mcp_write_consumer.py`、`test_mcp_media_consumer.py`，MCP 实现归同级 `web-presentation-mcp`，主仓生产代码与 lock 不依赖该包。

## 证据范围

- 真实主仓 Authlib、OAuth HTTP、自省、服务 Basic 交换、External Principal、ORM 成员/对象校验。
- SDK HTTP 只读工具：身份/空间、当前 guide、专属规范、项目列表、完整页面源码/版本。
- 两用户并发不互见数据或规范；错误空间/对象拒绝；refresh 轮换后调用；主仓账号端撤销 Grant 后下一请求 401，新旧 access 都失效。
- 专属 loopback 随机端口：SDK 2.3→TCP MCP→TCP Backend→隔离 SQLite，2026-07-28 discover 和 2025-11-25 initialize 均验证 tools/list/call 与完整结构化结果；错误实际 Host/Origin 通过 TCP 拒绝。
- 分页 DTO/External URL Query 共用 1 起始页、1～100 页长；OpenAPI 公开真实上限，保留各接口默认页长。MCP 超上限 filters 在委托/业务 HTTP 之前拒绝，不复制分页白名单。
- 写入实际入队后丢失响应，同键重放获得原 Job、同键异载荷返回 409；只读授权和动态 component Job 的 page-only 授权拒绝。
- Job 短等待/取消/新 ID 重试及原 payload、版本/hash 保留；领域提交冲突保留 failed 诊断，MCP 给出 source/draft 重读入口，不提高基线重放。cancel/retry 公开真实 202 状态，避免消费者把已接受任务误判为响应损坏。
- SDK 2026/2025 TCP 同时覆盖页面创建→查询 pending Job→取消。
- page/project 真实 PreviewService 与隔离 memory artifact、签名钥验证 URL、票据 exp 与存储期限一致；缺 Scope/跨空间拒绝。SDK 2026/2025 TCP 均接收 PNG 图片块/原字节/页面版本，截图队列结果为合成 PNG，仅证明适配，不证明 Renderer。

初始 Grant 由夹具预批准并通过真实授权码兑换，不代表 ChatGPT 浏览器 consent 已验收。公开契约使用当前生产 `v1_router` 生成；业务路由不 Mock、不替换认证依赖。测试库、用户和数据隔离，不启动后台 Worker 或重启现有服务；冲突测试使用受控规划结果与真实领域提交围栏，retry 使用预置失败状态，不证明 Renderer/Runtime 成功链。

## 命令与结果

先在 MCP 仓库构建 wheel：

```powershell
uv build --out-dir .tmp/dist
```

在主仓 `backend` 目录运行：

```powershell
$env:WP_MCP_CONSUMER_REQUIRED='1'
uv run --frozen --with '../../web-presentation-mcp/.tmp/dist/web_presentation_mcp_server-0.1.0-py3-none-any.whl' pytest -q tests/integration/test_mcp_consumer.py tests/integration/test_mcp_write_consumer.py tests/integration/test_mcp_media_consumer.py -k sqlite
```

媒体批次 SQLite **11 passed**，PostgreSQL **11 deselected**；相关 OpenAPI 测试 10 项、生成物一致性检查通过，本次未测 PG。早期 A4 为 3/3、A5 为 7/7。`--with` 是独立包消费者测试，不更改主仓依赖/lock。显式 REQUIRED 缺包必须失败；普通主仓回归没有安装 wheel 时该可选模块 skip，不能计为跨仓验证通过。SDK 本机客户端使用 `trust_env=False`，避免环境代理将测试 loopback 请求转发到其他服务。

上述 2026-10-04 批次尚未证明真实宿主授权、TLS/Gateway、PG、多进程/副本、Renderer、完整创作成功链和生产部署；2026-10-05 的后续完成项与剩余依赖以页首新记录为准。历史失败场景继续与 MCP 仓[写入/Job 实施记录](https://github.com/LLMxPM/web-presentation-mcp/blob/main/docs/write-baseline.md)同步边界。
