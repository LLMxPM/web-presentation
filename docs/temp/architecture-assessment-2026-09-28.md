<!-- 文件功能：docs/temp 现行架构评估（对照仓库代码重核版，2026-09-28）；执行计划见 plans/remaining-work-2026-09-28.md。 -->
# 架构评估（现状与问题）

> **日期**：2026-09-28。基线 `2d7858b`（分支 `dev`）；代码重核至 `3818eab`（仅文档提交）。  
> **定位**：`docs/temp` 唯一现行评估。只陈述**当前架构现状、已定决策与仍在问题**；执行细节见 [`plans/remaining-work-2026-09-28.md`](./plans/remaining-work-2026-09-28.md)。  
> **口径**：本版全部断言按当前仓库代码重核；「已实施」不等于「可对外承诺」；产品可接受残留（R-*）只登记。  
> **与上一版差异**：修正门禁覆盖面、任务方言计数与「空转测试」机制描述；补入 CP4 门禁假阴性、页面/组件队列恢复盲区、弱密钥单实例可上线、PG 备份脚本缺失、Renderer 同网段等遗漏；删除已过期的「构建 BackgroundTasks 无租约」判断。二次补强：Backend 多副本 Run 生命周期正确性、Runtime Build 凭证隔离、仓库 branch protection 未强制、Lite 容量口径、版本兼容矩阵、System DR、多副本措辞降档。

---

## 1. 一页结论

1. **控制面 / 执行面边界成立**：Backend 不跑浏览器（`pyproject.toml` 无 Playwright），渲染只在独立 Renderer（`packages/render-contracts`）；凭证 fail-closed；校验有单一谓词 `validation_result`；SQLite 单实例有锁。这层结构值得保持。
2. **剩余架构主轴仍是任务运行时统一**。领取时序已收口到 `durable_job_lease_service.claim_rows_by_cas`，但**实有 10 套任务模型、3 套认领方言**，心跳/恢复/终态词汇仍各写各的；且 CP4 防漂移门禁存在假阴性，已有认领实现绕过检测。
3. **有一批「假守卫」，且比上一版描述更严重**：布局脚本死副本 ×7；runtime-kit 跨模块契约测试断言了**不存在的键**（`capabilities`，真实键是 `exports`）；render-contracts JSON Schema 零消费且无 DTO 对拍。假安全感成本低、误导大，应优先清掉。
4. **多部署能力当前不仅「未验收」，仍有已知正确性与隔离缺口**：Runtime 已完成角色拆分、构建持久租约与部分多副本选址；Backend 已具备 PG / Redis / 共享签名与对象存储前提。但普通 AI Run 启动恢复是**全局扫描语义**，新副本启动会终态化其它副本活跃 Run；RenderCoordinator 全局/工作空间额度是 check-then-act，多副本可超限；Runtime Build 的可信 Worker 凭证与不可信构建执行仍共处同一容器。**Backend / Runtime / Renderer 多副本均不得作为生产承诺。**
5. **仓库级 merge gate 未强制**：`platform-test.yml` 的 PR workflow 跑得比较全，但 `main`/`dev` 的 branch protection 与 ruleset 均为空（API 实测 `protected=false`、ruleset `[]`），workflow 通过 ≠ 不可绕过合入。
6. **产品边界已定**（见 §3）：Run 承诺会丢；Lite 目标 5–10 人 / 预览并发约 3（**容量验收前不是 SLA**）；双库方言预算从宽。
7. **顺序建议**：死物/假守卫 + merge gate 强制 + CP4 补强 → **Backend 多副本 Run 语义与 Build 隔离** → 任务运行时契约冻结与恢复盲区 → 容量基线 → 多部署门槛与演练（含版本兼容）→ 契约机械化 → 巨石拆分 → System DR。多副本承诺最后。

---

## 2. 架构现状

