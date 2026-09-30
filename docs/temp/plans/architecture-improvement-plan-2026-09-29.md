# 架构改进与下一轮验证计划（2026-09-29）

> **状态：W01/W02/W03/W04/W05/W06/W08 代码与文档已提交（2026-09-30 两批），测试机验收未执行。** 详细进度见 §6。
> 基线：`7bff842b306503e894b4cde5b24b8f2a8319421b`（`arch-eval`）。问题定义以[现行评估](../architecture-assessment-2026-09-29.md)为准。
> **所有需要测试机器的动作均在下一轮执行，本轮不启动、连接或改变测试环境。** 历史完成记录见[归档](../archive/README.md)，不作为本轮验收结果。

## 1. 范围与执行顺序

不重建任务运行时，不合并有不同职责的 Job/Batch/Attempt 表，不重新讨论普通 Run 是否持久化。本计划首先补足已经存在机制的具体缺口，再验证部署承诺。

```text
已完成：静态复核 → 旧文档归档 → 新评估/计划/导航
代码批次：W02 契约、W03 指标、W04 探针准备 → 本地针对性验证
测试机下一轮：固定候选基线与测试数据 → M01 最终镜像链路 → M03 容量
        → W01 隔离 + M02；W05 兼容矩阵 + M04/M05
        → W06 恢复入口 + M07；M06 交付与门禁复核
        → M08 UI/跨仓回归 → 有证据后修订承诺
后续：按修改需要执行 W07 拆分；Lite 合并候选按 §3 决定
```

上图是依赖关系，不要求新增并行团队。机器暂不可用时先完成代码与本地验证；W08 随实现同步维护，不能提前写入尚未通过的容量或发布结论。

## 2. 工程工作包

下表保留各 W 项的完整完成条件，实施状态以 §6 为准。责任域用于交接，不指定实际人员。优先级与评估一致；本地测试可随代码执行，所有测试机操作仍放在下一轮。

| ID / 责任域 | 对应问题 | 具体产出 | 完成条件 / 验证关联 |
| :--- | :--- | :--- | :--- |
| **W01 · Runtime/部署，P1** | AR-01 | 明确可信领取器、编译执行进程、单任务 token、共享文件与网络的权限矩阵；实现执行侧无法读取全局 Worker 凭证的边界 | M02 证明确实不可读/不可越权；环境变量删键不能独立关闭本项 |
| **W02 · Backend/Editor/Runtime，P1** | AR-02 | 把 API 生成物接入实际类型消费；CI 从当前 Backend 重导 OpenAPI 后检查生成差异；previewSchema 生产结构校验消费 Schema；双入口测试精确到 method/path | 类型、必填性、枚举、嵌套结构变更均能使门禁失败；正常与非法样本三端一致；M08 覆盖用户路径 |
| **W03 · Backend/观测，P1** | AR-03 | 修正渲染 queued/retry_wait/executing 映射，租约统计落 Attempt；补 ExternalBatch、component kind、waiting_provider 逾期视图；明确 totals 单位与重复投影 | 非空数据集与 DB 对账；不把业务请求、执行槽位、领域投影相加当吞吐量；是 M03 的前置 |
| **W04 · 交付/测试，P1** | AR-04 | 最终镜像探针调用真实 Renderer 链路，保存 PNG/构建下载证据；整理每个模板引用的版本/digest；区分 amd64 启动与 arm64 执行 | M01/M06；旧 IMG0/2/3/4/9/10/11/12 的必要工作在此承接 |
| **W05 · Backend/Runtime/部署，P1** | AR-05 | 明确 N/N-1 服务版本、DB revision、Kit/产物兼容矩阵；定义停机或摘流策略；补 hostname/PID 条件下 Run 收敛说明和验收用例 | M04/M05；409 是拒绝证据，不等于滚动升级可用 |
| **W06 · 部署/运维，P1** | AR-06 | PG/SQLite 与对象存储、密钥、版本的备份清单；可重复的隔离恢复入口；备份一致性、顺序、RPO/RTO 目标和回滚步骤 | M07 恢复业务数据、资产、凭据解密、预览/截图/构建均有证据；不能只验 DB |
| **W07 · Backend/Editor，P2** | AR-07 | 按实际改动拆分 AssetsView 的筛选/详情/批量区域；后续触及 asset_service/运行态持久化时按职责拆；逐步缩小分层白名单 | 不改变 API 与租约语义；相关测试 + M08；不要以行数达标替代职责改善 |
| **W08 · 文档维护，P2** | AR-08 | 在本轮归档注记与跟踪状态修正基础上，进一步修订任务契约迁移前描述、Lite 文档的历史发布/HEAD/目标区分；更新验收证据 | 静态链接检查；所有“已通过/已发布”均有版本和记录；待验收项保持开放 |

