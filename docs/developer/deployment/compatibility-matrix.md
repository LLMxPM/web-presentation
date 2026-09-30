<!-- 文件功能：定义 Backend/Runtime/Renderer/DB/Runtime Kit 的 N/N-1 支持组合、升级窗口与摘流策略，支撑 AR-05/W05 与 M05。 -->
# 版本兼容矩阵与升级窗口

本文定义平台各组件在升级或回滚时的支持边界，对应 AR-05 / W05。M05 已有特定版本组合的实机记录；[09-30 复核](../../temp/architecture-assessment-2026-09-30.md)发现 `4c7eee8` 的页面 Batch ORM 仍查询 N 已删除的列，撤回 B/E 的完整业务兼容结论。入口 409 也尚未覆盖正常浏览器子请求，跨版滚动继续待验收。

## 1. 组件与版本轴

| 组件 | 版本标识 | 取值来源 |
| :--- | :--- | :--- |
| Backend | Release tag / Git SHA / 镜像 digest | 发布流水线；`alembic_version` 另记 DB revision |
| Runtime（preview/build/check） | 同一镜像 tag + `runtime_kit_version` + `build_id` | `/__runtime_healthz` |
| Renderer | Release tag / 镜像 digest | `capabilities.protocol_version` = `internal/render/v1` |
| Runtime Kit | `runtime-kit.manifest.json` 的 `version`（当前 `1.0.0`）与导出 `.vN` | 清单与 `@runtime-kit` import path |
| 渲染契约 | `PROTOCOL_VERSION` = `internal/render/v1`；`RUNTIME_RENDER_PROTOCOL_VERSION` = `render-ready.v1` | `packages/render-contracts` |
| 数据库 | Alembic `alembic_version` | `backend/migrations/versions/` |
| 页面/组件产物 | 预览 artifact、构建 ZIP、组件 previewSchema | 存储中的产物元数据 |

## 2. N / N-1 支持矩阵（目标约定）

N/N-1 必须绑定具体版本。当前 M05 样本为 `a06120e + 修复` 与 `4c7eee8`，后者是选定 Git 稳定点，不是任意前一 Release 的兼容保证。下表结合该样本与 09-30 复核；局部成功不能代替完整业务验收。

| 组合 | Backend N | Runtime N | Renderer N | DB revision N | Backend N-1 | Runtime/Renderer N-1 | 结论（M05 实测后） |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| A | ✓ | ✓ | ✓ | ✓ | — | — | 同版本全量，支持 |
| B | ✓ | ✓ | ✓ | ✓ | ✓ | — | **当前不支持完整页面业务混跑**：N 删除 `ai_page_mutation_batches.lease_generation`，`4c7eee8` ORM 仍查询该列；登录 200 不证明页面任务入队可用。须保留旧列或排空并停止旧版后迁移 |
| C | ✓ | ✓ | ✓ | ✓ | — | ✓ | 特定 Renderer 混池有局部记录；协议/Kit 一致只是必要条件。N-1 Runtime 的 allowedHosts 差异与浏览器跨版子请求仍需验收；当前预览池固定同一发布版本 |
| D | ✓ | — | — | N-1 | — | — | **迁移窗口内**旧 DB + 新 Backend：**不支持**（N ORM 需要新列）；必须先 upgrade 再启 N。N-1 + 旧 DB 可运行 |
| E | — | — | — | ✓ | ✓ | ✓ | **当前不支持仅回退应用镜像**：旧迁移命令缺 revision，旧页面 ORM 还缺已删列。需用包含新 revision 的迁移器按兼容顺序恢复 schema，或采用保留旧列的发布方案，再启动 N-1；恢复操作须先备份并在隔离库验证 |
| F | 混用不同发布版本的 Runtime 副本 | | | | | | **不支持**；入口携带失配期望头时 409 `PREVIEW_VERSION_SKEW`，正常浏览器子请求的自动拒绝尚待实现；见 §4 |

### 2.1 明确不支持 / 明确拒绝

| 场景 | 行为 |
| :--- | :--- |
| 删除或修改仍被依赖的 `@runtime-kit/...vN` 公开路径 | 旧产物/旧页面源码导入失败；必须保留旧版本文件或做迁移 |
| Backend 调用 Renderer 时契约版本不一致 | `contract_version` 校验失败，任务失败并留错误码 |
| 预览请求携带与 Runtime 副本不一致的 `x-expected-runtime-version-fingerprint` | 409 拒绝（指纹门禁） |
| DB `alembic_version` 指向镜像不包含的 revision | 启动失败（`Can't locate revision identified by '…'`） |
| `4c7eee8` 页面 Batch ORM 运行在已删除 `lease_generation` 的 N schema | 完整 ORM 查询缺列失败；登录可成功，页面变更入队仍不兼容 |
| N Backend + DB 仍停在 N-1 schema | 启动失败（`UndefinedColumnError`，如 `ai_agent_runs.process_owner`）；必须先 migration |
| 预览请求 `x-expected-runtime-version-fingerprint` 与副本不符 | **409** `PREVIEW_VERSION_SKEW`（不得收成 500） |
| 破坏性 External API 字段变更未做消费者迁移 | CLI/Skill/Editor 契约门禁失败；禁止静默兼容 |

## 3. 升级窗口与摘流策略

### 3.1 预览角色：同版池切换与排空

同版副本替换可增减池内实例；跨版切换当前按以下停机/排空顺序处理：