```text
Editor ──HTTP──► Gateway ──┬──► Backend（控制面）
                           │     ├─ 领域服务 / AI Run（进程内）/ 工具规格（tool_specs SSOT）
                           │     ├─ 重任务队列（10 套任务模型；3 套认领方言）
                           │     ├─ render_requests → RenderCoordinator（多副本额度未原子化）
                           │     └─ SQLite（单实例锁）| PostgreSQL
                           │         + memory:// | redis://（窄命令）
                           │
                           ├──► Runtime（preview|build|check 三角色；build 编译不可信 SFC）
                           └──► Renderer（单槽 Chromium）
                                   packages/render-contracts
```

| 能力面 | 现状 | 可对外承诺？ |
| :--- | :--- | :--- |
| 浏览器截图/渲染 | 只在 Renderer，凭证 fail-closed，每 attempt 新建 Context | 是 |
| 页面校验通过判定 | 唯一谓词 `validation_result.is_validation_passed` | 是 |
| SQLite Lite | 单进程/单容器，`memory://` 运行态 | 是（**目标规模**，见 §3；D2 未过不是 SLA） |
| 重任务恢复 | 页面/图片/截图/构建/回填/外部 Batch 走 DB 租约 | **部分**（页面/组件队列运行中不恢复，见 P1-Recovery） |
| 普通 AI Run | 进程内，重启即 `AI_RUN_PROCESS_STOPPED` | **是：承诺会丢**（文档已披露，UI 弱） |
| Runtime 多副本 | **固定副本、静态注册形态**（手工复制 service + nginx upstream）；动态发现/扩缩容/摘流与跨副本演练未做 | **否** |
| Backend 多副本 | 共享前提（RSA/密钥/对象存储/Redis）已校验；**Run 启动恢复全局扫描会杀其它副本活跃 Run** | **否（已知不正确）** |
| Renderer 多协调器 | 单 Worker 占用有 `active_occupancy` 唯一索引保护；**全局/工作空间额度 check-then-act 可超限** | **否** |
| 双库（SQLite / PG） | 迁移与认领双方言，有门禁（含 PG 认领必跑） | 是（成本见 §3 D1） |
| 工具目录 | `tool_specs.py` 单一事实源，派生链完整 | 是（防漂移主测不在 PR，见 P0-Gates） |
| 仓库 merge gate | PR workflow 存在；**branch protection / ruleset 为空** | **否** |

---

## 3. 已定决策

| 决策 | 结论 | 成本与边界 |
| :--- | :--- | :--- |
| **Lite 地位** | 长期一等公民（SQLite） | 双库永久税；Lite 禁止多副本共用 DB 卷 |
| **Lite 目标规模** | **目标 5–10 人小团队，预览并发约 3** | **产品目标，容量验收（D2）前不得作为 SLA/硬承诺**；常规演示文稿工作区，非海量资产库 |
| **Run 持久性** | **承诺「会丢」** | 不做可恢复 Run；用户文档已披露重启不续跑；UI 仅显示「运行已停止」 |
| **双库方言预算** | **从宽** | 正常双方言成本 = 固定税。正常 ≤ 8 人周/季。**重开 D1 仅当**：单季计入 > 12 人周，或连续两季 > 8 人周/季，或方言阻塞发版 ≥ 3 次/季，或放弃 Lite 一等公民 |
| **写路径基线（D2）** | 作为节奏参数来源 | **尚未采集**；不阻塞任务运行时设计，但阻塞 Lite 规模升格为承诺 |
| **截图环境身份** | 现状可接受 | 升级后可复用旧图；不强制环境指纹（R-Screenshot） |
| **CDP / 浏览器池** | 不做 | 渲染只走远程 Renderer |
| **多副本承诺门槛** | **已知正确性缺口关闭 + 跨副本故障演练通过** 后才开放 | 不是「有 compose 模板」即可宣称 |

---

## 4. 仍在问题

### 4.1 优先（P0 / P1）

