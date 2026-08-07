/**
 * 文件功能：验证内容助手输入区的批量选图、图片粘贴与附件数量限制。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import AgentComposer from '@/components/agent/AgentComposer.vue'
import type { AgentImageAttachmentItem } from '@/types/api'

/** 创建测试图片文件。 */
function imageFile(name: string, type = 'image/png') {
  return new File(['image'], name, { type })
}

/** 创建待发送附件摘要。 */
function attachment(id: number): AgentImageAttachmentItem {
  return {
    id,
    session_id: 'session-1',
    source_kind: 'user_upload',
    original_name: `image-${id}.png`,
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

/** 渲染最小可交互输入区。 */
function renderComposer(props: Record<string, unknown> = {}) {
  return render(AgentComposer, {
    props: {
      modelValue: '',
      placeholder: '请输入',
      ...props,
    },
  })
}

describe('AgentComposer 图片附件', () => {
  it('一次选择多张图片时按原顺序抛出单个批次', async () => {
    const view = renderComposer()
    const files = [imageFile('first.png'), imageFile('second.png')]
    const input = view.container.querySelector('input[type="file"]') as HTMLInputElement

    expect(input).toHaveAttribute('multiple')
    await fireEvent.change(input, { target: { files } })

    expect(view.emitted('uploadImage')).toEqual([[files]])
  })

  it('粘贴图片时阻止同批文本插入并补全无扩展名文件名', () => {
    const view = renderComposer()
    const clipboardFile = imageFile('', 'image/png')
    const pasteEvent = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: {
        items: [{ kind: 'file', type: 'image/png', getAsFile: () => clipboardFile }],
        files: [clipboardFile],
        getData: () => '同时存在的文本',
      },
    })

    screen.getByRole('textbox').dispatchEvent(pasteEvent)

    expect(pasteEvent.defaultPrevented).toBe(true)
    const emittedFile = (view.emitted('uploadImage')?.[0]?.[0] as File[])[0]
    expect(emittedFile.name).toMatch(/^pasted-image-\d+-1\.png$/)
  })

  it('纯文本粘贴不拦截浏览器默认行为', () => {
    const view = renderComposer()
    const pasteEvent = new Event('paste', { bubbles: true, cancelable: true })
    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: { items: [], files: [], getData: () => '普通文本' },
    })

    screen.getByRole('textbox').dispatchEvent(pasteEvent)

    expect(pasteEvent.defaultPrevented).toBe(false)
    expect(view.emitted('uploadImage')).toBeUndefined()
  })

  it('达到上限后禁用上传，旧状态超限时同时禁用发送', async () => {
    const tenAttachments = Array.from({ length: 10 }, (_, index) => attachment(index + 1))
    const view = renderComposer({ imageAttachments: tenAttachments, modelValue: '继续处理' })

    expect(screen.getByLabelText('上传图片')).toBeDisabled()
    expect(screen.getByLabelText('上传图片')).toHaveAttribute('title', '每条消息最多上传 10 张图片')
    expect(screen.getByText('已添加 10/10 张')).toBeInTheDocument()

    await view.rerender({ imageAttachments: [...tenAttachments, attachment(11)] })
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
    expect(screen.getByText(/请移除至 10 张以内/)).toBeInTheDocument()
  })

  it('未发送的待发送图片只提供移除交互，不提供保存为资源', () => {
    renderComposer({ imageAttachments: [attachment(1)], modelValue: '' })

    expect(screen.getByLabelText('移除图片')).toBeInTheDocument()
    expect(screen.queryByLabelText('保存为资源')).toBeNull()
    expect(screen.queryByRole('button', { name: '保存为资源' })).toBeNull()
  })
})
