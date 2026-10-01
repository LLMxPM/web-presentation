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

## 截图取消、期限与 attempt 故障

本轮故障场景使用 `setup --fault-injection` 创建专属响应代理。代理只阻塞真实 Runtime 导航或已由 Renderer 生成的 PNG 返回，不构造执行回执或成功结果。固定转发目标位于本次 Compose 网络，控制端口只绑定随机回环端口；不记录完整导航 URL、票据、服务身份头或源码。

```powershell
uv run --project backend python scripts/testing/docker-architecture.py setup --fault-injection --backend-image wp-lite:drill --runtime-image wp-runtime:drill --renderer-image wp-renderer:drill
# 将上一步输出的专属目录赋给 $drillDirectory，再依次执行。
uv run --project backend python scripts/testing/docker-architecture.py seed --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py render-cancel --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py render-cancel-result --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py render-timeout --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py render-kill --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py render-late --directory $drillDirectory
```

| 阶段 | 故障注入与断言 |
| :--- | :--- |
| `render-cancel` | 真正 Chromium 导航阻塞时调用截图取消 API；Job/RenderRequest 取消，未发布页面截图或成功结果 |
| `render-cancel-result` | 真实 PNG 已下载到代理、attempt 仍占用时取消；随后返回原 PNG，结果 CAS 拒绝提升，Job 确认取消 |
| `render-timeout` | 导航一直阻塞，真实 Renderer 硬期限收敛；领域截图重试耗尽后失败，错误码、无结果及资源释放可对账 |
| `render-kill` | SIGKILL 本项目的执行中 Renderer，先证明容器已退出，等待原租约自然回收，再启动；新 attempt 成功，旧 attempt 无结果 |
| `render-late` | 阻塞真实 PNG 返回，重启不持有截图 Job 的 Backend 协调器；租约到期接管后再交付原 PNG，旧 attempt 不提升，新 attempt 产物可下载 |

这些阶段逐一创建新页面/Job，以 20 秒请求期限、6 秒 attempt 租约、10 秒 Worker 产物 TTL 缩短故障观察，属于演练配置。所有阶段串行执行；PNG gate 最多等待 90 秒。每轮记录真实 DB 状态与全局占用，结合 Worker 控制 API、`/proc` 的进程名/可执行文件/PID/状态及临时文件数量，核对 Worker 空闲、无 Chromium/Playwright 驱动进程（含僵尸）、临时产物释放。Renderer 镜像通过 tini 回收被 PID 1 接管的浏览器孤儿；历史僵尸负例仍保留。这不关闭完整 M02 进程隔离门。

重复场景创建带时间戳的新报告，失败报告不覆盖。恢复截图保存 PNG 与摘要，取消/超时保留未发布的状态证据。阶段结束恢复代理与被中断服务，全部演练结束后仍执行 `cleanup`。这些证据覆盖 M01/M04 的截图生命周期，构建 attempt 故障、页面/图片/组件 Batch 交接、恢复、容量和远端发布继续按现行计划独立验收。

## M05 完整旧镜像、迁移与公共能力

`legacy` 是旧源码配当前依赖的领域探针。完整 N-1 演练另从固定 Git 对象导出全部源码，以其原始 Dockerfile、两份锁文件和 CMD 构建 platform、Lite、Runtime、Renderer；不覆盖旧源码，不把继承的 uv 基镜像 OCI revision 当应用来源。

```powershell
uv run --project backend python scripts/testing/docker_architecture_images.py
docker build -f deploy/docker/Dockerfile.platform -t wp-platform-m05-n:local .
docker build -f deploy/docker/Dockerfile.lite -t wp-lite-m05-n:local .
docker build -f renderer/Dockerfile -t wp-renderer-m05-n:local .
uv run --project backend python scripts/testing/docker-architecture.py setup --backend-image wp-lite-m05-n:local --runtime-image wp-runtime:drill --renderer-image wp-renderer-m05-n:local
# 将该次 setup 输出赋给 $drillDirectory，再依次执行。
uv run --project backend python scripts/testing/docker-architecture.py seed --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py m05-baseline --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py m05-upgrade --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py m05-startup-negatives --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py m05-combinations --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py m05-current-entries --directory $drillDirectory
uv run --project backend python scripts/testing/docker-architecture.py m05-provenance --directory $drillDirectory
```

旧镜像脚本默认固定 `4c7eee8`；M05 阶段也绑定这些标签，改变样本时须同步修改并保存确切 Git SHA/镜像 ID。N Runtime 标签须预先按本文构建，不能直接复用来源不明的本地镜像。旧四镜像日志和锁摘要写入 `test-results/docker-architecture-images/4c7eee8/`。

