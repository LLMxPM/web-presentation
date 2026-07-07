# 架构文档

架构文档说明平台目标、模块边界、核心数据模型、预览构建链路、Runtime 接入和权限边界。

## 阅读顺序

| 文档 | 内容 |
| :--- | :--- |
| [平台架构总览](./overview.md) | 平台目标、控制面/数据面关系、模块职责和主流程 |
| [模块边界](./module-boundaries.md) | Backend、Editor、Runtime 和 Infra 的修改边界 |
| [核心数据模型](./data-model.md) | 用户、工作空间、项目、页面、资产、AI 运行态和构建对象 |
| [预览与构建链路](./preview-and-build-flow.md) | 页面预览、组件预览、截图和项目构建流程 |
| [Runtime 接入架构](./runtime-integration.md) | 子模块、Runtime Kit、平台回源和公开契约 |
| [认证与权限](./auth-and-permission.md) | 登录、工作空间隔离、Runtime 令牌和 AI 权限边界 |

## 使用建议

开发跨模块能力前先阅读 [模块边界](./module-boundaries.md)。涉及预览、截图、构建或 Runtime Kit 时，同时阅读 [预览与构建链路](./preview-and-build-flow.md) 和 [Runtime 接入架构](./runtime-integration.md)。
