/**
 * 文件功能：验证顶部主题菜单展示三种主题偏好并可切换当前选择。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it } from 'vitest'

import ThemeModeMenu from '@/components/nav/ThemeModeMenu.vue'
import { useTheme } from '@/composables/useTheme'

describe('ThemeModeMenu', () => {
  beforeEach(() => {
    useTheme().setMode('system')
  })

  it('应提供跟随系统、明亮和夜间三种选择', async () => {
    render(ThemeModeMenu)

    const trigger = screen.getByRole('button', { name: '界面主题：跟随系统' })
    await fireEvent.click(trigger)

    expect(await screen.findByText('跟随系统')).toBeTruthy()
    expect(screen.getByText('明亮模式')).toBeTruthy()
    expect(screen.getByText('夜间模式')).toBeTruthy()
  })

  it('选择固定模式后应更新入口标签并持久化', async () => {
    render(ThemeModeMenu)

    await fireEvent.click(screen.getByRole('button', { name: '界面主题：跟随系统' }))
    await fireEvent.click(await screen.findByText('夜间模式'))

    expect(screen.getByTitle('界面主题：夜间模式')).toBeTruthy()
    expect(window.localStorage.getItem('editor-theme-mode')).toBe('dark')
  })
})
