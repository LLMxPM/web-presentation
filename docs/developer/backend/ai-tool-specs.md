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

## 内容助手固定工具

平台只登记一个内容助手，并以工作空间为会话边界。它固定装配 `get_operation_guide`、通用查询、创建、修改、校验、归档和生命周期命令工具，以及提问、视觉、图片生成和 `delegate_task_to_self` 等特殊工具。项目路由、展示配置和样式应用统一由 `update_entity` 承载，不再登记危险动作工具。自委派不接收成员 ID，子运行复用同一个助手模型与权限且不再递归委派。

`get_operation_guide` 只是模型的普通只读操作手册。省略 `operation_key` 时返回紧凑索引，传入 `page.update.content` 等稳定操作键时返回精确参数 Schema。返回结果自然进入消息历史，不生成令牌、授权记录、契约快照或执行前置状态。模型未先查询手册时，写工具仍应按照真实业务 Schema 正常校验；参数错误必须返回明确校验信息，供模型查询手册后重试。

`AgentOperationGuideSpec` 同时登记稳定操作键、逻辑资源、操作、精确参数 Schema、处理工具 key、前端 mutation 类型、风险、确认、限制和示例。运行时通用工具只常驻合法对象、mode/action 的判别式顶层 Schema，复杂 `filters`、`payload` 和 `options` 由操作手册按需披露。`create_entity` 使用 `new/copy/upload` 区分普通创建、复制和可信附件创建；`validate_entity` 只执行页面/组件检查和资源差异预览，不产生 mutation；`execute_action` 只承载发布等生命周期命令。项目与样式共享 presentation 和 suggested components 配置结构，并通过 `get_entity.configuration` 返回同构快照；项目可通过 `apply_style` 复制完整独立快照。主题 key 和样式 key 只在创建时指定，已有对象不开放 key 修改。

通用返回 envelope 使用 `effect=read|create|update|lifecycle` 表达真实效果。创建返回新对象 `target`，复制额外返回 `source`；只读查询和校验返回 `mutation=null`。代码或布局校验不通过属于正常校验结果，工具调用仍返回 `success=true`，具体结果通过 `data.valid=false` 和 diagnostics 表达。

归档是内容助手唯一的移除能力：单项直接执行，批量在运行时动态请求确认；整批先校验后写入，限制为同类型、同工作空间、去重后最多 100 项。归档不使用版本参数，工作空间和项目不能归档；归档对象退出 AI 查询与操作边界，内容助手不开放恢复能力。永久删除接口不得注册为 AI 工具，也不得由普通 action 间接分派；工作空间 `default` 样式作为项目默认初始化来源，不允许归档。

## 变更要求

工具参数、确认要求、风险级别、上下文要求或返回结构变化时，应同步更新防漂移测试，确保工具 key、运行时 Tool、披露工具组和 `agent_guide` 一致。

## 文案边界

用户可以编辑智能体描述、智能体提示词、工具说明和工具提示词；工具调用契约、参数 JSON Schema 和返回示例是系统只读信息。

## 前端展示

账户 AI 设置页应展示面向 Agent 的完整工具说明，包括当前生效说明、系统默认说明、参数 JSON Schema、调用示例、返回示例、上下文要求与运行时披露组。
