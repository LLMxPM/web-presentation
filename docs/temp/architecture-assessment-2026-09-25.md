# 架构评估（批判性复核）：远程渲染与控制面收口之后（2026-09-25）

> 评估日期：2026-09-25。基线提交 `c6c9b1a`（分支 `dev`，较 origin 超前 12）。  
> 输入材料：`docs/temp/` 现行评估与 archive 专项稿、`e8afd67..c6c9b1a` 提交与对应实现。  
> 判断口径：对 **2026-09-24 评估**做批判性复核，而不是续写优点清单；代码可确认的问题与尚未验证的风险分开；单机 Lite 与 PostgreSQL 部署的行为差异单独标出。  
> 本文是 `docs/temp` 的**现行评估**。历史稿见 [`archive/`](./archive/)，未实施规划见 [`plans/`](./plans/)。  
> **本文相对 09-24 稿的立场变化**：主轴落地判断基本保留；「任务模型碎片化」「文档-实现漂移」被上调并重排优先序。截图环境身份（原 P1-Screenshot）**经产品判定降级**：不要求截图与渲染环境逐像素/逐版本严格一致，当前准确度可接受，不再作为 C0。

---

## 0. 一页结论

1. **改造主轴确实落地了**，这点不必推翻：浏览器执行出 Backend（远程 Renderer + `render-contracts`）、Runtime 并入主仓、双包 workspace 收拢、页面校验跨阶段语义收口、SQLite 单实例守卫、空闲写放大治理。`e8afd67..023c95c` 是完整的「执行面外移 → 仓库/构建边界 → 正确性与调度收口」链条。`ad4c8f1`/`5e24b7a`/`c4fa8d4` 又把 `memory://` 窄接口、回填任务 DB 租约、Lite 离线启动补完——**运行态适配器已从「规划」变成「已实施」**。
2. **09-24 评估本身已部分过时**：`plans/lite-memory-adapter.md` 有 2026-09-25 实施记录，`README.md` 仍写「规划（未实施）」，09-24 正文 §7 仍把该计划排在未来步骤。这不是笔误，而是 **docs/temp 作为第二事实源开始漂移**的信号。本次复核先修正状态，再谈架构。
3. **页面校验 P0 已关闭，有测试锁**。「无代码可确认的 P0」成立。原 P1-Screenshot（截图指纹不含环境身份）**不再按正确性 P0 处理**：产品明确截图不需要渲染环境级高准确，镜像升级后短期复用旧截图**可接受**。降为可接受残留 / 低成本硬化项，不挡发布、不进 Top 优先级。
4. **真正的结构性债务不是「13 条 loop」而是任务模型碎片化**：`external_task_queue` / `page_mutation_queue` / `component_mutation_queue` / `image_generation_queue` / `page_screenshot_queue_worker` / `mutation_job_service` / `asset_render_hint_backfill` / `render coordinator` / 构建 `BackgroundTasks` 至少 **9 套并行的领取-租约-心跳-恢复-错误码方言**。P3「统一任务运行时」不是清理项，而是本轮之后 **剩余架构工作的主轴**；不应等 D2 数据齐了才开始设计。
5. **D1=A（SQLite Lite 长期一等公民）产品上正确，工程上是永久税**。双库方言、迁移双方言证明、CI 矩阵会长期存在。09-24 稿庆祝了 D1 定案，却没有给「方言维护成本预算」和复审点。本评估要求补上：**每年/每季成本可见，超预算才重开 D1**。
6. **推荐优先序（重排后）**：**P3 任务运行时契约冻结（设计可先于 D2）** → D2 基线采集（并行）→ 构建持久领取 → 双入口对拍（先 Top 操作）→ AI 巨石拆分 → Lite 故障域 → 截图/发布身份硬化（可选）→ 多 Runtime。多副本仍最后。

---

## 1. 对 09-24 评估的批判性复核

### 1.1 仍然成立的部分

| 09-24 判断 | 复核结论 |
| :--- | :--- |
| 主轴已落地（执行面外移 / 单仓 / 校验收口 / SQLite 边界） | **成立**。`bdfcdab` 起 Backend 无 Chromium；`validation_result.py` 单谓词 + 防漂移测试；`sqlite_single_process` 排他锁在 lifespan 获取；`test_loop_gate` 存在。 |
| 不能宣称「可水平扩展」或「Lite 已适配 2C4G」 | **成立，且 09-25 补了部分数据**：`memory://` 适配器有 2C4G 实测（运行态峰值 ~105MB / 键 ~186），但 **混合负载端到端、构建产物下载、Renderer 实链**仍在未覆盖项。 |
| Browserless/CDP 已作废 | **成立**。`archive/cdp.md` 不应再进 roadmap。 |
| 多 Runtime 副本应等 D2 与阶段 0 | **成立**。`plans/runtime-multi-deployment-scaling-plan.md` 仍是规划，阶段 0 基线未验收。 |
| 「删编译省 50%」「纯内存租约」「内外 API 机械合并」等判断不成立 | **成立**。保持作废。 |

