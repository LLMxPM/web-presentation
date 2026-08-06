/**
 * 文件功能：验证一级页面标题栏的描述提示与标题旁元信息插槽。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import PageHeader from './PageHeader.vue'

describe('PageHeader', () => {
  it('空间描述默认收起并可通过标题旁信息按钮查看', async () => {
    render(PageHeader, {
      props: {
        title: '学术汇报',
        description: '用于维护学术演示项目。',
        descriptionLabel: '查看空间描述',
      },
      slots: {
        meta: '<span>标题旁操作</span>',
      },
    })

    expect(screen.getByText('标题旁操作')).toBeInTheDocument()
    expect(screen.queryByText('用于维护学术演示项目。')).not.toBeInTheDocument()

    await fireEvent.click(screen.getByRole('button', { name: '查看空间描述' }))

    expect(await screen.findByText('用于维护学术演示项目。')).toBeInTheDocument()
  })
})
