<!-- 文件功能：总结 AI Agent 从 Agno 迁移到 Pydantic AI 后的平台运行态、关键实现、问题修复和后续维护约束。 -->
# AI Agent 框架迁移总结报告

最后更新：2026-06-20

## 1. 结论

本次迁移已经把智能体运行链路切到 **Pydantic AI + 平台自有运行态**。Backend 不再把会话、run、HITL、工具事件和回放状态交给第三方框架或 Redis 管理，而是用 `ai_agent_*` 表作为事实源。

迁移后的核心取舍：

- Pydantic AI 只负责模型调用、工具 schema、工具流事件和 deferred tool 机制。
- 平台负责 session、run、消息、事件、工具调用、HITL、取消、回放、权限和上下文。
- 不保留 Agno 兼容层；旧 run、旧 Redis key 或历史坏数据不作为兼容目标。
- 工具目录继续以 `backend/app/ai/tool_specs.py` 为单一事实源。

## 2. 迁移背景

原有 Agent 相关复杂性主要来自三类耦合：

1. 框架状态与平台状态重复：第三方框架维护一套 run/message/tool 状态，平台又要为 Editor、权限和回放维护一套状态。
2. HITL 状态边界不清：工具确认、用户提问、停止、恢复运行和前端回放混在框架抽象里，难以精确控制。
3. 工具元数据容易漂移：工具实现、工具说明、前端披露、用户配置和运行时 Tool 之间存在多份事实。

迁移判断是：继续修补 Agno 层会让复杂性留在系统核心路径上；切到 Pydantic AI 后，可以把模型框架收敛为执行引擎，把业务状态收敛到平台数据库。

## 3. 当前架构

### Backend 运行链路

关键文件：

- `backend/app/ai/session_facade_pydantic.py`：Editor BFF facade，负责启动 run、继续 paused run、取消 run、图片输入和 SSE 输出。
- `backend/app/ai/pydantic_runner.py`：把 Pydantic AI 事件投影成平台 `AgentRunEvent`。
- `backend/app/ai/pydantic_tools.py`：把平台工具对象包装成 Pydantic AI `Tool`，处理上下文注入和返回值序列化。
- `backend/app/ai/platform_runtime.py`：平台运行态 store，负责 session/run/message/event/tool/requirement 的持久化与快照重建。
- `backend/app/ai/pydantic_model_resolver.py`：把用户模型配置解析为 Pydantic AI 模型对象和运行参数。
- `backend/app/ai/tool_specs.py`：工具目录、风险等级、确认要求、参数示例和工具组的单一事实源。
- `backend/app/scripts/diagnose_ai_run.py`：只读 AI run 诊断 CLI，按 `run_id` 或 `session_id` 输出事件、工具、HITL 和 message history 摘要。

基本流程：

1. Editor 创建或选择 `session_id`。
2. Backend `start_run` 写入 `ai_agent_runs`、用户消息和 `run.started`。
3. `PydanticAgentRunner` 创建 Pydantic AI `Agent`，装配模型、instructions、平台工具和 deps。
4. Pydantic AI 流式事件转成平台事件：
   - `message.delta`
   - `reasoning.delta`
   - `tool.started`
   - `tool.completed`
   - `run.paused`
   - `run.completed`
   - `run.error`
   - `run.cancelled`
5. Editor 通过 SSE 实时消费事件，刷新或重连时从 `ai_agent_run_events` 回放。

### 运行态数据表

核心表：

| 表 | 职责 |
| :--- | :--- |
| `ai_agent_sessions` | Agent 会话和业务 scope |
| `ai_agent_runs` | 单次运行状态、输入、聚合内容、Pydantic AI message history |
| `ai_agent_run_events` | SSE 事件事实源，按 `run_id + event_index` 单调排序 |
| `ai_agent_messages` | 可展示用户/助手消息 |
| `ai_agent_tool_calls` | 可展示工具调用详情 |
| `ai_agent_requirements` | pending/resolved HITL 动作 |
| `ai_agent_member_runs` | 成员助手运行记录 |
| `ai_agent_image_attachments` | 会话图片附件和 run 绑定 |

Redis 仍可用于预览 artifact、截图锁、构建心跳等临时能力，但不再保存 AI run/HITL 事实源。

### AI run 诊断 CLI

排查单次 run 时，优先使用 Backend 只读诊断脚本：

```powershell
uv run --project backend python -m app.scripts.diagnose_ai_run --run-id <run_id> --format summary
uv run --project backend python -m app.scripts.diagnose_ai_run --run-id <run_id> --format json
uv run --project backend python -m app.scripts.diagnose_ai_run --session-id <session_id> --format summary
uv run --project backend python -m app.scripts.diagnose_ai_run --session-id <session_id> --format json --output .tmp/ai-session-diagnostics.json
```

输出内容包括：

- run 基本状态、scope、聚合 content/reasoning 和错误信息。
- `ai_agent_run_events` 事件序列。
- `ai_agent_tool_calls` 工具调用输入、输出和状态。
- `ai_agent_requirements` pending/resolved HITL 状态。
- 可展示消息摘要。
- Pydantic AI `message_history_json` 的数量、消息类型和 part 类型摘要。