1. 启动新版 `runtime-preview`，等待 `/__runtime_readyz`，核对 `/__runtime_healthz` 的 `runtime_kit_version` / `build_id`。
2. 新版暂不加入旧池；暂停新的预览入口，旧池停止接收新请求。
3. 等待在途连接结束（注意 HMR WebSocket 可能长连接，排空应有上界，超时后强制下线并记录）。
4. 将预览池整体切换为新版并 `reload`，再恢复入口，避免同池混版。
5. 停止旧容器。

同一预览池当前只放同一发布构建标识，不能只比较 `runtime_kit_version`。现有指纹只在 HTML 入口收到期望请求头时检查，尚不能保证正常模块子请求拒绝混版。跨版升级应先排空旧池再切换，完整传播机制验收前不承诺滚动无中断。

### 3.2 构建 / 检查角色：排空后替换

1. 摘掉领取（停容器或阻断 `runtime-jobs-net`），等待在途任务完成或租约过期。
2. 部署新版本，确认 Worker 启动（`RUNTIME_ROLE=build` 缺凭证会 fail-closed）。
3. 构建任务有 attempt 围栏：迟到上传不会提升旧 attempt 产物。

### 3.3 Backend：停机或双副本

- **小团队 / Lite**：停机升级。先备份 → `backend-migrate` → 启动新 Backend。
- **多副本**：必须先逐项证明旧应用兼容新 schema，才能先扩新副本、再摘旧副本。当前 N/N-1 组合有删列冲突，页面业务按停机升级处理；共享签名密钥环、DB、对象存储与 Redis。普通 AI Run 不跨实例迁移（见 §5）。

### 3.4 DB migration 窗口

1. 备份数据库（见[备份与恢复](./backup-restore.md)）。
2. 兼容检查须同时覆盖新增与删除字段；当前含删除旧 ORM 仍映射的列时，先排空并停止旧业务实例，再只跑一次 `alembic upgrade head`（`backend-migrate` 或入口脚本）。
3. 再滚动/启动业务副本。
4. 回滚前确认旧镜像包含当前 `alembic_version`；不可逆 migration 只能前滚或从备份恢复。

## 4. 版本指纹门禁

Runtime 在 HTML 入口收到 `x-expected-runtime-version-fingerprint`（`runtime_kit_version+build_id`）时拒绝失配；无该头则放行。当前 Backend/Gateway/Editor 未自动传播期望值，模块分支不执行该检查。M05 人工请求的 409 只证明入口拒绝，多副本预览必须：

- 同池固定同一发布镜像，`build_id` 表示发布构建身份，各副本相同；副本 ID 独立记录；
- 滚动时按 §3.1 排空，避免 HTML 与模块来自不同版本；
- 检查角色缓存指纹包含 Runtime Kit 清单 hash（`CodeCheckFingerprintBuilder`），升级编译器后缓存自然失效。

## 5. Run 收敛边界（hostname / PID）

普通 AI Run 使用进程内执行，产品承诺「中断不自动续跑」。启动恢复见 `backend/app/ai/run_recovery.py`：

| 条件 | 启动恢复是否收敛 | 说明 |
| :--- | :--- | :--- |
| `process_owner` 为空 / 无法解析 | 仅单进程部署（`include_unowned`） | 多副本默认跳过，避免误杀 |
| hostname ≠ 本机 | **否** | 保护其它副本活跃 Run |
| hostname = 本机且 PID 仍存活 | **否** | 含当前进程与同机 sibling |
| hostname = 本机且 PID 已死 | 是 | 终态为 `AI_RUN_PROCESS_STOPPED` 或取消 |

**已知边界（M04 需覆盖）：**

1. **容器重建 / hostname 改变**：原 Run 归属旧 hostname，启动恢复不会收敛。`recover_stale_active_run()` 尚无生产调用点，SSE 只观察，当前需要用户 `force_cancel`；自动有界终态仍是待实现目标。
2. **PID 重用**：若原 PID 被新无关进程占用，`process_is_alive` 为真，启动恢复跳过；当前无后台空闲收敛补偿。`process_owner` 中的 uuid 不参与存活判定。
3. **同名主机、不同 PID namespace**：可能把异 namespace 进程误判为存活或死亡；多副本部署应保证 hostname 唯一（Docker 默认 container id 即可）。

## 6. 验收用例（M05 / M04）

1. 组合 A：全 N 完成一次登录 → 预览 → 截图 → 构建下载。
2. 组合 C：Backend N + Renderer/Runtime N-1（协议未变）完成截图；破坏性变更样本应明确失败。
3. 组合 B/E：除登录外，执行 N-1 页面任务入队与 Batch ORM 查询；缺列必须判不兼容。按既定 schema 恢复后再验证旧版完整业务。
4. 指纹：人工失配入口返回 409；另用正常浏览器让 HTML/模块落到不同版本，验证版本传播或稳定路由。
5. Run：强杀 Backend-A 后重建容器（hostname 变）→ B 的活跃 Run 不被误杀；实现独立 owner 收敛后验证旧 Run 有界终态。当前手动取消不算自动恢复通过。
6. Run：PID 重用模拟 → 启动恢复不误杀；记录收敛延迟。

## 7. 相关文档

- [升级与回滚](./upgrade-rollback.md)
- [多 Backend 与密钥一致性](./multi-backend.md)
- [Compose 部署说明](./compose.md)（预览滚动与指纹）
- [执行隔离与权限矩阵](./execution-isolation.md)
