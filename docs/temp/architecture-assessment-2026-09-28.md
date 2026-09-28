<!-- 文件功能：docs/temp 现行架构评估（现状与问题，2026-09-28）；执行计划见 plans/remaining-work-2026-09-28.md。 -->
# 架构评估（现状与问题）

> **日期**：2026-09-28。基线 `2d7858b`（分支 `dev`）。  
> **定位**：`docs/temp` 唯一现行评估。只陈述**当前架构现状、已定决策与仍在问题**；执行细节见 [`plans/remaining-work-2026-09-28.md`](./plans/remaining-work-2026-09-28.md)。  
> **口径**：代码可确认的问题与尚未验证的能力分开；「已实施」不等于「可对外承诺」；产品可接受残留（R-*）只登记。

---

## 1. 一页结论

1. **控制面 / 执行面边界清楚**：Backend 不跑浏览器，渲染在独立 Renderer（`render-contracts`）；校验有单一谓词；SQLite 单实例有锁；运行态走窄接口。这层结构值得保持。
2. **剩余架构主轴是任务运行时统一**。领取时序已收口到 `durable_job_lease_service.claim_rows_by_cas`，但各任务的租约/心跳/恢复/错误码仍是多方言并存，每加一类重任务就多一套。
3. **多部署能力不能对外承诺**：角色拆分、构建持久租约、预览缓存、签名共享已有代码，但跨副本演练未跑，分布式模板副本数为 1。
4. **存在一批“假守卫”**：布局脚本死副本、死契约测试、JSON Schema 死双源、关键架构测试不在 PR 阻塞层。成本低、误导大，应优先清掉。
5. **产品边界已定**（见 §3）：Run 承诺会丢；Lite 按 5–10 人 / 预览并发约 3；双库方言预算从宽。工程侧按此写文档与容量口径，不再悬置。
6. **顺序建议**：死物与门禁 → 任务运行时契约冻结 + 容量基线（并行）→ 多部署门槛与演练 → 契约机械化 → 巨石拆分 → 生产加固。多副本承诺最后。

---

## 2. 架构现状

```text
Editor ──HTTP──► Gateway ──┬──► Backend（控制面）
                           │     ├─ 领域服务 / AI Run（进程内）/ 工具规格
                           │     ├─ 重任务队列（多方言；claim 时序已收口）
                           │     ├─ render_requests → RenderCoordinator
                           │     └─ SQLite（单实例锁）| PostgreSQL
                           │         + memory:// | redis://（窄命令）
                           │
                           ├──► Runtime（预览 / 构建 / 编译诊断）
                           └──► Renderer（单槽 Chromium）
                                   packages/render-contracts
```

| 能力面 | 现状 | 可对外承诺？ |
| :--- | :--- | :--- |
| 浏览器截图/渲染 | 只在 Renderer，凭证 fail-closed | 是 |
| 页面校验通过判定 | 唯一谓词 `validation_result` | 是 |
| SQLite Lite | 单进程/单容器，`memory://` 运行态 | 是（规模见 §3） |
| 重任务恢复 | 页面/图片/截图/构建等走 DB 租约 | 部分（语义未统一，见 P1-TaskModel） |
| 普通 AI Run | 进程内，重启即停 | **是：承诺会丢** |
| Runtime 多副本 | 代码具备，演练未做，模板副本=1 | **否** |
| 双库（SQLite / PG） | 迁移与认领双方言，有门禁 | 是（成本见 §3 D1） |

---

## 3. 已定决策

| 决策 | 结论 | 成本与边界 |
| :--- | :--- | :--- |
| **Lite 地位** | 长期一等公民（SQLite） | 双库永久税；Lite 禁止多副本共用 DB 卷 |
| **Lite 推荐规模** | **5–10 人小团队，预览并发约 3** | 常规演示文稿工作区；非海量资产库。写入用户/部署文档 |
| **Run 持久性** | **承诺「会丢」** | 不做可恢复 Run；UI/文档须标明与 external 任务的差异 |
| **双库方言预算** | **从宽** | 正常双方言成本 = 固定税，不计入超支。正常 ≤ 8 人周/季。**重开 D1 仅当**：单季计入 > 12 人周，或连续两季 > 8 人周/季，或方言阻塞发版 ≥ 3 次/季，或放弃 Lite 一等公民 |
| **写路径基线（D2）** | 作为节奏参数来源 | **尚未采集**；不阻塞任务运行时设计 |
| **截图环境身份** | 现状可接受 | 升级后可复用旧图；不强制环境指纹（R-Screenshot） |
| **CDP / 浏览器池** | 不做 | 渲染只走远程 Renderer |

---

## 4. 仍在问题

### 4.1 优先（P0 / P1）

