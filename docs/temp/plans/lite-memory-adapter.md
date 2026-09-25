# Lite `memory://` 运行态适配器实施计划

> 状态：**规划，代码尚未实施**；基线核对日期：2026-09-25。  
> 已定前提：D1=A，SQLite Lite 长期作为正式部署形态；Lite 使用进程内 `memory://`，常规部署使用真实 Redis。  
> 规范正文：[运行态存储适配器](../../developer/backend/runtime-state-adapter.md)。本文安排实现、测试和发布验收；实施时同步修正该规范。  
> 本文件位于 `docs/temp/plans/`，已纳入版本控制。正式契约仍以 [`runtime-state-adapter.md`](../../developer/backend/runtime-state-adapter.md) 为准。

计划和完成定义详见下文；**实施记录（2026-09-25）**见文末第 7 节。

## 1. 目标、边界与完成口径

1. 业务通过有类型的窄接口访问短生命周期运行态；`memory://` 与 `redis://` / `rediss://` 在**已声明的命令和业务场景**上有相同可观察结果。
2. Lite 的单 Backend 进程、重启失效、内存预算和恢复操作成为可检查的部署承诺。`memory://` 不承担数据库任务的领取、租约、终态或渲染输入事实源。
3. 预览 artifact、构建状态缓存、PAT 限流与节流逐项定义失效语义；缓存故障不得把已经提交到数据库的任务错误地宣称为未创建。
4. 真 Redis 对拍是发布门禁，不以 `InMemoryRedis` 单测代替；Lite 镜像需通过真实启动和重启演练。

不在本计划内实现完整 Redis 协议、Stream 消费组、跨进程 Pub/Sub、普通 AI Run 跨进程续跑或 Backend 多副本。P3 统一任务运行时可以复用本计划确立的边界，但不能把它的交付当作本计划的前置条件。Runtime 角色拆分和多副本另按[部署扩容规划](./runtime-multi-deployment-scaling-plan.md)推进。

## 2. 已核实的代码基线与待修正处

| 领域 | 当前工作树中的事实 | 本计划要解决的差距 |
| :--- | :--- | :--- |
| 工厂与抽象 | [`redis_runtime_client.py`](../../../backend/app/services/redis_runtime_client.py)根据 `REDIS_URL.startswith("memory://")` 选择进程内字典，否则交给 `Redis.from_url`；`RedisRuntimeClient` 暴露原始 `.client`。代码中**没有**名为 `RuntimeStateStore` 的接口。 | 保留工厂兼容入口，新增窄命令接口并收起业务对原始客户端的访问；严格解析受支持 URL。 |
| 实际调用面 | `RuntimeArtifactStore` 使用 String、Hash、`pipeline`；PAT 安全服务使用 `incr/expire/ttl/get/set/delete`；PAT 最后使用时间节流与资源比例回填使用 `SET NX`。 | 以这些调用点冻结接口和返回语义，逐一迁移；不按 `InMemoryRedis` 已实现的方法反推产品承诺。 |
| 未使用的模拟命令 | `InMemoryRedis` 还有 `xadd/xread/xrange/publish/scan_iter`；当前 `backend/app` 没有这些业务调用，且 `publish` 固定返回 0。 | 契约不得宣称 Lite 有可用的消息通知或 Stream；删除无用模拟或移到测试专用代码，新增调用需先做设计评审。 |
| 批处理 | 真 Redis 的 pipeline 由 redis-py 执行；内存 pipeline 逐条调用，没有覆盖整个批次的锁。 | 明确 artifact 写入的可见性、顺序与失败语义，增加并发对拍。 |
| 任务锁 | [`asset_render_hint_backfill_job_service.py`](../../../backend/app/services/asset_render_hint_backfill_job_service.py)先 `SET NX`，再把 DB 任务标为 `running`。 | 这个 key 当前参与领取正确性，不能直接归类为“可丢弃短锁”；先把领取及迟到结果围栏落到 DB，再移除 Redis 正确性依赖。 |
| 重启 | `rt_...` 预览 artifact 只在运行态；数字 ID 的 Release 可从 DB 回源。构建的 `ProjectBuildJob` 在 DB，启动恢复会将遗留 `running` 标为失败。 | 验收“旧临时预览链接失效、重新创建可用、构建状态可解释”，不能写成旧预览自动恢复或在途构建自动续跑。 |
| 健康与清扫 | `/healthz` 只看进程，`/readyz` 当前检查 DB 和 Renderer 配置；`/system/health` 仍叫 `redis`。内存 key 由惰性过期和 30 秒 sweeper 清除；清扫任务异常会退出。 | 暴露后端类型而不泄露 URL；保留已有健康字段兼容性；清扫失败可见、可恢复。 |
| 已改文档 | 契约、Backend/deployment/渲染设计及 Lite 维护指南、FAQ 在当前工作树中已有相关表述，其中多份尚未提交。 | 对照实际行为复核，不重复做“待补一句”；修正开发/测试排障文档中“手动联调必须 Redis”的无条件表述。 |

