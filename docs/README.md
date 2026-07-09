# 文档中心

`docs/` 按阅读对象和维护职责拆分为用户文档、开发文档和图片资源。

## 用户文档

| 文档 | 内容 |
| :--- | :--- |
| [项目网站](https://llmxpm.github.io/web-presentation-site/) | 产品介绍、截图、演示入口和面向使用者的说明 |
| [用户文档入口](./user/README.md) | 推荐阅读路径、平台特性、常用工作流、参考资料和部署入口 |
| [平台介绍](./user/platform-overview.md) | 产品定位、核心概念、典型场景和平台组成 |
| [核心概念](./user/concepts.md) | 工作空间、项目、页面、资源、组件、主题、样式和 Runtime |
| [快速上手](./user/getting-started.md) | 从登录到创建项目、编辑页面、预览和构建的基础流程 |
| [Demo 使用指南](./user/demo-guide.md) | 公开 Demo 地址、体验账号、推荐流程和 AI 设置注意事项 |
| [自托管部署](./user/deployment.md) | 开源用户部署选型、SQLite 轻量部署、数据保存和升级建议 |
| [平台特性](./user/features/README.md) | 创作者视角理解 AI 创作、资产复用、预览构建和交付 |
| [AI 协作创作](./user/ai/README.md) | AI 侧边栏、工具确认、上下文注入和协作建议 |
| [项目与页面](./user/workflows/project-and-page.md) | 项目创建、页面组织、源码编辑、版本和构建入口 |
| [资源管理](./user/workflows/resources.md) | 资源类型、可编辑内容、替换归档删除和引用关系 |
| [组件管理](./user/workflows/components.md) | 组件草稿、发布版本、previewSchema、离线包和 AI 协作 |
| [主题、字体与样式](./user/workflows/design-system.md) | 主题库、字体注册、样式库、离线包和项目应用边界 |
| [预览、截图与构建](./user/workflows/preview-build-export.md) | Runtime 预览、截图、构建任务和产物访问 |
| [当前限制](./user/reference/limits.md) | 已落地能力、建设中事项和使用边界 |

## 开发文档

| 文档 | 内容 |
| :--- | :--- |
| [开发文档入口](./developer/README.md) | 架构、Backend、Editor、Runtime 接入、测试、部署和参考资料 |
| [本地开发指南](./developer/getting-started.md) | 本地依赖、启动方式、测试数据和运行态维护 |
| [平台架构总览](./developer/architecture/overview.md) | 平台目标、模块职责、目标流程和 Runtime 子模块协作 |
| [模块边界](./developer/architecture/module-boundaries.md) | Backend、Editor、Runtime 和 Infra 修改边界 |
| [Backend 开发文档](./developer/backend/README.md) | API、AI Agent、工具规格、预览 artifact 和排障 |
| [Editor 开发文档](./developer/editor/README.md) | 前端结构、AI 侧边栏和 Editor 测试 |
| [Runtime 接入文档](./developer/runtime-integration/README.md) | 子模块、Runtime Kit、previewSchema、构建产物和配置模板 |
| [测试文档](./developer/testing/README.md) | 测试分层、命令、契约测试和 E2E smoke |
| [生产部署指南](./developer/deployment/README.md) | compose 部署、环境变量、CI/CD、备份恢复、升级回滚和排障 |
| [参考资料](./developer/reference/conventions.md) | 开发约定、接口契约、环境变量、术语和模板包 |

## 图片资源

`docs/assets/` 存放文档配图、截图和占位图。正式截图替换占位图时，优先沿用已有文件名，减少文档链接变更。
