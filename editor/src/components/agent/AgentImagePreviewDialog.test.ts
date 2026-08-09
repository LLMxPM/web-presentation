/**
 * 文件功能：验证统一图片预览弹窗的大图展示、下载与保存为资源交互。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'

import AgentImagePreviewDialog from '@/components/agent/AgentImagePreviewDialog.vue'
import type { AgentMessageAttachmentItem } from '@/types/api'

/** 创建测试图片附件。 */
function attachment(id: number, promotedAssetId: number | null = null): AgentMessageAttachmentItem {
  return {
    id,
    source_kind: 'user_upload',
    original_name: `image-${id}.png`,
    content_type: 'image/png',
    file_size: 5,
    width: 1,
    height: 1,
    url: `/api/ai/attachments/images/${id}/content`,
    preview_available: true,
    promoted_asset_id: promotedAssetId,
    promotion_status: promotedAssetId ? 'promoted' : 'never',
  }
}

describe('AgentImagePreviewDialog', () => {
  it('打开后展示大图与带文件名的下载链接', () => {
    render(AgentImagePreviewDialog, {
      props: { open: true, attachment: attachment(1) },
    })

    expect(screen.getByAltText('image-1.png')).toBeInTheDocument()
    const downloadLink = screen.getByLabelText('下载图片')
    expect(downloadLink).toHaveAttribute('href', '/api/ai/attachments/images/1/content')
    expect(downloadLink).toHaveAttribute('download', 'image-1.png')
  })

  it('未提供保存入口时不渲染保存为资源按钮', () => {
    render(AgentImagePreviewDialog, {
      props: { open: true, attachment: attachment(1) },
    })

    expect(screen.queryByRole('button', { name: '保存为资源' })).toBeNull()
  })

  it('调用保存入口成功后回显已保存到资源库', async () => {
    const promoteAttachment = vi.fn().mockResolvedValue(true)
    render(AgentImagePreviewDialog, {
      props: { open: true, attachment: attachment(1), promoteAttachment },
    })

    const promoteButton = screen.getByRole('button', { name: '保存为资源' })
    await fireEvent.click(promoteButton)

    expect(promoteAttachment).toHaveBeenCalledWith(1)
    expect(screen.getByRole('button', { name: '已保存到资源库' })).toBeDisabled()
  })

  it('保存入口失败时保持可重试状态', async () => {
    const promoteAttachment = vi.fn().mockResolvedValue(false)
    render(AgentImagePreviewDialog, {
      props: { open: true, attachment: attachment(1), promoteAttachment },
    })

    await fireEvent.click(screen.getByRole('button', { name: '保存为资源' }))

    expect(screen.getByRole('button', { name: '保存为资源' })).not.toBeDisabled()
  })

  it('附件已保存过资源时直接展示已保存状态', () => {
    render(AgentImagePreviewDialog, {
      props: { open: true, attachment: attachment(2, 99), promoteAttachment: vi.fn() },
    })

    expect(screen.getByRole('button', { name: '已保存到资源库' })).toBeDisabled()
  })

  it('资源库副本删除后提供重新保存入口', async () => {
    const promoteAttachment = vi.fn().mockResolvedValue(true)
    const deletedAttachment = { ...attachment(3), promotion_status: 'deleted' as const }
    render(AgentImagePreviewDialog, {
      props: { open: true, attachment: deletedAttachment, promoteAttachment },
    })

    await fireEvent.click(screen.getByRole('button', { name: '重新保存为资源' }))

    expect(promoteAttachment).toHaveBeenCalledWith(3)
    expect(screen.getByRole('button', { name: '已保存到资源库' })).toBeDisabled()
  })
})
