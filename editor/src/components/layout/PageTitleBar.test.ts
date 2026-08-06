/**
 * 文件功能：验证页面标题栏的项目描述提示和标题旁操作布局。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import PageTitleBar from './PageTitleBar.vue'

describe('PageTitleBar', () => {
  it('项目描述默认收起，点击信息按钮后展示', async () => {
    render(PageTitleBar, {
      props: {
        title: '季度发布会',
        code: 'PRJ007',
        description: '用于季度业务复盘与新品发布。',
      },
    })

    expect(screen.queryByText('用于季度业务复盘与新品发布。')).not.toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '查看项目描述' }))

    expect(await screen.findByText('用于季度业务复盘与新品发布。')).toBeInTheDocument()
  })
})
