/**
 * 文件功能：验证开发用 UI Lab 能展示首批 Primitive 的关键状态与表单交互。
 */

import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import UiLabView from '@/views/UiLabView.vue'

describe('UiLabView', () => {
  it('应展示首批 Primitive 的关键状态与可访问名称', () => {
    render(UiLabView)

    expect(screen.getByRole('heading', { name: '基础组件状态展示' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '主要操作' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '禁用操作' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '保存中' })).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: '新增' })).toBeTruthy()
    expect(screen.getByText('已发布')).toBeTruthy()
    expect(screen.getByRole('radiogroup', { name: '发布方式' })).toBeTruthy()
    expect(screen.getByRole('radio', { name: '保留草稿' })).toBeChecked()
    expect(screen.getByRole('radio', { name: '全部' })).toBeChecked()
  })

  it('应允许在展示页验证输入与错误关联', async () => {
    render(UiLabView)

    const input = screen.getByLabelText(/项目名称/)
    await fireEvent.update(input, '年度报告')

    expect(input).toHaveValue('年度报告')
    expect(screen.getByRole('alert')).toHaveTextContent('路由标识不能为空')
  })
})