| ID | 问题 | 为何重要 | 出口 |
| :--- | :--- | :--- | :--- |
| **P0-BackendMultiInstance** | `recover_interrupted_agent_runs_on_startup` **无 owner/lease/epoch**，启动时把全库 `pending/running/cancelling` Run 一律终态化（`run_recovery.py:22-36`）。Backend-B 扩容/滚动启动会杀死 Backend-A 正在执行的 Run。`signing_identity` 多实例校验只查共享 RSA/密钥/对象存储/Redis，**不禁止该语义** | 跨副本正确性问题，不是「未演练」；配置层误示 multi-backend 已安全 | 并入 WS-C 前置 blocker；恢复改为按 owner/epoch 认领 |
| **P0-BuildIsolation** | `runtime-build` 编译用户 SFC（不可信），却挂载全局 `build_worker_credential`（`compose.runtime-roles.yml:212-225`）；子进程只删 env（`runtime-build-worker.ts:30-42`），同容器同 mount、Dockerfile 无 `USER`（root），仍可读 `/run/secrets/build_worker_credential`。该凭证可 claim **任意** pending 构建并领取 `build_token`/`service_token` | 可信 Worker 身份与不可信构建执行共处一容器，不是弱默认密码问题 | 并入 WS-G3 升级：sandbox 独立/降权/只拿单任务短 TTL token |
| **P0-MergeGate** | `main`/`dev` **branch protection 与 ruleset 均为空**（API 实测 `protected=false`、ruleset `[]`）；workflow 会跑但不阻止合并 | 「有 CI」≠「有门禁」；任何 check 可被绕过 | 并入 WS-B0：先启用 require PR + required checks，再谈清单 |
| **P0-DeadGoods** | 布局脚本死副本 ×7（约 1605 行）；runtime-kit 跨模块测试断言 `capabilities` 而 manifest 键为 `exports`（后两条循环恒空转）；render-contracts `schemas/*.v1.json` 零消费、无 DTO↔JSON 对拍 | 假安全感，误导维护；AGENTS 双源同步承诺失真 | 计划 WS-B |
| **P0-ClaimGate** | CP4 认领防漂移门禁有假阴性：`test_db_adapter_layer` 只识别内联 `execute(update(...))`；`mutation_job_service.claim_next_pending_job` 先赋 `update_stmt` 再 execute 可绕过；`rendering/repository.reserve_attempt` 因命名不含 `claim` 漏检 | 并发原语边界可被合法合入的自写认领破坏 | 并入 WS-B，门禁改为语法/AST 级 |
| **P0-Gates** | 工具目录主防漂移（`test_ai_agent_config.test_unified_tool_specs_should_match_runtime_and_guides`）在 **integration**，PR 默认 `full=false` 不跑；E2E / 镜像 smoke / CLI 跨仓契约亦非 PR 阻塞 | 漂移可合法合入 PR；**unit/api（含越权矩阵）实际在 PR**，缺口在 integration 与跨仓 | 计划 WS-B |
| **P1-Recovery** | 页面/组件变更队列 Worker 循环内**不做过期恢复**，仅启动时 `recover_interrupted_*_on_startup`；运行中租约过期的 running 任务滞留到进程重启 | 故障后任务挂死，用户无感知；与 image/screenshot/build/external 的循环内恢复不一致 | 并入 WS-A |
| **P1-TaskModel** | 重任务 **10 套任务模型**；认领时序 3 套（共享 CAS / lease_generation CAS / render claim_generation）；心跳比例、终态词汇（image `"error"` vs 他处 `"failed"`）不统一 | 正确性靠各队列自觉；扩展成本高；故障语义不可比 | 计划 WS-A |
| **P1-RenderQuota** | `RenderCoordinator._dispatch_once` 先 `count_active_attempts()` 再 `reserve_attempt()`（`coordinator.py:254-285`），非全局事务原子；多 Backend 可同时见 `active=0` 而突破 global/workspace limit（单 Worker 双派已有 `active_occupancy` 唯一索引保护） | 多协调器下额度失守 | 并入 WS-C |
| **P1-MultiDeploy** | 多部署门槛未达成；Runtime 多副本是**静态固定拓扑**（手工复制 service + nginx upstream、静态 `RUNTIME_CHECK_BASE_URLS`）；跨副本回归/故障演练未跑 | 容易把 compose 静态复制当成真正分布式 | 计划 WS-C |
| **P1-VersionSkew** | 滚动升级只约定 Runtime `build_id`/`runtime_kit_version` 指纹一致；缺 **兼容矩阵**：Backend↔Runtime API、Backend↔Renderer `render-contracts`、Backend↔DB schema、Runtime Kit↔产物。版本不一致直接拒绝会造成瞬时停机 | 多服务独立部署后滚动升级必需 | 并入 WS-C |
| **P1-Lite** | Lite 故障域合并（Backend+Runtime+Nginx）；混合负载未验收；`test:lite:runtime-state-drill` 有脚本但**不在 CI** | 目标规模缺运行证据 | WS-G1 + WS-D |
| **P1-Secrets** | 示例弱密钥（`AI_SECRET_ENCRYPTION_KEY=AAAA…`、`DEFAULT_ADMIN_PASSWORD=change-admin-password`）可被单实例/Lite 直接采用；占位拒绝仅在**多实例**路径 | 轻量部署可带弱 Fernet/弱管理员密码上线 | WS-G3 |
| **P1-Backup** | `deploy/scripts/` 仅 SQLite demo 备份/恢复；**无 PG 备份脚本、全仓无 `pg_dump`**。生产恢复实为 **DB + 对象存储 + AI 加密密钥 + RSA keyring + service credentials** 组合态，缺 System DR（RPO/RTO、恢复顺序、密钥备份/轮换） | DB 恢复了 S3 没恢复 = 悬空引用；密钥丢了密文永久不可读 | WS-G4 升格为 System DR |
| **P1-Health** | 队列/租约积压无对外指标；`code_check_result_cache.snapshot_metrics` 无出口；`/metrics/*` 仅 db-write/runtime-state | 积压不可见 | WS-G2 |
| **P1-RunDisclosure** | Run「会丢」在用户文档已披露（`docs/user/ai/workflow.md` 等），但 Editor UI 只显示「运行已停止」，未区分「取消」与「进程停止、不续跑」 | 与 external 任务持久承诺并存，用户不可辨 | WS-G7 |