### 1.2 被低估或表述偏软的部分

**（1）原 P1-Screenshot：技术事实成立，但产品验收标准更宽（2026-09-25 定案）**

技术事实仍然为真：`page_screenshot_fingerprint_service.build_hash` 只纳入 `schema_version`、`PLATFORM_FONT_REVISION`、页面尺寸/字号/描边、主题，不含 Runtime/Renderer/Chromium 环境版本；`profile.v1` 写死在 Compose 与默认配置。镜像升级后旧截图仍可复用。  
**产品判定（覆盖 09-24 的「最高残留正确性」表述）**：截图不需要渲染环境级严格准确，当前准确度可接受。复用旧截图属于可接受偏差，**不**与「渲染不可用却报 passed」同级。处理方式：降为可接受残留；仅在顺手时做低成本硬化（例如发布说明提示可手动刷新截图），**不**作为架构门禁或 Top 优先项。

**（2）「13 条 loop」掩盖了任务模型分裂**

09-24 把问题写成「调度写路径仍偏轮询 / loop 节奏未收敛」。实际上每个队列各自实现：

- 条件领取与 `lease_generation` 围栏（`external_task_queue`）
- 批级租约 + 写围栏（`page_mutation_queue` / `component_mutation_queue` / `image_generation_queue`）
- durable lease 服务与四套「恢复超时 running」口径（mutation job 曾对齐过，截图/回填/渲染仍有自己的）
- 构建仍走 FastAPI `BackgroundTasks`，**根本没有租约**
- 正常 AI Run 进程内 asyncio，重启即 `AI_RUN_PROCESS_STOPPED`

这是 **五种持久性承诺并存**，不是「轮询偏多」。P3 若只做「节奏配置化」会继续掩盖分裂；目标必须是 **一种任务运行时 + 有限角色扩展点**。

**（3）D1=A 缺成本边界**

D1=A 让 Lite 成为一等公民是对的产品决策。代价是：

- `app/db/` 适配层长期存在（已完成一轮，但双方言迁移证明是永久门禁）
- CI/发布矩阵长期双轨
- 「禁止多副本共用 SQLite 卷」写进承诺后，扩容故事对 Lite 永久关闭

09-24 §7「长期含义」写了三条约束，**没有写成本预算与复审触发器**。若方言分支每年消耗超过某个阈值（例如持续阻塞 ≥2 人周/季），应重开 D1，而不是无限默认 A。

**（4）文档-实现漂移已被自身证据证实**

| 位置 | 说法 | 实际 |
| :--- | :--- | :--- |
| `docs/temp/README.md` | `lite-memory-adapter` 列在「规划（未实施）」 | 计划正文 §7 已有 2026-09-25 实施记录与测试入口 |
| 09-24 评估 §7 第 4 步 | 「运行态半边按 plans/lite-memory-adapter.md 执行」 | `ad4c8f1`/`5e24b7a` 已落地窄接口、DB 租约、对拍与演练 |
| 计划「未覆盖项」 | 构建成功产物下载、不同宿主基线、Renderer 实链 | **仍然未覆盖**，不能因「计划已实施」抹掉 |

**结论**：`docs/temp` 需要维护纪律（见 §6），否则下一轮又会对着过时结论做决策。

**（5）「无 P0」的论证方法偏弱**

「当前无代码可确认的 P0」可以成立，前提是把口径写死：  
> 页面校验 P0 已关闭且有测试锁；截图环境身份属产品可接受偏差（不按 P0）；构建无接管与 Run 不可恢复是已声明边界，故障路径成功语义仍待故障注入验收。

---

## 2. 变更后的架构快照（修正版）

```text
Editor (Vue) ──HTTP──► Gateway ──┬──► Backend (FastAPI 控制面)
                                 │       ├─ 领域服务 / AI Run（进程内）/ 工具规格
                                 │       ├─ 任务执行（碎片化，见下）
                                 │       ├─ render_requests → RenderCoordinator
                                 │       └─ SQLite(单实例锁) | PostgreSQL
                                 │           + memory:// | redis://（窄接口已收口）
                                 │
                                 ├──► Runtime (Vue3+Vite)
                                 │       预览 / 构建 / 编译诊断 / 视觉编辑
                                 │
                                 └──► Renderer (单槽 Chromium)
                                         packages/render-contracts

任务持久性现状（关键，09-24 未画出）：
  durable + lease： external_batch / page|component mutation / image / screenshot / backfill / render_request
  durable + 无租约： ProjectBuildJob + BackgroundTasks
  非持久：          普通 AI Run（进程内）
```