| 阶段 | 真实边界与证据 |
| :--- | :--- |
| `m05-baseline` | 新建专属 `m05_pg` 库与 `m05.db` 卷，使用完整旧 platform/Lite 原始 CMD 自动迁移到旧 head；API 创建历史数据，受控供应商调用真实页面工具、生产队列、远程校验、取消与 deferred 自动续跑 |
| `m05-upgrade` | 停旧入口；PG 阻塞真实 DDL 后强杀迁移器，SQLite 在实际 ADD DDL 后强杀；检查列与 revision 原子回退。随后记录删列窗口旧 ORM 拒绝、前向补偿、旧入口未知 revision 拒绝、N 业务与关闭旧迁移器的完整应用回滚 |
| `m05-startup-negatives` | 在另建的专属 PG 库/SQLite 文件构造旧 schema，N platform/Lite 真实 CMD 关闭自动迁移，必须非零退出；不改业务演练库 |
| `m05-combinations` | 按版本组合分别核对正常 iframe、协议拒绝、真实 PNG/ZIP 与 ZIP 浏览器加载；完整旧 platform/Lite 生成的 ZIP 再由 N 应用原产物接口下载，摘要保持相同；旧镜像历史限制单独记录 |
| `m05-current-entries` | 在保留历史库的 N platform/Lite 真实 CMD 上，分别完成全 N 预览、PNG、ZIP 与浏览器加载；不重新播种 |
| `m05-old-entries` | 完整组合失败后的旧入口定向续跑；旧 Lite 使用远程 Worker 可达的 Runtime 角色基址，原始源码/CMD 保留。只有旧镜像与 N 下载入口身份、原 ZIP 摘要都匹配才复用旧产物记录 |
| `m05-provenance` | 无网络容器逐文件比较 N/N-1 Backend/Renderer 源码与记录候选，核对全部旧 Kit 公开路径/源码 hash；实际浏览器样本是 `DataTable.v1` 与 `usePageSize.v1`，不代表每项能力均已渲染 |

baseline/upgrade 是状态相关阶段：须从本次新演练的旧 head 执行，升级完成后不得为了重跑降库或 stamp；失败后先保留报告并恢复该专属快照，或创建新的隔离项目。其它阶段也须满足前置状态，Compose/context 改动串行执行。mock 只控制供应商工具调用，不替换生产队列、终态或续跑实现。

组合负例给 N Backend 临时配置 20 秒渲染期限，并真实执行截图重试到失败；记录无结果及占用释放后恢复配置。缺发布身份的旧 Runtime 预览/截图不支持，独立 ZIP 构建和 HTTP 加载另验。复用先前通过记录必须匹配实际三镜像、页面版本及原 ZIP 摘要；记录标记 `reused_evidence`，不冒充新的执行样本。

platform/Lite 使用真实交付 Nginx。旧入口产物地址是专属容器名，官方 HTTP 探针在本项目独立迁移容器中执行；主机 Chromium 将这些固定容器名映射到对应回环入口，映射单独留证，不注入版本头、不修改票据或响应。Renderer 浏览器仍在独立 Worker 执行。

## 证据与清理

脱敏 JSON、PNG、ZIP 和失败记录在 `test-results/docker-architecture/<项目>/`。`.tmp` 内的 `context.json` 和 `compose.json` 含测试凭证，禁止提交、分享或打印；入库证据只复制明确审核过的小型 JSON。阶段失败保持非零退出码，不能以健康接口或部分产物计成功。重复 pipeline 使用新的产物目录，不覆盖前轮失败证据。

无论成功或失败，结束后仅清理自己的项目：

```powershell
uv run --project backend python scripts/testing/docker-architecture.py cleanup --directory $drillDirectory
```

M05 cleanup 先对本次三个库、两个 Worker 分别执行只读 `app.scripts.check_render_worker_removal`，要求无未释放 attempt；任一门禁失败即停止摘除。随后保存清理前拓扑并删除本项目容器/数据卷，不执行全局 prune，不修改已有开发容器。失败阶段与浏览器失败报告带时间戳保留。Windows 不执行 POSIX 子进程权限测试时，应使用这些真实 Linux 容器补证；完整跨任务权限、attempt 故障/取消、Batch 一次消费、备份恢复、容量目标、arm64 和 Registry/远端部署仍需各自矩阵验收。
