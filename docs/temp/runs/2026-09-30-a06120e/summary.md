# 测试机运行记录 2026-09-30 · 候选 a06120e

> **状态**：M01（真实交付链路）+ IMG0 + F5/F6/F7/F9 修复 + **M03 探索性容量基线** 已执行；容量 SLA 未锁定，M03-F1 开放。  
> **候选**：`a06120e25bf13c9668ec42b5e41f6e022f765876`（`dev`，已推送 origin）。  
> **机器**：38.14.63.47 · Ubuntu 24.04 · 2C (Xeon 8168) / 3.8 GiB + 4 GiB swap · `/data` 50 GiB（Docker data-root）· Docker 29.8.1 / Compose v5.5.1 · amd64。  
> **时区**：容器日志 UTC；主机本地约 UTC+8。起止约 2026-09-30 01:05–02:00 UTC。

## 0. 产物入库边界

可再生产物 `m01-head/build.zip`（约 15MB）**不入库**；sha256 已记于 §2。完整 ZIP 留在测试机 `/data/wp-test/` 与运行目录，需要时按摘要中的校验和核对。

| 镜像 | Tag | Digest / Image ID | 说明 |
| :--- | :--- | :--- | :--- |
| Renderer | `llmxpm/web-presentation-renderer:m01-a06120e` | `sha256:1719abb341a1f6cb110d628ecbc23eb9b6a703284887126faf105e5ebc46e452` | HEAD `renderer/Dockerfile`，含 Playwright Chromium |
| Lite | `llmxpm/web-presentation:sqlite-lite-head-a06120e` | `sha256:3e2630e13f2eaa20d5644874f47cc1fcf558e869297dc72fc78b385b25ea744b` | HEAD `Dockerfile.lite`，含 tiktoken 预置；**无**内置浏览器 |
| 已发布对照 | `llmxpm/web-presentation:sqlite-lite` | `sha256:5bd8d0fa08a6fa0b2c54c830fd43c75327dcacb0fe9e265194a81f03b74ba9e5` | v0.2.x 旧架构，仅作差距对照 |

构建机即测试机（2C4G+4G swap）；`Dockerfile.lite` 与 `renderer/Dockerfile` 均一次构建成功。

## 2. M01 结果（HEAD 双进程拓扑）

**拓扑**：`platform-lite` + `renderer`（最终采用 `network_mode: service:platform-lite` 共享网络命名空间，进程分离、回环可达 Runtime）。见缺陷 M01-F5/F6。

| 检查项 | 结果 | 证据 |
| :--- | :--- | :--- |
| Backend→Renderer→Runtime 截图 | **通过** | `m01-head/page.png` 1920×1080 PNG，15294 bytes，sha256 `a8c7797d…8629ce` |
| `screenshot_is_latest`（默认视口） | **true** | `m01-head/pipeline.json` |
| 项目构建 ZIP 下载 | **通过** | `m01-head/build.zip` 15220246 bytes，sha256 `b8bd9d12…c0187`，19 项，含 `index.html`，与 job `artifact_sha256` 一致 |
| 登录空密码 | **拒绝** 422 | 密码最少 8 字符 |
| 登录错误密码 | **拒绝** 401 | `AUTH_INVALID` |
| IMG0 容器内 root Chromium（无 `--no-sandbox`） | **通过** | `renderer-img0/page.png` 320×240，控制 API 真实执行器出图 |

## 3. 缺陷与发现

