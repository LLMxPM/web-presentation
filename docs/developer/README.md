# 开发文档

开发文档面向平台维护者、功能开发者和部署人员。文档按架构、Backend、Editor、Runtime 开发、跨服务接入、测试、部署和参考资料分组。独立 Chromium 服务的运行说明由 Renderer 自身维护。

外部 Agent 接入代码（CLI、MCP Server、共享 API Client 和 Skill）位于同级独立仓库 `web-presentation-agent-kit`；本目录维护平台侧 External API v1 契约和集成规划。

## 快速入口

| 文档 | 内容 |
| :--- | :--- |
| [本地开发指南](./getting-started.md) | 本地依赖、四个应用服务启动和常用诊断命令 |
| [平台架构总览](./architecture/overview.md) | 平台目标、控制面/数据面关系、模块职责和主流程 |
| [模块边界](./architecture/module-boundaries.md) | Backend、Editor、Runtime、Renderer、Infra 的修改边界 |
| [测试文档入口](./testing/README.md) | 根仓、Backend、Editor、Runtime、契约和 E2E 测试入口 |
| [部署文档入口](./deployment/README.md) | Compose 部署、环境变量、备份恢复、升级回滚和排障 |
| [External Agent API v1 契约](./reference/external-agent-api.md) | CLI、MCP 和其他外部 Agent 共用的 Backend API、Scope、任务和交付契约 |
| [CLI 主仓集成边界](./cli.md) | 主仓负责的 CLI 外部 API 契约和 agent-kit 交接边界 |
| [MCP 主仓集成边界](./mcp.md) | 主仓负责的 MCP External API 依赖和 agent-kit 交接边界 |
| [大文件与媒体资产管理](./large-files.md) | Git LFS 规则、媒体文件提交检查和历史迁移约束 |

## 分组导航

| 分组 | 内容 |
| :--- | :--- |
| [架构](./architecture/overview.md) | 模块职责、数据模型、预览构建链路、Runtime 接入和权限 |
| [Backend](./backend/README.md) | API 分层、AI Agent、工具规格、预览 artifact 和排障 |
| [Renderer](../../renderer/README.md) | 独立 Chromium 服务、包边界、配置和真实截图验证 |
| [Editor](./editor/README.md) | 前端结构、AI 侧边栏、状态管理和测试约定 |
| [Runtime 开发](./runtime/README.md) | 页面、组件、Runtime Kit 与 Runtime 内部接入细节 |
| [Runtime 接入](./runtime-integration/README.md) | 运行时架构、Runtime Kit manifest、previewSchema、构建产物和配置模板 |
| [测试](./testing/README.md) | 测试分层、命令、契约测试和 E2E smoke |
| [部署](./deployment/README.md) | Compose 模板、生产环境变量、CI/CD、备份、回滚和排障 |
| [External Agent API](./reference/external-agent-api.md) | 外部 Agent 共用的 Backend 契约和变更流程 |
| [CLI](./cli.md) | CLI 主仓集成边界；具体命令实现由 agent-kit 维护 |
| [MCP](./mcp.md) | MCP 主仓集成边界；具体协议适配由 agent-kit 维护 |
| [参考资料](./reference/conventions.md) | 编码约定、接口契约索引、环境变量索引、术语和模板包 |

## 维护原则

- 用户理解路径更新时，优先同步 `docs/user/`。
- 开发边界、接口契约、测试入口或部署方式变化时，优先同步本目录。
- 本地启动命令以[本地开发指南](./getting-started.md)为入口，测试命令以根目录 `package.json` 和[测试命令](./testing/commands.md)为准，部署服务以 `deploy/compose/` 为准。
- Runtime 页面与组件能力更新时维护[Runtime 开发文档](./runtime/README.md)；跨服务协议变化时同步[Runtime 接入文档](./runtime-integration/README.md)和模块 README。
- 阶段性设计记录应标明当前状态；可执行步骤优先写入对应专题文档，避免与历史方案混用。