| ID | 问题 | 为何重要 | 出口 |
| :--- | :--- | :--- | :--- |
| **P1-TaskModel** | 重任务多方言：领取/租约/心跳/恢复/错误码不统一（约 9 套） | 正确性靠各队列自觉；扩展成本高；故障语义不可比 | 计划 WS-A |
| **P0-DeadGoods** | 布局脚本死副本 ×7；`manifest.capabilities` 空转测试；render-contracts JSON Schema 零消费 | 假安全感，误导维护 | 计划 WS-B |
| **P0-Gates** | 工具目录防漂移、契约往返、Runtime Kit 真断言、越权矩阵等架构测试不在 PR 阻塞层 | 漂移可合法合入 | 计计 WS-B |
| **P1-MultiDeploy** | 多部署门槛未达成；跨副本回归/故障演练未跑；分布式模板不可标可用 | 容易误判“已可扩容” | 计划 WS-C |
| **P1-Lite** | Lite 故障域仍合并（Backend+Runtime+Nginx）；混合负载未验收 | 规模承诺缺运行证据 | WS-G1 + WS-D |
| **P1-RunDisclosure** | Run「会丢」尚未在 UI/文档体现 | 与 external 任务持久承诺并存，用户不可辨 | WS-G7 |
| **P1-Health** | 队列/租约积压无对外指标 | 积压不可见 | WS-G2 |

### 4.2 维护性（P2）

| ID | 问题 | 出口 |
| :--- | :--- | :--- |
| **P2-Contracts** | 内外双入口无契约矩阵；Editor 类型手写镜像；previewSchema 三份手写 | WS-E |
| **P2-GodFiles** | `platform_runtime.py`、`session_facade_pydantic.py`、`page_mutation_queue.py` 等巨石；`ai↔services` 双向依赖 | WS-F |
| **P2-DialectOps** | 双库日常成本可见性（记账与复审触发器需落到治理文档） | WS-G6 |
| **P2-ProdHardening** | 示例密钥/弱默认、PG 备份演练不足、Renderer 同网段 | WS-G3/G4/G5 |

### 4.3 产品可接受残留（登记，不进优先级）

| ID | 问题 | 处理 |
| :--- | :--- | :--- |
| **R-Screenshot** | 截图指纹不含 Runtime/Chromium/字体环境版本 | 可复用旧图；可选发布提示手动刷新 |
| **R-Profile** | `profile.v1` 手填 | 多副本强一致成为目标时再改 |
| **R-CP5** | `memory://` + `BACKEND_MULTI_INSTANCE` 不拒绝 | 非真实部署形态 |
| **R-CP6** | AI 事件追加进程内锁保留 | 保护同一会话上的并发写，与方言无关 |

---

## 5. 尚未验证（不能当作已有能力）

- D2 容量基线（锁等待、队列年龄、P50/P95、混合负载 RSS/OOM）
- 故障注入（Renderer 全挂、构建被杀、写冲突耗尽、升级中断 Run）
- 多实例联调（共享对象存储、密钥、跨实例租约与迁移）
- Lite 成功构建产物下载
- 两阶段校验耗时拆分

---

## 6. 处理方向

| 序 | 工作 | 目标 |
| :--- | :--- | :--- |
| 1 | 死物清理 + 架构测试进 PR 门禁 | 消灭假守卫（1–2 天） |
| 2 | 任务运行时契约冻结 | 指定唯一角色模型 / 字段 / 恢复语义 |
| 3 | D2 与 Lite 规模基线采集 | 用数字支撑 §3 规模承诺 |
| 4 | 多部署门槛补齐 + 跨副本演练 | 不过则保持“单副本可用”口径 |
| 5 | 双入口对拍、类型/schema 单源 | 降低人肉对齐 |
| 6 | 巨石拆分（宜在运行时迁移前） | 降低改动面 |
| 7 | Run/ Lite 文档与 UI 承诺落地 | 与 §3 决策一致 |
| 8 | 生产加固（密钥、备份、隔离） | 运维风险 |
| 9 | 多副本对外承诺 | **严格最后** |

编号与验收口径见 [`plans/remaining-work-2026-09-28.md`](./plans/remaining-work-2026-09-28.md)。

---

## 7. 代码锚点

```text
backend/app/services/durable_job_lease_service.claim_rows_by_cas   认领时序
backend/app/services/project_build_service.py                      构建租约/attempt
backend/app/services/runtime_state/                                运行态窄接口
backend/app/services/validation_result.py                          校验谓词
backend/app/db/{retry,tx,profile}.py                               方言边界
backend/app/ai/*_queue.py + external_task_queue.py                 待统一的队列
backend/app/services/page_render_*_script.py                       死副本（待删）
tests/contracts/runtime-backend/runtime-kit-manifest.test.ts       空转测试（capabilities）
```