| ID | 严重度 | 描述 | 证据/复现 |
| :--- | :--- | :--- | :--- |
| **IMG0-PASS** | — | 历史「从未验证」的 root + 默认 seccomp Chromium 启动**成立**；无需 `--no-sandbox`。 | `renderer-img0/` |
| **M01-F5** | P1 | `page_screenshot_service` 构造浏览器 `preview_url` 使用 `resolve_runtime_role_base_url('preview')`（Backend 回环），忽略 `RENDER_RUNTIME_NAVIGATION_BASE_URL`。双容器下 Renderer Chromium 访问 `127.0.0.1:7373` → `ERR_CONNECTION_REFUSED`。 | job error_message；`backend/app/services/page_screenshot_service.py` 约 :424；`target_resolver.navigation_base_url()` 已有正确字段未接入 |
| **M01-F6** | P1 | Runtime Vite `allowedHosts` 拒绝 Docker 服务名：`http://platform-lite:7373/__preview` → **403 Blocked request**。即使修正 F5 的 URL，跨容器主机名仍被拒。 | curl 自 renderer 容器 |
| **M01-F7** | P1 | `render_workers` 注册在 `worker_epoch='pending'` 时 INSERT，撞 `UNIQUE(worker_id, worker_epoch)`，随后 `PendingRollbackError` 使协调器 tick **整轮失败**，截图调度停摆。Worker 配置/epoch 变更或残留 `pending` 行后可复现。 | platform-lite 日志 `render.worker.config.failed` / `render.coordinator.tick.failed` |
| **M01-F2** | P2 | `screenshot_is_latest` 在自定义视口（如 320×240）时恒为 false（与项目默认 1920×1080 比对）。`check-deployment-pipeline.py` 固定 320×240，故官方探针在默认语义下会误报。默认视口截图后为 true。 | 两种视口对照；`page_service._is_page_screenshot_latest` |
| **M01-F4** | P2 | Renderer 回执 `status=succeeded` 后 `cleaned_at=null`、`resource_state=retained`，直至 result-consumption；探针在下载前强制要求 `cleaned_at` 会失败。 | `renderer-img0/receipt.json` |
| **M01-F1** | P2 | 已发布 `sqlite-lite` 在 `--network none` 下因 tiktoken 外联失败退出；HEAD 已预置 BPE，离线启动待单独复测。 | `check-image-startup --variant lite` published vs HEAD |
| **M01-F8** | P3 | 容器重建后 Gateway 短暂 502（healthz 由 nginx 回 ok 时 Backend 未必就绪）；探针/脚本需按 ready+login 重试。 | compose recreate 窗口 |

## 4. 环境与拓扑记录

- 额外盘 `/dev/vdb` 50 GiB 已格式化挂载 `/data`，Docker `data-root=/data/docker`。
- 无 PG/Redis：Lite 形态 `DATABASE_URL=sqlite+aiosqlite` + `REDIS_URL=memory://lite`；`DATABASE_WRITE_PATH_METRICS_ENABLED=true` 已开。
- 并发按 Lite 模板固定 1（`RENDER_GLOBAL_CONCURRENCY` / `AI_PAGE_MUTATION_CONCURRENCY` 等）。
- 测试数据：API 创建 workspace/project/page + `home` 路由（构建需要入口路由）。
- 密钥：强 `DEFAULT_ADMIN_PASSWORD` / Fernet `AI_SECRET_ENCRYPTION_KEY` / `render_service_credential`；**不入库**。

## 3.2 修复状态（2026-09-30 第三批 · M04-F1/F2）

| 缺陷 | 状态 | 改动 |
| :--- | :--- | :--- |
| M04-F1 凭证 0444 fail-closed | **已修 + 实机验证** | 根因：Compose 顶层 secrets 的 `mode/uid/gid` 被忽略。改为服务级长语法；`readRuntimeBuildWorkerCredential` 对属主可写文件自动 `chmod 0400`；文档补齐宿主机 `chmod 400` |
| M04-F2 spawn EPERM | **已修 + 实机验证** | 根因：非 root 主进程无 `CAP_SETUID`；**`cap_add` 对非 root 无效**（实测仍 EPERM）。`runtime/Dockerfile` 改 `USER root`，spawn 降权到 `rtchild`；错误映射 `RUNTIME_BUILD_CHILD_IDENTITY_EPERM` |
| W01 隔离边界 | **实机成立** | root 读 secret OK；UID 10001 子进程读 `0400` 得 EACCES；`CHILD_UID=10001` 下真实构建 job 6 成功（16.3s / 15MB ZIP） |

本地：`test:runtime:gate` 587 项通过（含新增 auto-heal / EPERM 映射用例）。

| 缺陷 | 状态 | 改动 |
| :--- | :--- | :--- |
| M01-F5 | **代码已修** | `page_screenshot_service` 浏览器 `preview_url`/资源基址改走 `RenderTargetResolver.navigation_base_url()` / `asset_base_url()`；单测 `test_capture_target_uses_browser_navigation_base_url` |
| M01-F7 | **代码已修** | `ensure_workers_from_config` 复用 `worker_epoch=pending` 行，不再重复 INSERT；单测 `test_ensure_workers_from_config_reuses_pending_epoch_row` |
| M01-F6 | **代码已修** | Vite `allowedHosts` 合并回环与 `RUNTIME_BASE_URL`/`RUNTIME_PREVIEW_BASE_URL` 主机名；compose 增加 `RUNTIME_SERVER_ALLOWED_HOSTS` 与 `RENDER_RUNTIME_NAVIGATION_BASE_URL`；实测 `http://platform-lite:7373` 返回 401（鉴权）而非 403（host 拒绝） |
| M01-F2 / F4 | **探针已修** | `check-deployment-pipeline` 默认视口；renderer 探针不再要求下载前 `cleaned_at` |
| M01-F9 | **已修** | 浏览器资源基址曾丢 Vite base 路径：`RENDER_RUNTIME_ASSET_BASE_URL` 仅写主机时生成 `/@vite/client` → 404，`render-ready.v1` 永不就绪。`RenderTargetResolver.asset_base_url()` 对 host-only 配置自动补 `runtime_public_base_url` 路径；实测真双容器截图+ZIP 通过（`is_latest=true`）。诊断信息保留在 renderer 超时消息中（url/html/scripts/resources） |
| M01-F5 实测 | 部分 | 重建镜像后 `navigation_base_url() == http://platform-lite:7373`；POST executions 有发出，失败点在 render-ready |

