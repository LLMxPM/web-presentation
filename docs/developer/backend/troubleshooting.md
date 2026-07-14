# Backend 排障

## 数据库连接失败

检查 `DATABASE_URL`、数据库网络、账号权限和 Alembic migration。生产环境如果 migration 失败，应先确认平台镜像内是否包含当前数据库 `alembic_version` 指向的 revision 文件。

## Redis 连接失败

Redis 保存预览 artifact 和构建心跳等临时运行态。AI run/HITL 与截图任务租约都不依赖 Redis；截图重复、卡住或恢复问题应优先检查 `page_screenshot_jobs` 的状态、`worker_id`、`lease_expires_at` 和心跳。排查 Redis 时仍需检查 `REDIS_URL`、密码、网络和 `REDIS_KEY_PREFIX`。

## Runtime 调用失败

检查 `RUNTIME_BASE_URL` 是否是 Backend 访问 Runtime 的内网地址，`RUNTIME_PUBLIC_BASE_URL` 是否是浏览器访问地址。生产同域 Gateway 模式下，两者通常不同。

## AI 设置无法解密

`AI_SECRET_ENCRYPTION_KEY` 必须长期保存。更换该值会导致已有用户模型凭证密文无法解密。生产环境不要临时重生成该密钥。

## AI run 行为异常

优先使用只读诊断 CLI 查看 run、事件、消息、工具调用和 requirement 状态。不要直接修改运行态表，除非编写了限定范围的一次性维护脚本。

排查顺序：

1. 用 `--run-id` 查看单次 run 的状态、错误信息和事件序列。
2. 用 `--session-id` 查看会话消息、该会话下所有 run 和当前 active run。
3. 检查 `ai_agent_requirements` 是否存在未处理的 pending requirement。
4. 检查 `ai_agent_tool_calls` 的 input/output 是否完整，是否存在工具返回无法 JSON 序列化的对象。
5. 检查 `message_history_json` 是否为空，尤其是继续 paused run 时报错时。
6. 如果需要看模型供应商请求，临时开启 LLM HTTP trace，并在分享前脱敏。

## AI 工具确认卡住

确认当前 run 是否仍处于 `paused`，pending requirement 的 `tool_call_id` 是否和前端提交一致。前端提交 HITL 时必须携带 Backend requirement 中的 `tool_execution`；Backend 会以数据库 payload 为准合并，避免前端覆盖服务端事实。

如果 requirement 已 resolved 但前端仍显示确认面板，优先检查 Editor 是否正确回放 `ai_agent_run_events`，不要直接重放工具调用。

## AI 继续运行报 message history 为空

继续 paused run 依赖 Pydantic AI message history。正常情况下 Backend 会在 history 为空时重建最小 deferred 上下文。如果仍报 `Tool call results were provided, but the message history is empty.`，需要保存诊断 JSON，检查 run 输入 payload、pending requirement 和 deferred tool call 是否缺失。

历史坏数据不要通过诊断 CLI 修复，应编写限定 `run_id/session_id/user_id` 的一次性维护脚本。

## AI 工具详情 input 为空

同一工具可能先收到空 args，再收到完整 args。平台事件合并时应以后到的非空 args 补全工具详情。排查时同时查看事件序列和 `ai_agent_tool_calls`，确认是展示层回放问题还是持久化数据缺失。

## AI reasoning 显示异常

后端已投影的 `reasoning.delta` 是优先事件。流式正文中的 `<think>` / `<reasoning>` 只作为兼容入口，前端解析状态必须绑定到具体 run 或 member run，并在 `run.started`、`model.request.started`、暂停和终态时清理，避免未闭合标签污染后续输出。

## ask_user 回放失败

`ask_user` 使用结构化 JSON。前端不再兼容旧项目符号文本；如果历史 requirement 缺少结构化字段，应作为历史坏数据处理，不要扩展前端继续兼容旧格式。

## 截图或构建失败

先区分 Backend 任务创建失败、Runtime 执行失败和产物上传失败。常见原因包括页面源码运行错误、资源缺失、Runtime 服务不可达或令牌 audience 配置不一致。
