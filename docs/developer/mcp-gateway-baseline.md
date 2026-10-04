# MCP 真实 TLS 网关消费者基线

日期：2026-10-04。独立 MCP `29244e8b4c093b86c4655645ca0f9f59cbd54cc8` wheel 与主仓真实 OAuth/业务路由，经官方 Nginx 1.28.3 Windows 便携二进制、独立 loopback 端口与临时 TLS 证书联测。证书只由本次客户端信任，不安装到系统或修改 DNS；配置直接消费 MCP 仓 `deploy/nginx.conf.template`，主仓不复制实现。

`backend/tests/integration/test_mcp_gateway_consumer.py` 两项 SQLite 用例通过，两个 PG 用例暂未执行。覆盖健康/公开元数据、401 challenge、真实 Host/Origin、SDK `discover` 2026-07-28 与 `initialize` 2025-11-25、十五个工具、真实页面 Job 入队、最大 20 秒短等待与取消。用户 Token、幂等 payload 不出现在 Gateway 日志。

SDK stateless + JSON 当前拒绝独立 GET SSE（405），测试已冻结这一事实；不宣称通知/订阅通过。SDK HTTP 客户端使用 45 秒读取预算覆盖 20 秒等待，不能沿用默认 5 秒。测试服务有界退出并关闭连接池；业务取消仅经显式工具。

```powershell
# 主仓 backend 目录；指向已准备的专属测试二进制与独立仓模板
$env:WP_MCP_CONSUMER_REQUIRED='1'
$env:WP_MCP_GATEWAY_REQUIRED='1'
$env:WP_MCP_NGINX_BINARY='<绝对 nginx 二进制路径>'
$env:WP_MCP_GATEWAY_TEMPLATE='C:/code/wp/web-presentation-mcp/deploy/nginx.conf.template'
uv run --frozen --with 'C:/code/wp/web-presentation-mcp/.tmp/dist/web_presentation_mcp_server-0.1.0-py3-none-any.whl' pytest -q tests/integration/test_mcp_gateway_consumer.py -k sqlite
```

缺二进制/模板时普通本地测试可 skip，`WP_MCP_GATEWAY_REQUIRED=1` 必须失败。夹具只管理本次 Nginx 前缀、证书、临时目录和 loopback 服务，不复用开发数据。非 Windows 需提供可执行 Nginx；主仓现有 Docker Gateway 门禁独立保留。

证据边界：主仓 OAuth、对象/空间检查、ORM、幂等和 Job 路由真实，未启动业务 Worker/Renderer，页面仍为 pending 后 canceled。不证明创作成功、真实 PNG、主仓生产 Gateway/Editor consent、多进程 PG 竞争、Linux 镜像、真实域名或 ChatGPT 账户验收。镜像/config 状态见独立仓[部署说明](https://github.com/LLMxPM/web-presentation-mcp/blob/main/docs/deployment.md)。没有 push 或 CI 执行记录。