本地回归：`test_render_control_plane.py` 36 项 + screenshot/render 相关 unit 108 项通过；`vite.config.test.ts` 10 项通过；`test:repository` 13 项通过。

## 4.1 M03 预采样（探索性，非正式容量结论）

干净卷 + 成功截图后空闲采样（约启动后 2–3 分钟）：

| 指标 | 值 |
| :--- | :--- |
| platform-lite RSS | **1.605 GiB / 3.824 GiB（42%）** |
| renderer RSS | 36.3 MiB |
| 主机 used / swap | 2.2 GiB / 332 MiB |
| `/metrics/db-write`（:8000） | sql_total 20899，avg 2.25 ms，**max 4245 ms**，write_conflicts 0，invalid_writes 158，busy_timeouts 0 |
| `/metrics/job-queues` | 各队列 pending/running=0 |

注意：Gateway 对 `/metrics/*` 与 `/readyz` 回 SPA HTML，观测需走 Backend `:8000` 或补路由。Runtime 健康里 RSS 约 1.4 GB。**正式 M03 混合负载需在 F5/F7 修复后采集**，否则调度可能停摆导致样本失真。

## 5. 未执行

| 项 | 状态 |
| :--- | :--- |
| M03 Lite 2C4G 空闲+混合容量 | **已完成（探索性）** | 5 用户/并发 3 · 82 操作 · 成功率 100% · P50 6.4s / P95 98s · 写冲突 0 · 峰值 RSS 1.77+0.51 GiB · 无 OOM。见 `m03/summary.md` |
| M03 状态 drill | **部分** | baseline 启动与采样通过；`create_project_preview` 触发 `RUNTIME_STATE_CAPACITY_EXCEEDED`（M03-F1，约 6.9MB 时） |
| M03 正式 SLA | **未定** | 无预批阈值；容量门保持开放 |
| M02 凭证隔离 | 未执行 |
| M04/M05 多副本与版本矩阵 | **M04 门已关闭** | F1/F2/F3/F4 已处理；恢复上界 129s ≤ 租约 300s。见 `m04/summary.md` |
| M05 版本矩阵 | **门已关闭** | N-1=`4c7eee8` 实测 A/B/C/D/E/F + 中断迁移；B/E 边界写清（先 migrate 再混跑）；M05-F1 指纹 409 已修。见 `m05/summary.md` |
| M06 发布/双架构 | 未执行 |
| M07 备份恢复 | 未执行 |
| M08 UI/跨仓 | 未执行 |
| HEAD lite `--network none` 离线启动 | 有预置，未复测 |
| `check-deployment-pipeline.py` 官方探针全绿 | 受 M01-F2 视口语义限制 |

## 6. 后续建议

1. **先修 M01-F5**：截图 `preview_url` 改走 `RenderTargetResolver.navigation_base_url()`（或显式 `RENDER_RUNTIME_NAVIGATION_BASE_URL`）。
2. **M01-F6**：Runtime 允许部署配置的 preview 主机名，或文档要求 Renderer 与 Runtime 共享 netns / 使用 IP。
3. **M01-F7**：`ensure_workers_from_config` 对 `worker_epoch='pending'` 做 upsert/清理，避免 UNIQUE 后会话卡死。
4. **M01-F2**：明确 `screenshot_is_latest` 是否应包含视口语义；同步修正探针视口或字段含义。
5. 处理 M03-F1（drill 容量拒绝）并锁定延迟阈值后，再决定是否把 Lite 规模升格为承诺；多副本 M04/M05 申请 4C8G。

## 7. 证据索引

- `m01-head/pipeline.json` — HEAD M01 汇总
- `m01-head/page.png` / `m01-head/build.zip` — 真实产物
- `renderer-img0/image.json` / `page.png` / `receipt.json` — IMG0
- 测试机原始目录：`/data/wp-test/test-results/`，compose：`/data/wp-test/compose.head.yml`
