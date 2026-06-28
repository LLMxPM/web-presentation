/**
 * 文件功能：封装智能体会话图片附件的上传、移除和保存为资源动作。
 */
import {
  deleteAgentImageAttachment,
  promoteAgentImageAttachment,
  uploadAgentImageAttachment,
} from '@/api/ai'
import { getErrorMessage } from '@/api/http'
import type { AgentImageAttachmentItem, AgentScopeContext } from '@/types/api'
import { Message } from '@/utils/message'

const IMAGE_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
const ALLOWED_IMAGE_ATTACHMENT_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])

interface AgentImageAttachmentContext {
  getActiveSessionId: () => string
  getScope: () => AgentScopeContext
  getAgentId: () => string
  getImageUploadDisabledReason: () => string
  ensureActiveSession: () => Promise<string>
  getPendingImageAttachments: (sessionId: string) => AgentImageAttachmentItem[]
  setPendingImageAttachments: (sessionId: string, attachments: AgentImageAttachmentItem[]) => void
  setImageUploading: (sessionId: string, uploading: boolean) => void
  invalidateWorkspaceAssets: () => Promise<void>
}

/**
 * 生成图片附件动作；调用方负责提供会话状态读写和缓存刷新入口。
 */
export function useAgentImageAttachments(context: AgentImageAttachmentContext) {
  /**
   * 上传用户选择的图片附件，并把结果加入当前 Composer 待发送列表。
   */
  async function handleUploadImage(file: File) {
    const disabledReason = context.getImageUploadDisabledReason()
    if (disabledReason) {
      Message.warning(disabledReason)
      return
    }
    if (!isAllowedImageFile(file)) {
      Message.error('图片附件仅支持 png、jpg、jpeg、webp。')
      return
    }
    if (file.size > IMAGE_ATTACHMENT_MAX_BYTES) {
      Message.error('单张图片不能超过 10MB。')
      return
    }

    let sessionId = ''
    try {
      sessionId = await context.ensureActiveSession()
    } catch (error) {
      Message.error(getErrorMessage(error, '初始化智能体会话失败。'))
      return
    }

    context.setImageUploading(sessionId, true)
    try {
      const attachment = await uploadAgentImageAttachment(sessionId, context.getScope(), file, context.getAgentId())
      context.setPendingImageAttachments(sessionId, [
        ...context.getPendingImageAttachments(sessionId),
        attachment,
      ])
    } catch (error) {
      Message.error(getErrorMessage(error, '上传图片失败。'))
    } finally {
      context.setImageUploading(sessionId, false)
    }
  }

  /**
   * 从当前待发送列表移除图片，并通知后端归档附件记录。
   */
  async function handleRemoveImage(attachmentId: number) {
    const sessionId = context.getActiveSessionId()
    if (!sessionId) {
      return
    }
    context.setPendingImageAttachments(
      sessionId,
      context.getPendingImageAttachments(sessionId).filter(item => item.id !== attachmentId),
    )
    try {
      await deleteAgentImageAttachment(sessionId, context.getScope(), attachmentId, context.getAgentId())
    } catch (error) {
      Message.error(getErrorMessage(error, '删除图片失败。'))
    }
  }

  /**
   * 将图片附件保存为工作空间资源，并刷新资源相关缓存。
   */
  async function handlePromoteImage(attachmentId: number) {
    const sessionId = context.getActiveSessionId()
    if (!sessionId) {
      return
    }
    try {
      const promoted = await promoteAgentImageAttachment(sessionId, context.getScope(), attachmentId, {}, context.getAgentId())
      context.setPendingImageAttachments(
        sessionId,
        context.getPendingImageAttachments(sessionId).map(item => (
          item.id === promoted.id ? promoted : item
        )),
      )
      await context.invalidateWorkspaceAssets()
      Message.success('图片已保存为资源。')
    } catch (error) {
      Message.error(getErrorMessage(error, '保存为资源失败。'))
    }
  }

  return {
    handlePromoteImage,
    handleRemoveImage,
    handleUploadImage,
  }
}

/**
 * 校验前端允许上传给 Agent 的图片类型。
 */
function isAllowedImageFile(file: File) {
  if (ALLOWED_IMAGE_ATTACHMENT_TYPES.has(file.type)) {
    return true
  }
  return /\.(png|jpe?g|webp)$/i.test(file.name)
}
