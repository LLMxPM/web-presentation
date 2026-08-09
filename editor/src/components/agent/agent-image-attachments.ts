/**
 * 文件功能：封装智能体会话图片附件的上传、移除和保存为资源动作。
 */
import {
  deleteAgentImageAttachment,
  promoteAgentImageAttachment,
  uploadAgentImageAttachment,
} from '@/api/ai'
import { getErrorMessage } from '@/api/http'
import {
  AGENT_IMAGE_ATTACHMENT_ALLOWED_TYPES,
  AGENT_IMAGE_ATTACHMENT_MAX_BYTES,
  AGENT_IMAGE_ATTACHMENT_MAX_COUNT,
} from '@/components/agent/agent-image-attachment-constants'
import type { AgentImageAttachmentItem, AgentScopeContext } from '@/types/api'
import { Message } from '@/utils/message'

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
  refreshSessionRuntime: (sessionId: string) => Promise<void>
}

/**
 * 生成图片附件动作；调用方负责提供会话状态读写和缓存刷新入口。
 */
export function useAgentImageAttachments(context: AgentImageAttachmentContext) {
  let uploadBatchInFlight = false

  /**
   * 顺序上传一批图片附件，并把成功结果加入当前 Composer 待发送列表。
   */
  async function handleUploadImages(files: File[]) {
    const disabledReason = context.getImageUploadDisabledReason()
    if (disabledReason) {
      Message.warning(disabledReason)
      return
    }
    if (uploadBatchInFlight || !files.length) {
      return
    }

    const currentAttachments = context.getPendingImageAttachments(context.getActiveSessionId())
    const remainingCount = Math.max(0, AGENT_IMAGE_ATTACHMENT_MAX_COUNT - currentAttachments.length)
    if (remainingCount === 0) {
      Message.warning('每条消息最多上传 10 张图片。')
      return
    }
    const acceptedFiles = files.slice(0, remainingCount)
    if (acceptedFiles.length < files.length) {
      Message.warning('每条消息最多上传 10 张图片，超出部分已忽略。')
    }

    const failures: string[] = []
    const validFiles = acceptedFiles.filter((file) => {
      if (!isAllowedImageFile(file)) {
        failures.push(`${displayFileName(file)}：格式不支持`)
        return false
      }
      if (file.size > AGENT_IMAGE_ATTACHMENT_MAX_BYTES) {
        failures.push(`${displayFileName(file)}：超过 10MB`)
        return false
      }
      return true
    })
    if (!validFiles.length) {
      showBatchFailures(failures)
      return
    }

    let sessionId = ''
    uploadBatchInFlight = true
    try {
      sessionId = await context.ensureActiveSession()
    } catch (error) {
      Message.error(getErrorMessage(error, '初始化智能体会话失败。'))
      uploadBatchInFlight = false
      return
    }

    context.setImageUploading(sessionId, true)
    let accumulatedAttachments = [...context.getPendingImageAttachments(sessionId)]
    try {
      for (const file of validFiles) {
        try {
          const attachment = await uploadAgentImageAttachment(sessionId, context.getScope(), file, context.getAgentId())
          accumulatedAttachments = [...accumulatedAttachments, attachment]
          context.setPendingImageAttachments(sessionId, accumulatedAttachments)
        } catch (error) {
          failures.push(`${displayFileName(file)}：${getErrorMessage(error, '上传失败')}`)
        }
      }
    } finally {
      context.setImageUploading(sessionId, false)
      uploadBatchInFlight = false
    }
    showBatchFailures(failures)
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
   * @returns 是否保存成功，供预览弹窗回显已保存状态。
   */
  async function handlePromoteImage(attachmentId: number): Promise<boolean> {
    const sessionId = context.getActiveSessionId()
    if (!sessionId) {
      return false
    }
    try {
      await promoteAgentImageAttachment(sessionId, context.getScope(), attachmentId, {}, context.getAgentId())
      await context.invalidateWorkspaceAssets()
      await context.refreshSessionRuntime(sessionId)
      Message.success('图片已保存为资源。')
      return true
    } catch (error) {
      Message.error(getErrorMessage(error, '保存为资源失败。'))
      return false
    }
  }

  return {
    handlePromoteImage,
    handleRemoveImage,
    handleUploadImages,
  }
}

/**
 * 汇总展示批次内的校验或上传失败，避免连续弹出多条消息。
 */
function showBatchFailures(failures: string[]) {
  if (!failures.length) return
  Message.error(`部分图片未能上传：${failures.join('；')}`)
}

/**
 * 返回适合错误提示的文件名，兼容剪贴板生成的空文件名。
 */
function displayFileName(file: File) {
  return file.name.trim() || '剪贴板图片'
}

/**
 * 校验前端允许上传给 Agent 的图片类型。
 */
function isAllowedImageFile(file: File) {
  if (file.type) return AGENT_IMAGE_ATTACHMENT_ALLOWED_TYPES.has(file.type)
  return /\.(png|jpe?g|webp)$/i.test(file.name)
}