### 4.2 维护性（P2）

| ID | 问题 | 出口 |
| :--- | :--- | :--- |
| **P2-Contracts** | Editor `types/api.ts`（约 1551 行）手写镜像 Backend schema，无 OpenAPI→TS；previewSchema 三份手写（Backend 校验器 / Editor `component-preview.ts` / Runtime `runtime-preview.ts`）无对拍 | WS-E |
| **P2-GodFiles** | `platform_runtime.py`（2082 行，store+SSE+状态机）、`session_facade_pydantic.py`（1802 行）、`page_mutation_queue.py`（849 行）等；`ai↔services` 双向依赖（约 25↔15 文件），懒 import 掩盖环 | WS-F |
| **P2-DialectOps** | 双库日常成本可见性（记账与复审触发器需落到治理文档） | WS-G6 |
| **P2-ProdHardening** | Renderer 与 Backend 同 `platform-net`，浏览器可触达 Backend 内网 API（仅拦 Renderer 控制面路径）；`compose.with-deps` Redis `appendonly no`；各 Dockerfile 均无 `USER`（root） | WS-G3/G5 |
| **P2-AuthZGap** | 多用户/越权矩阵在 `tests/api/test_multi_user_access.py`（PR 在跑）；缺「A 用户 AI 工具调用写 B 用户实体」的跨用户工具矩阵 | 并入 WS-B |
| **P2-VocabDrift** | 终态词汇（`error`/`failed`/`skipped`）、心跳/租约比例、死列 `ai_page_mutation.lease_generation`、死 scope `COMPONENT_TOOL_DELETE_SCOPES` | 并入 WS-A |

