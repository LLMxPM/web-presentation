# 开发文档

本目录面向维护 `web-presentation` 的开发者。先根据任务找到当前生效的模块边界、契约和操作指南；阶段计划、工作包与历史验收有独立入口，不作为现行实现的唯一依据。

## 从哪里开始

| 要做的事 | 入口 |
| :--- | :--- |
| 准备本地环境 | [本地开发指南](./getting-started.md)、[测试文档](./testing/README.md)；服务通常已运行，先按 `dev-start-test` 探测 |
| 理解系统边界 | [架构总览](./architecture/README.md)、[模块边界](./architecture/module-boundaries.md) |
| 修改 Backend | [Backend 开发文档](./backend/README.md)、[API 契约索引](./reference/README.md) |
| 修改 Editor | [Editor 开发文档](./editor/README.md)、[项目级设计规范](../../DESIGN.md) |
| 修改 Runtime 或页面 | [Runtime 开发文档](./runtime/README.md)、[Runtime 接入契约](./runtime-integration/README.md) |
| 修改 Renderer | [Renderer 开发说明](../../renderer/README.md)、[远程渲染契约](./backend/remote-render-service.md) |
| 修改 CLI 依赖的服务端接口 | [External API v1](./reference/external-agent-api.md)、[CLI 主仓边界](./cli.md) |
| 部署或发布 | [部署文档](../deployment/README.md)、[发布检查清单](../deployment/release-checklist.md) |

## 按功能查现行文档

| 功能 | 入口 |
| :--- | :--- |
| 放映配置、媒体和演讲者模式 | [放映接入](./runtime-integration/slideshow/README.md)、[字段契约](./runtime-integration/slideshow/contract.md) |
| 音频资源、旁白与 cue | [音频接入](./runtime-integration/audio/README.md)、[字段契约](./runtime-integration/audio/contract.md) |
| 页面源码、Runtime Kit 和预览 | [Runtime 接入](./runtime-integration/README.md)、[预览源站与 artifact](./runtime-integration/preview/README.md)、[Runtime Kit 契约](./runtime-integration/runtime-kit-contract.md) |
| 页面与组件校验 | [组件源码校验](./runtime-integration/component-code-check.md)、[页面可视化编辑契约](./runtime-integration/page-visual-edit.md) |
| 工作空间资源与三维模型 | [资源 API](./reference/api-contracts.md)、[Runtime 资源引用](./runtime/integration/asset-usage-guide.md) |

## 专题工作与历史证据

- [进行中的专题工作](./projects/README.md)：尚有实施、验收或发布收尾的计划与工作包。
- [开发专题过程归档](../archive/developer-work-2026-10/README.md)：已结束的实施计划、审查和联合验收。
- [架构治理归档](../archive/architecture-2026-09/README.md)：2026 年 9–10 月架构评估与运行证据。

## 维护规则

- 开发者需要据以修改代码的字段、边界和操作步骤，保留在模块文档或契约中；实施过程写入 `projects/`。
- 阶段完成时，将仍有效的结论写回现行文档，过程记录移至 `docs/archive/`，并更新所有仓内链接。
- 用户理解路径写入 `docs/user/`，部署事项写入 `docs/deployment/`，测试选择和环境排障优先维护 `.agents/skills/dev-start-test/`。
- MCP 整体不在当前交付范围；本仓只维护它依赖的 External API 契约和边界说明。
