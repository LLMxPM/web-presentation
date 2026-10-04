# 独立 MCP wheel 消费者联测

日期：2026-10-04。测试源码：`backend/tests/integration/test_mcp_consumer.py`，MCP 实现归同级 `web-presentation-mcp`，主仓生产代码与 lock 不依赖该包。

## 证据范围

- 真实主仓 Authlib、OAuth HTTP、自省、服务 Basic 交换、External Principal、ORM 成员/对象校验。
- SDK HTTP 只读工具：身份/空间、当前 guide、专属规范、项目列表、完整页面源码/版本。
- 两用户并发不互见数据或规范；错误空间/对象拒绝；refresh 轮换后调用；主仓账号端撤销 Grant 后下一请求 401，新旧 access 都失效。
- 专属 loopback 随机端口：SDK 2.3→TCP MCP→TCP Backend→隔离 SQLite，2026-07-28 discover 和 2025-11-25 initialize 均验证 tools/list/call 与完整结构化结果；错误实际 Host/Origin 通过 TCP 拒绝。
- 分页 DTO/External URL Query 共用 1 起始页、1～100 页长；OpenAPI 公开真实上限，保留各接口默认页长。MCP 超上限 filters 在委托/业务 HTTP 之前拒绝，不复制分页白名单。

初始 Grant 由夹具预批准并通过真实授权码兑换，不代表 ChatGPT 浏览器 consent 已验收。公开契约使用当前生产 `v1_router` 生成；业务路由不 Mock、不替换认证依赖。测试库、用户和数据隔离，不启动 Worker、不重启现有平台服务。

## 命令与结果

先在 MCP 仓库构建 wheel：

```powershell
uv build --out-dir .tmp/dist
```

在主仓 `backend` 目录运行：

```powershell
$env:WP_MCP_CONSUMER_REQUIRED='1'
uv run --frozen --with '../../web-presentation-mcp/.tmp/dist/web_presentation_mcp_server-0.1.0-py3-none-any.whl' pytest -q tests/integration/test_mcp_consumer.py -k sqlite
```

SQLite **3 passed**，PostgreSQL **3 deselected**，本次未测 PG。`--with` 是独立包消费者测试，不更改主仓依赖/lock。显式 REQUIRED 缺包必须失败；普通主仓回归没有安装 wheel 时该可选模块 skip，不能计为跨仓验证通过。SDK 本机客户端使用 `trust_env=False`，避免环境代理将测试 loopback 请求转发到其他服务。

尚未证明：真实 ChatGPT/Codex/Inspector 授权、TLS/Gateway、PG、多进程/副本、Renderer、写入 Job/创作闭环和生产部署。后续联测继续扩展本入口，并与 MCP 仓[只读实施记录](https://github.com/LLMxPM/web-presentation-mcp/blob/main/docs/read-baseline.md)同步边界。
