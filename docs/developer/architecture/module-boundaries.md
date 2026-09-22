# 模块边界

模块边界用于判断一次改动应该落在哪里，以及需要联动哪些测试和文档。

## Backend

Backend 是平台控制面，负责用户、权限、工作空间、项目、页面、资源、组件、主题、样式、AI Agent、预览 artifact、构建任务和产物托管。

新增 Python 代码应按 `api/routes`、`schemas`、`models`、`repositories`、`services`、`ai` 等现有分层放置。路由只负责 HTTP 语义和依赖注入，业务规则进入 service，数据库访问进入 repository，接口结构进入 schema。

## Editor

Editor 是创作工作台，负责平台对象管理、代码编辑、AI 侧边栏、预览 iframe 和构建入口。新增前端能力应拆分视图、组件、组合式逻辑、状态和 API 请求层，并优先复用已有 `components/ui`、`components/project`、`components/agent` 组件。

## Runtime

`runtime/` 是演示运行时服务。涉及 Runtime Kit、预览入口、构建产物、镜像或环境变量变化时，要保持与平台接入形态一致。

## Infra

Infra 包括 `deploy/docker/`（Dockerfile、nginx、entrypoints）、`deploy/compose/`、`.github/workflows/` 和测试辅助脚本。生产部署模板只放在 `deploy/compose/`，本地开发与 CI 共享基础服务入口维护在 `scripts/dev/compose.infra.yml`。

## 联动规则

- Backend 接口变化：同步 Editor API 调用、契约测试和必要文档。
- Runtime Kit manifest 变化：同步 Backend 校验、Runtime manifest 测试和根仓契约测试。
- AI 工具规格变化：先改 `backend/app/ai/tool_specs.py`，再同步派生展示和防漂移测试。
- 部署变量变化：同步 `deploy/.env.example`、部署文档和 CI/CD 说明。
