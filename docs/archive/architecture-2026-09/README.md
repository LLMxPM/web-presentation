<!-- 文件功能：架构评估与治理归档索引，说明归档性质、目录结构和引用方式。 -->
# 架构评估与治理归档（2026-09）

本目录归档 2026 年 9-10 月架构评估、部署形态收敛与配置治理的全部历史记录。**文档归档不代表验收完成**；尚未闭环的事项已接续到 [发布检查与待验证事项](../../deployment/release-checklist.md)。

## 目录结构

| 目录 | 内容 |
| :--- | :--- |
| `reports/` | 历史架构评估、旧计划和技术分析报告 |
| `plans/` | 执行计划（部署形态收敛与配置治理工作计划） |
| `runs/` | 各批次验收运行记录与证据 |

## 关键文档

| 文档 | 定位 |
| :--- | :--- |
| [部署形态收敛与配置治理工作计划](./plans/deployment-form-and-config-governance-plan-2026-10-02.md) | 本轮唯一执行计划；B0–B6 全部完成，4 项待验证接续到发布检查 |
| [架构收尾计划（已归档）](./reports/architecture-closeout-plan-2026-10-01.md) | 上一轮 M01–M08 全部关闭的归档记录 |
| [历史评估索引](./reports/README.md) | 历史评估文档清单 |

## 永久契约维护位置

以下契约文档在归档后继续由正式文档目录维护，不在本归档中更新：

- 环境变量三分类：[`docs/developer/architecture/environment-variable-governance.md`](../../developer/architecture/environment-variable-governance.md)
- Lite 规模与隔离决策：[`docs/deployment/operations/lite-scale-and-isolation.md`](../../deployment/operations/lite-scale-and-isolation.md)
- 部署文档：[`docs/deployment/`](../../deployment/README.md)
- 开发协作规范：根目录 `AGENTS.md`

## 引用约定

- 归档文件中的内部链接保持原样（反映归档时的路径结构），不随正式文档目录变化更新。
- 正式文档引用归档内容时使用完整相对路径，如 `../../archive/architecture-2026-09/reports/xxx.md`。
- 归档记录中的失败、修复和运行证据是历史事实记录，不得修改或删除。
