<!-- 文件功能：说明 Runtime 构建执行侧与可信领取器的权限边界、单任务 token 语义和共享资源矩阵，支撑 AR-01/W01。 -->
# 构建执行隔离与权限矩阵

本文定义 Runtime 构建链路中「可信领取器」与「不可信编译执行进程」的边界，对应架构项 AR-01 / W01。**环境变量删键只是纵深防御，不能单独关闭本项**；关闭条件是操作系统级身份隔离（不同 UID）加上凭证文件权限，由 M02 在测试机验证。

## 1. 角色与信任级别

| 角色 | 进程 | 信任级别 | 允许持有 | 禁止持有 |
| :--- | :--- | :--- | :--- | :--- |
| 可信领取器 | Runtime Build Worker 主进程（`RUNTIME_ROLE=build` 内的 Node 主进程，root） | 受信服务身份 | 全局 `build_worker_credential`、单任务 `build_token` / `service_token` | 用户源码直接执行 |
| 编译执行进程 | Vite/Rollup 构建子进程、ZIP 归档子进程、诊断 worker 子进程（`rtchild`/UID 10001） | **不可信**（执行用户手写 SFC） | 仅任务工作区路径、Node 运行时 | 全局 Worker 凭证、其它任务的 token、Backend 控制 API 身份 |
| 检查执行进程 | `RUNTIME_ROLE=check` 诊断子进程（`rtchild`） | **不可信** | 任务工作区 | 任意 Worker 凭证（该角色本就不挂载） |
| 任务 token | claim 响应中的 `build_token` / `service_token` | 单任务短 TTL | 仅对应 job 的 renew/complete | 其它 job 的 claim/renew/complete |

## 2. 权限矩阵

### 2.1 凭证与 token

| 资源 | 可信领取器 | 编译执行进程 | 控制手段 |
| :--- | :--- | :--- | :--- |
| `RUNTIME_BUILD_WORKER_CREDENTIAL` 环境变量 | 可读 | **不可读** | `BUILD_CHILD_ENV_DENY_LIST` 删键 |
| `RUNTIME_BUILD_WORKER_CREDENTIAL_FILE`（如 `/run/secrets/build_worker_credential`） | 可读（0400 属主） | **不可读** | 不同 UID + 文件 `0400`；子进程 spawn 时降权到 `rtchild` |
| 单任务 `build_token` | 持有并用于该 job 的 renew/complete | **不下发** | 由父进程调用 Backend；子进程无控制面调用路径 |
| 单任务 `service_token` | 持有并用于拉取 snapshot/上传产物 | **不下发** | 同上 |

单任务 token 在 claim 时由 Backend 签发，TTL 不超过 job deadline。子进程即使被利用，也无法领取其它任务或伪造服务身份，因为它根本拿不到 token 与全局凭证。

### 2.2 文件系统

| 路径 | 可信领取器 | 编译执行进程 | 说明 |
| :--- | :--- | :--- | :--- |
| `/run/secrets/*` | 读 | **拒绝** | 凭证目录 `0400`；子进程 UID 无读权限 |
| 任务工作区（`/var/tmp/runtime-tasks/<task>`） | 创建、回收 | 读写 | setgid 目录，属组 `rtchild`，子进程可写自己的任务目录 |
| `/opt/runtime`（应用与 node_modules） | 读执行 | 读执行 | 只读共享，不写 |
| 宿主机其它路径 | 按容器文件系统 | 按容器文件系统 | 容器边界即隔离边界；不挂载宿主机敏感目录到 build 角色 |

### 2.3 网络

| 目标 | 可信领取器 | 编译执行进程 | 说明 |
| :--- | :--- | :--- | :--- |
| Backend 内部任务 API（claim/renew/complete、snapshot） | 需要 | **不需要** | 子进程纯本地编译；无凭证也无 token |
| Runtime 自身健康/预览端口 | 可选 | 不需要 | 构建角色只在 `runtime-jobs-net` |
| 公网 / Gateway | 不需要 | **不需要** | `runtime-build` 不挂 `platform-net` |

## 3. 操作系统边界（W01 实现）

生产镜像（`runtime/Dockerfile`）建立两个系统用户：

| 用户 | UID/GID | 用途 |
| :--- | :--- | :--- |
| root | 0 | Build Worker 主进程（可信领取器），须能 setuid 降权 |
| `rtchild` | 10001 | 编译/归档/诊断子进程，**无权读凭证** |
| `rtworker` | 10000 | 保留作凭证属主/兼容位；主进程现以 root 运行 |

