# 本地 Docker 架构演练（2026-09-30 至 2026-10-01）

本轮在 Docker Desktop 的 Linux amd64 环境验证 W05 修复，使用独立 Compose 项目 `wp-arch-drill-adc5a2ca`。Docker 分配 16 CPU、约 14 GiB 内存；专属 PostgreSQL 16、Redis 7、签名密钥和数据卷不复用已有开发容器。没有推送镜像、发布或修改业务数据库。

Runtime/Lite 候选先为 `43c6515`，真实截图链路暴露固定挂载入口的 403，修复后 Runtime 来源为 `e82c793`。普通 Run 与旧 ORM 演练使用 `aab57cd` 对应 Lite 镜像，只运行 uvicorn；随后独立任务竞争暴露 Renderer 迟到失败覆盖终态，最终 Backend/Lite 更新为 `a0779df`。AI 生产代码和 Runtime 源码在这次 Backend 修复中未变，镜像分别留证，见[来源与锁文件](./records/sources.json)。精确 image ID、数据库 revision 和清理前实际拓扑见 [environment.json](./records/environment.json)，本地 image ID 不代表 Registry 已验收。

Renderer 使用 `wp-renderer-drill:local`（`sha256:0dd732573c943b263ecfbbb8ec895d89279769b7d8d5d580a419ee5004d35589`）：冻结依赖及 Python 安装层复用官方 Dockerfile，系统包与 Chromium 通过本机临时缓存下载，上游保持 HTTPS/TLS 与 APT 完整性校验，源码及最终 CMD 沿用生产入口。构建差异与浏览器包摘要见[下载配置](./records/renderer-build-profile.json)和[有效构建文件](./records/Renderer.cache.Dockerfile.txt)。官方默认下载构建停在 Chromium 40%，随后终止；**本轮 Renderer 执行验证不关闭官方默认配方或 Registry 发布门**。

| 交付镜像 | 实际本地 image ID | 本轮用途 |
| :--- | :--- | :--- |
| `wp-lite-w05c:local` | `sha256:1e189f5a786d8e9ff81bbd5f3c2d14a999c63288d3d814212a3dcaf7d72471e3` | owner、迁移演练及迟到失败的修复前复现 |
| `wp-runtime-w05h:local` | `sha256:03a6187ff277ec58d7e530d136ec84a10425ce770599f41162e149f84d38bc23` | 最终双 preview、双 build、单 check 与实际镜像入口 |
| `wp-lite-w05i:local` | `sha256:95fcbe2cb43e83e2f93d1251281a9277794f78e9c5fba160f5517d35d06501d8` | 最终双 Backend、独立任务/完整链路复测与实际镜像入口 |

最终 Runtime/Lite 的发布指纹均为 `1.0.0+sha256-e535a03c41e595276df3c61a864e79e0063521df4db535b69e9acaa9b1338f55`；各副本 ID 独立，不参与版本匹配。`credentials-runtime.json` 是中间候选记录，最终 Runtime 与 Renderer 凭证负例以 `credentials.json` 为准。

## 已完成的场景

