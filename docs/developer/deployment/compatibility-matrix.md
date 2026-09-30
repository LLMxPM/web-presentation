<!-- 文件功能：定义 Backend/Runtime/Renderer/DB/Runtime Kit 的 N/N-1 支持组合、升级窗口与摘流策略，支撑 AR-05/W05 与 M05。 -->
# 版本兼容矩阵与升级窗口

本文定义平台各组件在升级或回滚时的支持边界，对应 AR-05 / W05。M05 已有特定版本组合的实机记录；[09-30 复核](../../temp/architecture-assessment-2026-09-30.md)发现 `4c7eee8` 的页面 Batch ORM 仍查询 N 已删除的列，撤回 B/E 的完整业务兼容结论。W05a/b/c 修复后已在[本地 Docker](../../temp/runs/2026-09-30-docker/summary.md)通过旧源码 PG 领域探针、普通 Run 强杀/暂停/重建和正常 iframe 同版双副本/真实旧 Runtime 跨版拒绝；完整业务、回滚与外部任务保护矩阵继续开放，见[现行计划](../../temp/plans/architecture-improvement-plan-2026-09-29.md) §7。

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
| B | ✓ | ✓ | ✓ | ✓ | ✓ | — | **完整业务混跑待复测**：补偿列与 SQLite 旧/新 ORM 已通过；真实 PG 上 `4c7eee8` 完整 Batch 读写、页面入队幂等、过期清扫和取消通过，但使用当前 Python 依赖，未覆盖完整旧镜像/自动续跑。迁移仍先删列再恢复，必须排空旧任务并停旧实例 |
| C | ✓ | ✓ | ✓ | ✓ | — | ✓ | 特定 Renderer 混池有局部记录；协议/Kit 一致只是必要条件。当前浏览器跨版明确拒绝已有证据，完整 N-1 Runtime/Renderer 截图组合及 allowedHosts 差异仍待验；当前预览池固定同一发布版本 |
| D | ✓ | — | — | N-1 | — | — | **迁移窗口内**旧 DB + 新 Backend：**不支持**（N ORM 需要新列）；必须先 upgrade 再启 N。N-1 + 旧 DB 可运行 |
| E | — | — | — | ✓ | ✓ | ✓ | **完整回滚待复测**：先用新迁移器前滚到含 `20260930_0200` 的 schema，再保留 schema 回退应用并关闭旧入口的自动迁移；旧迁移器无法识别新 revision。补偿列值为 0，不能恢复删列前历史值 |
| F | 混用不同发布版本的 Runtime 副本 | | | | | | **不承诺无中断混跑**；正常 iframe 同版跨两个副本可用，当前 Runtime HTML + 实际旧 Runtime 子请求明确 409，HTTP/HMR 门禁通过；局部拒绝不代表任意 N/N-1 滚动兼容，见 §4 |

### 2.1 明确不支持 / 明确拒绝

| 场景 | 行为 |
| :--- | :--- |
| 删除或修改仍被依赖的 `@runtime-kit/...vN` 公开路径 | 旧产物/旧页面源码导入失败；必须保留旧版本文件或做迁移 |
| Backend 调用 Renderer 时契约版本不一致 | `contract_version` 校验失败，任务失败并留错误码 |
| 预览请求携带与 Runtime 副本不一致的 `x-expected-runtime-version-fingerprint` | 409 拒绝（指纹门禁） |
| 正常预览签名版本或 `/__runtime_version/<指纹>/` 与当前 Runtime 不符 | HTTP 409 `PREVIEW_VERSION_SKEW`；跨版 HMR Upgrade 拒绝握手 |
| 旧 Runtime 探针未提供非空版本/发布身份 | Backend 返回 503 `RUNTIME_VERSION_UNKNOWN`；不能静默把旧镜像当同一 dev 版本 |
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

同一预览池当前只放同一发布构建标识，不能只比较 `runtime_kit_version`。新实现自动传播并拒绝跨版请求；拒绝意味着预览需要刷新，不能等同无中断。当前候选正常浏览器双副本与旧镜像拒绝已验证；更早 Runtime 可能没有完整版本门禁，任意 N/N-1 混池仍不支持。跨版升级继续排空旧池再切换。

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

`20260930_0200` 是 W05a 的前向补偿：恢复旧 ORM 需要的兼容列并设置服务端默认 0，当前 ORM 无需重新使用它。已应用的 `20260930_0100` 保持不变，补偿不能恢复历史代次。升级前排空页面任务并停旧实例；应用回滚保留补偿 schema，通过 `PLATFORM_SIMPLE_RUN_MIGRATIONS=false` / `PLATFORM_LITE_RUN_MIGRATIONS=false` 关闭旧镜像迁移器。旧列删除须另等旧实例退出和回滚窗口结束，不将数据库降回删列 revision 当应用回滚步骤。

## 4. 版本指纹门禁

W05c 将发布身份与传播机制收口为以下链路：

