# MCP 域名前本地验收

日期：2026-10-05。本轮仅本地提交，没有 push、部署或 GitHub Actions 执行记录。主仓运行于 `mcp` 分支，独立 MCP 仓运行于 `main`。首期能力已完成本地实现与下述验证，生产交付仍需公网 HTTPS 和真实 ChatGPT 授权验收。

## 版本与契约

- 主仓生产契约：`f45764a60580a4f478c2f6d81d576870bf389ee8`；Runtime 根路由修复：`c463b55`。
- MCP：0.1.0、SDK 2.3.0；创作联测使用 `29244e8` 的独立 wheel。最终 `144cdeae66f49f969e467fd6c6fb2a6432ae07af` 增加 URL 审计保护和当前编辑契约回归，并重新通过独立 wheel 进程探针。
- OpenAPI：256 路径、357 Schema；MCP 75 binding / 70 HTTP 路由。当前契约摘要 `90cec608a60c475a4e16969a876377e1802a02d32c4841f62c01d702b23b72d2`。MCP CI 固定上述完整主仓 commit，缺失不能回退旧生成物。
- 编辑结构复用 `backend/app/schemas/source_edits.py`：`replace_exact`、`insert_after`、`rewrite_file`。页面/组件入队和候选校验的 OpenAPI 都公开联合类型，错误 type、缺字段或额外字段在 MCP 和 Backend 入队前拒绝。

## 已执行的验证

| 验证 | 结果与边界 |
| --- | --- |
| 独立 MCP 回归 | Python 3.13.3、3.11.15 各 283 passed，无 skip |
| 四组 wheel 消费者 | SQLite 15 passed；PostgreSQL 17.11 15 passed，涵盖真实 OAuth、权限、幂等、Job、媒体适配和 TLS Gateway |
| OAuth/存储/业务专题 | SQLite 139 passed；PG 139 passed，包含授权码/刷新竞争、服务登记与停用、权限和幂等恢复 |
| OAuth 迁移往返 | SQLite、PG 共 2 passed；真实 Alembic 升降级、ORM 对拍及既有用户保留。PG 使用本例创建后删除的 UUID 数据库 |
| PG 跨进程事务 | 3 passed；两个独立进程的授权码一次消费、refresh 重放整链失效及服务停用/交换竞争 |
| PG 认领与迁移契约 | 9 passed、1 skipped；跳过的是早期 SQLite revision 缺少 `thinking_enabled` 的旧例，PG 认领及双库 head 对拍已执行 |
| 创作与真实 PNG | TLS Nginx 下 SDK 2026-07-28 discover、2025-11-25 initialize 共 2 passed；详见下面链路 |
| Runtime 回归 | 根路由/项目路由 10 passed，Runtime `vue-tsc` 通过 |
| 契约/生成物 | 相关 Backend 18 passed；codegen 与生成物一致性、Editor `vue-tsc` 通过 |
| 本机生产 Gateway | 完整 OpenAPI、OAuth 发现/302/400、Basic/request ID、16 KiB 上限、上游 503 与 Editor SPA 边界通过 |
| 独立安装入口 | frozen 依赖的 Python 3.11 wheel 真进程、缺配置拒绝、健康和 SDK TCP 通过；不含 Backend/CLI 包 |
| Linux 镜像 / Compose | 非 root、实际只读、TLS 回源、生产 Compose/TLS、健康、两协议和在途 SIGTERM 排空通过 |
| Docker 生产组件 | 双 Backend + PG 16.15 / Redis 7.4.11 + Runtime/Renderer；真实页面/PNG、非终态 Job 跨 MCP 重启、授权竞争/撤销及专属资源清理通过 |

跨进程 PG 门禁另由 `test_oauth_multiprocess.py` 验证两个独立 Python 服务进程的授权码一次消费、refresh 重放整链撤销，以及服务停用/交换竞争。它执行生产 OAuth 服务、真实数据库锁与事务；不代表完整生产 Backend/Redis 拓扑或多副本负载验收。

Docker 恢复后，另用真实交付镜像跑通两个完整 Backend 与 PG/Redis、Runtime、Renderer、MCP/TLS 网关；版本、命令、PNG、非终态恢复与证据边界见 [Docker 本地验收](mcp-docker-acceptance.md)。这补齐本地生产组件拓扑证据，仍不代表公网发布或容量验收。

## 真实创作链路

`backend/tests/integration/test_mcp_render_consumer.py` 使用真实 SDK → TLS Nginx → MCP wheel → TCP Backend → 持久队列/规划器/提交 → Runtime → Renderer Chromium。专属 SQLite + memory 是允许的单进程部署形态；没有替换编译器、浏览器、Worker、锁、CAS 或最终提交。

