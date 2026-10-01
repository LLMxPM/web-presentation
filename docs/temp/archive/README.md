# 历史评估与计划归档

整理日期：2026-10-01。本文是历史材料索引；[架构调整收尾工作计划](../plans/architecture-closeout-plan-2026-10-01.md)是唯一现行执行入口，状态与证据导航见[目录索引](../README.md)。

归档不是删除证据，也不是确认旧计划全部完成。历史文档内的“现行”“已完成”、测试数字、registry 状态和排期只代表当时记录。未完成项在现行收尾计划维护；运行证据保留原位置，包括修复前失败与复测结果。

## 2026 年 10 月 1 日归档

| 文档 | 原位置 | 接续方式 |
| :--- | :--- | :--- |
| [09-30 架构评估](./architecture-assessment-2026-09-30.md) | `docs/temp/architecture-assessment-2026-09-30.md` | 历史缺口与风险定义保留；W05 实施、截图生命周期与完整旧镜像结果由收尾计划按版本更新 |
| [09-29 改进计划的 10-01 快照](./architecture-improvement-plan-2026-09-29.md) | `docs/temp/plans/architecture-improvement-plan-2026-09-29.md` | 保留最新工作区正文和 M01–M08 原始要求，包括尚未提交的 M05 状态；由唯一收尾计划确定停止点与剩余工作 |

两份正文只增加历史说明并修正链接，原始要求和结果没有删除。`runs/` 中的实施与验收目录保留原位置；未验收门继续开放。正式文档与导航同步引用收尾计划或明确标注的历史材料。

## 此前归档

| 文档 | 原位置 | 接续方式 |
| :--- | :--- | :--- |
| [09-29 架构基线评估](./architecture-assessment-2026-09-29.md) | `docs/temp/architecture-assessment-2026-09-29.md` | 09-30 纳入实机进展，复现旧 ORM 缺列，收紧 Run 收敛、版本传播与完整验收范围 |
| [09-28 架构评估](./architecture-assessment-2026-09-28.md) | `docs/temp/architecture-assessment-2026-09-28.md` | 新评估按当前代码重核，修正多处过期结论 |
| [09-28 残留工作计划](./remaining-work-2026-09-28.md) | `docs/temp/plans/remaining-work-2026-09-28.md` | WS-A–H 完成/残留映射见新评估 §5 |
| [镜像交付调研](./image-delivery-research-2026-09-29.md) | `docs/temp/image-delivery-research-2026-09-29.md` | 保留历史镜像证据；本轮不重新背书体积、tag 与 registry 状态 |
| [镜像收口与 Lite 合并计划](./deployment-image-consolidation-2026-09-29.md) | `docs/temp/plans/deployment-image-consolidation-2026-09-29.md` | IMG0–IMG12 由新计划 §3 接续；内置 Renderer 为条件候选 |
| [旧测试机执行清单](./test-machine-runbook-2026-09-29.md) | `docs/temp/plans/test-machine-runbook-2026-09-29.md` | 由新计划 M01–M08 替代；原清单也未开跑 |
| [富文本源码范围加固计划](./rich-text-source-range-hardening-plan.md) | `docs/developer/runtime-integration/rich-text-source-range-hardening-plan.md` | 当前 shell 分类、降级与测试源码已存在；下一轮 M08 验证交互 |

以上历史正文保留；仅添加归档说明并调整相对链接。其他历史材料中指向已移动文档的链接同步修复。

## 既有历史评估

| 文档 | 历史主题 |
| :--- | :--- |
| [首轮架构评审](./architecture_review_report.md) | 2026-09-08 架构与质量评审 |
| [09 月架构复核](./architecture-assessment-2026-09.md) | 2026-09-23 对首轮结论的复核 |
| [SQLite 与任务旧合并稿](./architecture-assessment-sqlite-jobs-2026-09.md) | 已拆分的历史稿 |
| [SQLite 专项](./architecture-assessment-sqlite-2026-09.md) | 方言兼容与写路径 |
| [内存运行态专项](./architecture-assessment-memory-2026-09.md) | 进程内状态与 memory 运行态 |
| [09-24 架构评估](./architecture-assessment-2026-09-24.md) | 平台演进阶段判断 |
| [09-25 架构评估](./architecture-assessment-2026-09-25.md) | 后续平台演进复核 |
| [09-25 结构批判](./architecture-assessment-critical-2026-09-25.md) | 量化基线、契约与门禁问题 |
| [09-28 合并评估稿](./architecture-assessment-2026-09-28-merge.md) | 上一轮整理中的历史合并版本 |

## 既有专项、计划与实施记录

| 文档 | 历史主题 / 接续 |
| :--- | :--- |
| [CDP 方案](./cdp.md) | 已作废，由独立 Renderer 路径取代 |
| [问题状态汇总](./docs-temp-issue-status-2026-09.md) | 旧编号与阶段状态，仅供追溯 |
| [SQLite 基线模板](./baseline-sqlite-2026-09.md) | D2 采集模板；真实容量验证由 M03 接续 |
| [Lite memory 适配器](./lite-memory-adapter-2026-09.md) | 适配器实施记录；容量与产物下载仍由新计划验证 |
| [Runtime 多部署计划](./runtime-multi-deployment-scaling-plan-2026-09.md) | T0–T4 历史方案与实施记录；M04/M05 接续联合验收 |
| [多部署落地评审](./review-multi-deployment-e2efe6c-head.md) | 历史 C/M 问题编号与修复背景 |
| [数据库并发原语](./db-concurrency-primitives-2026-09.md) | CP1–CP6 实施记录；不替代 D2 或当前故障验收 |
