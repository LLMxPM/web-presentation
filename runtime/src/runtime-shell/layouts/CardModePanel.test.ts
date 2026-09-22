// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file */

/**
 * 文件用途：验证卡片模式的页面卡片渲染、卡片尺寸调整与页面选择事件。
 */

import { runtimePreferenceKey } from '@/core/utils/runtime-preferences'
import { createApp, nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/runtime-shell/preview/ViewPreview.vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    default: defineComponent({
      name: 'ViewPreviewStub',
      props: {
        filePath: {
          type: String,
          required: true,
        },
      },
      setup(props) {
        return () => h('div', { 'data-file-path': props.filePath }, 'preview')
      },
    }),
  }
})

vi.mock('@lucide/vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    X: defineComponent({
      name: 'XStub',
      setup() {
        return () => h('span', { 'data-testid': 'x-icon' })
      },
    }),
  }
})

import CardModePanel from './CardModePanel.vue'

const pages = [
  {
    path: '/intro',
    title: '开场页',
    pageNumber: 1,
    componentPath: '@/views/intro.vue',
    speakerNotes: '',
  },
  {
    path: '/summary',
    title: '总结页',
    pageNumber: 2,
    componentPath: '@/views/summary.vue',
    speakerNotes: '',
  },
]

afterEach(() => {
  localStorage.clear()
  document.body.innerHTML = ''
})

describe('CardModePanel', () => {
  it('应展示页面卡片并按滑杆调整卡片宽度', async () => {
    const { host, app } = mountPanel()
    await nextTick()

    expect(host.querySelectorAll('.presenter-console__tile')).toHaveLength(2)
    expect(host.querySelector<HTMLElement>('.presenter-console__grid')?.style.gridTemplateColumns)
      .toBe('repeat(auto-fill, minmax(300px, 1fr))')

    const sizeInput = host.querySelector<HTMLInputElement>('input[type="range"]')
    expect(sizeInput).not.toBeNull()
    if (sizeInput) {
      sizeInput.value = '420'
      sizeInput.dispatchEvent(new Event('input', { bubbles: true }))
    }
    await nextTick()

    expect(host.querySelector<HTMLElement>('.presenter-console__grid')?.style.gridTemplateColumns)
      .toBe('repeat(auto-fill, minmax(420px, 1fr))')
    expect(localStorage.getItem(runtimePreferenceKey('web-presentation.card-mode.cardSize'))).toBe('420')

    app.unmount()
  })

  it('点击页面卡片应抛出目标路径', async () => {
    const select = vi.fn()
    const { host, app } = mountPanel({ onSelect: select })
    await nextTick()

    host.querySelectorAll<HTMLButtonElement>('.presenter-console__tile')[1]?.click()

    expect(select).toHaveBeenCalledWith('/summary')
    app.unmount()
  })
})

/**
 * 挂载卡片模式面板。
 * @param listeners 面板事件监听器
 * @returns Vue 应用和宿主节点
 */
function mountPanel(listeners: Record<string, unknown> = {}) {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp(CardModePanel, {
    pages,
    currentPath: '/intro',
    ...listeners,
  })
  app.config.errorHandler = (error) => {
    throw error
  }
  app.mount(host)
  return { app, host }
}