### 2.1 W02 的约束

- OpenAPI 导出应在隔离配置下可重复，不依赖开发者正在运行的服务；不能静默连业务数据库或下载生产数据。
- 手写兼容层可以短期保留，但必须有明确映射和迁移边界；不能长期依赖 8 类字段名子集测试代表完整类型契约。
- JSON Schema 结构验证与 Runtime Kit/工作空间引用授权是两层检查，接入前者不能删除后者。
- 补至少四类反例：只改 Backend 字段类型、可选改必填、非法 previewSchema 嵌套字段、删除一个指定 method/path 但保留相同路径前缀。要求相应门禁确实失败。
- 不修改 External API v1 的 `canceled` 拼写来追求内部统一；破坏性变化需单独迁移方案和消费者验证。

### 2.2 W03 的约束

- 使用真实队列状态词汇，避免另一份不受约束的映射；缺列不能无声地等同“没有过期租约”。
- 给 pending、运行占用、供应商等待、Batch 续跑分别定义时间起点与单位。
- 页改/图片领域 Job 与 ExternalTask 的关系要可解释；组件执行虽存于 ExternalTask，也必须能单独观察。
- 用非空 fixture 验证正常排队、重试等待、执行、过期租约和终态；空库只作为补充。
- 采集开销也计入 M03。快照中的最老年龄不能直接冒充所有请求的 P95，分位数需从带时间戳的任务样本计算。

## 3. Lite 镜像专项的接续方式

旧 IMG 方案提出“Lite 内置独立 Renderer 进程，同时继续发布独立 Renderer 镜像”。该方案及历史体积估算已归档；当前 HEAD 未实施 Lite 内置 Renderer。保留既有自用/小团队风险接受，不把文档归档视作新方案获批或工程完成。

| 旧项 | 新计划处置 |
| :--- | :--- |
| IMG0 | M01，走 executor 默认实际路径，不单凭是否出现 `--no-sandbox` 作结论 |
| IMG1 | 旧文档纠偏已有记录；AR-08 发现的剩余矛盾由 W08 更新 |
| IMG2–IMG4 | W04/M06；先核对现有发布，再决定是否需要预发布 |
| IMG5–IMG8 | **条件候选**：若仍选择内置 Renderer，落实包/进程隔离、监督退出、强随机凭据持久化、卷权限和编排迁移 |
| IMG9–IMG11 | W04/M01/M03/M06；两种架构各自保留真实截图和产物下载证据 |
| IMG12 | 仅在对应交付形态实际通过后更新发布与回滚文档 |

候选实现的前置是 M01 基础链路通过、M03 有当前拓扑基线、W01/既有威胁模型对拟合并形态给出明确权限设计。若实施合并，**变更后必须重新跑 M01/M03/M07**，原两容器结果不能直接给新形态背书。合并镜像不意味着把浏览器放回 Backend 进程；Backend 运行环境约束继续遵守 AGENTS.md。

本轮不设“必须合并”的里程碑，也不根据历史压缩层大小保证体积持平。若测试不达标，保留已验证的独立 Renderer 交付路径，记录候选推迟原因。

## 4. 下一轮测试机执行矩阵

**以下 M01–M08 全部未执行，均属下一轮。** 有机器只是开跑条件，不代表任何项已通过。

### 4.1 开跑前固定条件

- 记录候选提交 SHA、工作区差异、镜像 digest/CPU 架构、主机 CPU/内存、Docker/Compose 版本、依赖锁文件和 DB revision。
- 优先复用明确属于本次测试的环境；先确认已有服务和端口，避免反复启动。使用独立 Compose project、数据卷、数据库、对象前缀及测试账号；不使用生产恢复目录。
- Lite 基准目标为受限 **2C4G**；多副本使用独立较充足资源（旧清单 4C8G+ 仅作资源起点，不是“足够”的证明），每个角色记录实际资源限制。
- 采用有效测试凭据，记录 key id/来源即可，不把密钥、访问 token 或登录态写入结果仓库。
- PG 与 Redis 使用真实测试实例，不能以缺配置跳过冒充通过。双库/租约参数与部署形态一同记录。
- M03 前必须完成 W03；若指标尚未修复，只允许做预采样并标注，不签署容量结论。

