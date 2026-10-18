// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file */

/**
 * 文件用途：验证侧边缩略图栏底部的视图切换与卡片模式入口。
 */

import { createApp, h, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SidePreviewStrip from './SidePreviewStrip.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/home' }),
  useRouter: () => ({ push: vi.fn() }),
}))

afterEach(() => {
  document.body.innerHTML = ''
})

describe('SidePreviewStrip', () => {
  it('底部操作区提供切换底部缩略图与卡片模式入口', async () => {
    const onToggleMenuMode = vi.fn()
    const onOpenCardMode = vi.fn()
    const { app, host } = mountSidePreviewStrip({ onToggleMenuMode, onOpenCardMode })

    await nextTick()

    const switchButton = host.querySelector<HTMLButtonElement>('[data-testid="side-preview-switch-mode"]')
    const cardButton = host.querySelector<HTMLButtonElement>('[data-testid="side-preview-card-mode"]')
    expect(switchButton).not.toBeNull()
    expect(cardButton).not.toBeNull()
    expect(switchButton?.textContent).toContain('底部缩略图')
    expect(cardButton?.textContent).toContain('卡片模式')

    switchButton?.click()
    cardButton?.click()
    expect(onToggleMenuMode).toHaveBeenCalledTimes(1)
    expect(onOpenCardMode).toHaveBeenCalledTimes(1)

    app.unmount()
  })

  it('未开放入口时不渲染底部操作区', async () => {
    const { app, host } = mountSidePreviewStrip({
      modeToggleAvailable: false,
      cardModeAvailable: false,
    })

    await nextTick()

    expect(host.querySelector('[data-testid="side-preview-switch-mode"]')).toBeNull()
    expect(host.querySelector('[data-testid="side-preview-card-mode"]')).toBeNull()

    app.unmount()
  })

  it('侧边栏收起后操作入口保留图标并隐藏文字', async () => {
    const { app, host } = mountSidePreviewStrip({})

    await nextTick()
    host.querySelector<HTMLButtonElement>('button[title="收起侧边栏"]')?.click()
    await nextTick()

    const switchButton = host.querySelector<HTMLButtonElement>('[data-testid="side-preview-switch-mode"]')
    expect(switchButton).not.toBeNull()
    expect(switchButton?.textContent).not.toContain('底部缩略图')

    app.unmount()
  })
})

/**
 * 挂载侧边缩略图栏。
 * @param options 入口开关与事件回调
 * @returns 挂载后的 Vue 应用与宿主 DOM
 */
function mountSidePreviewStrip(options: {
  modeToggleAvailable?: boolean
  cardModeAvailable?: boolean
  onToggleMenuMode?: () => void
  onOpenCardMode?: () => void
} = {}) {
  const host = document.createElement('div')
  document.body.appendChild(host)

  const app = createApp(SidePreviewStrip, {
    navigationItems: [],
    appConfig: {
      title: '测试项目',
    },
    modeToggleAvailable: options.modeToggleAvailable ?? true,
    cardModeAvailable: options.cardModeAvailable ?? true,
    onToggleMenuMode: options.onToggleMenuMode,
    onOpenCardMode: options.onOpenCardMode,
  })

  app.component('RouterLink', {
    props: {
      to: {
        type: [String, Object],
        required: true,
      },
    },
    setup(props, { slots }) {
      return () => h('a', { href: String(props.to) }, slots.default?.())
    },
  })
  app.mount(host)
  return { app, host }
}