关键边界（应遵守，部分已有测试锁）：

| 边界 | 约束 | 锁强度 |
| :--- | :--- | :--- |
| 浏览器执行 | 只在 Renderer | 代码 + 配置拒绝旧 Playwright env |
| 校验通过 | 唯一谓词 `validation_result` | 单定义门禁 + 跨阶段契约测试 |
| SQLite | 文件库单进程/单容器 | 排他锁 + worker 数拒绝 |
| 运行态 | 业务只走窄命令 facade | 静态门禁禁 raw redis / `.client` |
| 普通 AI Run | 进程内，不承诺重启恢复 | 明示语义，**产品面未统一** |
| 截图身份 | 环境版本可不进指纹 | **产品接受现状**（非门禁） |
| 任务模型 | 应统一运行时 | **未锁**（9 套方言） |

---

## 3. 已关闭项（相对 09-23 / 09-24）

| 问题 | 关闭证据 | 提交 |
| :--- | :--- | :--- |
| P0：Renderer 不可用仍 `passed` 落库 | `validation_result.py` + stages 契约 + 跨阶段测试 | `5c459ae` |
| `_is_validation_passed` 多份拷贝 | 单定义 + 防漂移测试 | `5c459ae` |
| SQLite 多进程并发写 | `sqlite_single_process` + lifespan 取锁 | `a9dd2c1` |
| Backend 无 readiness | `/readyz` + lite healthcheck | `a9dd2c1` |
| 空闲态无条件 DML 放大 | 探测-命中再写、心跳节流、`test_loop_gate` | `023c95c` |
| 运行态原始 Redis 调用面扩散 | `runtime_state/` 窄接口 + 静态门禁 + memory/redis 对拍 | `ad4c8f1`/`5e24b7a` |
| 回填任务正确性依赖 `SET NX` | DB 条件领取 + attempt 围栏，key 已删 | `ad4c8f1` |
| Lite 镜像离线启动失败 | 构建期预置 tiktoken，`--network none` smoke | `c4fa8d4` |
| Agent Store 双向同步 | 按会话分片单一状态 | `44282d6` |
| Backend 内嵌 Chromium | 远程 Renderer | `bdfcdab` 起 |

---

## 4. 仍在风险（重排后）

### 可接受残留 — 截图 / 发布身份（产品已降级，非 C0）

| ID | 问题 | 处理 |
| :--- | :--- | :--- |
| **R-Screenshot** | 截图指纹不含 Runtime/Renderer/字体/Chromium 环境身份；升级后可能复用旧图 | **产品接受**。不挡发布、不进 Top 优先级。可选低成本硬化：文档提示手动刷新、或发布脚本顺手失效截图；非架构门禁。 |
| **R-Profile** | `profile.v1` 手填、Compose 默认值相同 | 与 R-Screenshot 同根，同级接受。仅当未来要做多副本/缓存强一致时再回头。 |

### P1 — 可用性与承诺边界

| ID | 问题 | 说明 |
| :--- | :--- | :--- |
| **P1-TaskModel** | 任务模型碎片化（9 套领取/租约/恢复方言） | 每加一种重任务就复制一套队列。P3 必须统一运行时，而不是只调 sleep。 |
| **P1-Run** | 普通 AI Run 绑 Backend 进程 | 与 external 任务的持久承诺不一致；用户无法从产品面区分「会丢」和「不会丢」。 |
| **P1-Build** | 构建派发依赖 `BackgroundTasks` | 无租约、无 attempt 围栏、进程故障接管不足；是 9 套方言里 **最弱** 的一套。 |
| **P1-Lite** | Lite 故障域仍合并 | Backend+Runtime+Nginx 同容器；Renderer 已隔离。`memory://` 适配器有单机 2C4G 数据，但故障域与混合负载未验收。 |
| **P1-Health** | `/readyz` 不反映 Renderer 与调度 loop 积压 | 有意不探 Renderer 可以，但 loop 队列年龄/租约年龄仍无对外指标。 |

### P2 — 成本与维护性