### 4.2 场景、门槛与产物

| ID / 优先序 | 前置 | 下一轮测试机动作 | 通过条件与必须保留的证据 |
| :--- | :--- | :--- | :--- |
| **M01 · 真实交付链路，第一批** | W04；隔离凭据和最终镜像 | 构建或拉取记录 digest 的 Runtime/Renderer/platform/lite；按实际入口启动；Backend→Renderer→Runtime 截图；Lite 完整拓扑构建 ZIP 并下载；缺失/空凭据负例 | PNG 可解码且内容对应目标页，ZIP 含可加载入口；凭据缺失拒绝；取消后浏览器/槽位释放。健康端点或手动 Playwright launch 不替代这些证据 |
| **M02 · 凭证与执行隔离** | W01、M01 | 使用测试 secret 验证编译子进程的挂载、UID、权限与网络；尝试读取全局 Worker 凭证、访问非本任务接口；渲染控制 API/内网访问负例；取消和超时回收 | 禁止资源确实不可访问，单任务 token 不能领取其他任务；记录允许/拒绝矩阵与进程退出证据。保留 Lite 既定接受项，不能把它算作生产隔离通过 |
| **M03 · Lite 容量与双库压力** | W03、M01 | 2C4G 空闲 10 分钟后混合预览/页改/截图/图片/构建；逐级提升到约 3 个预览并发和 5–10 测试用户；SQLite 锁竞争与 PG 对照；两阶段校验、归档/上传资源采样；运行 Lite 状态 drill | 无数据串写、重复结果或永久悬挂；负载停止后队列收敛，OOM/超时/拒绝均有计数。输出请求 P50/P95、成功率、锁等待/重试耗尽、队列/租约年龄、父子进程 RSS、构建 ZIP。延迟数值门槛在开跑前锁定，不能看结果后倒填 |
| **M04 · 跨副本与故障恢复** | W05、M01；2 Backend、2 preview、2 build/check 执行副本、2 Renderer，共享 PG/Redis/存储/密钥 | 强制跨 preview 子请求；重启 Backend-A 时 B 持续 Run；容器重建/PID 重用条件；杀执行进程、租约超时、迟到上传；双协调器竞争与 Worker 摘流；页面/图片/组件/Batch 取消与续跑 | B 活跃 Run 不被 A 收敛；旧 attempt 不提升；全局/工作空间额度不超限；一个 Batch 只消费一次续跑结果；任务最终完成/失败/取消，恢复时间有界且与租约配置一致 |
| **M05 · 版本与升级回滚** | W05、M04 基础场景 | 按矩阵运行 N/N-1 Backend/Runtime/Renderer、旧 Kit 产物与 DB migration；注入指纹不符；中断升级后按预定顺序恢复 | 支持组合可完成真实任务；不支持组合明确拒绝；无静默损坏。记录迁移窗口、请求错误、回滚步骤；不支持滚动时明确按停机升级验收 |
| **M06 · 发布与远端门禁** | W04、M01；可访问目标 registry/仓库 | 所有 Compose 模板配置与镜像 manifest/digest 检查；amd64/arm64 各实际执行一次截图；从外部 Gateway 验 OpenAPI；核对 GitHub required checks 与真实 job 名；如确需发布，采用固定预发布 tag | 模板各镜像按预定公开/私有权限可拉取；记录两种架构产物，非 QEMU 构建成功即结束；外部契约 JSON 满足检查；门禁设置与运行结果分别留证。不得自动移动 latest/sqlite-lite 或修改仓库可见性来“修绿” |
| **M07 · 系统恢复** | W06、M01 | 在测试数据副本做 SQLite 与 PG 备份/恢复；同步资源/产物与密钥；模拟缺资产、错误密钥、版本不匹配；恢复后登录、读页、解密 AI 配置、截图与下载构建 | 实际恢复点与恢复时长可计算；关键资产校验和一致；负例清晰失败。真实 RPO/RTO 与开跑前目标对照；测试后清理仅限本轮创建的环境 |
| **M08 · UI、权限与跨仓回归** | W02；W07 有改动时纳入；M01 | Editor 资产筛选/详情/批量、AI 进程停止文案、富文本自闭合/成对空节点；A 用户写 B 工作空间实体；双入口读写/异步任务/归档；与匹配 agent-kit 版本联调 | UI 行为和权限符合现有契约；自闭合无富文本写绑定，成对空节点可编辑，诊断不使整页失败；保留 E2E 报告、截图、双方提交版本 |

