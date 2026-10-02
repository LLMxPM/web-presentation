# 架构文档

架构文档说明平台目标、Backend/Editor/Runtime/Renderer 边界、核心数据模型、预览与渲染链路和权限边界。

## 阅读顺序

| 文档 | 内容 |
| :--- | :--- |
| [平台架构总览](./overview.md) | 平台目标、控制面/数据面关系、模块职责和主流程 |
| [模块边界](./module-boundaries.md) | Backend、Editor、Runtime、Renderer 和 Infra 的修改边界 |
| [核心数据模型](./data-model.md) | 用户、工作空间、项目、页面、资产、AI 运行态和构建对象 |
| [预览与构建链路](./preview-and-build-flow.md) | 页面预览、组件预览、截图和项目构建流程 |
| [Runtime 接入架构](./runtime-integration.md) | 运行时架构、Runtime Kit、平台回源和公开契约 |
| [认证与权限](./auth-and-permission.md) | 登录、工作空间隔离、Runtime 令牌和 AI 权限边界 |
| [统一任务运行时契约](./task-runtime-contract.md) | Worker/Lease/Attempt/Terminal 角色、字段与状态词汇、错误码族、恢复语义、10 套任务模型映射 |
| [双库方言维护预算](./dialect-budget.md) | 双库固定税口径、重开 D1 的复审触发器、每季粗记账模板 |
| [契约生成与队列观测](./contract-and-queue-observation.md) | API/previewSchema 的生成与生产校验、队列 v2 分层及汇总口径 |
| [环境变量治理与配置 Web UI 迁移](./environment-variable-governance.md) | 环境变量三分类、两种部署形态的必填差异、配置解析优先级与防变砖、热更新边界、密钥自动生成契约与五道防线 |
| [架构计划与验收记录](../../temp/README.md) | 现行唯一执行入口、批次与停止条件、逐门验收状态、历史归档与运行证据 |

## 使用建议

开发跨模块能力前先阅读 [模块边界](./module-boundaries.md)。涉及预览、截图、构建或 Runtime Kit 时，同时阅读 [预览与构建链路](./preview-and-build-flow.md) 和 [Runtime 接入架构](./runtime-integration.md)。

涉及部署模板、环境变量、密钥或新增配置项时，先读 [环境变量治理与配置 Web UI 迁移](./environment-variable-governance.md) 确定该配置属于哪一类、能否热更新、是否必须留在 ENV；批次与验收状态在 [架构计划目录](../../temp/README.md) 维护，本目录不放排期。
