# 文档中心

`docs/` 按阅读对象拆分为用户文档和开发文档，图片、示意图和截图占位资源统一放在 `docs/assets/`。

## 用户文档

| 文档 | 内容 |
| :--- | :--- |
| [平台介绍](./user/platform-overview.md) | 面向使用者说明产品定位、核心概念、典型场景和平台组成 |
| [演示文稿创作路径对比](./user/platform-comparison.md) | 对比演示创作产品、PPT skills、OOXML/HTML/图片生成工具与平台化资产沉淀路径 |
| [平台宣传 PPT 大纲](./user/platform-pitch-deck-outline.md) | 面向宣传介绍场景，规划平台介绍 deck 的页面叙事、布局和配图建议 |
| [Demo 使用指南](./user/demo-guide.md) | 公开 Demo 地址、体验账号、推荐流程和 AI 设置注意事项 |
| [用户快速上手](./user/getting-started.md) | 从登录到创建项目、编辑页面、预览和构建的基础流程 |
| [AI 协作创作指南](./user/ai-assisted-creation/README.md) | 说明 AI 侧边栏、工具确认、上下文注入和协作建议 |
| [主题、字体与样式管理体系](./user/design-system-management.md) | 说明主题库、字体注册、样式库、离线包和项目应用边界 |
| [组件管理体系](./user/component-management.md) | 说明组件草稿、发布版本、引用升级、离线包和 AI 协作方式 |
| [资源管理体系](./user/resource-management.md) | 说明资源类型、可编辑内容、替换归档删除、引用检查和字体资源 |
| [当前状态与路线](./user/project-status.md) | 已落地能力、建设中事项和后续方向 |

## 开发文档

| 文档 | 内容 |
| :--- | :--- |
| [平台架构说明](./developer/platform-architecture.md) | 平台目标、模块职责、目标流程和 Runtime 子模块协作 |
| [开发与测试指南](./developer/development-guide.md) | 本地依赖、测试入口、测试数据和运行态维护 |
| [测试治理说明](./developer/testing-strategy.md) | L0-L3 测试分层、目录归属和 CI 策略 |
| [AI Agent 图片处理机制](./developer/ai-agent-image-handling.md) | 智能体视觉图片的上传、工具输出、对象存储、模型水合、历史持久化和排障约束 |
| [生产部署指南](./developer/deployment-guide.md) | compose 部署、外部依赖接入、升级、回滚和运维检查 |
| [CI/CD 与容器部署说明](./developer/deployment-cicd.md) | 平台镜像、Runtime 镜像、Docker Hub 发布和 compose 策略 |

## 图片资源

`docs/assets/` 存放文档配图、截图和占位图。正式截图替换占位图时，优先沿用已有文件名，减少文档链接变更。
