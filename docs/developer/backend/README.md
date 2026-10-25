# Backend 开发文档

Backend 是平台控制面，负责 API、权限、数据持久化、AI Agent、预览 artifact、构建任务和产物托管。

## 文档导航

| 文档 | 内容 |
| :--- | :--- |
| [API 分层与契约](./api-overview.md) | 路由、schema、service、repository 分层和接口变更规则 |
| [放映配置与接口契约](../runtime-integration/slideshow/contract.md) | 项目与路由字段、默认值、继承、快照和写入语义 |
| [AI Agent 运行态](./ai-agent.md) | 会话、run、HITL、诊断 CLI 和模型 trace |
| [AI 模型配置与目录](./ai-model-configuration.md) | 聊天模型、图片模型、Models.dev 目录和协议白名单 |
| [AI 模型能力与推理策略](./ai-model-capabilities.md) | 模型能力档案、三态四档、上下文预算和兼容快照 |
| [AI 凭证密钥轮换与迁移](./ai-secret-rotation.md) | Fernet 密钥机制、安全检查与数据库凭证平滑重密迁移 |
| [AI 工具规格](./ai-tool-specs.md) | `tool_specs.py` 单一事实源和防漂移要求 |
| [重资源队列与复用运行态](./resource-queues.md) | AI 页面变更、截图、Runtime 与 Chromium 的限流、恢复和排障 |
| [运行态存储适配器](./runtime-state-adapter.md) | Redis / `memory://` 契约、Lite 正式适配器边界与禁止事项 |
| [远程渲染服务](./remote-render-service.md) | Renderer 边界、调度、执行契约与修改入口；历史实施方案已归档 |
| [AI Agent 图片处理机制](./ai-image-handling.md) | 图片上传、模型水合、工具输出和历史持久化 |
| [预览 artifact 与构建任务](./preview-artifacts.md) | 预览、截图、构建 snapshot 和产物托管 |
| [文件存储鉴权专题](../projects/file-storage-auth-cache-plan.md) | 文件权限、对象缓存、版本身份与尚待完成的发布验收 |
| [时间存储与展示](./time-handling.md) | UTC 存储、历史无时区值和 Editor 展示规则 |
| [Backend 排障](./troubleshooting.md) | 数据库、Redis、Runtime、AI 和截图常见问题 |

## 修改原则

- 路由、模型、仓储和业务逻辑不要写进同一个文件。
- 新增接口前先明确路径、入参、出参、权限和错误语义。
- 涉及页面源码、组件源码和 previewSchema 导入时，必须经过 Backend 边界校验。
- AI 工具目录只以 `backend/app/ai/tool_specs.py` 为单一事实源。
