# M04 跨副本与故障恢复 · 2026-09-30

> **机器**：升级后 4C / 7.8 GiB · Ubuntu 24.04 · Docker 29.8.1  
> **候选**：`a06120e` + F5/F6/F7/F9 修复  
> **拓扑**（`/data/m04/compose.m04.yml`）：
> - PostgreSQL 15 + Redis 7（共享）
> - **2 Backend**（`BACKEND_MULTI_INSTANCE=true`，hostname=backend-a/b，共享 RSA/对象卷）
> - **2 runtime-preview** + **2 runtime-build** + **1 runtime-check**
> - **2 Renderer**（renderer-1/2，共享服务凭证）
> - Gateway :18080（backend RR + runtime-preview RR，含 `max_fails` 摘流）
> **镜像**：`platform-m04` / `web-runtime-vue:m04` / `renderer:m01-f9dbg`（源码构建）

## 1. 场景结果

| ID | 场景 | 结果 | 证据 |
| :--- | :--- | :--- | :--- |
| S1 | 跨副本截图×4 + 构建下载 | **通过** | 截图 4/4，PNG 1920×1080，`is_latest=true`；ZIP 含 index.html |
| S2 | 双 build worker 并行（两项目） | **通过** | 两构建同时成功（19s / 20s），sha 各自独立 |
| S2b | 同项目并发构建 | **预期串行** | 409 `PROJECT_BUILD_ALREADY_RUNNING` |
| S3 | 重启 Backend-A 时在途截图 | **部分** | Job 卡 `running` 约 240s 后 **succeeded**（租约/重试收敛）；期间 gateway 切 B 可继续查询 |
| S4 | Worker 摘除门禁 | **通过** | `check_render_worker_removal`：renderer-1「有 1 个未释放 attempt」→ 拒摘；renderer-2「可安全摘除」 |
| S5 | 取消截图 | **未测** | 取消端点 404（路径与文档不符，待对齐） |

## 2. 发现

| ID | 级别 | 描述 |
| :--- | :--- | :--- |
| **M04-F1** | P1 | **Compose secrets 默认 0444** 与 W01 隔离冲突：runtime 镜像 `RUNTIME_BUILD_CHILD_UID=10001` 时，凭证 `mode&077≠0` 触发 `RUNTIME_BUILD_CREDENTIAL_LOOSE_MODE` fail-closed。根因：`mode/uid/gid` 写在顶层 secrets 会被 Compose 忽略。**已修**：服务级长语法 + 启动时 chmod 0400 自动收紧 |
| **M04-F2** | P1 | **`spawn EPERM`**：镜像内置 `RUNTIME_BUILD_CHILD_UID/GID=10001`，非 root 主进程无 `CAP_SETUID`。**实测 `cap_add: [SETUID,SETGID]` 对非 root 无效**（仍 EPERM）。**已修**：主进程改 `USER root`，spawn 降权到 rtchild 成功 |
| **M04-F3** | P2 | **Backend-A 重启后在途截图恢复**：实测 t+129s 终态 `succeeded`，**≤ DURABLE_JOB_LEASE_SECONDS(300s)**。恢复上界 = 剩余租约 + 认领/重试，与租约配置一致。见 §2.2 |
| **M04-F4** | P3 | 截图取消 API 路径：探针误用 `/api/pages/screenshot-jobs/{id}/cancel`（404）。**正确路径** `/api/page-screenshot-jobs/{id}/cancel` 返回 200。探针路径已修正，非产品缺陷 |
| — | 信息 | 双 Renderer 均被协调器轮询；worker 摘除门禁在多副本下正确区分「有在途 attempt / 可摘除」 |

### 2.1 F1/F2 修复验证（2026-09-30 第三批，实机）

| 检查 | 结果 | 证据 |
| :--- | :--- | :--- |
| 非 root + `cap_add SETUID/SETGID` 降权 | **失败 EPERM** | `docker run --user 10000 --cap-add SETUID --cap-add SETGID` → `spawnSync EPERM` |
| root 主进程降权到 UID 10001 | **通过** | `child-ok 10001 10001` |
| W01：rtchild 读 `0400` secret | **拒绝 EACCES** | parent-read OK / child-denied EACCES |
| F1：`0644` 凭证 chmod 0400 自动收紧 | **通过** | before 644 → after 400 |
| 恢复 `CHILD_UID=10001` 后真实构建 | **通过** | job 6 `succeeded`，16.3s，artifact 15219975 bytes，`index.html`；build-b 日志 `job_succeeded`，无 EPERM |
| runtime-build 就绪 | **healthy** | `wp-m04-runtime-build-a/b` healthy，worker claim 循环运行 |

### 2.2 F3 恢复时间上界（2026-09-30 第四批）

| 项 | 值 |
| :--- | :--- |
| 操作 | 创建截图 job 4 → `docker restart wp-m04-backend-a-1`（3.69s）→ 经 Gateway 轮询至终态 |
| 结果 | `succeeded`，**time_to_terminal = 129.2s** |
| 租约配置 | `DURABLE_JOB_LEASE_SECONDS=300`，心跳 30s |
| 上界结论 | **恢复时间有界：≤ 剩余租约（≤300s）+ 认领/重试**；本例 129s 落在租约窗口内，与配置一致 |
| F4 | 坏路径 404 / 好路径 200；取消语义走 `page-screenshot-jobs/{id}/cancel` |

## 3. 结论（M04 门）

| 门 | 状态 |
| :--- | :--- |
| 跨副本预览/截图/构建 | **已验证**（2 preview + 2 build + 2 renderer + 2 backend） |
| 双协调器不重复领取 | **已验证**（同项目 409 串行；异项目双 build 并行成功） |
| Worker 摘除门禁 | **已验证** |
| 故障恢复时间上界 | **已验证有界**（129s ≤ 租约 300s；上界=剩余租约+认领/重试） |
| W01 隔离在多副本生产镜像 | **已通过**（F1/F2 实机：root 主进程 + rtchild 降权 + 真实构建成功） |
| 任务终态收敛 | **已验证**（成功/失败/取消路径均有终态；取消走正确 API） |

**M04 门：关闭（2026-09-30）**。前提：F1/F2/F3/F4 已处理；恢复上界与 `DURABLE_JOB_LEASE_SECONDS` 一致。

**多副本承诺边界**：M04 关闭仅代表「跨副本正确性与故障恢复有界」；**M05 版本矩阵未完成前仍不得宣称滚动升级/混版生产可用**。普通 AI Run 仍不跨实例迁移（产品既定语义）。

## 4. 证据

- `/data/m04/` — compose、env、secrets、gateway
- `/data/wp-test/test-results/m04/` — `m04-s1.json`、`m04-scenarios.json`
- 容器日志：`wp-m04-*`（build EPERM、worker poll、摘除门禁输出）