M03 的性能门槛在第一次正式采集前由目标工作负载确定并写入运行记录；当前只有团队规模和预览并发目标，没有已批准的 P95 数字，本计划不虚构 SLA。若暂时不能定阈值，产物仅标“探索性基线”，容量门保持开放。

### 4.3 可复用命令

下列为仓库已有入口，按工作包选择最小相关集合。故障注入、版本组合、恢复与 registry 检查仍需对应场景脚本，不能仅靠总测试命令关闭。本地已运行的最小集合见 §6；下面的远程依赖、容器、E2E 与环境命令均未执行。

```powershell
# 契约与代码改动验证
pnpm run test:backend:unit
pnpm run test:backend:api
pnpm run test:backend:integration
pnpm run test:contracts
pnpm run test:repository
pnpm run test:editor:gate
pnpm run test:runtime:gate
pnpm run test:render-contracts
pnpm run test:renderer
pnpm run test:python-workspace

# 真实依赖与交付验证：仅在本轮专用测试环境已准备后执行
pnpm run test:backend:pg-claim
pnpm run test:backend:runtime-state-parity
pnpm run test:contracts:gateway
pnpm run test:contracts:docker-context
pnpm run test:lite:runtime-state-drill
pnpm run test:render-e2e
pnpm run test:e2e:regression
pnpm run test:contracts:cli-skill
```

`test:render-e2e` 和 E2E regression 的 prepare 会准备/重置 smoke 数据，只能指向本轮专用测试数据。PG 配置使用 `P4_POSTGRES_DATABASE_URL`、`P4_POSTGRES_REQUIRED=1`；Redis 对拍使用独立库和 `RUNTIME_STATE_PARITY_REQUIRED=1`，不能将生产 Redis 填入。执行前按[测试命令文档](../../developer/testing/commands.md)复核环境变量。

外部 Gateway 契约使用 [check-gateway-openapi.py](../../../scripts/contracts/check-gateway-openapi.py)；镜像使用 [check-image-startup.py](../../../scripts/contracts/check-image-startup.py)，完整拓扑使用新增 [check-deployment-pipeline.py](../../../scripts/contracts/check-deployment-pipeline.py)；入口与证据边界见[测试命令](../../developer/testing/commands.md)；Worker 摘除使用 `uv run --project backend python -m app.scripts.check_render_worker_removal`。参数在下一轮按入口 `--help` 和实际测试拓扑填写，本轮不猜测地址或凭据。

### 4.4 结果记录模板

下一轮创建 `docs/temp/runs/<实际日期>-<候选短SHA>/summary.md`；不要提前创建空的“通过”报告。原始大日志/二进制进入 CI artifact 或既有 `test-results/e2e/`，摘要只记录可访问的证据位置、校验和与必要统计，不将可重生成的大产物入库。

| 字段 | 必填内容 |
| :--- | :--- |
| 标识 | M 项编号、关联 AR/W 项、执行人、起止时间与时区 |
| 环境 | Git SHA/差异、镜像 digest/架构、机器资源、拓扑、DB revision、租约配置 |
| 前置/目标 | 前置工作是否完成；性能/RPO/RTO 预定阈值；测试数据范围 |
| 操作 | 实际命令与故障注入顺序（脱敏）、退出码 |
| 结果 | 通过/失败/受阻/未执行；样本量、时间窗、实际数值与阈值对照 |
| 证据 | 日志、PNG/ZIP、状态迁移和指标快照的路径或 artifact 链接 |
| 后续 | 缺陷编号、恢复/清理结果、复测条件、承诺是否可调整 |

机器未到位、权限不足、测试跳过、探针通过但业务失败，都保持“受阻/未通过”，不能将旧记录粘贴为当前成功。

## 5. 验收门与失败后的处理

| 门 | 关闭条件 | 未通过时 |
| :--- | :--- | :--- |
| 契约门 | W02 的正反例与真实消费链通过 | 保持 AR-02，不声称完整单源 |
| 观测门 | W03 非空数据对账、M03 采集口径正确 | 容量只做探索，不升格承诺 |
| 镜像交付门 | M01 + M06 对目标版本/架构通过 | 不将历史 tag 或 workflow 定义当已可交付 |
| 隔离门 | W01 + M02 | 维持既有受限威胁模型，不扩大多租户承诺 |
| 多副本门 | M04 + M05，相关隔离/存储前提齐备 | 静态模板继续标待验收；不承诺滚动无中断 |
| 容量门 | M03 达到开跑前目标且有稳定样本 | 降低推荐规模或调整实现后复测，不保留名义 SLA |
| 恢复门 | M07 完整业务恢复达到预定目标 | 保持 AR-06 与恢复限制 |

