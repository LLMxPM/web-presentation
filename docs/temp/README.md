# docs/temp 索引

工作区评估与规划文档目录（已纳入版本控制；根 `.gitignore` 仅忽略其他 `temp/`，本目录通过 `!docs/temp/` 反选跟踪）。  
整理日期：2026-09-24。现行结论以当日架构评估为准。

## 现行文档

| 文档 | 说明 |
| :--- | :--- |
| [`architecture-assessment-2026-09-24.md`](./architecture-assessment-2026-09-24.md) | **现行架构评估**。汇总 `e8afd67..023c95c` 架构变更、已关闭项、仍在风险与下一步。 |

## 规划（未实施）

| 文档 | 说明 |
| :--- | :--- |
| [`plans/lite-memory-adapter.md`](./plans/lite-memory-adapter.md) | Lite `memory://` 运行态适配器：契约固化、双后端对拍与 Lite 承诺（D1=A 后正式化）。 |
| [`plans/runtime-multi-deployment-scaling-plan.md`](./plans/runtime-multi-deployment-scaling-plan.md) | Runtime 多部署形态与横向扩容路线图。角色拆分、预览无状态化等均未开始。 |

## 归档（历史）

| 文档 | 日期 | 备注 |
| :--- | :--- | :--- |
| [`archive/cdp.md`](./archive/cdp.md) | 2026-09-09 | **已作废**。Browserless/CDP 浏览器池方案，由远程 Renderer 取代，不再作为计划。 |
| [`archive/architecture_review_report.md`](./archive/architecture_review_report.md) | 2026-09-08 | 首轮架构/质量评审；若干执行面结论已过时。 |
| [`archive/architecture-assessment-2026-09.md`](./archive/architecture-assessment-2026-09.md) | 2026-09-23 | 对首轮的复核与风险清单；框架被现行评估继承。 |
| [`archive/architecture-assessment-sqlite-jobs-2026-09.md`](./archive/architecture-assessment-sqlite-jobs-2026-09.md) | 2026-09-23 | 已拆分的旧合并稿，仅存对照。 |
| [`archive/architecture-assessment-sqlite-2026-09.md`](./archive/architecture-assessment-sqlite-2026-09.md) | 2026-09-23/24 | SQLite 兼容与任务写路径专项；含 09-24 复核修订。 |
| [`archive/architecture-assessment-memory-2026-09.md`](./archive/architecture-assessment-memory-2026-09.md) | 2026-09-23 | 内存状态与 `memory://` 专项。 |
| [`archive/docs-temp-issue-status-2026-09.md`](./archive/docs-temp-issue-status-2026-09.md) | 2026-09-23/24 | 问题状态总览（已解决/仍在/不成立）。 |
| [`archive/baseline-sqlite-2026-09.md`](./archive/baseline-sqlite-2026-09.md) | 2026-09-24 | SQLite 写路径采集模板；打点入口已落地，采集待目标机执行。 |

## 维护约定

1. 新评估写在本目录根下，文件名带日期；旧评估移入 `archive/`，不在原文件上大改。
2. 未实施方案放 `plans/`，正文须标明「规划/未实施」，避免被当成现状缺陷清单。
3. 归档文档中的相对链接若指向当时的 `./` 同级文件，已随移动失效时以本索引为准。
