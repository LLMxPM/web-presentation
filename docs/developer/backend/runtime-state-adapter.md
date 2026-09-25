<!-- 文件功能：定义 Backend 运行态存储适配器契约，说明 memory:// 作为 SQLite Lite 正式适配器的能力边界、重启语义与非目标。 -->
# 运行态存储适配器（Redis / `memory://`）

Backend 的**短生命周期运行态**通过统一窄接口访问，由 `REDIS_URL` 选择适配器。**SQLite Lite 正式支持 `memory://`**，与真实 Redis 同属受支持后端，不是测试专用旁路。

| `REDIS_URL` 前缀 | 适配器 | 适用部署 |
| :--- | :--- | :--- |
| `redis://` / `rediss://` | 真实 Redis | 常规单实例、分角色、分布式（共库多副本） |
| `memory://<name>` | 进程内适配器（`InMemoryRuntimeStateBackend`） | SQLite Lite（`compose.sqlite-lite`）、单测/契约测试 |

实现位置：

- 业务入口 facade：`backend/app/services/redis_runtime_client.py` 的 `RedisRuntimeClient` 与 `get_redis_runtime_client()`；测试与对拍用 `create_runtime_state_client()` 注入独立实例与前缀。
- 窄命令契约：`backend/app/services/runtime_state/contracts.py` 的 `RuntimeStateCommands` / `RuntimeStateBatch`。
- 两种后端实现：`backend/app/services/runtime_state/memory_backend.py`、`redis_backend.py`。

> 早期规划中出现的 `RuntimeStateStore` 指的就是"facade + `RuntimeStateCommands` 协议"这一对；当前代码没有同名独立类，业务唯一入口仍是 `get_redis_runtime_client()`。

## 1. 契约：什么可以放在这里

**允许（可丢弃临时态）**

- Runtime 预览 artifact（manifest、config bundle、modules、asset blobs）
- 构建任务运行态心跳/状态快照（只写缓存，状态事实源在数据库）
- PAT 限流、鉴权失败计数、短锁与节流

**禁止（事实源不得进入适配器）**

| 类别 | 事实源位置 |
| :--- | :--- |
| AI 会话 / Run / 事件 / HITL | 主库 `ai_agent_*` 表 |
| 页面、组件、资源、构建产物元数据 | 主库 |
| 截图 / 页面 Job 租约与恢复 | 主库任务表（如 `page_screenshot_jobs`） |
| 资源比例回填任务领取与迟到结果围栏 | 主库 `asset_render_hint_backfill_jobs` 的 `worker_id` / `lease_expires_at` |
| 渲染请求排队与 attempt | 主库 `render_requests` / `render_execution` / `render_attempt` |

AI run/HITL **不依赖** Redis run hash 或 Redis stream；截图认领、资源比例回填领取与恢复也不依赖运行态存储。

## 2. 已登记命令与封闭能力

业务侧只承诺以下命令在两种后端上有相同可观察结果：

- 命令：`ping`、`set(ex,nx)`、`get`、`incr`、`delete`、`expire`、`ttl`、`hset(mapping)`、`hget`、`hmget`、`hgetall`。
- facade 辅助能力（非 Redis 命令）：`key`、`dumps`、`loads`、`batch`、`sweep_expired`、`stats`。
- `batch` 只允许 `set` / `hset` / `expire` / `delete` 组合。进程内实现整批在同一把锁内执行（读者看不到半个批次，超预算整批回滚）；真实 Redis 使用事务 pipeline。

固定语义（对拍覆盖）：缺失 key 返回 `None` / `TTL=-2`、`DELETE` 返回删除数量、重复 `SET NX` 返回 `False` 且不覆盖、`INCR` 保留原 TTL、`TTL=-1` 表示无过期、`HSET` 只统计新增字段、`HMGET` 按输入顺序返回、String/Hash 类型冲突按 `RuntimeStateTypeError` 拒绝、过期后重写不继承旧 TTL。

**明确不承诺**：Stream、消费组、跨进程 Pub/Sub、任意 pipeline 命令、Redis 全命令兼容。未登记命令（`publish`、`xadd`、`xread`、`scan_iter`、`pipeline` 等）不进入能力矩阵，内存后端也不实现它们；需要跨进程通知时应另立协议，正确性仍由数据库轮询兜底。

## 3. Key 用途与故障归属

| Key 类别 / 调用方 | 保存内容及 TTL | 事实源与缺失后的动作 |
| :--- | :--- | :--- |
| `runtime:artifact:*` / `RuntimeArtifactStore` | manifest、config bundle、modules、asset blobs、meta；预览默认 3600 秒，诊断结束主动删除 | 临时预览需由页面/项目数据**重新生成新 artifact**；旧 `rt_` ID 不会悄悄指向新内容，访问已失效地址返回 404。数字 Release 走现有数据库回源。 |
| `runtime:build:*` / `ProjectBuildService` | 进度、心跳和错误摘要；默认 604800 秒 | `ProjectBuildJob`、Release 与产物元数据在主库；缓存写入失败只告警，状态查询以主库为准，不因缓存故障回滚已提交任务。 |
| `pat:rate_limit:*`、`pat:auth_fail:*`、`pat:lockout:*` / `PatRateLimitService` | 60 秒窗口与 900 秒封禁 | 仅临时安全计数；进程重启会清零。存储故障按既有策略 Fail-Open 放行，`429` 仍带 `Retry-After`。 |
| `pat:last_used_throttle:*` / `ApiAccessTokenService` | 300 秒节流 | `ApiAccessToken.last_used_at` 在主库；key 丢失只会多一次更新，不影响鉴权。 |

