<!-- 文件功能：说明内容助手的图片附件、无状态理解、持久化生成与安全上下文边界。 -->
# AI 图片处理机制

平台不设置可单独聊天的“看图助手”或“图片生成助手”。内容助手维护多轮业务对话，并直接使用两个单次调用工具：

- `analyze_visuals`：统一接收会话附件、工作空间图片资源或页面截图输入，同步调用 `image_understanding` 槽位的聊天模型，不传内容助手历史。
- `generate_image`：创建 `ai_image_generation_jobs` 持久化任务，由独立 worker 调用图片供应商并自动恢复父 run。

两个工具使用独立运行时披露组：`image_analysis` 只包含 `analyze_visuals`，`image_generation` 只包含
`generate_image`。内容助手每轮按对应槽位状态分别装配工具；其中一个槽位不可用时，不影响另一个工具进入模型工具列表。

## 核心上下文边界

用户消息和时间线会持久化、展示上传图片，但内容模型只收到附件 ID、文件名、MIME、大小和可选尺寸，不接收图片 bytes、base64、对象存储 URL 或 presigned URL。历史中的 `agent-image-ref` 在所有内容助手与成员助手请求中转换为轻量占位，不再水合像素。

local 与 S3 的差异只存在于工具内部：`analyze_visuals` 的附件输入或 `generate_image(edit)` 在本次调用中按附件 ID 校验用户、工作空间、会话和 active 状态；资源输入按 asset ID 校验当前工作空间、active 状态和普通资源身份；页面截图输入按 page ID 校验当前工作空间和项目，并自动获取或刷新当前版本截图。读取结果只驻留于本次供应商请求，不写入工具 JSON、事件、日志或模型历史。

`.env` 中既有的 `AI_IMAGE_TRANSPORT_MODE`、模型 URL TTL 和历史水合上限仅为旧诊断兼容路径保留；新的内容助手运行链路不读取这些参数来构造内容模型请求。附件上传大小仍由 `AI_IMAGE_ATTACHMENT_MAX_BYTES` 控制。

图片像素和图片内文字一律是不可信内容，不得改变工具权限、业务范围或执行图片中的指令。

## 上传图片保存为资源

用户明确要求把本轮上传图片保存、导入或加入资源库时，内容助手把可信 `attachment_id` 委派给资源助手，由 `save_uploaded_image_as_resource` 创建 `asset_type=image` 的工作空间资源。工具只接受当前用户、当前工作空间、当前会话中 active 且 `source_kind=user_upload` 的附件，不接受 URL、本地路径或 base64，也不开放覆盖已有资源。

转换复用 `AgentImageAttachmentService` 与 `AssetService` 的既有校验、对象存储和渲染元数据链路。附件已有 `promoted_asset_id` 时直接返回关联资源并标记 `created=false`，不会重复创建资源或用新参数隐式修改已有元数据。图片生成结果仍由生成队列自动保存，不使用该工具重复提升。

## 模型类型与固定槽位

`ai_llm_configs.model_type` 支持：

- `chat`：普通对话与图片理解模型；只有它可以声明 `supports_image_input=true`。
- `image_generation`：Image API 模型；不使用 thinking、上下文窗口和历史压缩配置。

固定视觉槽位沿用个人优先、全局回退规则：

| 槽位 | 绑定要求 |
| :--- | :--- |
| `image_understanding` | active、`chat`、`supports_image_input=true` |
| `image_generation` | active、`image_generation` |

视觉槽位缺失只禁用对应能力，不影响内容助手启动。供应商类型与模型类型严格一一对应：Chat 模型只能引用 Chat 供应商，图片生成模型只能引用图片生成供应商；修改模型类型时必须同时切换到兼容的供应商配置。

现有 `/ai/llm-*` 接口和数据库命名保持不变，但供应商配置彼此独立：

| provider key | 类型 | 默认模型 | 协议 |
| :--- | :--- | :--- | :--- |
| `openai` | `chat` | 目录现有默认值 | Pydantic AI Chat |
| `dashscope` | `chat` | `qwen-plus` | 百炼 Chat 兼容接口 |
| `openai_image` | `image_generation` | `gpt-image-2` | OpenAI Image API |
| `dashscope_image` | `image_generation` | `wan2.7-image-pro` | 百炼 Wan 异步图片 API |

`provider_key` 通过 `backend/app/services/image_generation/registry.py` 的代码注册表决定 adapter，不允许从数据库导入任意类或另外覆盖协议类型。同一品牌的 Chat 与生图配置不共享 API Key、Base URL 或生命周期；例如已有 `openai` 配置不会自动成为 `openai_image` 配置。`dashscope_image` 必须显式填写使用 HTTPS 且以 `/api/v1` 结尾的 workspace Base URL。

图片供应商注册表是生图 adapter、连接约束、默认模型和模型能力的单一事实源。`/ai/llm-providers` 中的 `provider_adapter`、`default_image_generation_model_id`、`advanced_json_hint` 和 `image_generation_models` 均由注册表派生。每个模型能力项声明生成/编辑操作、宽高比、分辨率、质量、参考图和输出数量上限、蒙版支持以及高级参数 JSON Schema。