- 独立 Runtime 与 Lite 的构建阶段按 Runtime 源码/公开配置/构建脚本、包配置、Vite 配置与根 `pnpm-lock.yaml` 生成 `.runtime-build-id`，并复制到生产依赖裁剪后的目录。`RUNTIME_BUILD_ID` 可统一覆盖该值，不能使用副本名；`RUNTIME_INSTANCE_ID` 只出现在内部健康观测。交付镜像缺发布身份时启动失败，`dev` 仅是本地开发默认值。
- Backend 正常 iframe 入口验签原 token，再从受信 Runtime 探针绑定 `runtime_kit_version+build_id` 到子票据 `runtime_version_fingerprint`，保留原 artifact、权限和 `exp`。已绑定票据不重新探测换版；期望请求头由服务端覆盖，浏览器无需自填。
- HTML、Vite 的嵌套模块/CSS 和 HMR 使用 `<公开挂载路径>/__runtime_version/v1.<base64url 指纹>/`。HTTP 版本门禁早于 Vite/base/源码转换，失配返回 409；HMR Upgrade 在握手前拒绝。远程模块、Tailwind 与资源代理仍验签绑定声明，不依赖本进程缓存授权。
- 同版副本使用固定依赖预优化集合；跨副本 Vue 子请求在本次票据验签后恢复主模块描述符，ctx 前置保留样式转换。正常浏览器样本覆盖页面、scoped CSS 和字体；新增依赖及公共能力组合继续补对应冷启动验收。
- 固定 `/__preview` 入口与版本资源路径共用挂载解析；本轮真实 Renderer 截图、ZIP 下载及构建入口浏览器加载通过。两个协调器同时读取结果时，迟到产物 410 的失败写入也必须先取得占用条件更新，不能由 ORM 自动 flush 重开已释放的 attempt。
- Backend 保留上游错误状态、版本响应头和缓存语义；探针与 HTML 恰好落到不同发布时明确拒绝。重新导航原预览入口可绑定当前发布，不延长票据有效期。
- 同池继续固定同一发布镜像并按 §3.1 排空；本地 Docker 浏览器定向结果只覆盖记录的候选和场景，不能替代完整 N/N-1、最终模板与公共能力 M05 验收。
- 检查角色缓存指纹包含 Runtime Kit 清单 hash（`CodeCheckFingerprintBuilder`），升级编译器后缓存自然失效。

## 5. Run 收敛边界（实例心跳 / 历史 owner）

普通 AI Run 使用进程内执行，产品承诺「中断不自动续跑」。W05b 已新增实例心跳表与独立后台收敛；真实双 Backend 的强杀、暂停、hostname 改变/PID 重用、静默 B 保护、会话解除及旧实例迟到写拒绝通过，完整外部交接 M04 仍待执行：

- 新 Run 使用同一进程实例的 `hostname:pid:uuid`，登记 `ai_agent_process_owners`；容器/主机名改变或 PID 重用不会让过期的 UUID 重新存活。心跳不依赖模型输出，默认 TTL 90 秒、心跳/扫描各 10 秒；过期实例不能续期复活，当前执行器停止接收普通 Run，须重启实例。
- `process_reaper` 复用统一 CAS 时序；复核 owner、状态、取消快照与外部交接，在同事务写终态/事件、解除会话占用。普通执行与工具提交传播存活写围栏，迟到结果被拒绝。paused、waiting_external、未完成外部 Batch 交接保持原路径，人工继续绑定新 owner。
- 在数据库可用、时钟同步且无额外调度/重试延迟时，最后有效心跳后约 TTL + 扫描周期收敛。实机应记录配置、写冲突/数据库不可用时长与完整收敛时间，不能只拿一次恢复耗时与 TTL 比较。

历史未登记 owner 不自动补造心跳。升级前排空旧 Run；下表仅是 `run_recovery.py` 的历史兼容路径，跨容器历史遗留继续用 `force_cancel`：

| 条件 | 启动恢复是否收敛 | 说明 |
| :--- | :--- | :--- |
| `process_owner` 为空 / 无法解析 | 仅单进程部署（`include_unowned`） | 多副本默认跳过，避免误杀 |
| hostname ≠ 本机 | **否** | 保护其它副本活跃 Run |
| hostname = 本机且 PID 仍存活 | **否** | 含当前进程与同机 sibling |
| hostname = 本机且 PID 已死 | 是 | 终态为 `AI_RUN_PROCESS_STOPPED` 或取消 |

**历史路径边界（M04 需区分新/旧实例）：**

1. **容器重建 / hostname 改变**：历史未登记 Run 归属旧 hostname，启动恢复不收敛，需 `force_cancel`；新登记实例按过期心跳处理。SSE 始终只观察。
2. **PID 重用**：历史未登记 Run 的 `process_is_alive` 为真时跳过；新实例以 UUID/持久化租约区分，不依赖 PID 存活探测。
3. **同名主机、不同 PID namespace**：可能把异 namespace 进程误判为存活或死亡；多副本部署应保证 hostname 唯一（Docker 默认 container id 即可）。

## 6. 验收用例（M05 / M04）

1. 组合 A：全 N 完成一次登录 → 预览 → 截图 → 构建下载。
2. 组合 C：Backend N + Renderer/Runtime N-1（协议未变）完成截图；破坏性变更样本应明确失败。
3. 组合 B/E：除登录外，执行 N-1 页面任务入队与 Batch ORM 查询；缺列必须判不兼容。按既定 schema 恢复后再验证旧版完整业务。
4. 指纹：人工失配入口返回 409；另用正常浏览器让 HTML/模块落到不同版本，验证版本传播或稳定路由。
5. Run：强杀 Backend-A 后重建容器（hostname 变）→ 新登记的失效 Run 有界终态、会话可再发起，B 活跃 Run 不被误杀；历史未登记 Run 单独验证手动补偿，不算新实例自动收敛通过。
6. Run：PID 重用模拟 → 启动恢复不误杀；记录收敛延迟。

## 7. 相关文档

- [升级与回滚](./upgrade-rollback.md)
- [多 Backend 与密钥一致性](./multi-backend.md)
- [Compose 部署说明](./compose.md)（预览滚动与指纹）
- [执行隔离与权限矩阵](./execution-isolation.md)