| ID | 问题 | 说明 |
| :--- | :--- | :--- |
| **P2-Dialect** | 双库方言是 D1=A 的永久税 | 需要成本预算与复审点，不是「全做」就结束。 |
| **P2-API** | 内外双入口无契约矩阵 | 31 个内部路由 vs 13 个 External；领域服务共享，权限/202/错误码仍可漂。 |
| **P2-GodFiles** | AI 域巨石未收敛 | `platform_runtime.py` 1854、`session_facade_pydantic.py` 1687、`page_mutation_queue.py` 1384、`asset_service.py` 1336；Editor `AssetsView` 1791。前端 Agent 面板已拆，**Backend AI 域未拆**。 |
| **P2-Locks** | 进程内订阅/锁表仍在 | SSE 有 DB 回放；限制在 Run 生命周期。不得当作可扩展原语。 |
| **P2-Docs** | docs/temp 双事实源漂移 | README/评估/计划状态不一致（见 §1.2-4）。 |

### 决策状态

| 决策 | 状态 | 复核意见 |
| :--- | :--- | :--- |
| **D1** SQLite Lite 地位 | 已定案 A（长期一等公民） | **维持**，但补：方言成本预算 + 复审触发器。P2/P3 全做、P4/P5 必做不变；2b 写重试维持重立。 |
| **D2** 写路径基线门 | **仍待实测** | **降级为节奏参数来源，不再挡 P3 设计**。设计冻结可先行，数字后填。 |
| **Lite 运行态 `memory://`** | **已实施**（非仅定案） | 计划 §7 完成；未覆盖项（构建产物下载、跨宿主基线、Renderer 实链）保留为缺口。 |
| **CDP/Browserless** | 已作废 | 维持。 |
| **截图准确度** | **已定（2026-09-25）：现状可接受** | 不要求环境级高准确；旧截图复用可接受。原 P1-Screenshot/C0 撤销，降为 R-Screenshot。 |
| **正常 Run 可恢复？** | **未决策**（被写成实现约束） | 应升为产品决策：要么承诺「会丢」并在 UI 标明，要么立项可恢复 Run。 |

---

## 5. 尚未验证（不可当作已有能力）

- **容量基线**：SQLite 锁等待、队列年龄、P50/P95、混合负载 RSS/OOM。`memory://` 适配器有 **运行态** 2C4G 数据，**不能替代 D2 写路径与端到端混合负载**。
- **故障注入**：Renderer 全挂、Worker 掉线、busy_timeout 耗尽、构建进程被杀、滚动升级中断 Run——均无端到端验收。
- **多实例联调**：共享对象存储、密钥一致、迁移与租约跨实例。
- **构建成功产物在 Lite 真实可下载**（计划自列未覆盖项）。
- **性能等价**：两阶段校验耗时拆分仍无基线；「删编译省 50%」继续作废。

---

## 6. 文档与治理建议（本轮新增）

1. **单一现行评估**：`docs/temp` 根下只保留一份带日期的「现行评估」；写入时记录 `HEAD` 提交；若后续提交触及评估结论范围，应在文首加「已过时」横幅或直接归档重写。
2. **计划 ≠ 现状**：`plans/` 文档一旦出现「实施记录」，同步改 `README.md` 分类（规划 → 已实施/部分实施），禁止「README 说未实施、正文说已交付」。
3. **未覆盖项不得被完成勾选吃掉**：实施记录里的未覆盖项应自动进入下一轮评估的「尚未验证」表。
4. **架构决策（D1/D2/…）必须带成本与复审条件**，只有定案日期不够。

---

## 7. 架构重估

### 7.1 适配度评分（定性）

| 产品目标 | 适配度 | 依据 |
| :--- | :--- | :--- |
| AI 演示文稿创作（主场景） | **较好** | 单仓 + 工具规格单源 + 渲染契约 + 校验写门，Agent 可协作；执行面边界清楚。 |
| 个人 / 小团队 Lite | **可用但脆** | `memory://` + SQLite 已收口；故障域仍粗；无混合负载承诺。 |
| 团队生产 / 横向扩容 | **未就绪** | 无基线、无多副本验收、构建不持久（截图身份产品已接受，不在此列）。 |
| 长期可维护性 | **中等风险** | 任务模型分裂 + 双入口 + 双库税 + AI 巨石；测试锁在关键正确性上不错，但覆盖面不均。 |

### 7.2 结构判断

**做对的结构**

- **控制面 / 执行面分离**：Backend 不跑浏览器，Renderer 单槽可独立升级，是本轮最值钱的边界。
- **契约包 `render-contracts`**：协议与实现分离，远程渲染可测可演进。
- **校验写门单一谓词**：把「检查通过」从散落布尔收成领域语义，是正确性工程的正确姿势。
- **运行态窄接口**：把「短生命周期缓存」和「任务事实源」划清，避免了 Lite 把 Redis 模拟越做越大。

