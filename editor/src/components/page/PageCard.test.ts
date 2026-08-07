/**
 * 文件功能：验证 PagesView 页面卡片底部名称与编码的布局和复制交互。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PageCard from './PageCard.vue'
import { createPageItem } from '@/test/factories'

const clipboardWriteTextMock = vi.hoisted(() => vi.fn())

vi.mock('@/utils/message', () => ({
  Message: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('PageCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    clipboardWriteTextMock.mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: clipboardWriteTextMock },
    })
  })

  it('名称和编码应限制长度并分别复制，且不触发详情打开', async () => {
    const pageTitle = '这是一个用于验证页面卡片名称截断行为的超长页面名称'
    const page = createPageItem({ title: pageTitle, code: 'PAGE-CODE-202605120001' })
    const { emitted } = render(PageCard, {
      props: {
        page,
        mode: 'routed',
        selected: false,
        selectionTestId: 'page-card-selection',
        screenshotAspectRatio: '16 / 9',
        screenshotDisabled: false,
        screenshotPending: false,
        archivePending: false,
        routePath: '/季度发布/封面',
      },
    })

    expect(screen.getByText(pageTitle)).toHaveClass('block', 'max-w-full', 'truncate')
    expect(screen.getByText(page.code)).toHaveClass('block', 'truncate')

    await fireEvent.click(screen.getByRole('button', { name: `复制页面名称：${pageTitle}` }))
    await fireEvent.click(screen.getByRole('button', { name: `复制页面编码：${page.code}` }))

    expect(clipboardWriteTextMock).toHaveBeenNthCalledWith(1, pageTitle)
    expect(clipboardWriteTextMock).toHaveBeenNthCalledWith(2, page.code)
    expect(emitted().open).toBeUndefined()
  })
})