### 4.3 产品可接受残留（登记，不进优先级）

| ID | 问题 | 处理 |
| :--- | :--- | :--- |
| **R-Screenshot** | 截图指纹不含 Runtime/Chromium/字体环境版本 | 可复用旧图；可选发布提示手动刷新 |
| **R-Profile** | `profile.v1` 手填 | 多副本强一致成为目标时再改 |
| **R-CP5** | `sqlite :memory:` + `BACKEND_MULTI_INSTANCE` 不被拓扑拒绝（`sqlite_single_process.py` 内存库 early-return 在拓扑校验之前）。注：`memory://` Redis + 多实例**已**被拒 | 非真实部署形态 |
| **R-CP6** | AI 事件追加进程内锁保留 | 保护同一会话上的并发写，与方言无关 |

---

## 5. 尚未验证（不能当作已有能力）

- D2 容量基线（锁等待、队列年龄、P50/P95、混合负载 RSS/OOM）——**Lite 规模升格为承诺的前置**
- 故障注入（Renderer 全挂、构建被杀、写冲突耗尽、升级中断 Run、**多副本并发启动互相杀 Run**）
- 多实例联调（共享对象存储、密钥、跨实例租约与迁移；**Render 额度在多协调器下是否超限**）
- 版本 skew 兼容（Backend N ↔ Runtime/Renderer N-1、DB migration 期间旧副本存活）
- Lite 成功构建产物下载；`test:lite:runtime-state-drill` 未进 CI
- 两阶段校验耗时拆分
- System DR 演练（脚本本身不存在；密钥备份/轮换未定义）
- Build sandbox 逃逸面（同一容器 root + 全局 credential 的实际风险）

---

## 6. 处理方向

| 序 | 工作 | 目标 |
| :--- | :--- | :--- |
| 0 | **启用 branch protection / ruleset（WS-B0）** | require PR + required checks，merge gate 真正强制 |
| 1 | 死物清理 + 假守卫修复 + CP4 门禁补强 | 消灭假安全感（1–2 天） |
| 2 | **Backend 多副本 Run 恢复语义 + Build credential 隔离** | 关闭跨副本正确性与信任边界缺口（多部署前置） |
| 3 | 任务运行时契约冻结 + 页面/组件恢复盲区 | 统一角色模型 / 字段 / 恢复语义；循环内恢复 |
| 4 | D2 与 Lite 规模基线采集 | 用数字支撑目标规模；通过前不写 SLA |
| 5 | 多部署门槛 + Render 额度原子化 + 版本兼容矩阵 + 跨副本演练 | 不过则保持“单副本可用”口径 |
| 6 | 双入口对拍、类型/schema 单源 | 降低人肉对齐 |
| 7 | 巨石拆分（宜在运行时迁移前） | 降低改动面 |
| 8 | Run / Lite 文档与 UI 承诺落地 | 与 §3 决策一致 |
| 9 | System DR + 生产加固（弱密钥拒绝、密钥/对象存储/DB 联合恢复、网络隔离） | 运维与安全风险 |
| 10 | 多副本对外承诺 | **严格最后** |

编号与验收口径见 [`plans/remaining-work-2026-09-28.md`](./plans/remaining-work-2026-09-28.md)。

---

## 7. 代码锚点