`--session-id` 模式会输出会话基本信息、会话消息和该会话下所有 run 的诊断集合。`--output <path>` 会将结果写入 UTF-8 文件，并自动创建父目录；未指定时输出到 stdout。

从根仓运行 CLI 时会自动补读 `backend/.env`；已存在的环境变量优先，不会被 `.env` 覆盖。

脚本只读查询 `ai_agent_*` 表，不修改 run、requirement、tool call、message 或 Redis 状态。`run_id/session_id` 不存在时返回非 0 退出码。历史坏数据修复必须通过单独的一次性维护脚本完成，并明确限定 `run_id/session_id/user_id` 范围。

## 4. HITL 和恢复机制

### 工具确认

写入类工具通过 Pydantic AI deferred approval 暂停。平台保存 `AgentPendingRequirement`，前端展示确认面板。用户确认后，Backend 构造 `DeferredToolResults.approvals` 继续同一个 run。

### ask_user 结构化提问

`ask_user` 现在是强 schema 工具：

- `questions[].question` 是唯一问题文案字段。
- `questions[].options[].label` 是选项显示文本。
- `multi_select` 固定为 `false`。
- 禁止 `title/value` 等额外字段。

用户提交后，Backend 把答案写成 JSON 文本返回给模型：

```text
User feedback received: [{"question": "...", "selected": ["..."]}]
```

前端回放只解析该 JSON 格式，不兼容旧项目符号文本。

### 继续 paused run

继续 paused run 时会：

1. 校验当前 active run 是 `paused`。
2. 校验 pending requirement 的 `tool_call_id` 未过期。
3. 从数据库 requirement payload 合并前端提交的 `tool_execution`。
4. 构造 `DeferredToolResults`。
5. 使用保存的 Pydantic AI message history 继续运行。
6. 如果旧 run 的 message history 为空，则用用户输入和 deferred tool call 重建最小历史，避免 Pydantic AI 报 `Tool call results were provided, but the message history is empty.`

## 5. 迁移期间修复的问题

| 问题 | 根因 | 修复 |
| :--- | :--- | :--- |
| 插入 `ai_agent_messages` 外键失败 | 同批 flush 时消息可能先于 run 写入 | `start_run` 先 flush 父 run，再写用户消息 |
| `SimpleNamespace` 无法序列化 | 平台工具返回值不是 JSON 安全结构 | `_safe_tool_result` 递归处理 namespace、dataclass、Pydantic model、二进制和媒体对象 |
| 停止运行时事件序号冲突 | 流式事件和取消事件并发分配 `event_index` | 追加事件前刷新并锁定 run 游标，取消逻辑做幂等处理 |
| 前端回放按消息类型排序 | 快照从多张表拼装时丢了事件时间线 | Runtime snapshot 优先从 `ai_agent_run_events` 按事件顺序重建 |
| 用户确认后继续运行报空 history | paused run 的 Pydantic AI 历史为空 | 使用输入 payload 和 tool execution 重建最小 deferred 上下文 |
| ask_user 已回答回放异常 | 后端返回项目符号文本，前端只解析 JSON | 后端统一返回 JSON 文本，前端只保留 JSON 契约 |
| ask_user 显示“缺少可展示的问题” | LLM 输出 `title`，后端只认 `question` | `ask_user` 使用强 Pydantic schema，非法参数 fail fast |
| 工具详情 input 为空 | 同一工具先收到空 args，后续完整 args 没覆盖 | 工具事件同步和时间线合并时用后到非空 args 补全 |
| `<think>` / `<reasoning>` 跨分片显示异常 | 前端只用无状态正则解析完整标签 | `agent-stream-reasoning.ts` 为每个 run/member run 维护解析状态，支持跨 delta 标签 |

## 6. 前端状态管理要点

关键文件：

- `editor/src/components/agent/AgentConversationPanel.vue`：会话、SSE、mutation、HITL action 的主容器。
- `editor/src/components/agent/agent-run-state.ts`：运行态事件归一和 timeline 更新。
- `editor/src/components/agent/agent-stream-reasoning.ts`：解析模型正文中夹带的 `<think>` / `<reasoning>` 标签，支持跨 chunk 分片。
- `editor/src/components/agent/agent-conversation-panel.ts`：timeline display items 构造、工具折叠、ask_user 回放解析。
- `editor/src/components/agent/AgentComposer.vue`：普通输入、停止按钮、HITL 面板切换。
- `editor/src/components/agent/AgentChoicePrompt.vue`：ask_user 单选提问交互。
- `editor/src/components/agent/AgentToolConfirmPrompt.vue`：工具确认交互。
- `editor/src/components/agent/agent-hitl-actions.ts`：确认、拒绝、提交回答、取消和强制释放动作。

维护原则：

