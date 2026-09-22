// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file */
/* eslint-disable vue/component-definition-name-casing */

/**
 * 文件用途：验证通用 Icon 组件默认尺寸收敛为 Tailwind class，并保留描边宽度配置。
 */

import { computed, createApp } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { loadAppConfig } from '@/core/utils/config'
import { setRuntimePreloadedConfig } from '@/core/utils/path'

import Icon from './Icon.v1.vue'

vi.mock('@/core/composables/useIcon', () => ({
  useIcon: () => ({
    iconExists: computed(() => true),
    isStaticIcon: computed(() => true),
    isStaticSvg: computed(() => true),
    staticIconSrc: computed(() => ''),
    iconDescription: computed(() => '测试图标'),
    staticSvgContent: computed(() => '<svg viewBox="0 0 24 24"><path d="M4 12h16" stroke="#111"/></svg>'),
    supportsStrokeWidth: computed(() => true),
  }),
}))

afterEach(async () => {
  setRuntimePreloadedConfig({
    app: {
      app: {
        icon: 'slider',
        title: '默认项目',
        description: '',
        page: {
          width: 1920,
          height: 1080,
          baseFontSize: '16px',
          iconDefaultStrokeWidth: 2,
        },
      },
    },
  })
  await loadAppConfig(true)
  setRuntimePreloadedConfig(undefined)
  document.body.innerHTML = ''
})

describe('Icon', () => {
  it('未显式传入尺寸类时应使用 size-4 作为默认尺寸', async () => {
    setRuntimePreloadedConfig({
      app: {
        app: {
          icon: 'slider',
          title: '图标规格项目',
          description: '',
          page: {
            width: 1440,
            height: 900,
            baseFontSize: '18px',
            iconDefaultStrokeWidth: 3,
          },
        },
      },
      themes: {
        themes: {
          lightblue: {
            name: '测试主题',
            description: '',
            palette: {
              text: { primary: '#111111', secondary: '#222222', invert: '#ffffff' },
              background: { default: '#ffffff', invert: '#111111' },
              border: { default: '#dddddd', subtle: '#cccccc' },
              link: { default: '#3b82f6', hover: '#2563eb', visited: '#7c3aed' },
              accent: ['#111111', '#222222', '#333333', '#444444', '#555555', '#666666'],
            },
            typography: {
              headingfont: 'system-ui',
              bodyfont: 'system-ui',
              codefont: 'monospace',
            },
          },
        },
        default: {
          theme: 'lightblue',
        },
      },
    })
    await loadAppConfig(true)

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(Icon, { name: 'arrow-right' })
    app.mount(host)

    const root = host.querySelector('.app-icon') as HTMLElement | null
    expect(root?.classList.contains('size-4')).toBe(true)
    expect(root?.style.width).toBe('')
    expect(root?.style.height).toBe('')
    expect(host.innerHTML).toContain('stroke-width="3"')

    app.unmount()
  })

  it('传入 size-* 尺寸类时不应叠加默认 size-4', async () => {
    await loadDefaultTestAppConfig()

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(Icon, { name: 'arrow-right', class: 'size-6 text-primary' })
    app.mount(host)

    const root = host.querySelector('.app-icon') as HTMLElement | null
    expect(root?.classList.contains('size-4')).toBe(false)
    expect(root?.classList.contains('size-6')).toBe(true)

    app.unmount()
  })

  it('传入 h/w 尺寸类时不应叠加默认 size-4', async () => {
    await loadDefaultTestAppConfig()

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(Icon, { name: 'arrow-right', class: 'h-6 w-6 text-primary' })
    app.mount(host)

    const root = host.querySelector('.app-icon') as HTMLElement | null
    expect(root?.classList.contains('size-4')).toBe(false)
    expect(root?.classList.contains('h-6')).toBe(true)
    expect(root?.classList.contains('w-6')).toBe(true)

    app.unmount()
  })

  it('size 属性不应再产生内联尺寸样式', async () => {
    await loadDefaultTestAppConfig()

    const host = document.createElement('div')
    document.body.appendChild(host)
    const app = createApp(Icon, { name: 'arrow-right', size: 32 })
    app.mount(host)

    const root = host.querySelector('.app-icon') as HTMLElement | null
    expect(root?.classList.contains('size-4')).toBe(true)
    expect(root?.style.width).toBe('')
    expect(root?.style.height).toBe('')
    expect(root?.hasAttribute('size')).toBe(false)

    app.unmount()
  })
})

async function loadDefaultTestAppConfig() {
  setRuntimePreloadedConfig({
    app: {
      app: {
        icon: 'slider',
        title: '默认项目',
        description: '',
        page: {
          width: 1920,
          height: 1080,
          baseFontSize: '16px',
          iconDefaultStrokeWidth: 2,
        },
      },
    },
  })
  await loadAppConfig(true)
}
