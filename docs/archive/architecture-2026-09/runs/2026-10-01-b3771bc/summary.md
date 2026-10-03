# 截图执行生命周期演练（2026-10-01）

本轮执行现行计划 M01/M04 的截图取消、硬期限、Renderer 强杀、租约恢复和迟到结果场景，修复实测缺口后全部通过。执行人为 Codex，实机故障与修复复测时间为 2026-10-01 06:05–06:45（Asia/Shanghai）。基线为 `b3771bc8eb3ed9eceb8dbd3cbf061cc26fc2737e`，候选包含本轮补丁（镜像构建和验证时尚未提交），代码及验收记录随后一并提交；源码文件、锁文件及验证时的补丁校验和见[来源记录](./records/sources.json)。没有推送镜像或发布。

## 环境与证据边界

使用 Docker Desktop/Linux amd64，16 CPU、约 14 GiB 内存。专属 PostgreSQL 16、Redis 7、数据卷、签名密钥和回环端口不复用开发环境。第一次项目 `wp-arch-drill-c4fa60f6` 用于复现和 Backend 修复；发现僵尸残留后清理该项目，第二次项目 `wp-arch-drill-2c42908d` 从空库完整复测最终候选。最终拓扑为双 Backend、双 Preview、双 Build、双 Renderer、单 Check、Gateway 和演练代理，数据库 revision 为 `20260930_0300`，见[环境记录](./records/environment.json)。

| 镜像 | Docker inspect 的实际本地身份 | 来源与用途 |
| :--- | :--- | :--- |
| `wp-lite-lifecycle:local` | `sha256:191a9ca17d8c304ea8ba6ad38d6b4da9b2d74e5a57d8a5241d6e9eabee1d1eac` | HEAD + 本轮 Backend 生命周期补丁；双控制面及实际 Lite 入口 |
| `wp-renderer-lifecycle:local` | `sha256:936a3647eaceda79261705a9c3065d8e1af2d1209a78ad7d1a9ddfa5ed35db68` | 官方默认 Dockerfile + tini 入口修复；实际 CMD、控制 API 与故障执行 |
| `wp-runtime-w05h:local` | `sha256:03a6187ff277ec58d7e530d136ec84a10425ce770599f41162e149f84d38bc23` | 复用上一轮 `e82c793`；源码和指纹不变 |

Renderer 默认 HTTPS Debian 源、默认 Playwright 下载地址及冻结 uv 依赖已完整构建，没有使用替代下载配方；最终添加 tini 时复用该官方浏览器安装层。Playwright 为 1.63.0，Chromium 为 153.0.8010.12。上述身份和探针中的 `repo_digests` 均是本地 Docker 记录，不代表 Registry 发布/拉取验证。

故障代理只延迟真实导航或已经生成的真实 PNG，不生成回执或成功结果。演练参数为请求期限 20 秒、attempt 租约 6 秒、未知状态复核 3 秒、Worker 产物 TTL 10 秒、全局/工作空间占用上限 2。取消收敛预算 12 秒、强杀后原租约回收预算 14 秒；资源释放观察预算为 TTL10 + 15 秒。这些参数用于故障演练，不是生产 SLA。

## 发现与修复

1. 截图 Job 取消没有传递到正在执行的 RenderRequest，实际取消观察失败，见[修复前记录](./records/before-cancel-propagation.json)。父子取消现在同事务提交；活动执行的短会话观察者补偿「取消先提交、请求随后入队」竞争，并受当前 Job owner 和有效租约约束。
2. Renderer 被强杀后，网络错误仍不断续租，阻止自然租约回收，见[修复前记录](./records/before-unreachable-lease-fix.json)。现在只有真实 accepted/running/cleaning 回执才续租，不可达保留原租约等待收敛。
3. PNG 下载期间的取消、总期限或租约失效可能与结果提交竞争。结果 CAS 同时检查占用、有效租约、请求取消和总期限，竞争失败整笔回滚；租约已过期但回收器尚未处理也拒绝提交。截图最终发布失败时重新确认取消，避免 Job 遗留 running。
4. 第一轮虽无存活浏览器，PID 1 仍留下 Chromium 僵尸，见[原始进程记录](./records/pre-init/scenario-summary.json)。Renderer 官方镜像改用 tini；最终门禁要求浏览器/驱动进程全部消失，包含僵尸，最终探针记录 PID 1 为 tini。
5. 根仓交付扫描将历史证据中的 `Renderer.cache.Dockerfile.txt` 当成交付镜像，导致契约检查误报。扫描排除 `docs/` 证据目录，实际源码中的全部 Dockerfile 仍逐项匹配发布与镜像验证矩阵。

## 最终场景结果

