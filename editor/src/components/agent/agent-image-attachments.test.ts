/**
 * 文件功能：验证智能体图片附件批量上传的顺序、容量限制与部分成功语义。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAgentImageAttachments } from '@/components/agent/agent-image-attachments'
import type { AgentImageAttachmentItem } from '@/types/api'

const uploadMock = vi.fn()
const messageErrorMock = vi.fn()
const messageWarningMock = vi.fn()

vi.mock('@/api/ai', () => ({
  uploadAgentImageAttachment: (...args: unknown[]) => uploadMock(...args),
  deleteAgentImageAttachment: vi.fn(),
  promoteAgentImageAttachment: vi.fn(),
}))

vi.mock('@/utils/message', () => ({
  Message: {
    error: (...args: unknown[]) => messageErrorMock(...args),
    warning: (...args: unknown[]) => messageWarningMock(...args),
    success: vi.fn(),
  },
}))

/** 创建上传成功后的附件摘要。 */
function attachment(id: number, name = `${id}.png`): AgentImageAttachmentItem {
  return {
    id,
    session_id: 'session-1',
    source_kind: 'user_upload',
    original_name: name,
    content_type: 'image/png',
    file_size: 5,
    width: 1,
    height: 1,
    sha256: `sha-${id}`,
    url: `/attachments/${id}`,
    preview_available: true,
    promoted_asset_id: null,
  }
}

/** 创建可观察状态变化的附件上下文。 */
function createContext(initialAttachments: AgentImageAttachmentItem[] = []) {
  let attachments = [...initialAttachments]
  const ensureActiveSession = vi.fn().mockResolvedValue('session-1')
  const uploadingStates: boolean[] = []
  return {
    context: {
      getActiveSessionId: () => 'session-1',
      getScope: () => ({ workspace_id: 1, source: 'test' }),
      getAgentId: () => 'agent-coordinator',
      getImageUploadDisabledReason: () => '',
      ensureActiveSession,
      getPendingImageAttachments: () => attachments,
      setPendingImageAttachments: (_sessionId: string, value: AgentImageAttachmentItem[]) => { attachments = value },
      setImageUploading: (_sessionId: string, value: boolean) => { uploadingStates.push(value) },
      invalidateWorkspaceAssets: vi.fn(),
    },
    ensureActiveSession,
    getAttachments: () => attachments,
    uploadingStates,
  }
}

describe('useAgentImageAttachments', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('整批只初始化一次会话，并按文件顺序逐张上传', async () => {
    const state = createContext()
    const files = [
      new File(['1'], 'first.png', { type: 'image/png' }),
      new File(['2'], 'second.png', { type: 'image/png' }),
    ]
    uploadMock
      .mockResolvedValueOnce(attachment(1, 'first.png'))
      .mockResolvedValueOnce(attachment(2, 'second.png'))

    await useAgentImageAttachments(state.context).handleUploadImages(files)

    expect(state.ensureActiveSession).toHaveBeenCalledTimes(1)
    expect(uploadMock.mock.calls.map(call => (call[2] as File).name)).toEqual(['first.png', 'second.png'])
    expect(state.getAttachments().map(item => item.original_name)).toEqual(['first.png', 'second.png'])
    expect(state.uploadingStates).toEqual([true, false])
  })

  it('仅填充剩余名额并忽略超出 10 张的文件', async () => {
    const state = createContext(Array.from({ length: 9 }, (_, index) => attachment(index + 1)))
    const files = [
      new File(['10'], 'tenth.png', { type: 'image/png' }),
      new File(['11'], 'ignored.png', { type: 'image/png' }),
    ]
    uploadMock.mockResolvedValueOnce(attachment(10, 'tenth.png'))

    await useAgentImageAttachments(state.context).handleUploadImages(files)

    expect(uploadMock).toHaveBeenCalledTimes(1)
    expect(state.getAttachments()).toHaveLength(10)
    expect(messageWarningMock).toHaveBeenCalledWith('每条消息最多上传 10 张图片，超出部分已忽略。')
  })

  it('保留成功附件并汇总校验与网络失败', async () => {
    const state = createContext()
    const files = [
      new File(['ok'], 'ok.png', { type: 'image/png' }),
      new File(['bad'], 'bad.png', { type: 'image/gif' }),
      new File(['failed'], 'failed.webp', { type: 'image/webp' }),
    ]
    uploadMock
      .mockResolvedValueOnce(attachment(1, 'ok.png'))
      .mockRejectedValueOnce(new Error('网络异常'))

    await useAgentImageAttachments(state.context).handleUploadImages(files)

    expect(state.getAttachments().map(item => item.original_name)).toEqual(['ok.png'])
    expect(messageErrorMock).toHaveBeenCalledTimes(1)
    expect(messageErrorMock.mock.calls[0][0]).toContain('bad.png：格式不支持')
    expect(messageErrorMock.mock.calls[0][0]).toContain('failed.webp')
  })
})
