# docs/temp 索引

工作区评估与规划文档目录（已纳入版本控制；根 `.gitignore` 仅忽略其他 `temp/`，本目录通过 `!docs/temp/` 反选跟踪）。  
整理日期：**2026-09-28**。基线 `2d7858b`。**单一现行评估 + 单一现行计划**；其余全部在 `archive/`。

## 现行

| 文档 | 说明 |
| :--- | :--- |
| [`architecture-assessment-2026-09-28.md`](./architecture-assessment-2026-09-28.md) | **现行架构评估**（唯一）。只写**现状与问题**：架构能力表、已定决策（含方言预算）、P0–P2 问题与处理方向。 |
| [`plans/remaining-work-2026-09-28.md`](./plans/remaining-work-2026-09-28.md) | **现行计划**。残留问题按 WS-A…H：P3 统一任务运行时（主轴）、死物清理+门禁、多部署门槛、D2 基线、契约机械化、巨石拆分、Lite/生产加固、产品拍板。 |

## 归档 · 评估

| 文档 | 备注 |
| :--- | :--- |
| [`archive/architecture-assessment-2026-09-28-merge.md`](./archive/architecture-assessment-2026-09-28-merge.md) | 09-28 合并整理稿（含对 09-25 的过期修正表）。已被「现状与问题」版取代。 |
| [`archive/architecture-assessment-2026-09-25.md`](./archive/architecture-assessment-2026-09-25.md) | 平台演进复核稿。实现层判断已过期。 |
| [`archive/architecture-assessment-critical-2026-09-25.md`](./archive/architecture-assessment-critical-2026-09-25.md) | 结构批判证据快照（量化基线、死契约/死副本、门禁错位）。 |

## 归档 · 计划与实施记录（已交付，残留项已抽入现行计划）

| 文档 | 日期 | 备注 |
| :--- | :--- | :--- |
| [`archive/lite-memory-adapter-2026-09.md`](./archive/lite-memory-adapter-2026-09.md) | 2026-09-25 | Lite `memory://` 运行态适配器。**已实施**。残留 → WS-D。 |
| [`archive/runtime-multi-deployment-scaling-plan-2026-09.md`](./archive/runtime-multi-deployment-scaling-plan-2026-09.md) | 2026-09-25/26 | Runtime 多部署。**T0–T4 已落地**，C/M 多数已修。残留 → WS-C。 |
| [`archive/review-multi-deployment-e2efe6c-head.md`](./archive/review-multi-deployment-e2efe6c-head.md) | 2026-09-25 | `e2efe6c..HEAD` 落地后评审（C/M/# 编号）。修复在 plan §13。 |
| [`archive/db-concurrency-primitives-2026-09.md`](./archive/db-concurrency-primitives-2026-09.md) | 2026-09-28 | DB 并发原语 CP1–CP6。**已全部实施**。不关闭 P1-TaskModel / D2。 |

## 归档 · 历史评估与专项

| 文档 | 日期 | 备注 |
| :--- | :--- | :--- |
| [`archive/architecture-assessment-2026-09-24.md`](./archive/architecture-assessment-2026-09-24.md) | 2026-09-24 | 上一现行评估；主轴判断仍有效。 |
| [`archive/cdp.md`](./archive/cdp.md) | 2026-09-09 | **已作废**。Browserless/CDP，由远程 Renderer 取代。 |
| [`archive/architecture_review_report.md`](./archive/architecture_review_report.md) | 2026-09-08 | 首轮架构/质量评审。 |
| [`archive/architecture-assessment-2026-09.md`](./archive/architecture-assessment-2026-09.md) | 2026-09-23 | 对首轮的复核与风险清单。 |
| [`archive/architecture-assessment-sqlite-jobs-2026-09.md`](./archive/architecture-assessment-sqlite-jobs-2026-09.md) | 2026-09-23 | 已拆分的旧合并稿。 |
| [`archive/architecture-assessment-sqlite-2026-09.md`](./archive/architecture-assessment-sqlite-2026-09.md) | 2026-09-23/24 | SQLite 兼容与任务写路径专项。 |
| [`archive/architecture-assessment-memory-2026-09.md`](./archive/architecture-assessment-memory-2026-09.md) | 2026-09-23 | 内存状态与 `memory://` 专项。 |
| [`archive/docs-temp-issue-status-2026-09.md`](./archive/docs-temp-issue-status-2026-09.md) | 2026-09-23/24 | 问题状态总览。 |
| [`archive/baseline-sqlite-2026-09.md`](./archive/baseline-sqlite-2026-09.md) | 2026-09-24 | SQLite 写路径采集模板；**D2 采集仍待执行**（WS-D）。 |

## 维护约定

1. **根下最多一份现行评估 + 一份现行计划**。新评估写在根下、文件名带日期；旧评估移入 `archive/` 并加归档横幅，不在原文件上大改。
2. 未实施方案放 `plans/`，正文须标明「规划/未实施」；出现「实施记录」后同步改本索引，整体交付则移入 `archive/`，残留项抽入现行计划。
3. 归档时顺手修正相对链接（同目录改 `./`，跨目录改 `../`）；历史失效链接以本索引为准。
4. 实施记录中的「未覆盖项」自动进入现行计划对应工作流，不得被完成勾选吞掉。
5. 架构决策（D1/D2/…）除定案日期外，必须写清成本影响与复审触发条件。
6. 产品可接受残留（R-*）只登记、不进优先级；重开须有新的产品目标。
7. 评估正文若含实现层描述，后续提交触及该描述时：**就地加「已过时」注记或归档重写**，禁止与代码长期相反。
