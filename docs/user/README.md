# 用户文档

用户文档面向平台使用者、内容创作者和团队管理员。建议先按“我现在要做什么”选择入口，不必按目录顺序通读。

项目网站：[https://llmxpm.github.io/web-presentation-site/](https://llmxpm.github.io/web-presentation-site/)

## 从这里开始

| 目标 | 首选入口 | 之后可以阅读 |
| :--- | :--- | :--- |
| 先了解平台 | [平台介绍](./platform-overview.md) | [用户快速上手](./getting-started.md) |
| 第一次实际使用 | [用户快速上手](./getting-started.md) | [常用工作流](./workflows/README.md) |
| 直接体验公开环境 | [Demo 使用指南](./demo-guide.md) | [AI 协作创作](./ai/README.md) |
| 部署到自己的环境 | [快速部署](./quick-deployment/README.md) | [生产部署指南](../developer/deployment/README.md) |
| 遇到问题 | [常见问题](./reference/faq.md) | [当前限制](./reference/limits.md) |

## 文档怎么分工

用户文档分为五组，各组关注点不同：

- **平台介绍与概念**：解释平台是什么，以及工作空间、项目、页面和资产之间的关系；不展开具体操作步骤。
- **常用工作流**：按“要完成的任务”给出操作顺序，是日常使用的主线文档。
- **平台特性**：解释 AI 创作、资产复用、预览和交付的价值与能力边界；具体操作以工作流文档为准。
- **AI 协作**：集中说明提示词、上下文、工具确认、会话恢复和不同助手的能力边界。
- **参考资料与部署**：用于查 FAQ、术语、限制和自托管部署，不属于首次创作的必读内容。

## 平台特性（理解能力）

| 文档 | 内容 |
| :--- | :--- |
| [AI 原生创作](./features/ai-native-creation.md) | AI 如何理解项目上下文、调用工具并通过确认机制参与创作 |
| [资产复用](./features/asset-reuse.md) | 资源、组件、主题、字体和样式如何沉淀为团队资产 |
| [预览、构建与交付](./features/preview-build-delivery.md) | Runtime 如何支撑实时预览、截图、构建产物和交付链接 |

## 常用工作流

| 文档 | 内容 |
| :--- | :--- |
| [项目与页面](./workflows/project-and-page.md) | 创建项目、组织页面、编辑源码、管理版本和构建入口 |
| [资源管理](./workflows/resources.md) | 管理图片、图标、字体、DrawIO、Mermaid、图表、公式等素材 |
| [组件管理](./workflows/components.md) | 管理工作空间组件、草稿、发布版本、引用升级和离线包 |
| [主题、字体与样式](./workflows/design-system.md) | 维护主题库、字体注册、样式库和项目应用边界 |
| [AI 协作创作](./workflows/ai-assisted-creation.md) | 把创作任务拆给 AI，并理解确认、上下文和边界 |
| [预览、截图与构建](./workflows/preview-build-export.md) | 使用 Runtime 预览、截图、构建和访问发布产物 |

推荐的实际创作顺序是：

`项目与页面` → `资源管理` → `主题、字体与样式` → `组件管理` → `AI 协作创作` → `预览、截图与构建`

## 部署

| 文档 | 内容 |
| :--- | :--- |
| [快速部署](./quick-deployment/README.md) | Docker、飞牛 fnOS、群晖 Container Manager 的 SQLite 单体快速部署 |
| [生产部署指南](../developer/deployment/README.md) | HTTPS、外部依赖、备份、升级和生产环境配置 |

## 参考资料

| [当前限制](./reference/limits.md) | 已落地能力、建设中事项和使用边界 |
| [常见问题](./reference/faq.md) | 登录、AI 设置、预览、构建、部署入口等常见问题 |
| [术语表](./reference/glossary.md) | 平台核心术语解释 |

## 部署入口

如果你只是体验或小规模自托管，请阅读 [快速部署](./quick-deployment/README.md)。如果要正式上线，再转到 [生产部署指南](../developer/deployment/README.md)，其中包含环境变量、备份恢复和升级回滚文档入口。