每个协议执行页面创建→成功 Job→读取版本→`replace_exact` 编辑→成功 Job；随后真实组件创建→带 hash 草稿编辑→发布 v1→用发布响应的公共 import path 更新页面→成功 Job。PNG 必须可解码为 1920×1080，并与最新页面 v3 对拍。截图已目视确认包含页面编辑结果和发布组件内容。

| 协议 | 冷截图 | 缓存命中 | PNG |
| --- | --- | --- | --- |
| 2026-07-28 | 5.247 秒 | 1.694 秒 | 32,821 字节 |
| 2025-11-25 | 11.399 秒 | 1.709 秒 | 32,821 字节 |

两次 PNG 摘要均为 `9c0bdabbc04e91d491661915dadbc1f03211bd143bafadece766bbbf447171ef`。这是单页、单用户、简单组件的本机量测，不是容量承诺，也不证明 ChatGPT 图片展示或复杂页面排队预算。脱敏 Job/版本/时间证据见 [JSON 记录](mcp-local-evidence-20261005.json)。原始测试图片和日志留在忽略的 `.tmp/mcp-render/`，不提交生成媒体、凭证或临时证书。

联测定位并修复了 Runtime 默认空路径重定向遮挡实际 `/` 页面的问题；隐藏根页和空字符串根路径也由真实 Vue Router 回归覆盖。单独 GET SSE 仍为 SDK stateless/JSON 的 405，不宣称通知/订阅可用。

## 可复用入口

从主仓根目录运行；先在独立 MCP 仓构建 wheel。测试复用已安装的 Runtime/Renderer/Chromium，各例只启动自己的 loopback 进程，结束后清理，不重启开发平台。

```powershell
$env:WP_MCP_CONSUMER_REQUIRED='1'
$env:WP_MCP_GATEWAY_REQUIRED='1'
$env:WP_MCP_NGINX_BINARY='<本机 Nginx 二进制绝对路径>'
$env:WP_MCP_GATEWAY_TEMPLATE='C:/code/wp/web-presentation-mcp/deploy/nginx.conf.template'
$env:WP_MCP_RENDER_REQUIRED='1'
uv run --all-packages --frozen --with '../web-presentation-mcp/.tmp/dist/web_presentation_mcp_server-0.1.0-py3-none-any.whl' pytest -c backend/pyproject.toml -q backend/tests/integration/test_mcp_render_consumer.py -k sqlite

# PG URL 仅接受 wp_oauth_test_* 专属库；各业务例创建/删除自己的 Schema
$env:OAUTH_TEST_POSTGRES_REQUIRED='1'
$env:OAUTH_TEST_POSTGRES_DATABASE_URL='<postgresql+asyncpg 的专属测试库连接串>'
uv run --all-packages --frozen pytest -c backend/pyproject.toml -q backend/tests/integration/test_oauth_migration.py backend/tests/integration/test_oauth_multiprocess.py -k postgresql

# 只验证主仓生产网关路由，HTTP fixture 不代表 OAuth 业务
uv run --all-packages --frozen python scripts/contracts/test-gateway-native.py --nginx-binary '<Nginx 路径>' --openapi-file editor/src/types/openapi.json
```

真实渲染门禁目前按 SQLite 单进程形态运行；不要把 PG + memory 改成通过来绕过部署校验。PG 消费者联测和跨进程服务事务独立验证。

## 下一步外部依赖

1. 给平台授权服务/Editor、MCP resource 和预览入口配置公网可达 HTTPS。可以使用受控隧道域名；购买独立域名不是本地协议验证的前置条件。地址必须同步到 issuer、resource、API audience、Cookie/CORS、Host/Origin 和服务登记。
2. 用 ChatGPT 网页端真实账号执行固定 CIMD 客户端授权、空间/Scope 确认、工具调用、PNG/预览展示和撤销。SDK、预批准 Grant、fixture 元数据和自签 loopback 证书不能替代 consent。
3. Linux 独立镜像、在途 SIGTERM、生产 Compose/TLS 和双 Backend/PG/Redis/Runtime/Renderer 本地门禁已通过；正式容量、多 MCP 副本、跨版本升级与远端发布继续按各自矩阵验收。此前 Docker socket 阻塞已解除。
4. 取得用户对发布范围的授权后，再推送双方提交并执行远端 CI；当前固定主仓提交未推送，不能记录 CI 成功。

批量确认、二进制上传、Resources/订阅和正式多副本属于 A7 独立扩展，首期仍不支持。部署、升级和回退见独立 MCP 仓 [部署说明](https://github.com/LLMxPM/web-presentation-mcp/blob/main/docs/deployment.md)。
