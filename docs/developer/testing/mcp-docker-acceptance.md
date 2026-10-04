# MCP Docker 本地验收

日期：2026-10-05。Docker Desktop 4.66.1 / Engine 29.3.1、Linux amd64。独立镜像与生产组件联测已通过；此前 Docker socket 阻塞已解除。本轮只构建本地镜像和提交代码，没有推送、发布或执行 GitHub Actions。

## 独立镜像与生产 Compose

独立 MCP 仓 `scripts/check_image.py` 已改为专属 bridge 网络、容器 TLS 上游与动态回环端口，不需要开启 Docker Desktop host network。合成上游只提供公开契约、服务 Basic 自省和短期主体；不把 fixture 计为真实 Backend 授权或创作。

实际验证：UID/GID 10001、只读根文件系统写入失败、无 Backend/CLI/Playwright 包及源码目录、缺配置拒绝且不回退 PAT、私有 CA 回源、health 命令、SDK discover 2026-07-28 和 initialize 2025-11-25。生产 `deploy/compose.yml` 与 Nginx TLS 模板实际启动，覆盖认证挑战、资源发现、错误 Host、1 MiB 上限和日志无凭证。

SIGTERM 在真实认证请求进入上游自省后注入：上游延迟三秒，原 tools/list 请求成功返回十五工具，容器在约 3.81 秒内以 0 退出。没有用 SIGKILL、Windows 进程清理或仅查看 Docker 参数替代排空验收。

```powershell
# 独立 MCP 仓根目录；探针只管理本次随机网络/容器。
docker build -t wp-mcp:local-2609847 .
uv run --frozen python scripts/check_image.py --image wp-mcp:local-2609847 --openapi-file ../web-presentation/editor/src/types/openapi.json
```

## 真实生产组件链路

主仓 `scripts/testing/mcp-docker.py` 消费独立 MCP 交付镜像与原始平台、Runtime、Renderer Dockerfile 产物。两个平台容器运行原始 CMD、生产 lifespan、完整 API 路由与 Worker；A 执行真实迁移，B 不重复迁移。它们共用专属 PostgreSQL 16.15、Redis 7.4.11、签名身份与数据卷。没有替换业务规划器、队列、锁/CAS、编译器、Chromium 或最终提交。

MCP 的入口和平台授权回源都经过真实 TLS Nginx，只在本次客户端/容器增补临时 CA。Renderer 浏览器使用专属 Docker 网络内的 HTTP 产物地址；没有关闭浏览器或 HTTP 客户端 TLS 验证。真实公网预览地址及浏览器证书仍需正式域名联调。

完成以下场景：

- 两个 HTTP Backend 并发消费同一授权码，仅一个成功；两个用户使用不同 Grant，分别通过 discover / initialize 读取自己的身份和空间。
- 创建页面，同幂等键取得同一持久 Job；另一个用户不能跨空间读取。
- 暂停真实 Runtime 后观察 Job 为 `running`，重启 MCP，再恢复 Runtime；原 Job 成功完成，没有发出业务取消。
- 真实 `replace_exact` 编辑到页面 v2；重启 MCP 和 Backend A，新 MCP 按原 Job ID 查询成功结果，源码版本保持一致。
- 实际 Renderer/Runtime PNG 可解码为 1920×1080，已目视确认“MCP 容器编辑成功”；冷获取 2.994 秒、缓存命中 1.471 秒，均 27,830 字节且 SHA 相同。
- 两 Backend 并发刷新触发重放整链撤销，成功方新 access/refresh 也失效；第二用户 Grant 仍有效，公开 revoke 后 MCP 立即拒绝。
- 容器 stdout/stderr 不含本轮授权码、PKCE、密码、access/refresh 或服务 Secret；本次容器和数据卷全部清理，开发 PostgreSQL/Redis 保持运行。

最终演练耗时 110.8 秒。PNG 摘要为 `bc5e47660b729256e23ea84ac6d9aedfa1ec225f710780bc5b3e1d6b5421af53`。这是简单页面的本机量测，不是容量或复杂页面时限保证。组件完整创作仍由[此前两协议真实创作门禁](mcp-local-acceptance.md)单列，不把它冒充本轮 Docker 组件样本。

## 版本、证据与复跑

主仓交付镜像从 `ff87fd5be3f989f78d76e8349b528f6f4e71d922` 构建；MCP 镜像从 `2609847` 构建，包实现包含 `144cdea` 的审计保护。新探针提交为主仓 `1a8c9fd` 与 MCP `be347e5`，不改变这四个交付镜像内的产品源码。

| 产物 | 本地 image ID |
| --- | --- |
| Backend / Editor | `sha256:35709c4a449263face494697f9201dd89b370bed1ed86badc3b513f55c1f3be4` |
| Runtime | `sha256:899dcd5809c89707f54463d712747ef12220a807130ffa9c33e523e2bb6e39f2` |
| Renderer | `sha256:65fb279795d2f74eab16e07eb0269da0c4e0ebca3f0cd8e37d409c2d1ad1fea4` |
| MCP | `sha256:79be92d3b50113b2412da25628be45cbf215e829b9a8a31c6a0f9e00165f0fae` |

这些是本地 image ID，不能当作远端 Registry 发布 digest。脱敏汇总见 [JSON 证据](mcp-docker-evidence-20261005.json)；原始 PNG、失败记录与 cleanup 在 `test-results/mcp-docker/`。`.tmp/mcp-docker/` 含合成密码、令牌和证书，不打印、不提交。失败场景保留：初始种子入口的模块路径，以及 Renderer 拒绝未信任的自签证书；后者通过明确内部产物地址修正测试配置。

```powershell
# 主仓根目录。四镜像均需从对应仓的当前源码构建。
docker build -f deploy/docker/Dockerfile.platform -t wp-platform:mcp-ff87fd5 .
docker build -f runtime/Dockerfile -t wp-runtime:mcp-ff87fd5 .
docker build -f renderer/Dockerfile -t wp-renderer:mcp-ff87fd5 .
uv run --all-packages --frozen --with '../web-presentation-mcp/.tmp/dist/web_presentation_mcp_server-0.1.0-py3-none-any.whl' python scripts/testing/mcp-docker.py --backend-image wp-platform:mcp-ff87fd5 --runtime-image wp-runtime:mcp-ff87fd5 --renderer-image wp-renderer:mcp-ff87fd5 --mcp-image wp-mcp:local-2609847
```

脚本自动清理本次项目；不复用开发数据或执行全局 prune。真实初始 Grant 由夹具预批准，CIMD 浏览器确认、ChatGPT 展示、公开预览、容量、多 MCP 副本共享限额、跨版本升级/回退、arm64 和 Registry/远端发布仍属于各自验收，不能从这一个本地拓扑推导完成。