```text
backend/app/ai/run_recovery.py:22-36                                 全局扫描终态化（P0-BackendMultiInstance）
backend/app/services/signing_identity.py:257-310                     多实例共享前提校验（不含 Run 语义）
backend/app/services/rendering/coordinator.py:254-285                额度 check-then-act（P1-RenderQuota）
runtime/src/core/plugins/runtime-build-worker.ts:30-42                仅删 env（P0-BuildIsolation）
deploy/compose/compose.runtime-roles.yml:203-225                     runtime-build 挂全局 credential
runtime/Dockerfile                                                   无 USER（root）
backend/app/api/routes/internal_runtime.py:442+                      全局 claim → build_token/service_token
.github/workflows/{platform,reusable-quality}-.yml                   PR 测试面（merge gate 未强制）
backend/app/services/durable_job_lease_service.claim_rows_by_cas     认领时序（共享 CAS）
backend/app/services/mutation_job_service.claim_next_pending_job      自写认领（CP4 门禁漏检）
backend/app/services/rendering/repository.reserve_attempt            render 认领方言
backend/app/ai/{page_mutation,component_mutation}_queue.py            恢复仅启动时（P1-Recovery）
backend/app/services/project_build_service.py                        构建租约/attempt（已走 CAS）
backend/app/services/runtime_state/                                  运行态窄接口
backend/app/services/validation_result.py                            校验谓词
backend/app/db/{retry,tx,profile,sqlite_single_process}.py            方言边界
backend/app/ai/tool_specs.py                                         工具目录 SSOT
backend/tests/integration/test_ai_agent_config.py:194                工具防漂移主测（不在 PR）
backend/tests/unit/test_db_adapter_layer.py                          CP4 门禁（有假阴性）
backend/app/services/page_render_*_script.py                         死副本 ×7（待删）
tests/contracts/runtime-backend/runtime-kit-manifest.test.ts         空转测试（键名错误）
packages/render-contracts/schemas/*.v1.json                          零消费死双源
deploy/scripts/                                                      仅 SQLite demo 备份
```

---

## 8. 对上一版评估的修正与补漏

| 上一版表述 | 代码重核结论 |
| :--- | :--- |
| 「manifest.capabilities 空转测试」 | **更严重**：测试读 `capabilities`，manifest 真实键是 `exports`，后两条断言恒空转；仅 alias 有效 |
| 「约 9 套」任务方言 | **10 套任务模型**；认领时序实为 **3 套**；「构建 BackgroundTasks 无租约」**已过期**（现走 `claim_rows_by_cas`） |
| 「架构测试不在 PR 阻塞层」 | **过宽**：unit/api（含 `test_multi_user_access` 越权矩阵）在 PR；**integration（工具防漂移主测）/E2E/镜像 smoke/CLI 契约不在 PR** |
| 「PG 备份演练不足」 | **更严重**：PG 备份/恢复脚本全仓不存在；且应升格为 System DR（DB+对象存储+密钥组合态） |
| 「示例密钥/弱默认」（P2） | **应为 P1**：单实例/Lite 无启动拒绝，可带弱密钥上线 |
| R-CP5「memory:// + 多实例不拒绝」 | **不精确**：`memory://` Redis + 多实例已拒；未拒的是 `sqlite :memory:` + 多实例 |
| 「Run 会丢尚未在 UI/文档体现」 | **部分过时**：用户文档已披露；缺口在 Editor UI 文案未区分取消/进程停止 |
| 「多部署：代码具备，演练未做」 | **不充分**：不仅是未演练——Run 全局恢复会杀其它副本活跃 Run（P0）、Build 全局凭证与不可信执行同容器（P0）、Render 额度非原子（P1） |
| 「Lite 推荐规模 5–10 人」写进「可承诺」 | **口径冲突**：D2 未过时只能是**目标规模**，不得作 SLA |
| （未记） | **新增 P0**：Backend 多副本 Run 生命周期、Build 凭证隔离、branch protection 未强制；CP4 门禁假阴性；页面/组件恢复盲区；Renderer 同网段 |
| （未记） | **新增 P1**：版本兼容矩阵缺失（rolling upgrade 会瞬时停机）；Render 多协调器额度竞态 |