**基线判定**：当前是“按 URL 切换的 Redis 子集实现”，尚未形成封闭的业务接口。特别是回填任务锁和内存 pipeline，使“所有允许状态均可丢弃、双后端同契约”仍属于目标，而非现状。

## 3. 实施前冻结的契约

### 3.1 Key 用途与故障归属

| Key 类别 / 调用方 | 保存内容及现有 TTL | 事实源与缺失后的动作 |
| :--- | :--- | :--- |
| `runtime:artifact:*` / `RuntimeArtifactStore` | manifest、配置、模块、模板资源；预览默认 3600 秒，诊断结束主动删除。 | 临时预览需由页面/项目数据**重新生成新 artifact**；旧 `rt_` ID 不应悄悄指向新内容。数字 Release 走现有数据库回源。 |
| `runtime:build:*` / 构建服务 | 进度、心跳和错误摘要；默认 604800 秒。 | `ProjectBuildJob`、Release 和产物元数据在 DB；缓存缺失时状态 API 以 DB 为准，不能因缓存写失败回滚已经提交的任务。 |
| `pat:rate_limit:*`、`pat:auth_fail:*`、`pat:lockout:*` / PAT 安全服务 | 60 秒窗口与 900 秒封禁。 | 仅为临时安全计数；进程重启会清零。保留现有存储故障降级策略，并测试 429、`Retry-After` 和计数 TTL。 |
| `pat:last_used_throttle:*` / PAT 服务 | 300 秒节流。 | `ApiAccessToken.last_used_at` 在 DB；临时 key 丢失只会多一次更新，不应影响鉴权。 |
| `runtime:asset-render-hint-backfill-job-lock:*` / 回填服务 | 当前 180 秒 `SET NX` 锁。 | **迁移对象**。任务领取、重试与结果提交改为 DB 条件更新和 attempt 围栏后，该 key 才可删除或降为非必要加速。 |

新 key 必须登记用途、拥有者、TTL、容量上限、重启后的动作及是否涉及正确性；无法证明“丢失仍正确”的状态只能放主库。现有 `REDIS_KEY_PREFIX` 继续用于两种后端的命名隔离；`memory://<name>` 中的 name 只是实例配置标识，不是跨进程共享命名空间。

### 3.2 命令与返回语义

