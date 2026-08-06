# API 分层与契约

Backend API 应保持清晰分层，避免接口语义、数据库访问和业务规则混在一起。

## 分层职责

- `api/routes`：HTTP 路由、依赖注入、状态码和错误响应。
- `schemas`：请求、响应和业务 DTO。
- `models`：数据库模型。
- `repositories`：数据库查询和持久化操作。
- `services`：业务流程、权限校验、跨仓储编排和外部服务调用。
- `ai`：AI Agent、工具规格、上下文构造和运行态。

## 接口变更流程

1. 定义路径、方法、权限和错误语义。
2. 定义请求和响应 schema。
3. 明确是否影响 Editor、Runtime 或 AI 工具。
4. 补充 Backend 测试和跨模块契约测试。
5. 更新相关开发文档和用户文档。

## 错误语义

接口应区分未登录、无权限、对象不存在、参数错误、状态冲突和下游服务失败。不要把所有失败都压成通用 `400` 或 `500`。

## 跨模块契约

Editor 调用的 API、Runtime 回源 API、构建产物 API 和 AI 工具披露 API 都属于跨模块契约。路径或返回结构变化时，应同步更新调用方和 `tests/contracts/`。

## 项目与样式配置写入

项目是独立的样式配置快照，工作空间样式是可复用模板；二者共享 `presentation` 与 `suggested_components.component_ids` 结构，但继续写入各自扁平展示列和建议组件关联表。应用样式时 Backend 在同一事务复制展示配置与有效已发布组件，不建立继承关系。

- 项目创建的 `configuration.mode` 支持 `default`、`style`、`custom`；未传时使用工作空间 `key=default` 样式。
- 项目更新使用 `configuration.mode=patch` 部分修改，或使用 `mode=style` 完整应用样式快照。
- 样式创建一次提交完整 `configuration`；样式更新通过配置 Patch 与建议组件完整替换完成。
- `theme_config_yaml` 只保留给历史项目、模板包与 Runtime 内部兼容，不属于普通写入契约。
- 项目和样式建议组件的独立 PUT 写入口已删除，GET 管理查询仍保留。
- 工作空间 `default` 样式允许修改配置，但 key 不可修改，也不可删除或归档。