| 关联项 | 场景与实际结果 | 原始小型记录 |
| :--- | :--- | :--- |
| W05b / M04 owner | 真实普通 Run，无 SSE；强杀 A 后同 hostname/PID=1 重启，13.299 秒收敛为 `AI_RUN_PROCESS_STOPPED`，只有一次终态；B 静默运行受保护，同会话可启动新 Run | [owner.json](./records/owner.json) |
| W05b / M04 迟到结果 | `docker pause` 后 11.635 秒收敛；unpause 并释放真实模型流后，旧 Run 的事件序号与终态计数不变，失效写围栏拒绝迟到提交 | [owner-pause.json](./records/owner-pause.json) |
| W05b / M04 重建 | 改变 hostname、重建容器，PID 仍为 1，新 UUID 区分身份；11.479 秒收敛，会话可继续，B 未误杀 | [owner-hostname.json](./records/owner-hostname.json) |
| W05a / M05 旧 ORM | 专属真实 PG 从 `20260926_0100` 前滚至 `20260930_0300`；实际 `4c7eee8` app 源码完成页面入队幂等、完整 Batch SELECT/INSERT/UPDATE、过期 Batch 清扫及 Run 取消 | [legacy-postgres.json](./records/legacy-postgres.json) |
| W05a / M05 旧迁移器 | 实际旧 Alembic 对 `20260930_0300` 返回非零（255），明确拒绝未知 revision | [legacy-migrator.json](./records/legacy-migrator.json) |
| W05c / M05 正常同版 iframe | 浏览器从正常预览 API 返回的入口导航，57 条响应；子请求覆盖两个同版副本，scoped CSS 实际颜色/间距正确，字体解析完成，身份一致，无失败网络请求或页面异常 | [browser-same.json](./records/browser-same.json) |
| W05c / M05 正常跨版 iframe | HTML 绑定 A（当前候选），子请求强制落到真实旧镜像 `wp-runtime-w05c:local`（`aab57cd`）的 B；main.ts、Tailwind CSS、Vite 均为 409，目标页面未加载；没有手工版本头 | [browser-cross.json](./records/browser-cross.json) |
| W04 / M01 Runtime/Lite 入口 | 生产依赖裁剪后实际入口健康；真实模块/CSS/Vite HTTP 与跨版 HMR Upgrade 拒绝通过，两镜像指纹一致 | [Runtime](./records/image-runtime.json)、[Lite](./records/image-lite.json) |
| W04 / M01 Renderer 入口 | 镜像实际 CMD，真实控制 API/默认执行器截图，PNG 像素及摘要校验，消费确认后槽位 idle | [Renderer](./records/image-renderer.json) |
| W04 / M01 凭证负例 | Runtime/Renderer 各自缺配置、不存在文件、0400 空文件，六种实际 CMD 启动均非零拒绝 | [credentials.json](./records/credentials.json) |
| W04 / M01 完整链路 | 最终 Backend 候选、新页面 10；经 Gateway 产生截图 Job 11 与构建 Job 10，PNG 1920×1080/22589 字节，ZIP 15220410 字节，版本/尺寸/摘要均通过；已查看 PNG，目标标题与正文正确 | [pipeline.json](./records/pipeline.json) |
| W04 / M01 构建入口 | 从实际 ZIP 安全解压后用 HTTP 加载，12 条浏览器响应；目标页面及 scoped CSS 生效，字体就绪，无失败请求或页面异常 | [browser-build.json](./records/browser-build.json) |
| M04 独立任务竞争 | 四个不同项目/页面，各自一次入队构建与截图；Build Job 6–9、截图 Job 7–10 全部一次成功，两个 Build/两个 Renderer 均执行；产物下载摘要正确，四个 render attempt 全部释放 | [jobs.json](./records/jobs.json) |
| M04 Worker 摘除门禁 | 两个 Worker 的只读摘除检查均通过，无未释放 attempt | [worker-removal.json](./records/worker-removal.json) |

owner 演练采用 TTL/心跳/扫描 12/2/1 秒，预算 16 秒，包含事务与采样容差；这不是默认生产配置或容量 SLA。模型流只指向本地 fixture，但经过真实 API、适配器和后台执行器。paused / waiting_external / 有效 Batch 续跑租约的完整保护矩阵尚未覆盖。

跨版 script/CSS 的 409 状态及响应身份来自浏览器。Chromium 对被拒绝资源不保留响应正文时，探针按其原始 URL HTTP 复读，核对同一 409/身份及 `PREVIEW_VERSION_SKEW`；记录中的 `code_source` 明确标记这种来源。CSS 使用 HTML 自然请求的 Tailwind 链接；main.ts 已拒绝，不会再触发其嵌套 global.css import。

旧 app 使用当前 Lite Python workspace 依赖环境，覆盖真实领域代码和完整 ORM，未执行完整 N-1 镜像入口、旧模型 deferred 自动续跑、迁移中断与完整发布回滚。升级仍先排空并停旧实例，应用回滚保留新 schema 并关闭旧迁移器。

## 浏览器发现的缺口与修复

实测没有沿用上一轮“镜像入口健康”结论关闭浏览器门，而是从正常 iframe 发起请求。先后复现并修复：