- 对外只承诺现有业务用到的 `ping`、`set(ex,nx)`、`get`、`incr`、`delete`、`expire`、`ttl`、`hset(mapping)`、`hget`、`hmget`、`hgetall`，以及由 facade 提供的有限批处理。`key/dumps/loads/sweep_expired` 是封装辅助能力，不是 Redis 命令。
- 明确缺失 key、重复 `SET NX`、`INCR` 保留原 TTL、`TTL=-2/-1`、`HSET` 新字段计数、`HMGET` 顺序、`DELETE` 数量、String/Hash 类型冲突、过期后再次写入和并发 `SET NX` 的行为。对不在业务输入域内的 Redis 特性不做全兼容承诺。
- `pipeline` 只允许已登记命令组合；artifact 写入不得被其他线程读到半个批次。内存实现应在同一锁内执行批次；真 Redis 继续使用事务 pipeline。正常写入完成后，主 key、模块和 TTL 必须同时可用。异常时不返回可访问的 artifact ID，并清理已写入的临时 key。
- 不提供“假成功”的通知：`publish` 的 no-op 不进入正式接口；Stream 既无生产调用也不进入能力矩阵。将来确需跨进程通知时另立协议，正确性仍由 DB 轮询兜底。

### 3.3 配置与部署组合

正式 Lite 组合为 **SQLite 文件库 + 单 Backend 进程 + `memory://lite` + 持久 `lite-data` 卷**；常规部署为 PostgreSQL + Redis。测试可直接注入独立内存实例。启动校验要拒绝正式运行中可识别的错误组合，例如不支持的 URL scheme、空 `memory://` 标识、`memory://` 配 PostgreSQL、显式多 worker；SQLite 文件锁继续防止两容器共用同一 DB。迁移脚本中仅为不连接 Redis 而设置的 `memory://` 不应被应用生命周期校验误伤，需单独覆盖测试。

`/readyz` 可增加 `runtime_state_backend=memory|redis` 与 `runtime_state_ephemeral` **静态元数据**，不把一次 Redis 瞬断转换为容器重启；`/healthz` 仍只表示进程存活。External API `/system/health` 的现有 `redis` 字段先保持兼容，若要改名须另行变更 External API v1 契约、客户端和 Gateway 测试。日志、响应与指标不输出完整连接串、口令或 key 内容。

## 4. 分阶段工作包

### 阶段 0：审计与测试夹具（先做）

| 编号 | 实施内容 | 交付 / 验收 |
| :--- | :--- | :--- |
| 0.1 | 用 `rg` 和必要的 AST 检查列出 `backend/app` 全部 `get_redis_runtime_client()`、`.client`、`redis` 导入、运行态 key 与错误降级路径；记录 owner、TTL、事实源。 | 命令和 key 清单与 §3 一致，发现新调用先更新清单和计划。测试中的 `InMemoryRedis` 注入不计为业务违规。 |
| 0.2 | 为 `memory://test` 提供每例独立实例/前缀；为对拍准备专用真实 Redis DB 或独立服务及随机前缀。 | 单测不依赖 Redis；对拍不能连接部署环境的 DB/前缀，测试清理仅触碰本次创建的 key。 |
| 0.3 | 锁定现有响应：预览缺失、数字 Release 回源、构建中断、PAT 限流与回填领取。 | 留下失败前基线测试，后续接口变化可逐项比较。 |

### 阶段 A：规范与用户语义

| 编号 | 实施内容 | 交付 / 验收 |
| :--- | :--- | :--- |
| A1 | 按 §3 修订 [`runtime-state-adapter.md`](../../developer/backend/runtime-state-adapter.md)：将 `RuntimeStateStore` 作为目标抽象说明，明确现存实现名；收窄 Stream/PubSub 表述，区分临时预览与持久 Release。 | 文档的“已实现 / 待实施”与代码一致，能力矩阵不暗示完整 Redis 模拟。 |
| A2 | 复核已改的 Backend README、部署 README/env-vars/compose、渲染设计、资源队列、用户维护指南与 FAQ；补旧预览链接、PAT 临时计数和构建中断动作。 | 这些文档互相链接且语义一致；保留用户已有未提交改动，只改冲突处。 |
| A3 | 修正 `docs/developer/getting-started.md`、`docs/developer/testing/strategy.md`、Backend troubleshooting 中“手动联调必须启动 Redis”等无条件说法；全仓搜索绝对化措辞。 | 写明 Lite `memory://` 与常规 Redis 各自适用条件；`pnpm run test:repository` 通过。 |

