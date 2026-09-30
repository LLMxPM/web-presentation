<!-- 文件功能：定义 Backend/Runtime/Renderer/DB/Runtime Kit 的 N/N-1 支持组合、升级窗口与摘流策略，支撑 AR-05/W05 与 M05。 -->
# 版本兼容矩阵与升级窗口

本文定义平台各组件在滚动升级或停机升级时的**支持组合**与**不支持组合**，对应架构项 AR-05 / W05。矩阵本身是工程约定；**M05 在测试机按组合实测前，不得把任何组合标为「已验收」**。409/指纹拒绝只证明失配可被识别，不等于滚动升级可用。

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

N 表示当前 Release，N-1 表示上一个稳定 Release。**下表是支持目标，不是已通过 M05 的结论。**

| 组合 | Backend N | Runtime N | Renderer N | DB revision N | Backend N-1 | Runtime/Renderer N-1 | 结论（M05 实测后） |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| A | ✓ | ✓ | ✓ | ✓ | — | — | 同版本全量，支持 |
| B | ✓ | ✓ | ✓ | ✓ | ✓ | — | **仅当 DB 已迁到 N**：N-1 对 N schema 向后兼容（多出的列可忽略）。**N 不可跑在 N-1 schema**（缺 `process_owner` 等列会启动失败）。灰度顺序：先 `upgrade head` → 再混跑/替换 Backend |
| C | ✓ | ✓ | ✓ | ✓ | — | ✓ | **仅当**内部协议仍为 `internal/render/v1` 且 Runtime Kit 公开路径未删 `.vN`；条件支持。N-1 Runtime 缺 F6 allowedHosts 修复时，跨主机名预览可能 403 |
| D | ✓ | — | — | N-1 | — | — | **迁移窗口内**旧 DB + 新 Backend：**不支持**（N ORM 需要新列）；必须先 upgrade 再启 N。N-1 + 旧 DB 可运行 |
| E | — | — | — | ✓ | ✓ | ✓ | 回滚到 N-1 镜像 + DB 已迁到 N：`alembic` 明确拒绝（`Can't locate revision`）；N-1 **应用**在 N DB 上可运行（多列无害），但 **不得**再跑 N-1 的 `upgrade head`。需回退 schema 时按序 `downgrade` |
| F | 混用不同 `runtime_kit_version` 的 Runtime 副本 | | | | | | **不支持**（指纹不符 409 `PREVIEW_VERSION_SKEW`）；见 §4 |

### 2.1 明确不支持 / 明确拒绝

| 场景 | 行为 |
| :--- | :--- |
| 删除或修改仍被依赖的 `@runtime-kit/...vN` 公开路径 | 旧产物/旧页面源码导入失败；必须保留旧版本文件或做迁移 |
| Backend 调用 Renderer 时契约版本不一致 | `contract_version` 校验失败，任务失败并留错误码 |
| 预览请求携带与 Runtime 副本不一致的 `x-expected-runtime-version-fingerprint` | 409 拒绝（指纹门禁） |
| DB `alembic_version` 指向镜像不包含的 revision | 启动失败（`Can't locate revision identified by '…'`） |
| N Backend + DB 仍停在 N-1 schema | 启动失败（`UndefinedColumnError`，如 `ai_agent_runs.process_owner`）；必须先 migration |
| 预览请求 `x-expected-runtime-version-fingerprint` 与副本不符 | **409** `PREVIEW_VERSION_SKEW`（不得收成 500） |
| 破坏性 External API 字段变更未做消费者迁移 | CLI/Skill/Editor 契约门禁失败；禁止静默兼容 |

## 3. 升级窗口与摘流策略

### 3.1 预览角色：可滚动

顺序固定为「新副本就绪 → 流量切换 → 旧副本排空 → 下线」：

1. 启动新版 `runtime-preview`，等待 `/__runtime_readyz`，核对 `/__runtime_healthz` 的 `runtime_kit_version` / `build_id`。
2. 把新副本加入 Gateway 预览池。
3. 将旧副本标记 `down` 或移出 upstream 并 `reload`。
4. 等待在途连接结束（注意 HMR WebSocket 可能长连接，排空应有上界，超时后强制下线并记录）。
5. 停止旧容器。

同一预览池内**禁止**混用不同 `runtime_kit_version`；指纹不一致的子请求会被拒绝。

### 3.2 构建 / 检查角色：排空后替换

1. 摘掉领取（停容器或阻断 `runtime-jobs-net`），等待在途任务完成或租约过期。
2. 部署新版本，确认 Worker 启动（`RUNTIME_ROLE=build` 缺凭证会 fail-closed）。
3. 构建任务有 attempt 围栏：迟到上传不会提升旧 attempt 产物。

### 3.3 Backend：停机或双副本

- **小团队 / Lite**：停机升级。先备份 → `backend-migrate` → 启动新 Backend。
- **多副本**：先扩新副本、再摘旧副本；共享签名密钥环、DB、对象存储与 Redis。普通 AI Run **不**跨实例迁移（见 §5）。

### 3.4 DB migration 窗口

1. 备份数据库（见[备份与恢复](./backup-restore.md)）。
2. 只跑一次 `alembic upgrade head`（`backend-migrate` 或入口脚本）。
3. 再滚动/启动业务副本。
4. 回滚前确认旧镜像包含当前 `alembic_version`；不可逆 migration 只能前滚或从备份恢复。

## 4. 版本指纹门禁

Runtime 通过 `x-expected-runtime-version-fingerprint`（`runtime_kit_version+build_id`）拒绝失配请求。该门禁证明「失配可识别」，**不**自动提供零停机升级。多副本预览必须：

- 同池副本指纹一致；
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

1. **容器重建 / hostname 改变**：原 Run 归属旧 hostname，本机启动恢复不会收敛；依赖空闲超时与用户 `force_cancel`。可见终态时间应有界。
2. **PID 重用**：若原 PID 被新无关进程占用，`process_is_alive` 为真，恢复会推迟到空闲超时。`process_owner` 中的 uuid 当前不参与存活判定。
3. **同名主机、不同 PID namespace**：可能把异 namespace 进程误判为存活或死亡；多副本部署应保证 hostname 唯一（Docker 默认 container id 即可）。

## 6. 验收用例（M05 / M04）

1. 组合 A：全 N 完成一次登录 → 预览 → 截图 → 构建下载。
2. 组合 C：Backend N + Renderer/Runtime N-1（协议未变）完成截图；破坏性变更样本应明确失败。
3. 组合 E：DB 已 upgrade 后回滚 N-1 镜像 → 应出现 revision 缺失错误或按 downgrade 恢复，禁止静默损坏。
4. 指纹注入：预览池混入不同 `build_id` → 409 且错误码可读。
5. Run：杀 Backend-A 进程后重建容器（hostname 变）→ Run 不被 B 收敛；空闲超时后终态。
6. Run：PID 重用模拟 → 启动恢复不误杀；记录收敛延迟。

## 7. 相关文档

- [升级与回滚](./upgrade-rollback.md)
- [多 Backend 与密钥一致性](./multi-backend.md)
- [Compose 部署说明](./compose.md)（预览滚动与指纹）
- [执行隔离与权限矩阵](./execution-isolation.md)
