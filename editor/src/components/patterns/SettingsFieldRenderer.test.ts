/**
 * 文件功能：SettingsFieldRenderer 统一配置字段渲染器单元测试。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import SettingsFieldRenderer from './SettingsFieldRenderer.vue'

describe('SettingsFieldRenderer', () => {
  it('正确渲染基础文本输入框与 ENV 覆盖提示', async () => {
    render(SettingsFieldRenderer, {
      props: {
        label: '应用名称',
        description: '平台对外展示名称',
        modelValue: 'Web Presentation',
        envOverridden: true,
      },
    })

    expect(screen.getByText('应用名称')).toBeInTheDocument()
    expect(screen.getByText('平台对外展示名称')).toBeInTheDocument()
    expect(screen.getByText('ENV 覆盖')).toBeInTheDocument()

    const input = screen.getByRole('textbox', { name: '应用名称' })
    expect(input).toBeDisabled()
  })

  it('正确渲染数字输入框并转换数值类型触发事件', async () => {
    const { emitted } = render(SettingsFieldRenderer, {
      props: {
        type: 'number',
        label: '会话时长',
        modelValue: 24,
        min: 1,
        max: 720,
      },
    })

    const input = screen.getByRole('spinbutton', { name: '会话时长' })
    expect(input).toHaveAttribute('min', '1')
    expect(input).toHaveAttribute('max', '720')

    await fireEvent.update(input, '48')
    expect(emitted()['update:modelValue']).toBeTruthy()
    expect(emitted()['update:modelValue'][0]).toEqual([48])
    await fireEvent.update(input, '')
    expect(emitted()['update:modelValue'][1]).toEqual([''])
  })

  it('正确渲染布尔开关字段', async () => {
    render(SettingsFieldRenderer, {
      props: {
        type: 'boolean',
        label: '启用抓包',
        description: '记录原始 HTTP 请求',
        modelValue: false,
      },
    })

    expect(screen.getByText('启用抓包')).toBeInTheDocument()
    expect(screen.getByText('记录原始 HTTP 请求')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '启用抓包' })).toBeInTheDocument()
  })
})