### 阶段 B：先解除任务正确性对运行态锁的依赖

| 编号 | 实施内容 | 交付 / 验收 |
| :--- | :--- | :--- |
| B1 | 资源比例回填任务用 DB 原子条件更新领取 `pending`，保存本次 attempt 身份与过期边界；对 PostgreSQL 竞争和 SQLite 单写者都返回唯一赢家。涉及 schema 时做向后兼容迁移。 | 两个并发领取者最多一个成功；Redis / memory 清空后不改变领取结果。 |
| B2 | 终态提交和资源元数据写入复核 attempt 身份、任务版本与有效租约；恢复超时 `running` 任务时建立新 attempt。 | 旧 worker 的迟到成功或失败不能覆盖新 attempt；进程在“领取后、提交前”退出仍能按重试预算收敛。 |
| B3 | 移除回填业务对 `SET NX` 锁的依赖及 key，或在 DB 约束生效后仅保留可丢弃的加速层；同步修改契约允许清单。 | 对拍及故障注入证明不依赖运行态锁；若保留加速层，禁用它后结果不变。 |

### 阶段 C：封闭接口与双后端行为

| 编号 | 实施内容 | 交付 / 验收 |
| :--- | :--- | :--- |
| C1 | 在 `redis_runtime_client.py` 定义窄命令 Protocol / facade；保持 `get_redis_runtime_client()` 兼容入口。把内存实现和 pipeline 拆到独立模块，避免单文件继续膨胀。 | 业务目录不再访问 `.client` 或直接导入 `InMemoryRedis`；类型检查可发现新命令未被两种后端实现。 |
| C2 | 迁移 `RuntimeArtifactStore`、PAT 服务、访问令牌节流与系统健康调用；只允许 adapter 内访问 redis-py 对象。 | 静态门禁检查 `backend/app` 的原始 Redis 调用，仅测试夹具允许注入内存实现。 |
| C3 | 修正内存批处理的并发可见性、类型隔离、TTL 与过期回收；封闭未登记命令，避免 `publish` no-op 被业务误用。 | 相同场景分别运行 `memory` 和真实 Redis：正常返回、缺失、TTL 窗口、并发 NX、覆盖 Hash、批处理与错误路径对拍一致。 |
| C4 | 审查 DB 提交前后所有构建缓存写入。缓存不可用时由 DB 状态保证任务创建和终态可解释；预览 artifact 写入失败则不能签发可用 URL。 | 注入运行态异常：已提交构建任务不被误报“未创建”；预览无残留半成品；PAT 按既有降级策略工作。 |

测试建议：纯内存语义放 `backend/tests/unit/`；业务对拍放 `backend/tests/contracts/test_runtime_state_adapter.py`；真实 Redis 作为 CI 专门 job 的**必跑发布门禁**，开发机缺少测试 Redis 时显式 skip，不能显示为“对拍通过”。每个对拍用例在两种后端执行同一组业务操作，比较归一化结果；TTL 只比较合法区间，避免依赖毫秒级时钟偶然性。

### 阶段 D：Lite 容量与可观测

