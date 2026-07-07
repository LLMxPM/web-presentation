# 用户文档

用户文档面向平台使用者、内容创作者和团队管理员，说明如何理解平台、完成创作流程、管理可复用资产，并在需要时跳转到部署与运维文档。

## 推荐阅读路径

| 顺序 | 文档 | 适合场景 |
| :--- | :--- | :--- |
| 1 | [平台介绍](./platform-overview.md) | 先理解 `web-presentation` 解决什么问题 |
| 2 | [核心概念](./concepts.md) | 理解工作空间、项目、页面、资源、组件、主题和样式的关系 |
| 3 | [快速上手](./getting-started.md) | 从登录到创建页面、预览和构建的完整流程 |
| 4 | [Demo 使用指南](./demo-guide.md) | 体验公开 Demo 或准备演示流程 |
| 5 | [AI 协作创作](./ai/README.md) | 使用 AI 侧边栏、工具确认和上下文注入 |

## 常用工作流

| 文档 | 内容 |
| :--- | :--- |
| [项目与页面](./workflows/project-and-page.md) | 创建项目、组织页面、编辑源码、管理版本和构建入口 |
| [资源管理](./workflows/resources.md) | 管理图片、图标、字体、DrawIO、Mermaid、图表、公式等素材 |
| [组件管理](./workflows/components.md) | 管理工作空间组件、草稿、发布版本、引用升级和离线包 |
| [主题、字体与样式](./workflows/design-system.md) | 维护主题库、字体注册、样式库和项目应用边界 |
| [AI 协作创作](./workflows/ai-assisted-creation.md) | 把创作任务拆给 AI，并理解确认、上下文和边界 |
| [预览、截图与构建](./workflows/preview-build-export.md) | 使用 Runtime 预览、截图、构建和访问发布产物 |

## 参考资料

| 文档 | 内容 |
| :--- | :--- |
| [演示文稿创作路径对比](./platform-comparison.md) | 对比传统 PPT、AI PPT、PPT skills 和平台化创作路径 |
| [当前限制](./reference/limits.md) | 已落地能力、建设中事项和使用边界 |
| [常见问题](./reference/faq.md) | 登录、AI 设置、预览、构建、部署入口等常见问题 |
| [术语表](./reference/glossary.md) | 平台核心术语解释 |

## 部署入口

如果你需要自己部署平台，直接阅读 [部署文档入口](../developer/deployment/README.md)。试用单机部署优先看 [Compose 部署说明](../developer/deployment/compose.md)，生产环境上线前需要同时确认 [部署环境变量](../developer/deployment/env-vars.md)、[备份与恢复](../developer/deployment/backup-restore.md) 和 [升级与回滚](../developer/deployment/upgrade-rollback.md)。
