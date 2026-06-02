<!-- 文件功能：提供 docs 文档中心入口，区分用户文档、开发文档和文档图片资源目录。 -->
# 文档中心

`docs/` 按阅读对象拆分为用户文档和开发文档，图片、示意图和截图占位资源统一放在 `docs/assets/`。

## 用户文档

| 文档 | 内容 |
| :--- | :--- |
| [平台介绍](./user/platform-overview.md) | 面向使用者说明产品定位、核心概念、典型场景和平台组成 |
| [用户快速上手](./user/getting-started.md) | 从登录到创建项目、编辑页面、预览和构建的基础流程 |
| [AI 协作创作指南](./user/ai-assisted-creation.md) | 说明 AI 侧边栏、工具确认、上下文和协作建议 |
| [主题、字体与样式管理体系](./user/design-system-management.md) | 说明主题库、字体注册、样式库、离线包和项目应用边界 |
| [组件管理体系](./user/component-management.md) | 说明组件草稿、发布版本、引用升级、离线包和 AI 协作方式 |
| [资源管理体系](./user/resource-management.md) | 说明资源类型、可编辑内容、替换归档删除、引用检查和字体资源 |
| [当前状态与路线](./user/project-status.md) | 已落地能力、当前限制和后续方向 |

## 开发文档

| 文档 | 内容 |
| :--- | :--- |
| [平台架构说明](./developer/platform-architecture.md) | 平台目标、模块职责、目标流程和 Runtime 子模块协作 |
| [开发与测试指南](./developer/development-guide.md) | 本地依赖、测试入口、测试数据和运行态维护 |
| [测试治理说明](./developer/testing-strategy.md) | L0-L3 测试分层、目录归属和 CI 策略 |
| [生产部署指南](./developer/deployment-guide.md) | compose 部署、外部依赖接入、升级、回滚和运维检查 |
| [CI/CD 与容器部署说明](./developer/deployment-cicd.md) | 平台镜像、Runtime 镜像、Docker Hub 发布和 compose 策略 |

## 图片资源

`docs/assets/` 存放文档配图、截图和占位图。正式截图替换占位图时，优先沿用已有文件名，减少文档链接变更。
