# docs/temp 索引

工作区评估与规划文档目录（已纳入版本控制；根 `.gitignore` 仅忽略其他 `temp/`，本目录通过 `!docs/temp/` 反选跟踪）。  
整理日期：2026-09-25。现行结论以当日批判性架构评估为准。

## 现行文档

| 文档 | 说明 |
| :--- | :--- |
| [`architecture-assessment-2026-09-25.md`](./architecture-assessment-2026-09-25.md) | **现行架构评估**。对 09-24 稿做批判性复核与重估：上调 C0 截图身份、任务模型碎片化，重排优先序；基线 `c6c9b1a`。 |

## 规划与实施状态

| 文档 | 说明 |
| :--- | :--- |
| [`plans/lite-memory-adapter.md`](./plans/lite-memory-adapter.md) | Lite `memory://` 运行态适配器。**代码已实施（2026-09-25）**，见文末实施记录；未覆盖项（构建产物下载、跨宿主基线、Renderer 实链）仍是缺口。 |
| [`plans/runtime-multi-deployment-scaling-plan.md`](./plans/runtime-multi-deployment-scaling-plan.md) | Runtime 多部署形态与横向扩容路线图。**未实施**：角色拆分、预览无状态化、构建持久领取均未开始。 |

## 归档（历史）

| 文档 | 日期 | 备注 |
| :--- | :--- | :--- |
| [`archive/architecture-assessment-2026-09-24.md`](./archive/architecture-assessment-2026-09-24.md) | 2026-09-24 | 上一现行评估；主轴判断仍有效，优先序与风险分级以 09-25 稿为准。 |
| [`archive/cdp.md`](./archive/cdp.md) | 2026-09-09 | **已作废**。Browserless/CDP 浏览器池方案，由远程 Renderer 取代，不再作为计划。 |
| [`archive/architecture_review_report.md`](./archive/architecture_review_report.md) | 2026-09-08 | 首轮架构/质量评审；若干执行面结论已过时。 |
| [`archive/architecture-assessment-2026-09.md`](./archive/architecture-assessment-2026-09.md) | 2026-09-23 | 对首轮的复核与风险清单；框架被后续评估继承。 |
| [`archive/architecture-assessment-sqlite-jobs-2026-09.md`](./archive/architecture-assessment-sqlite-jobs-2026-09.md) | 2026-09-23 | 已拆分的旧合并稿，仅存对照。 |
| [`archive/architecture-assessment-sqlite-2026-09.md`](./archive/architecture-assessment-sqlite-2026-09.md) | 2026-09-23/24 | SQLite 兼容与任务写路径专项；含 09-24 复核修订。 |
| [`archive/architecture-assessment-memory-2026-09.md`](./archive/architecture-assessment-memory-2026-09.md) | 2026-09-23 | 内存状态与 `memory://` 专项。 |
| [`archive/docs-temp-issue-status-2026-09.md`](./archive/docs-temp-issue-status-2026-09.md) | 2026-09-23/24 | 问题状态总览（已解决/仍在/不成立）。 |
| [`archive/baseline-sqlite-2026-09.md`](./archive/baseline-sqlite-2026-09.md) | 2026-09-24 | SQLite 写路径采集模板；打点入口已落地，采集待目标机执行。 |

## 维护约定

1. 新评估写在本目录根下，文件名带日期；旧评估移入 `archive/`，不在原文件上大改。写入时记录 `HEAD` 提交。
2. 未实施方案放 `plans/`，正文须标明「规划/未实施」；一旦出现「实施记录」，同步更新本索引分类，禁止 README 与正文状态相反。
3. 归档文档中的相对链接若指向当时的 `./` 同级文件，已随移动失效时以本索引为准。
4. 实施记录中的「未覆盖项」自动进入下一轮评估的「尚未验证」表，不得被完成勾选吞掉。
5. 架构决策（D1/D2/…）除定案日期外，必须写清成本影响与复审触发条件。
