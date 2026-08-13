# AI 模型配置与目录

聊天模型和图片生成是两个独立数据域。聊天模型使用 `ai_chat_provider_configs`、`ai_chat_model_configs` 和 `ai_chat_slot_bindings`；图片生成使用对应的 `ai_image_*` 表，图片任务只引用图片模型配置。

Backend 每 24 小时从 `https://models.dev/api.json` 拉取目录，经过大小限制、Schema 校验和协议白名单后，原子写入 `ai_chat_provider_catalog` 与 `ai_chat_model_catalog`。同步失败保留上一版，下架项标记为非当前但不删除用户配置。管理员可调用 `POST /ai/model-catalog-sync` 手工刷新；空库先载入最小启动目录。

Models.dev 只提供身份和能力事实，不决定 SDK。服务端把目录记录映射到固定 `protocol_key`，当前不支持的 Anthropic、Bedrock 等记录不会暴露。OpenAI 使用 Pydantic AI 的 `OpenAIChatModel`，不会切换到 Responses API。自定义供应商固定为 `openai_compatible_chat` 且 Base URL 必填。

升级迁移会一次性清空旧 AI 运行态和混合模型配置。需要在迁移后再次清理测试或异常恢复数据时，应先停止 AI 后台任务，再显式执行：

```powershell
uv run --project backend python -m app.scripts.reset_ai_model_configuration --confirm RESET_AI_CONFIGURATION
```

该命令保留用户、工作空间、项目、页面、资源、Models.dev 目录缓存和已经生成的图片文件。

模型能力按“用户覆盖、当前目录、保守默认”合并。助手槽位只保存模型绑定，不保存推理或 token 策略。输入预算直接采用模型目录的 input limit；输出预算统一封顶 32,768 tokens，并继续服从模型更小的 output limit。推理策略在发起每个 Run 时以当前模型的 Models.dev `reasoning_options` 为事实源，并写入不可变 Run 快照；通用 OpenAI-compatible 连接可转换目录明确声明的标准 `effort`，toggle 和 token budget 等供应商方言仍要求固定转换器。目录后续更新不改变已经开始或完成的 Run。

本次拆表迁移会清理旧模型配置、绑定、AI 会话和持久化 AI 任务，不迁移历史记录；用户、工作空间、项目、页面、资源和已生成文件不受影响。