**结构上仍错位的**

1. **任务运行时没有成为平台层**：页面/组件/图片/截图/回填/渲染/构建/Run 各自为政。产品已经依赖「重任务可恢复」，平台却只给部分任务恢复能力。
2. **持久性承诺不透明**：external 任务可恢复、构建靠进程活着、Run 会丢——同一 Agent 会话里三种语义并存。
3. **发布身份不是构建产物的一部分**：`profile.v1` 人工对齐。产品已接受截图缓存不与环境版本强绑定；仅在多副本/缓存强一致成为目标时再升级。
4. **复杂度集中在 AI 编排**：`platform_runtime` + `session_facade` + 多队列是变更频率最高、文件最大、契约测试最薄的交集。
5. **双入口是产品事实，但治理缺位**：External API 给 CLI/agent-kit，内部 API 给 Editor；不合并是对的，不对拍是错的。

### 7.3 处理顺序（相对 09-24 的重排）

| 序 | 工作 | 为何提前/靠后 |
| :--- | :--- | :--- |
| 1 | **P3 任务运行时：先冻结契约与角色模型** | 剩余架构主轴；设计可先行，D2 只填 sleep/租约数字。 |
| 2 | **D2 基线采集**（与 1 并行） | 打点已就绪；产出节奏参数与容量承诺。 |
| 3 | **P1-Build 持久领取 + attempt 围栏** | 直接套用已有 external 任务模式，收益高。 |
| 4 | **双入口对拍（Top 操作先行）** | 不必全矩阵；先页面读写、校验、预览、归档。 |
| 5 | **AI 巨石按队列边界拆分** | 降低 P3 迁移面；避免在 1800 行文件里改运行时。 |
| 6 | **P5 Lite 边界固化 + 故障域评估** | 承诺文档化优先于拆容器。 |
| 7 | **P4 迁移双方言**（与 1–3 并行） | 维持必做，不无限期推迟。 |
| 8 | **截图/发布身份硬化**（可选） | 产品已接受现状；仅低成本顺手项，或将来缓存强一致需求出现时再做。 |
| 9 | **多 Runtime / 角色拆分** | 严格排在 1–2 之后。 |

### 7.4 需要产品/负责人拍板、不应再静默默认的问题

1. **普通 AI Run 的丢失语义**是永久产品承诺，还是待修缺口？UI/文档是否明确标注？
2. **Lite 的推荐规模**到底是什么（人数、并发预览、项目数）？没有这个，D1=A 的「一等公民」无法写进用户承诺。
3. **双库方言年维护预算**多少？超预算是否重开 D1？
4. ~~截图缓存策略~~ **已定（2026-09-25）**：截图不要求环境级高准确，现状可接受；不强制「环境身份哈希」或「发布全量失效」。若将来多副本/缓存强一致成为目标，再重开。

---

## 8. 与历史文档的关系

| 文档 | 位置 | 关系 |
| :--- | :--- | :--- |
| `architecture-assessment-2026-09-24.md` | `archive/` | 上一现行评估；主轴判断仍有效，优先序与风险分级以本文为准。 |
| `docs-temp-issue-status-2026-09.md` | `archive/` | 问题状态表；截图项已按产品判定降级，其余以本文 §4 为准。 |
| `lite-memory-adapter.md` | `plans/` | **已实施**（见其 §7）；未覆盖项仍属缺口。README 分类需修正。 |
| `runtime-multi-deployment-scaling-plan.md` | `plans/` | **未实施规划**；阶段 0 门禁仍有效。 |
| 其余 `archive/*` | `archive/` | 专项证据库；细节可追溯，结论以本文为准。 |

---

## 附录 A. 本轮复核用到的代码锚点

```text
backend/app/services/validation_result.py              校验唯一谓词
backend/app/services/page_screenshot_fingerprint_service.py  截图指纹（无环境身份，产品接受）
backend/app/services/runtime_state/                    运行态窄接口（已落地）
backend/app/services/redis_runtime_client.py           facade + 部署组合校验
backend/app/services/rendering/coordinator.py          渲染协调（单槽 Worker）
backend/app/ai/*_queue.py + external_task_queue.py     任务方言集合
backend/app/api/routes/build_jobs.py                   BackgroundTasks 构建派发
backend/tests/unit/test_loop_gate.py                   亚秒循环白名单
backend/tests/unit/test_validation_result.py           谓词单定义门禁
deploy/.env.example / deploy/compose/*.yml             RENDER_PROFILE_DIGEST=profile.v1
```