新增 key 必须先登记用途、拥有者、TTL、容量上限、重启后的动作以及是否涉及正确性；无法证明"丢失仍正确"的状态只能放主库。`REDIS_KEY_PREFIX` 对两种后端都生效；`memory://<name>` 中的 name 只是实例配置标识与启动日志标识，**不是**跨进程共享命名空间。

业务侧错误语义：运行态后端不可用转换为 `RUNTIME_STATE_UNAVAILABLE`（503，可重试）；进程内 payload 预算拒绝转换为 `RUNTIME_STATE_CAPACITY_EXCEEDED`（503，带重试/缩减资源提示）。

## 4. 两种适配器语义

| 能力 | 真实 Redis | `memory://`（Lite） |
| :--- | :--- | :--- |
| String / Hash 读写、TTL | 支持 | 支持（进程内字典 + 惰性过期 + 主动扫描） |
| 批处理可见性 | MULTI/EXEC 原子 | 同一把锁内整批生效，超预算整批回滚 |
| 进程重启后临时态 | 视 Redis 持久化配置而定 | **全部丢失** |
| 多 Backend 副本共享 | 支持 | **不支持** |
| 内存上限 | Redis `maxmemory` | 进程内 payload 预算（见 §6） |
| 过期清理 | Redis 自身 TTL | 惰性过期 + `RUNTIME_ARTIFACT_SWEEP_INTERVAL_SECONDS` 周期扫描 |

### Lite 承诺（写进部署语义）

1. **单实例**：`platform-lite` 单 Backend 进程；已有 SQLite 单实例锁，禁止多容器共用数据卷。
2. **重启语义**：容器/进程重启后，预览 artifact、构建运行态与短锁失效，用户需重新触发预览或构建；**主数据与渲染输入快照不丢**（SQLite + 对象/本地持久目录）。
3. **故障域**：`memory://` 与 Backend 同进程；运行态膨胀会直接占 Backend 内存，依赖 TTL、清扫与 payload 预算控制，不承诺隔离。
4. **可丢弃**：运行态清空不得改变任何领取、租约、终态或渲染输入结果（回归测试覆盖资源比例回填与 PAT 计数）。
5. **离线冷启动**：交付镜像构建期预置 tiktoken `cl100k_base` 词表（`TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken`），`alembic` / `uvicorn` 导入期不再外联下载 BPE；`--network none` 与气隙部署可完成冷启动。覆盖该变量时需自行保证缓存已存在，详见[部署环境变量](../deployment/env-vars.md)。

### 常规部署承诺

- `REDIS_URL` 指向真实 Redis；密钥带 `REDIS_KEY_PREFIX` 隔离。
- 运行态重启丢缓存时，从持久化快照/主数据重建；**已接纳的渲染请求不得因 Redis 重启丢失输入**。

## 5. 配置与部署组合

| 变量 | 说明 |
| :--- | :--- |
| `REDIS_URL` | `memory://<name>` 或 `redis://…`；Lite 固定 `memory://lite` |
| `REDIS_KEY_PREFIX` | 两种适配器均做 key 前缀隔离 |
| `RUNTIME_ARTIFACT_SWEEP_INTERVAL_SECONDS` | `memory://` 过期扫描周期（默认 30s） |
| `runtime_preview_artifact_ttl_seconds` | 预览 artifact TTL（默认 3600s） |
| `RUNTIME_STATE_MEMORY_MAX_BYTES` | 进程内运行态总 payload 预算（默认 128 MiB） |
| `RUNTIME_STATE_MEMORY_MAX_ITEM_BYTES` | 单项 payload 上限（默认 16 MiB） |
| `TIKTOKEN_CACHE_DIR` | 词表缓存目录；交付镜像固定 `/app/.cache/tiktoken` 并预置 `cl100k_base`，保证离线冷启动不依赖出网（非运行态存储，属镜像内置依赖） |

启动校验（只由应用生命周期执行，不进入导入期）：

- 拒绝不支持的 URL scheme 与空 `memory://` 标识；`memory://` 标识必须写在主机位置（如 `memory://lite`）。
- 拒绝 `memory://` 与 PostgreSQL 组合；`memory://` 只适用于 SQLite Lite 单进程部署。
- 拒绝 `memory://` 配显式多 worker（`WEB_CONCURRENCY` / `UVICORN_WORKERS` > 1）。
- 迁移脚本等为了不连 Redis 而临时设置 `memory://` 的场景不经过该校验，导入与建应用都不受影响（有单独回归测试）。

