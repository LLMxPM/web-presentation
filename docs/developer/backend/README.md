# Backend 开发文档

Backend 是平台控制面，负责 API、权限、数据持久化、AI Agent、预览 artifact、构建任务和产物托管。

## 文档导航

| 文档 | 内容 |
| :--- | :--- |
| [API 分层与契约](./api-overview.md) | 路由、schema、service、repository 分层和接口变更规则 |
| [AI Agent 运行态](./ai-agent.md) | 会话、run、HITL、诊断 CLI 和模型 trace |
| [AI 工具规格](./ai-tool-specs.md) | `tool_specs.py` 单一事实源和防漂移要求 |
| [重资源队列与复用运行态](./resource-queues.md) | AI 页面变更、截图、Runtime 与 Chromium 的限流、恢复和排障 |
| [AI Agent 图片处理机制](./ai-image-handling.md) | 图片上传、模型水合、工具输出和历史持久化 |
| [预览 artifact 与构建任务](./preview-artifacts.md) | 预览、截图、构建 snapshot 和产物托管 |
| [Backend 排障](./troubleshooting.md) | 数据库、Redis、Runtime、AI 和截图常见问题 |

## 修改原则

- 路由、模型、仓储和业务逻辑不要写进同一个文件。
- 新增接口前先明确路径、入参、出参、权限和错误语义。
- 涉及页面源码、组件源码和 previewSchema 导入时，必须经过 Backend 边界校验。
- AI 工具目录只以 `backend/app/ai/tool_specs.py` 为单一事实源。