| 编号 | 实施内容 | 交付 / 验收 |
| :--- | :--- | :--- |
| D1 | 启动日志记录后端类型、`ephemeral`、单进程和清扫周期；`/readyz` 增加 §3.3 的静态字段，必要时增加受控指标：活跃 key 数、近似 payload 字节、清扫次数/耗时/最近成功时间、容量拒绝次数。 | Lite 与 Redis 启动 smoke 可区分后端；日志/接口不含密钥或 artifact 内容；已有 `/healthz` 和 `/system/health` 兼容测试通过。 |
| D2 | sweeper 仅在内存后端做主动扫描；单次失败记录事件并按有界间隔重试，不让后台任务静默退出。`get` 仍做惰性过期，因此扫描延迟不延长数据有效期。 | 模拟一次扫描失败后下一轮恢复；过期 key 无再次访问也被释放，key 数/字节指标回落。 |
| D3 | **独立采集 Lite 内存基线**：在 2C4G 镜像运行空闲和混合负载，覆盖小/中/大预览、带二进制资源的模板预览、诊断删除、构建运行态及重复刷新；记录 artifact 字节、Backend/Node/容器 RSS、清扫延迟、OOM 与请求失败。 | 有可复现夹具、持续时间和峰值记录；不能用 D2 数据库写路径指标替代本项。保留 D2 仅用于 P3 任务调度节奏。 |
| D4 | 依据 D3 给进程内后端设置**有限** payload 预算与单项大小上限，超限在写入前返回稳定容量错误，不留半个 artifact；设定阈值时保留 Runtime/Renderer 调用与 Backend 的内存余量。 | 配额覆盖覆盖写、Hash 增减、TTL、删除和批处理；临界并发不会突破预算或 OOM。阈值与测试硬件一起记录，不从 D2 猜数字。 |

容量错误对预览创建、诊断工具和模板预览分别给出可理解的重试/缩小资源提示；不要在健康端点返回所有缓存 key 或资源大小明细。是否调整 3600 秒预览 TTL、604800 秒构建状态 TTL 和 30 秒清扫周期，必须在 D3 报告之后决定；即使不调整，也要留下理由。

### 阶段 E：重启演练与发布

| 编号 | 场景 | 必须观察到的结果 |
| :--- | :--- | :--- |
| E1 | Lite 创建 `rt_` 预览和数字 Release，重启 `platform-lite` 后访问旧 URL，再重新创建预览。 | 旧临时 artifact 明确不可用且提示重开预览；数字 Release 仍可从 DB 读取；新预览成功；SQLite 项目/页面/资源仍在。对失效原因无法可靠区分“TTL / 重启”时统一使用 `PREVIEW_ARTIFACT_UNAVAILABLE` 一类错误，不伪称自动恢复。 |
| E2 | 构建处于 `running` 时重启，再查询任务并重建。 | 原任务按当前恢复策略成为可解释的失败，已成功的构建产物仍可下载；新构建可启动，不把丢失的运行态心跳当成任务事实源。 |
| E3 | 清空内存后触发 PAT 限流和回填任务恢复。 | PAT 临时计数重新开始且 DB 凭证不丢；回填 DB 领取不重复，迟到结果被围栏拒绝。 |
| E4 | 在真实 Redis 模式执行同一业务用例、短暂断连和恢复。 | 明确各业务的失败/降级行为，恢复后无部分 artifact、重复任务或错误成功状态。 |
| E5 | 构建 Lite 生产镜像，运行 `scripts/contracts/check-image-startup.py`（默认 `--network none`，依赖镜像内置 tiktoken 词表）和 Lite Compose smoke；运行范围内最小质量门禁。 | 单容器真实启动、`/readyz`、Renderer 配置、预览与截图实际产物通过；不以单元测试或 HTTP 200 代替。 |

最小测试入口：`pnpm run test:backend:unit`、`pnpm run test:backend:api`、相关 `backend/tests/contracts` / integration、`pnpm run test:repository`。如果改变 External API v1 的字段或 Gateway 路径，另跑 `pnpm run test:contracts:gateway` 与消费者契约；镜像/渲染链路变化再跑 `pnpm run test:render-e2e`。不要无差别运行全仓 E2E。

## 5. 顺序、依赖与提交切分

```text
阶段 0 审计和基线测试
  ├─→ A 文档契约（可与 B 的设计并行）
  └─→ B 回填 DB 领取/围栏（先解除正确性依赖）
          → C 窄接口 + 双后端对拍
          → D 可观测 + 独立内存基线 + 有界容量
          → E 重启/断连演练 + 发布门禁
```