失败只重跑与修复相关的集合及必要跨域回归；若变更了镜像拓扑、DB Schema、权限或执行生命周期，则相应门重新开放。架构项关闭需要具体提交与结果位置，禁止用“WS 已完成”替代。

## 6. 实施进度与本地证据（2026-09-30 第二批）

首批（W02/W03/W04）已随 `2045f55` 提交；第二批 W01/W05/W06/W08 已随 `a49d1c7`、`acae00e`、`541bc90` 提交。以下证据针对已提交代码，不代表已发布或远端 CI 通过。

| 工作包 | 当前状态 | 本批交付与剩余条件 |
| :--- | :--- | :--- |
| W02 | 约定范围内代码与本地门禁已完成 | 核心 API DTO 实际引用生成物；CI 隔离重导并比较完整生成物；previewSchema 生产结构校验与两端类型生成；共享正反例；Top 操作精确 method/path、响应与差异对拍。其余手写视图/请求类型保留明确迁移边界；M08 未执行 |
| W03 | 代码与 SQLite 非空对账已完成 | 修复渲染状态，区分 Request/Attempt；增加组件 kind、Batch 与供应商轮询指标；totals 只汇总领域任务行。真实 PG、采集开销和 M03 容量验收仍待执行 |
| W04 | 探针代码与本地模拟测试已完成，交付门开放 | Renderer 镜像走真实控制 API/生产执行器并保存 PNG、回执和镜像身份；完整拓扑探针经 Gateway 检查截图和构建 ZIP；CI 上传镜像证据。真实容器、最终站点加载、全 Compose 版本清单及双架构执行仍待 M01/M06 |
| W01 | 代码与权限矩阵已落地，M02 开放 | 执行隔离文档；rtworker/rtchild 分 UID、spawn 降权、任务工作区 setgid；凭证宽松权限在已配置降权时 fail-closed。**M02 测试机证明不可读/不可越权仍未执行** |
| W05 | 兼容矩阵与 Run 边界已文档化并补测，M04/M05 开放 | N/N-1 组合、停机/滚动/排空策略；修正 multi-backend 误写的全局收敛；hostname/PID/PID 重用边界与验收用例。实测组合仍未执行 |
| W06 | PG 备份恢复入口与清单已交付，M07 开放 | `pg-backup.sh`/`pg-restore.sh`（校验和、alembic、隔离目标）；备份清单、一致性顺序、RPO/RTO、隔离演练与验证/负例。真实演练未执行 |
| W07 | 筛选/批量/详情已拆出 | `useAssetListFilters`+`AssetFilterSidebar`、`useAssetBatchSelection`、`useAssetDetail`+`AssetDetailDialog`；AssetsView 约 1885→1009 行，19 项集成测试通过。新建/上传/回填弹窗与 asset_service 后续按改动再拆 |
| W08 | 随本批更新 | 更新计划进度、任务运行时契约恢复列与 Run 收敛描述；兼容矩阵/执行隔离/备份恢复已入部署文档导航。其余历史专题矛盾继续按实际修改维护 |

本地验证（第二批）：

- Runtime：`runtime-build-worker` / `runtime-build-runner.infrastructure` / `runtime-diagnostics-workspace-pool` 共 48 项通过（2 项 POSIX-only 在 Windows 跳过）；`pnpm --filter web-runtime-vue check` 通过。
- Backend：`test_ai_run_recovery_owner.py` 12 项通过。
- `pnpm run test:repository`：13 项通过（含文档链接）。
- 首批既有本地验证仍有效（contracts/generated、editor/runtime check、previewSchema、队列指标等）。

**M01–M08 全部未执行。** 本轮未连接测试机器，未启动/重启业务服务或容器，未运行真实 PG/Redis、E2E、构建镜像、发布、数据库迁移或恢复演练。Vite 测试输出既有的未来 native config-loader 兼容提示，未据此改动运行配置。

下一批：W07 按实际改动继续拆分；机器到位后从 M01 固定基线并执行 M02/M04/M05/M07，不能把本地结果填写为测试机通过。探针产物、容量数字与恢复记录必须来自实际执行。
