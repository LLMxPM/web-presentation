# AI 侧边栏

AI 侧边栏负责承接用户输入、展示会话消息、展示工具调用、处理 HITL 确认和恢复中断会话。

## 工具说明展示

工具说明、参数 JSON Schema、调用示例、返回示例、上下文要求和披露组来自 Backend 规格接口。前端不应维护第二份工具清单。

## 会话恢复

恢复会话时，应以 Backend 返回的会话、run、消息、事件和 requirement 为事实源。前端本地状态只用于交互体验，不应覆盖服务端状态。

## HITL 确认

确认工具调用前，应清晰展示操作对象、参数和影响范围。用户拒绝或超时后，UI 需要反映 requirement 状态，避免重复提交。

## 图片附件

图片附件需要展示上传状态、预览和失败原因。上传可用性由图片理解或图片生成任一视觉槽位决定，不再依赖内容会话模型的 `supports_image_input`。

`analyze_visuals` 与 `generate_image` 使用专用工具卡：前者合并展示用户附件、工作空间资源图片与页面截图缩略图、分析类型、状态和短摘要；后者展示 `queued/running/saving/completed/error` 进度、输出画廊与资源库标记。SSE、runtime snapshot 和历史回放必须使用同一 `progress/input_attachments/output_attachments` 协议。普通工具继续使用通用卡片。