- 当前 pending ask_user 只在输入区展示，不在时间线重复展示。
- 已回答 ask_user 在时间线中作为 `feedback_request` 展示问题和答案。
- 普通工具可以折叠成工具组，ask_user 不作为普通工具名暴露给用户。
- Timeline 排序以平台事件顺序为准，不按消息类型分组。
- 流式正文中的 `<think>` / `<reasoning>` 只作为 inline reasoning 兼容入口；后端已投影的 `reasoning.delta` 仍是优先事件。
- inline reasoning 解析状态必须绑定到具体 run 或 member run，并在 `run.started`、`model.request.started`、暂停和终态时清理，避免未闭合标签污染后续输出。
- 前端提交 HITL 时必须携带后端 requirement 中的 `tool_execution`，Backend 会以数据库 payload 为准合并。

## 7. 工具体系维护约束

新增或调整工具时，优先改 `backend/app/ai/tool_specs.py` 和实际工具构造函数。

需要同步检查：

- `AgentToolSpec` 中的 label、description、instructions、risk_level、requires_confirmation。
- 工具函数签名和参数类型，优先使用强类型 Pydantic model，不要退回 `dict[str, Any]`。
- 资源工具 `tags` 入参应保持 `list[str] | str | None`，其中 `str` 只用于兼容模型输出 JSON 数组字符串或逗号分隔文本；JSON Schema 中数组项必须明确为 `string`。
- `tools/disclosure.py`、`agent_catalog.py`、`/ai/agent-catalog`、`/ai/agent-configs` 的派生展示。
- Editor 账户 AI 设置页展示的参数 schema、调用示例和返回示例。
- 防漂移测试，确保实际平台工具 key 与规格 key 一致。

## 8. 不兼容点

本次迁移不兼容 Agno 运行态，也不迁移旧 Redis run key。

已知影响：

- 迁移前或中间失败产生的旧 run 可能无法继续。
- 已持久化的坏 `ask_user` requirement 如果 `user_feedback_schema=[]`，不会自动回填。
- 旧格式 ask_user 工具结果不再由前端兼容解析。
- 历史事件中已经写入的空工具 input 不会批量修复；新事件会自动补全。

如果需要清理历史坏数据，应单独写一次性维护脚本，并明确限定 `run_id/session_id/user_id` 范围。

## 9. 验证记录

迁移期间已跑过的关键测试：

```powershell
pnpm run test:backend
```

曾验证全量 Backend：270 passed。

最近针对性验证：

```powershell
uv run --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_pydantic_tool_bridge.py -q --tb=short
uv run --project backend pytest -c backend/pyproject.toml backend/tests/integration/test_ai_agent_config.py -q --tb=short
uv run --project backend pytest -c backend/pyproject.toml backend/tests/integration/test_ai_platform_runtime.py -q --tb=short
pnpm --dir editor test -- agent-conversation-panel.helpers.test.ts
git diff --check
```

当前这些 targeted tests 均通过；`git diff --check` 仅出现仓库既有 CRLF warning。

2026-06-20 高优先级第一阶段补充验证：

```powershell
uv run --project backend pytest -c backend/pyproject.toml backend/tests/unit/test_pydantic_tool_bridge.py backend/tests/integration/test_ai_agent_config.py backend/tests/integration/test_ai_platform_runtime.py backend/tests/integration/test_ai_pydantic_runner_smoke.py -q --tb=short
uv run --project backend pytest -c backend/pyproject.toml backend/tests/integration/test_ai_run_diagnostics.py -q --tb=short
pnpm --dir editor test -- ai.test.ts agent-run-state.test.ts agent-conversation-panel.helpers.test.ts agent-hitl-actions.test.ts
git diff --check
```

覆盖重点：

- Pydantic AI `FunctionModel` 真实框架事件投影。
- `ask_user` 暂停、回答、继续、回放和非法参数 fail fast。
- `DeferredToolResults.calls[tool_call_id]` 恢复 requires-approval 工具结果。
- AI run 诊断 CLI 核心查询函数。
- SSE 多 chunk、多 `data:` 行、命名 event 补齐和非法 JSON fallback。
- 前端 inline reasoning 跨 chunk、正文夹 reasoning、member run reasoning 和 `model.request.started` 状态收敛。
- 工具 schema 防漂移：`ask_user` 禁止额外字段，资源 `tags` 数组项为 string。

## 10. 后续建议

优先级较高：

- 继续压缩 `AgentConversationPanel.vue` 与 `agent-run-state.ts` 的复杂度，把 SSE、snapshot merge、HITL action 分层拆小。
- 对所有 LLM 可调用工具逐步使用强类型参数 model，减少 schema 太松导致的运行时坏数据。
- 后续可增加可选真实 LLM smoke，但应默认关闭并避免进入 CI 必跑路径。

优先级中等：

- 为旧坏 run 提供管理员侧“强制终止/释放”入口和诊断信息。
- 在配置页突出展示工具参数 schema 中的必填字段，降低用户自定义工具说明覆盖后误导模型的概率。
- 增加 run 状态图文档，把 `running/paused/cancelling/completed/cancelled/failed` 的转换条件写清楚。

不建议回头做的事：

- 不恢复 Agno 兼容层。
- 不让 Redis 再承担 AI run 状态事实源。
- 不在前端为多种历史 ask_user 输出格式继续堆兼容分支。
