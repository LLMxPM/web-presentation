# AI Agent 运行态

AI Agent 由 Backend 统一承载，负责会话、run、消息、事件、工具调用、HITL requirement 和模型调用链路。

## 运行链路

1. Editor 通过 `session_facade_pydantic.py` 发起会话 run、继续 paused run、取消 run 或发送图片输入。
2. Backend 写入 `ai_agent_runs`、用户消息和 `run.started` 事件。
3. `pydantic_runner.py` 创建 Pydantic AI `Agent`，装配模型、instructions、平台工具和 deps。
4. `pydantic_tools.py` 把平台工具对象包装为 Pydantic AI Tool，并负责上下文注入和返回值序列化。
5. `platform_runtime.py` 把模型流式事件、工具事件、HITL requirement 和终态事件持久化为平台运行态。
6. Editor 通过 SSE 实时消费事件；刷新或重连时，从 `ai_agent_run_events` 按事件顺序回放。

## 事实源

AI 会话、run、事件、消息、工具调用和 HITL 状态写入 Backend 主库 `ai_agent_*` 表。Redis 不保存 AI run/HITL 事实源，只保留预览、截图和构建等临时运行态。

| 表 | 作用 |
| :--- | :--- |
| `ai_agent_sessions` | 会话主记录 |
| `ai_agent_runs` | 单次运行状态、输入、聚合内容、错误信息和 Pydantic AI message history |
| `ai_agent_messages` | 会话消息 |
| `ai_agent_run_events` | SSE 事件事实源，按 `run_id + event_index` 单调排序 |
| `ai_agent_tool_calls` | 可展示工具调用详情 |
| `ai_agent_requirements` | pending/resolved HITL 动作 |
| `ai_agent_member_runs` | 成员助手运行记录 |
| `ai_agent_image_attachments` | 会话图片附件和 run 绑定 |

## 工具确认

写入、删除、发布、构建等高风险工具调用需要用户确认。确认要求、风险级别、上下文要求和返回示例必须来自 `backend/app/ai/tool_specs.py`。

工具确认会通过 Pydantic AI deferred approval 暂停 run。平台保存 `AgentPendingRequirement`，前端展示确认面板；用户确认后，Backend 构造 deferred tool 结果继续同一个 run。

继续 paused run 时需要满足这些条件：

1. 当前 active run 状态是 `paused`。
2. pending requirement 的 `tool_call_id` 未过期。
3. Backend 以数据库 requirement payload 为准，合并前端提交的 `tool_execution`。
4. 如果旧 run 的 message history 为空，Backend 会使用输入 payload 和 deferred tool call 重建最小上下文，避免继续运行时报空 history。

`ask_user` 是结构化提问工具，前端回放只解析结构化 JSON 格式。不要再依赖旧的项目符号文本格式。

## 诊断 CLI

排查 AI run 时使用只读诊断 CLI：

```powershell
uv run --project backend python -m app.scripts.diagnose_ai_run --run-id <run_id> --format summary
uv run --project backend python -m app.scripts.diagnose_ai_run --run-id <run_id> --format json
uv run --project backend python -m app.scripts.diagnose_ai_run --session-id <session_id> --format summary
uv run --project backend python -m app.scripts.diagnose_ai_run --session-id <session_id> --format json --output .tmp/ai-session-diagnostics.json
```

诊断输出包含：

- run 基本状态、scope、聚合 content/reasoning 和错误信息。
- `ai_agent_run_events` 事件序列。
- `ai_agent_tool_calls` 工具调用输入、输出和状态。
- `ai_agent_requirements` pending/resolved HITL 状态。
- 会话消息摘要。
- Pydantic AI `message_history_json` 的消息数量、消息类型和 part 类型摘要。

`--session-id` 模式会输出会话基本信息、会话消息和该会话下所有 run 的诊断集合。`--output <path>` 会将结果写入 UTF-8 文件，并自动创建父目录；未指定时输出到 stdout。

从根仓运行 CLI 时会自动补读 `backend/.env`；已存在的环境变量优先，不会被 `.env` 覆盖。

诊断 CLI 只能只读查询 `ai_agent_*` 表，不得修改 run、requirement、tool call、message 或 Redis 状态。`run_id/session_id` 不存在时应返回非 0 退出码。历史坏数据修复必须通过单独的一次性维护脚本完成，并明确限定 `run_id/session_id/user_id` 范围。

## LLM HTTP trace

本地需要查看模型供应商请求时，可临时开启：

```env
AI_LLM_HTTP_TRACE_ENABLED=true
AI_LLM_HTTP_TRACE_DIR=.tmp/llm-http-trace
AI_LLM_HTTP_TRACE_BODY_MAX_BYTES=200000
```

trace 文件可能包含用户输入、页面源码或业务敏感内容，提交复现材料前必须检查和脱敏。