| 场景 / 页面 / Job | 实际结果 | 阶段记录耗时（含清理） | 记录 |
| :--- | :--- | ---: | :--- |
| 导航中取消 / 2 / 1 | Job、请求取消；1 个 attempt 释放，无成功结果/页面截图 | 6.097 秒 | [cancel](./records/render-cancel.json) |
| PNG 返回竞争取消 / 3 / 2 | 真 PNG 延迟返回后拒绝提升；Job、请求取消，无成功结果 | 13.898 秒 | [cancel-result](./records/render-cancel-result.json) |
| Renderer SIGKILL / 4 / 3 | 确认容器退出，原租约自然回收；新 attempt 成功，旧 attempt 无结果 | 16.191 秒 | [kill](./records/render-kill.json) |
| 租约失效后返回 PNG / 5 / 4 | 新协调器接管后释放真实原 PNG；旧 attempt 无结果，新 attempt 成功 | 26.090 秒 | [late](./records/render-late.json) |
| 导航硬期限 / 6 / 5 | 三次领域重试耗尽后 failed，记录 `RENDER_DEADLINE_EXCEEDED`，无成功结果/页面截图 | 65.109 秒 | [timeout](./records/render-timeout.json) |

每轮最终两个 Worker 均 idle，临时文件数为 0，浏览器/驱动进程列表为空，无僵尸。全程采样占用未超过 2；本轮单场景最大观察值为 1，不代表满额拒绝或压力容量已验证。强杀与迟到恢复均下载到当前页面的有效 PNG，22589 字节，摘要见[场景汇总](./records/scenario-summary.json)。

最终正常链路经 Gateway 创建截图 Job 6、构建 Job 1：PNG 1920×1080、22589 字节；ZIP 15220399 字节，版本/尺寸/摘要及入口校验通过，见[完整链路](./records/pipeline.json)。真实 ZIP 安全解压后从 HTTP 加载，12 条浏览器响应，目标页面/scoped CSS/字体正确，无失败请求或页面异常，见[浏览器记录](./records/browser-build.json)。已查看 PNG 与浏览器截图，标题及正文正确。

## 验证与收口

- Backend 10 组定向单元/API/集成/DB 边界测试：85 项通过；包含真实双 Session 的取消、期限、已回收租约、尚未回收的过期租约、正常成功、父子事务回滚和先取消后入队。
- 根仓 contracts：41 项通过；repository：13 项通过。新增 Python 模块和脚本 Ruff、改动旧模块的未定义变量检查及 `git diff --check` 通过；Docker 上下文门禁通过。
- 官方 Renderer 默认构建、真实 CMD 控制 API 截图探针通过，见[镜像身份](./records/image-renderer.json)及[回执](./records/renderer-receipt.json)。最终 Lite 实际入口、Runtime HTTP/HMR 版本门禁通过，见[Lite 记录](./records/image-lite.json)。Runtime/Renderer 缺配置、文件不存在、0400 空文件的六种实际启动负例通过，见[凭证记录](./records/credentials.json)。
- 两个 Worker 的只读摘除检查均通过，无未释放 attempt，见[摘除门禁](./records/worker-removal.json)。两个专属项目均完成清理；最终项目无残留容器/数据卷，见[清理记录](./records/cleanup.json)。原开发 PostgreSQL/Redis 仍运行且健康。
- 未执行全量 Backend/Editor/Runtime/E2E、完整 M02 隔离、构建 attempt 强杀/迟到上传、页面/图片/组件 Batch 交接、M05 旧镜像完整入口/回滚、正式容量、platform/arm64/Registry 发布矩阵。没有变更 HTTP DTO、渲染 DTO 或 Runtime Kit 公共路径。

逐阶段命令与依赖顺序见[演练说明](../../../../developer/testing/docker-architecture-drill.md)，实际命令、十个 Backend 测试文件及退出码见[测试记录](./records/tests.json)。实际执行官方 Dockerfile 构建、`setup --fault-injection`、seed、五个 render 阶段、pipeline、browser-build、credentials、摘除门禁及 cleanup，各最终阶段退出码为 0。

本地完整时间轴、PNG/ZIP 位于 `test-results/docker-architecture/wp-arch-drill-2c42908d/`；第一轮原件位于 `test-results/docker-architecture/wp-arch-drill-c4fa60f6/`。校验和见[证据清单](./records/evidence-manifest.json)。timeout 入库记录只保留首尾和状态迁移采样，完整 64 次状态采样留在本地原件；采样方式和原件摘要明确标记。`pre-init/` 保存改用 tini 前的边界记录，不能冒充最终无僵尸验收。带凭证的 context/compose 不入库，大二进制不入库。

本轮关闭截图生命周期的定向场景，M01/M04 完整门继续开放。下一步推进 M05 的完整 N-1 镜像入口、迁移中断/应用回滚及 N/N-1 公共能力组合；M04 外部交接/Batch 一次消费、构建故障及额度饱和分别继续验收。