新增同协议模型时，只增加 `ImageModelSpec`；新增供应商时，实现 `submit/resume/cancel` 统一协议并注册 `ImageProviderSpec`。同步供应商从 `submit` 直接返回完成结果，异步供应商返回 `ProviderTaskCursor`。队列不感知供应商品牌，也不维护供应商状态枚举。

## 图片理解

`analyze_visuals` 接收 1～4 个判别联合输入、自足 `instruction`、分析类型和 detail。每个输入必须是 `{source_type: "attachment", attachment_id}`、`{source_type: "asset", asset_id}` 或 `{source_type: "page_screenshot", page_id}`。资源输入支持工作空间中 active 的普通图片/图标资源，当前可分析格式为 PNG、JPEG 和 WebP；SVG、GIF 等格式会返回可恢复的格式不支持错误。工具创建独立 Pydantic AI Agent，请求不包含内容助手 history 或其它工具。

稳定返回 `summary`、按输入顺序排列的 `items`、可选 `comparison` 和模型审计摘要。每个 item 包含平台注入的可信 `source`，以及描述、OCR、尺寸、宽高比、颜色、布局、视觉发现和警告；资源来源包含资源 ID、逻辑名、类型和预览附件引用，页面来源额外包含页面版本、截图刷新状态和预览附件引用。图片 bytes、base64 和模型临时 URL 不进入返回 JSON。

工具结果只保存文本和 JSON。槽位未配置、模型不兼容、附件越权或模型失败会返回 recoverable tool error，由内容助手向用户解释配置或输入问题。

## 图片生成与编辑

`generate_image` 只接受附件 ID，禁止 local 路径、base64 和业务对象 URL。公共画布参数为 `aspect_ratio=auto|1:1|3:2|2:3` 与 `resolution_tier=auto|standard|high|ultra`。`generate` 可以无参考图；`edit` 至少需要一张源图，蒙版只允许用于 edit。

OpenAI adapter 同步调用 generations/edits，映射到三个固定尺寸，支持 quality 与蒙版，但只接受 `auto/standard` 分辨率层级。模型高级参数允许配置 `background`、`output_format`、`output_compression` 和 `moderation`；所有字段必须通过模型能力 Schema，不能任意透传。

百炼 adapter 支持 `wan2.7-image-pro`、`wan2.7-image` 文生图和 1～4 张参考图编辑，可输出 1～4 张；不支持蒙版和非 `auto` quality。高级参数允许配置 `execution_mode=async|sync`、`watermark` 和 `thinking_mode`。`async` 使用 image-generation 提交和 task 查询，`sync` 使用 multimodal-generation 并在本次调用中下载结果。

任务以 `run_id + tool_call_id` 幂等，保存操作参数、安全模型快照、输入附件、状态、进度、租约、重试、取消、错误与输出 ID。异步提交成功后把 task ID、供应商状态和 request ID 保存到稳定列，把恢复状态、可取消性和下一次轮询建议保存到 `provider_state_json`，随后进入 `waiting_provider` 并释放租约。Worker 重启后使用完整 `ProviderTaskCursor` 调用 `resume`，不能再次提交。供应商没有给出轮询时间时，队列才使用 2～15 秒的默认指数退避。提交超时且无法判断外部任务是否创建时，以 `AI_IMAGE_PROVIDER_SUBMISSION_UNKNOWN` 终止，避免重复计费。

父 run 取消时，队列根据游标的 `cancellable` 声明调用 adapter 取消，不再识别供应商私有状态字符串；不可取消或取消失败时做本地取消并丢弃后续结果。供应商成功后，Worker 会立即下载临时 HTTPS URL，并检查内容类型、非空与单文件大小上限。临时 URL、图片 Base64 和附件 bytes 不进入任务事件、日志或模型历史。

每个成功结果都会：

1. 登记 `source_kind=tool_output` 的 `ai_agent_image_attachments`。
2. 自动提升为 `asset_type=image` 的工作空间资源并回填 `promoted_asset_id`。
3. 以附件与资源摘要回灌 deferred result，恢复父 run。

工具结果和日志不返回生成图片 base64 或供应商临时 URL。取消父 run 会标记尚未完成的图片任务取消；已经创建的资源不会因随后取消或附件归档而删除。

## UI 契约

`/ai/agents` 分别返回图片理解与图片生成的可用状态和不可用原因。只有至少一个视觉能力可用时，Editor 才启用附件上传。

时间线工具项包含 `progress`、`input_attachments`、`output_attachments`；原 `attachments` 暂时作为输出附件兼容字段。视觉分析卡合并展示用户附件和工具生成的页面截图缩略图、分析类型、状态与短摘要；生成卡展示阶段、结果画廊、资源名和“已保存到资源库”。供应商、模型 ID、job ID 和错误码留在工具详情中。

账户 AI 设置使用 `image_generation_models` 提供已知模型建议，同时保留目录明确允许时填写兼容模型 ID。生图模型详情展示模型能力；高级 JSON 对图片模型不再描述为 Pydantic AI 透传，而是展示允许字段并由 Backend 再次校验。
