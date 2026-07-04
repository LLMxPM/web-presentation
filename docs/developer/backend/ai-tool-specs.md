# AI 工具规格

`backend/app/ai/tool_specs.py` 是智能体工具目录、工具组、风险级别、确认要求、上下文要求、调用格式与返回示例的单一事实源。

## 维护范围

新增、删除或调整智能体工具时，必须先更新 `tool_specs.py`，再由规格派生：

- `agent_catalog.py`
- `tools/disclosure.py`
- 组件管理工具注册
- `/ai/agent-catalog`
- `/ai/agent-configs`
- Editor 中展示给用户的工具说明和 `agent_guide`

不要在其它文件复制第二份工具清单、工具分组或返回示例。

## 变更要求

工具参数、确认要求、风险级别、上下文要求或返回结构变化时，应同步更新防漂移测试，确保工具 key、运行时 Tool、披露工具组和 `agent_guide` 一致。

## 文案边界

用户可以编辑智能体描述、智能体提示词、工具说明和工具提示词；工具调用契约、参数 JSON Schema 和返回示例是系统只读信息。

## 前端展示

账户 AI 设置页应展示面向 Agent 的完整工具说明，包括当前生效说明、系统默认说明、参数 JSON Schema、调用示例、返回示例、上下文要求与运行时披露组。
