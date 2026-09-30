# 本地 Docker 架构演练

`scripts/testing/docker-architecture.py` 用专属 Compose 项目验证多 Backend、分角色 Runtime、远程 Renderer 与 PostgreSQL。它为每次演练创建数据库、Redis、共享卷、签名密钥、临时账号和回环端口，不连接开发或生产数据。运行前确认 Docker Desktop 使用 Linux 容器，并已安装根仓 pnpm/uv 依赖及 Node Playwright Chromium。

演练的 Gateway 是用于强制分发的测试配置，不替代正式 Nginx 契约回归。Backend 复用包含 Python workspace 的 Lite 镜像，但只启动 `uvicorn app.main:app`；它不在 Backend 进程里启动浏览器。预览、构建、检查和 Renderer 均使用独立容器。

## 构建并固定镜像

从根仓构建三种交付镜像，示例标签可自行调整：

```powershell
docker build -f runtime/Dockerfile -t wp-runtime:drill .
docker build -f deploy/docker/Dockerfile.lite -t wp-lite:drill .
docker build -f renderer/Dockerfile -t wp-renderer:drill .
uv run --project backend python scripts/testing/docker-architecture.py setup --backend-image wp-lite:drill --runtime-image wp-runtime:drill --renderer-image wp-renderer:drill
```

脚本把镜像标签解析为实际本地 image ID 后写入 Compose，避免后续标签变化影响环境。`environment.json` 记录实际拓扑与各镜像；本地 ID 不代表镜像已推送或远端 Registry 验证通过。复用不同提交的 Backend 镜像时，必须在运行摘要分别标明 Backend 源码与 Runtime/Renderer 候选，不能以当前 HEAD 代替全部组件的来源。

Renderer 首次构建包含 Python wheel、Debian 依赖和 Chromium 下载，耗时受网络影响。需要先验证控制面时，可在 setup 加 `--defer-renderer`，待镜像构建完成再执行 `renderer --renderer-image <镜像>` 阶段。镜像支持 `DEBIAN_MIRROR`、`PLAYWRIGHT_DOWNLOAD_HOST`、`UV_INDEX_URL` 构建参数；冻结 uv 锁中的 wheel URL 仍按锁文件下载，覆盖索引不能保证替换这些 URL。

## 分阶段执行

setup 输出类似 `.tmp/docker-architecture/wp-arch-drill-xxxxxxxx` 的目录。后续阶段必须显式传入该目录：

```powershell
$drillDirectory = '.tmp/docker-architecture/wp-arch-drill-xxxxxxxx'
uv run --project backend python scripts/testing/docker-architecture.py seed --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py owner --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py owner-pause --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py owner-hostname --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py legacy --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py browser-same --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py browser-cross --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py credentials --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py pipeline --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py browser-build --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py jobs --directory $drillDirectory
```

| 阶段 | 验证范围 |
| :--- | :--- |
| `owner` | 无 SSE 订阅的真实普通 Run；强杀 A，同 hostname/PID 重用后 UUID 改变；双收敛者仅写一次终态、解除会话，B 无模型事件期间保持活跃 |
| `owner-pause` | 暂停 A，心跳失效收敛后恢复进程并释放模型结果，旧写围栏拒绝迟到提交；重启后会话可创建新 Run |
| `owner-hostname` | 强杀并重建 A、改变 hostname；PID=1 重用，新旧 UUID 区分 |
| `legacy` | 真实 PG 从 `20260926_0100` 前滚至 head；只读挂载 `4c7eee8` app 源码验证旧页面入队幂等、完整 Batch ORM 读写、过期恢复及 Run 取消；旧迁移器对未知 revision 拒绝 |
| `browser-same` | 正常 iframe 导航，真实请求跨两个同版预览副本，页面、scoped CSS 与字体可用；响应身份一致，无失败请求或页面异常 |
| `browser-cross` | HTML 绑定 A 身份，浏览器自然子请求强制走发布身份不同的 B；模块、Tailwind CSS、Vite 明确 409。Chromium 不保留拒绝响应正文时，用原浏览器 URL HTTP 复读核对错误码，单独记录来源，不注入版本头 |
| `credentials` | Runtime/Renderer 实际镜像 CMD 在无网络下验证缺凭证、不存在文件、0400 空文件启动失败；镜像构建中可先执行 `credentials-runtime` |
| `pipeline` | 调用官方完整部署探针，经 Gateway 下载实际 PNG 和 ZIP，校验尺寸、版本、摘要及 ZIP 入口；安全解压并记录最新站点目录 |
| `browser-build` | 通过本地静态 HTTP 实际打开本轮 ZIP 入口，确认目标页面可见且无失败请求或页面异常 |
| `jobs` | 四个不同项目/页面，各自入队构建与截图；双 Build Worker、双 Renderer 参与，记录运行期 owner/attempt、每个产物摘要和终态槽位释放 |

`runtime --runtime-image <镜像>` 可替换本演练全部 Runtime 角色并重新记录身份；`backend --backend-image <Lite 镜像>` 可更新双 Backend，沿用专属数据与密钥，不重新初始化。所有改变副本或 Gateway 分发的阶段应串行执行；镜像探针等独立临时环境可以并行。

browser-cross 默认覆盖测试副本发布身份；验证真实不同版本的二进制时，显式加 `--other-runtime-image <旧 Runtime 镜像>`，记录会区分 `older_image` 与 `identity_override`，结束后恢复原副本。

普通 Run fixture 使用本地受控 Chat Completions 流，经过真实 API、模型适配器和后台执行器，不调用外部模型。owner TTL/心跳/扫描为 12/2/1 秒，观察预算为 16 秒；这只是演练参数，不是生产 SLA。legacy 每次只重置该专属 PG 中的 `compat_e2e` 夹具库，保证从 N-1 schema 重新前滚；旧 app 源码使用当前 Python 依赖环境，不能据此宣称完整 N-1 镜像或发布回滚已验收。

## 证据与清理

脱敏 JSON、PNG、ZIP 和失败记录在 `test-results/docker-architecture/<项目>/`。`.tmp` 内的 `context.json` 和 `compose.json` 含测试凭证，禁止提交、分享或打印；入库证据只复制明确审核过的小型 JSON。阶段失败保持非零退出码，不能以健康接口或部分产物计成功。重复 pipeline 使用新的产物目录，不覆盖前轮失败证据。

无论成功或失败，结束后仅清理自己的项目：

```powershell
uv run --project backend python scripts/testing/docker-architecture.py cleanup --directory $drillDirectory
```

cleanup 保存清理前拓扑并删除本项目容器/数据卷，不执行全局 prune，不修改已有开发容器。Windows 不执行 POSIX 子进程权限测试时，应使用这些真实 Linux 容器补证；完整跨任务权限、attempt 故障/取消、Batch 一次消费、备份恢复、容量目标、arm64 和 Registry/远端部署仍需各自矩阵验收。