1. Vite 自动发现依赖引入进程相关的预优化 browserHash，同版副本之间出现 `Outdated Optimize Dep`。`8407ae6` 固定显式浏览器依赖集合并禁用自动发现，保留过期请求检查。
2. 版本中的 `+` 被 Vite 字体 URL 重复编码，静态资源误报跨版。`0543f5a` 改用 URL 安全的 `v1.<base64url>` 路径段，签名中的指纹原文保持原语义。
3. scoped CSS 请求落到未加载主模块的副本，Vue descriptor 缺失，尝试读取虚拟文件路径并返回 500。`1bc9ed0` 在合法 ctx 验签后加载该 SFC，恢复本副本描述符；SaaS 解析先于 Vue 接管子请求。
4. ctx 追加到 `lang.css` 后使 Vite 不再把子模块当样式处理；响应虽为 200，浏览器 import 原始 CSS 仍出现语法错误。`43c6515` 前置 ctx，回归同时检查 Vite JS 样式模块，不能只断言 HTTP 200。
5. 正常浏览器入口通过后，真实 Renderer 从 `/runtime/__preview` 导航被误判为独立 SPA，返回 403，导致截图等待协议超时。`e82c793` 共用固定挂载/版本路径解析，受保护入口继续验签，独立页面继续拒绝；旧探针失败保留在[首轮记录](./records/pipeline-before-mounted-preview-fix.json)。

Renderer 首次构建另因默认 Debian HTTP 源失败；`25824b2` 默认使用 HTTPS，并把 Python 同步拆成独立缓存层，避免重试浏览器依赖时重新下载 Python wheel。

独立任务正常竞争首次失败于清理断言：八个业务 Job 均成功，但一个 attempt 被另一协调器的迟到 410 改回 `unknown/pending`，占用已经为 0。`a0779df` 将失败状态与错误字段写入放到占用条件更新成功后，避免 ORM 自动 flush 绕过围栏；真实双会话回归在修复前两种 release 分支均失败，修复后通过。修复前[完整样本](./records/jobs-before-render-cas-fix.json)及[异常字段](./records/render-cas-before-fix.json)保留，修复后重新创建四个独立项目复测，未修改历史记录冒充通过。

## 测试与执行收口

- Runtime 定向 52 项测试及类型检查通过；涵盖固定挂载解析、票据、SFC 子请求与样式转换。
- Backend 渲染控制面、结果冲突、迟到失败真实 ORM 双会话与 DB 分层门禁，共 56 项通过。
- 根 contracts 41 项、repository 13 项通过；新演练 Python 脚本 Ruff、浏览器脚本语法检查通过。Docker 上下文门禁在 Renderer Dockerfile 修改后通过。
- 真实 Docker 场景及生产入口探针按上表执行；未跑全量 Backend/Editor/Runtime/E2E、正式 platform 镜像或 arm64，未执行取消/超时/强杀 attempt、外部 Batch 完整保护和容量 SLA。

逐阶段命令见[演练说明](../../../developer/testing/docker-architecture-drill.md)。最终使用 `backend --backend-image wp-lite-w05i:local`、`runtime --runtime-image wp-runtime-w05h:local`；跨版显式提供 `--other-runtime-image wp-runtime-w05c:local`。Runtime/Lite 官方镜像入口探针输出分别为 `test-results/images/w05h-runtime`、`test-results/images/w05i-lite`，Renderer 为 `test-results/images/w05-renderer-cache`。

本轮修复按问题分别提交：`8407ae6`、`0543f5a`、`25824b2`、`1bc9ed0`、`43c6515`、`e82c793`、`a0779df`。可重跑脚本为 `44fa476`，证据与计划作独立文档提交，未推送远端。

演练结束前执行双 Worker 摘除检查，再使用 `cleanup` 删除本项目容器与卷，见[清理记录](./records/cleanup.json)。开发 PostgreSQL/Redis 继续运行；临时下载服务已停止。没有推送或发布，镜像与可再生成的本地证据保留供复查。

## 重跑与剩余验收

入口、逐阶段命令、隔离约束及清理说明见[本地 Docker 架构演练](../../../developer/testing/docker-architecture-drill.md)。原始大日志、PNG、ZIP 和失败截图保存在本机 `test-results/docker-architecture/wp-arch-drill-adc5a2ca/`，不提交可再生成的大文件或带凭证的上下文。`records/` 只收录脱敏小型 JSON。

M01/M04/M05 只按上述已通过场景推进，完整门继续开放。M02 跨任务文件/token/网络权限，M04 attempt 故障、取消竞争、额度与 Batch 一次消费，M05 完整 N-1 入口/回滚与公共能力组合，M03 正式容量、M06 arm64/Registry/外部部署、M07 业务恢复、M08 UI/跨仓行为仍需各自证据。

本地 Docker 可继续执行行为、权限、故障、迁移和隔离恢复；正式容量需要无干扰资源，arm64 与外部部署需要对应架构/环境。无需把尚未验证的普通 Docker 场景都推给远程测试机。