- 建议按 **文档与测试基线 → 回填任务 DB 围栏及迁移 → adapter 接口与调用方迁移 → 容量/观测 → 故障演练** 分别提交，便于定位回归。若 B 涉及数据库迁移，先发兼容 schema，再切代码；回退时旧代码必须仍可读取新 schema。
- D2 是**数据库写路径**基线，影响 P3 调度节奏；本计划的内存配额由 D3 单独测量。D2 未完成不阻塞 A/B/C。
- P3 后续可以使用进程内唤醒减少轮询，但每个队列必须在通知丢失时仍能靠 DB 领取与恢复；不得调用 `InMemoryRedis.publish` 充当可靠通知。
- Lite 的 SQLite 单实例锁已存在。本计划补充的是后端组合校验、可丢弃运行态的正确性边界与用户恢复路径。

## 6. 风险、回退和完成定义

| 风险 | 处理与回退依据 |
| :--- | :--- |
| facade 迁移改动面过大 | 保留 `get_redis_runtime_client()` 入口，按调用方迁移；静态门禁在最后启用。发现对拍差异时只回退该调用方，不回退已生效的 DB 围栏。 |
| 内存实现越做越像完整 Redis | 只实现 §3.2 的当前调用面；Stream、PubSub 和任意 pipeline 命令不进入支持承诺。 |
| Redis 故障或配额拒绝留下“DB 成功、API 失败” | 对 DB 事实源的写入使用明确提交顺序和缓存降级；对 ephemeral preview 在返回 ID 前清理部分写入。通过异常注入锁定。 |
| 进程重启后旧链接误导用户 | 对临时 ID 返回稳定失效提示并提供重新创建动作；数字 Release 保持 DB 回源。 |
| Lite RSS 与 Runtime Vite 互相挤压 | D3 记录容器整体 RSS；D4 有限预算和可观测拒绝，调整 TTL 前必须复测。 |
| 文档与实现在发布期间漂移 | 同一提交更新契约、部署文档、测试和必要的错误码说明；`test:repository` 与真实 Redis 对拍列入发布检查。 |

全部满足后才把本计划标记为完成：

- [ ] §3 的 key、命令、失效语义已落到正式契约，开发/部署/用户文档与代码一致。
- [ ] 回填任务仅依赖 DB 领取和 attempt 围栏；运行态清空、并发领取、迟到提交测试通过。
- [ ] `backend/app` 中除 adapter 实现外无原始 `.client` 调用；未登记命令无法被业务静默使用。
- [ ] 内存单测、真实 Redis 对拍、异常注入和必要的 API/集成测试通过；记录测试 Redis 的隔离方式。
- [ ] Lite 后端类型、ephemeral、清扫与容量状态可观察；存在基于 2C4G 实测的有限预算和阈值记录。
- [ ] Lite 真实镜像启动、重启、旧预览失效、新预览、构建中断和持久数据验证通过；测试记录写明未覆盖项。

计划完成并不表示 P3 统一任务运行时、普通 AI Run 续跑或 Runtime 多副本已经交付。

## 7. 实施记录（2026-09-25）

代码与测试已按阶段 0/A/B/C/D/E 落地；下列清单说明逐项结论与**未覆盖项**。

### 已完成

