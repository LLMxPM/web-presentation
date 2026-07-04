# 接口契约索引

本文档索引需要跨模块同步维护的接口契约。具体 API 细节以 Backend schema、Runtime 文档和契约测试为准。

## Editor 与 Backend

- 登录、会话和用户信息。
- 工作空间、项目、页面 CRUD。
- 资源、组件、主题、样式和字体注册。
- AI 会话、工具披露、工具确认和账户 AI 设置。
- 构建任务、截图和预览状态。

## Runtime 与 Backend

- 预览上下文读取。
- 资源和配置包读取。
- build snapshot 拉取。
- 构建产物上传。
- JWKS、预览令牌、构建令牌和诊断令牌校验。

## AI 工具体系

- `/ai/agent-catalog`
- `/ai/agent-configs`
- 工具说明、参数 JSON Schema、调用示例和返回示例。

## 测试入口

跨模块契约变化时，优先补充或更新 `tests/contracts/`，再根据影响范围补 Backend、Editor、Runtime 或 E2E 测试。