要点：

1. 凭证文件必须 `0400`（或 `0600`）。Compose secrets 的 `mode`/`uid`/`gid` 必须写在**服务级长语法**（写在顶层 secrets 会被忽略并退回 0444）；权限过宽时启动会先尝试 `chmod 0400` 自动收紧（root 主进程总能成功），仍过宽则 fail-closed。
2. 子进程通过 `child_process.spawn` 的 `uid`/`gid` 降权到 `rtchild`。对应环境变量：`RUNTIME_BUILD_CHILD_UID` / `RUNTIME_BUILD_CHILD_GID`。**主进程必须以 root 运行**才能 setuid；`cap_add: [SETUID, SETGID]` 对非 root 进程无效（已实测仍 EPERM）。不要用 file capabilities 打在 `node` 上——子进程 exec 同一二进制会重新获得能力，反而破坏隔离。降权成功后子进程 UID=10001，读 `0400` 凭证得到 EACCES。
3. 任务工作区父目录为 setgid（`2770`，属组 `rtchild`），父进程 `mkdir` 的子目录自动继承属组，子进程可写。
4. **环境变量删键仍保留**，作为纵深防御；缺少 UID 隔离时只能算开发/受限形态，不能宣称 W01 关闭。仅删环境变量不够：同 UID 子进程可读 `/proc/<parent>/environ`。

### 3.0 为何主进程是 root

`spawn(uid/gid)` 在 Linux 上走 setuid/setgid。非 root 进程默认没有 `CAP_SETUID`；Docker `cap_add` 只进 bounding set，不会进非 root 的 effective set，实测仍 `EPERM`。root 主进程天然可降权，降权后的 rtchild 无任何 capability（setuid-from-root 会清空），且读不到 `0400` 凭证。信任边界是「root 只跑 claim/renew/complete 与本地编排，不编译用户 SFC」；用户代码永远在 rtchild 里执行。

### 3.1 宿主机 secret 文件（bind-mount / Compose file secrets）

Compose 对 file secrets 多数实现为 bind-mount，**保留宿主机属主与权限**；服务级 `mode`/`uid`/`gid` 部分版本不生效。生产准备 secret 时：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))" > deploy/secrets/build_worker_credential
chmod 400 deploy/secrets/build_worker_credential
```

主进程为 root，可读任意属主的 `0400` 文件并可在启动时收紧权限；降权后的 `rtchild` 读不到。

Windows 开发机不支持 POSIX `uid`/`gid`，本地测试覆盖配置解析与删键行为；不可读验证由 M02 在 Linux 测试机执行。

## 4. 与 Lite 形态的关系

SQLite 轻量单容器把 Backend/Runtime/浏览器放在同一容器，属既有风险接受范围。Lite **不得**把本矩阵的生产隔离结论直接背书到自身；Lite 内置 Renderer 若推进合并，须重新设计权限并重跑 M01/M02/M03/M07。

## 5. M02 验收要点（下一轮测试机）

1. 在 build 子进程内尝试读取 `/run/secrets/build_worker_credential` → 必须失败（EACCES）。
2. 使用子进程打印的环境变量，确认无 `RUNTIME_BUILD_WORKER_CREDENTIAL(_FILE)`。
3. 尝试用全局凭证领取其它 pending 构建 → 应使用主进程身份验证；子进程无法发起该调用。
4. 单任务 `build_token` 不能 renew/complete 其它 job_id。
5. 取消/超时后子进程 PID 必须退出，无僵尸占用槽位。
6. 记录允许/拒绝矩阵实测结果到 `docs/temp/runs/<date>-<sha>/summary.md`。

## 6. 相关代码与配置

- 环境剔除与降权：[`runtime/src/core/plugins/runtime-build-worker.ts`](../../../runtime/src/core/plugins/runtime-build-worker.ts)
- 镜像用户与目录：[`runtime/Dockerfile`](../../../runtime/Dockerfile)
- 编排 secrets：[`deploy/compose/compose.runtime-roles.yml`](../../../deploy/compose/compose.runtime-roles.yml)
- 凭证宽松告警：[`runtime/src/core/plugins/runtime-build-runner.ts`](../../../runtime/src/core/plugins/runtime-build-runner.ts)