| 阶段 | 结论 | 证据 |
| :--- | :--- | :--- |
| 0 | 运行态调用点已按 §3.1 复核：`runtime:artifact:*`、`runtime:build:*`、`pat:*` 四类 key 之外无新增；`memory://test` 每例独立实例 + 前缀隔离，对拍使用独立非 0/非 15 库号与随机前缀 | `test_runtime_state_deployment.py`、`test_runtime_state_adapter.py` |
| A | 契约正文改为与实现一致（窄命令、key 表、部署组合、可观测、容量、对拍门禁）；开发/部署/用户文档与排障不再要求"联调必须真实 Redis" | `docs/developer/backend/runtime-state-adapter.md`、`getting-started.md`、`testing/strategy.md`、`troubleshooting.md`、`preview-artifacts.md`、`resource-queues.md`、`deploy/.env.example` |
| B | 回填任务领取、续租、终态提交全部改为数据库条件更新 + attempt 围栏；`SET NX` 锁与 key 已删除 | 迁移 `20260925_0100`、`test_asset_render_hint_backfill_job_queue.py` |
| C | 窄命令 facade + 两种后端实现落地；`backend/app` 静态门禁禁止 raw redis / `.client` / 内存后端引用；未登记命令（`publish`/Stream/任意 pipeline）封闭；对拍 12 例在 memory 与真实 Redis 上全绿 | `app/services/runtime_state/`、`test_runtime_state_adapter_boundary.py`、`test_runtime_state_adapter.py` |
| D | 启动日志、`/readyz` 静态元数据、`/metrics/runtime-state` 聚合指标；清扫失败有界重试；容量预算按 2C4G 实测定为 128 MiB / 16 MiB | `main.py`、`config.py`、`test_health.py`、`test_runtime_state_capacity.py`、基线报告 |
| E | 重启演练：旧临时预览 200 → 404、新预览 200、SQLite 数据保留、构建任务收敛为 failed、清空运行态后回填任务仍按 DB 领取并终态化；真实 Redis 断连：`/readyz` 保持 ready、预览创建与读取 503 `RUNTIME_STATE_UNAVAILABLE`、恢复后创建成功且无残留 | `test-results/lite-runtime-state/{restart-drill,redis-drill}-*.json` |
| E（补） | Lite/平台镜像构建期预置 tiktoken `cl100k_base` 到 `TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken`，导入期不再外联；`check-image-startup.py --variant lite` 在 `--network none` 下通过。未改 AI 模块 | `deploy/docker/Dockerfile.lite`、`Dockerfile.platform`；本地 `web-presentation:lite-tiktoken-preseed` 离线 smoke |

2C4G 实测（两次重复运行一致）：运行态峰值 102–105 MB / 182–186 keys，`capacity_rejections=0`，清扫 31–32 次全部成功（单次 ≤ 5.9 ms），Backend RSS 峰值 613–637 MB，Node 峰值 2.5–2.6 GB，容器峰值 2.74–2.76 GiB / 4 GiB，无 OOM、无异常请求失败。阈值理由与复现命令见契约文档 §6。

### 未覆盖项（必须在后续处理）

1. ~~**Lite 镜像离线启动**~~ **已处理（2026-08-15 引入的既有缺陷，2026-09 修复）**：根因是 `history_compression_values.py:17` / `history_compression.py:34` 导入期 `tiktoken.get_encoding("cl100k_base")`，再经 `app/__init__.py` 重导出放大到 `alembic`/`uvicorn` 全路径。**修复方式为镜像预置 BPE，不改 AI 模块**：构建期 `get_encoding('cl100k_base')` 写入 `TIKTOKEN_CACHE_DIR=/app/.cache/tiktoken` 并校验缓存非空；`check-image-startup.py --variant lite` 在 `--network none` 下已通过。AI 侧惰性加载/瘦 `app/__init__.py` 仍属可选加固，不在本计划必做范围。
2. **构建成功产物下载**：E2 只验证"运行中断 → 可解释失败"；"已成功构建产物仍可下载"依赖一次真实 Vite 构建，本次未在 Lite 容器内执行。
3. **运行时容器资源基线**：D3 记录基于本机 Docker 的 2C4G 限制容器；不同宿主内核/磁盘下 RSS 与清扫耗时可能不同，更换机型需重跑。
4. **Playwright/Renderer 实链**：Lite 单容器不含 Renderer，截图与渲染实链仍由 `test:render-e2e` 与 E2E 套件覆盖，不在本计划演练范围。

### 新增/变更的验证入口

- `pnpm run test:backend:runtime-state-parity`（CI job `runtime-state-parity`，缺少对拍 Redis 时显式失败）
- `pnpm run test:lite:runtime-state-drill -- --mode baseline|restart-drill|redis-drill --image <tag>`
- `backend/tests/unit/test_runtime_state_adapter_boundary.py`（业务不得绕过窄接口的静态门禁）
