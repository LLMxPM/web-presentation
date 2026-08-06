/**
 * 文件功能：集中定义 Editor 会话图片附件的数量、大小与格式约束。
 */
export const AGENT_IMAGE_ATTACHMENT_MAX_COUNT = 10
export const AGENT_IMAGE_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
export const AGENT_IMAGE_ATTACHMENT_ALLOWED_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])