就绪与健康：`/healthz` 仍只表示进程存活；`/readyz` 只报告数据库、Renderer 配置、SQLite 单进程与**静态**运行态元数据 `runtime_state_backend` / `runtime_state_ephemeral`，不做 Redis 连接探测，因此一次瞬断不会把容器打成 `not_ready` 或触发重启。External API `/system/health` 的 `redis` 字段保持兼容，改名需另行变更 External API v1 契约与 Gateway 测试。

## 6. 可观测与容量预算

- 启动日志事件 `runtime_state.startup`：后端类型、`ephemeral`、SQLite 单进程标记与清扫周期；**不含** URL、口令或 key 内容。
- `GET /metrics/runtime-state`（`include_in_schema=false`）：`active_keys`、`approx_bytes`、`max_bytes`、`capacity_rejections`、`sweep_count`、`sweep_failures`、`last_sweep_at`、`last_sweep_seconds`。只返回聚合值，不返回 key 名称或 payload。
- 进程内后端清扫失败记录 `runtime_state.sweep.failed` 事件后按同一有界间隔重试，后台任务不静默退出；`get` 仍做惰性过期，扫描延迟不延长数据有效期。
- 容量拒绝在写入生效前发生，不留半个 artifact；跨类型、覆盖写、Hash 增减、TTL、删除与批处理都计入预算。

### Lite 内存基线（2C4G 实测记录）

| 项 | 记录 |
| :--- | :--- |
| 硬件与限制 | 2 vCPU / 4 GiB（`--cpus 2 --memory 4g`），Lite 单容器镜像 |
| 固定载荷 | 3 轮混合负载：小/中/大页面预览（8 KiB / 256 KiB / 2 MiB 源码）、资源预览、带二进制资源的模板包预览、构建任务创建；再连续重复刷新 120 次（TTL 30s、清扫 5s 加速观测） |
| 运行态峰值 | **104.5 MB / 186 keys**（120 次重复刷新后） |
| 清扫回收 | 31 次清扫、0 失败、单次最长 5.5 ms；过期后回落到 438 B / 2 keys |
| 进程 RSS 峰值 | Backend（uvicorn）637 MB；Node（Vite）2.54 GB；容器 2.76 GiB / 4 GiB |
| 稳定性 | 无 OOM、无容器重启、无异常请求失败 |
| 复现命令 | `docker build -f deploy/docker/Dockerfile.lite -t web-presentation:lite-local .` 后运行 `pnpm run test:lite:runtime-state-drill -- --mode baseline --image web-presentation:lite-local` |
| 阈值结论 | 总预算取 128 MiB（实测峰值 1.2 倍外再留余量，同时封住 1 小时 TTL 窗口内的无限增长）；单项上限 16 MiB 覆盖最大单 artifact（本次实测约 2.5 MiB）并拒绝超大模板资源。TTL 与清扫周期保持 3600s / 30s：实测清扫成本为毫秒级，瓶颈在 Node 常驻内存而非清扫频率。 |

阈值与硬件绑定，更换机型或大幅调整载荷后必须重跑基线再调整。

## 7. 工程约束

1. 业务代码只经 `get_redis_runtime_client()` facade 访问；不得 `import redis`、不得访问 `.client`、不得直接引用内存后端实现。该约束由 `backend/tests/unit/test_runtime_state_adapter_boundary.py` 静态门禁守住。
2. 已登记命令必须被两种后端同时实现；未登记命令不得出现在后端或批处理面上（同上门禁覆盖）。
3. 运行态变化必须同时提供两种后端的对拍测试：`backend/tests/contracts/test_runtime_state_adapter.py` 在 `memory://` 与真实 Redis 上执行同一组业务操作并比对归一化结果；TTL 只比较合法区间。
4. 真实 Redis 对拍是**发布门禁**：CI 的 `runtime-state-parity` job（或本地 `RUNTIME_STATE_PARITY_REDIS_URL=… RUNTIME_STATE_PARITY_REQUIRED=1 pnpm run test:backend:runtime-state-parity`）必跑；缺少对拍 Redis 时显式失败，不能显示为"对拍通过"。对拍只使用独立的非 0/非 15 库号与随机前缀，且只清理本次创建的 key。
5. 文档与 Compose 不得再写「所有部署必须真实 Redis」；**Lite 使用 `memory://` 是产品形态，不是临时凑合**。

## 8. 相关文档

- 部署与环境变量：[`../deployment/env-vars.md`](../deployment/env-vars.md)
- Lite 拓扑：[`../deployment/compose.md`](../deployment/compose.md)
- 渲染 artifact 生命周期：[`./remote-render-service-design.md`](./remote-render-service-design.md)
- 任务租约与队列：[`./resource-queues.md`](./resource-queues.md)
- 排障入口：[`./troubleshooting.md`](./troubleshooting.md)