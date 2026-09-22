// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file */

/**
 * 文件用途：验证底部缩略图导航条的项目标题、项目图标、激活项居中与翻页按钮交互。
 */

import { createApp, defineComponent, h, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import BottomPreviewStrip from './BottomPreviewStrip.vue'
import type { MenuItem } from '@/core/types/menu'

interface MockRouteState {
  path: string
}

const routeHarness = vi.hoisted((): { route: MockRouteState | null } => ({
  route: null,
}))

vi.mock('vue-router', async () => {
  const vue = await vi.importActual<typeof import('vue')>('vue')
  routeHarness.route = vue.reactive({ path: '/home' })

  return {
    useRoute: () => routeHarness.route,
    RouterLink: vue.defineComponent({
      name: 'RouterLinkStub',
      inheritAttrs: false,
      props: {
        to: {
          type: String,
          required: true,
        },
      },
      setup(props, { attrs, slots }) {
        return () => vue.h('a', {
          ...attrs,
          href: props.to,
        }, slots.default?.())
      },
    }),
  }
})

vi.mock('@/runtime-shell/layouts/AppBrandIcon.vue', () => ({
  default: defineComponent({
    name: 'AppBrandIconStub',
    props: {
      name: {
        type: String,
        default: '',
      },
      size: {
        type: [Number, String],
        default: 14,
      },
      alt: {
        type: String,
        default: '',
      },
    },
    setup(props) {
      return () => h('span', {
        'data-testid': 'app-title-icon',
        'data-icon-name': props.name,
        'data-icon-size': props.size,
        'data-icon-alt': props.alt,
      })
    },
  }),
}))

class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

const originalScrollIntoView = HTMLElement.prototype.scrollIntoView
const originalScrollBy = HTMLElement.prototype.scrollBy
let scrollIntoViewMock: ReturnType<typeof vi.fn>
let scrollByMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', ResizeObserverMock)
  if (routeHarness.route) {
    routeHarness.route.path = '/home'
  }
  scrollIntoViewMock = vi.fn()
  scrollByMock = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    configurable: true,
    writable: true,
    value: scrollIntoViewMock,
  })
  Object.defineProperty(HTMLElement.prototype, 'scrollBy', {
    configurable: true,
    writable: true,
    value: scrollByMock,
  })
})

afterEach(() => {
  document.body.innerHTML = ''
  restorePrototypeFunction('scrollIntoView', originalScrollIntoView)
  restorePrototypeFunction('scrollBy', originalScrollBy)
  vi.unstubAllGlobals()
})

describe('BottomPreviewStrip', () => {
  it('应在底栏项目标题旁展示项目图标', async () => {
    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(BottomPreviewStrip, {
      navigationItems: [],
      appConfig: {
        icon: 'theme-project-icon',
        title: '主题图标项目',
      },
      pageConfig: {
        width: 1920,
        height: 1080,
      },
    })

    app.mount(host)
    await nextTick()

    const icon = host.querySelector('[data-testid="app-title-icon"]')
    expect(icon).not.toBeNull()
    expect(icon?.getAttribute('data-icon-name')).toBe('theme-project-icon')
    expect(icon?.getAttribute('data-icon-alt')).toBe('主题图标项目')
    expect(host.textContent).toContain('主题图标项目')

    app.unmount()
  })

  it('路由变化后应将激活缩略图滚动到横向中部', async () => {
    const { app, host } = mountBottomPreviewStrip({
      navigationItems: [
        createMenuItem('/home', '首页'),
        createMenuItem('/chapter/page-2', '第二页'),
        createMenuItem('/chapter/page-3', '第三页'),
      ],
    })

    await nextTick()
    await nextTick()
    scrollIntoViewMock.mockClear()

    routeHarness.route!.path = '/chapter/page-2'
    await nextTick()
    await nextTick()

    const activeThumbnail = host.querySelector('[data-preview-thumbnail-path="/chapter/page-2"]')
    expect(activeThumbnail).not.toBeNull()
    expect(scrollIntoViewMock).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'nearest',
      inline: 'center',
    })
    expect(scrollIntoViewMock.mock.contexts.at(-1)).toBe(activeThumbnail)

    app.unmount()
  })

  it('应在缩略图根节点输出可查询的路径标识', async () => {
    const { app, host } = mountBottomPreviewStrip({
      navigationItems: [
        createMenuItem('/home', '首页'),
      ],
    })

    await nextTick()

    const thumbnail = host.querySelector('[data-preview-thumbnail-path="/home"]')
    expect(thumbnail).not.toBeNull()
    expect(thumbnail?.getAttribute('href')).toBe('/home')

    app.unmount()
  })

  it('右侧翻页按钮第一次点击应直接触发缩略图滚动', async () => {
    const { app, host } = mountBottomPreviewStrip({
      navigationItems: [
        createMenuItem('/home', '首页'),
        createMenuItem('/page-2', '第二页'),
        createMenuItem('/page-3', '第三页'),
      ],
    })

    await showScrollButtons(host)

    const rightButton = host.querySelector<HTMLButtonElement>('[aria-label="向右滚动缩略图"]')
    const hostClickHandler = vi.fn()
    const clickEvent = new MouseEvent('click', {
      bubbles: true,
      cancelable: true,
    })

    expect(rightButton).not.toBeNull()
    host.addEventListener('click', hostClickHandler)
    rightButton?.dispatchEvent(clickEvent)

    expect(scrollByMock).toHaveBeenCalledWith({
      left: 300,
      behavior: 'smooth',
    })
    expect(clickEvent.defaultPrevented).toBe(true)
    expect(hostClickHandler).not.toHaveBeenCalled()

    app.unmount()
  })

  it('翻页按钮层级应高于缩略图遮罩并提供无障碍标签', async () => {
    const { app, host } = mountBottomPreviewStrip({
      navigationItems: [
        createMenuItem('/home', '首页'),
        createMenuItem('/page-2', '第二页'),
        createMenuItem('/page-3', '第三页'),
      ],
    })

    await showScrollButtons(host)

    const leftButton = host.querySelector<HTMLButtonElement>('[aria-label="向左滚动缩略图"]')
    const rightButton = host.querySelector<HTMLButtonElement>('[aria-label="向右滚动缩略图"]')
    const thumbnailShield = host.querySelector('.preview-thumbnail__frame .z-20')

    expect(leftButton).not.toBeNull()
    expect(rightButton).not.toBeNull()
    expect(thumbnailShield).not.toBeNull()
    expect(leftButton?.classList.contains('z-30')).toBe(true)
    expect(rightButton?.classList.contains('z-30')).toBe(true)
    expect(thumbnailShield?.classList.contains('z-20')).toBe(true)

    app.unmount()
  })
})

/**
 * 挂载底部缩略图组件。
 * @param props 组件属性
 * @returns 挂载后的 Vue 应用与宿主 DOM
 */
function mountBottomPreviewStrip(props: {
  navigationItems: MenuItem[]
  appConfig?: {
    icon?: string
    title?: string
  }
  pageConfig?: {
    width?: number
    height?: number
  }
}) {
  const host = document.createElement('div')
  document.body.appendChild(host)

  const app = createApp(BottomPreviewStrip, {
    pageConfig: {
      width: 1920,
      height: 1080,
    },
    ...props,
  })

  app.mount(host)
  return { app, host }
}

/**
 * 创建测试用菜单项。
 * @param path 菜单路径
 * @param title 菜单标题
 * @returns 可渲染的菜单项
 */
function createMenuItem(path: string, title: string): MenuItem {
  return {
    id: path,
    title,
    path,
    order: 1,
    hidden: false,
    disabled: false,
  }
}

/**
 * 模拟滚动区域产生横向溢出，让左右翻页按钮进入可见状态。
 * @param host 组件宿主 DOM
 */
async function showScrollButtons(host: HTMLElement): Promise<void> {
  await nextTick()
  const scrollContainer = host.querySelector<HTMLElement>('.scrollbar-none')
  expect(scrollContainer).not.toBeNull()
  Object.defineProperties(scrollContainer!, {
    clientWidth: {
      configurable: true,
      value: 400,
    },
    scrollWidth: {
      configurable: true,
      value: 1200,
    },
    scrollLeft: {
      configurable: true,
      writable: true,
      value: 200,
    },
  })
  scrollContainer!.dispatchEvent(new Event('scroll'))
  await nextTick()
}

/**
 * 恢复被测试替换过的 HTMLElement 原型函数。
 * @param name 函数名
 * @param original 原始函数
 */
function restorePrototypeFunction(name: string, original: unknown): void {
  if (typeof original === 'function') {
    Object.defineProperty(HTMLElement.prototype, name, {
      configurable: true,
      writable: true,
      value: original,
    })
    return
  }

  delete (HTMLElement.prototype as unknown as Record<string, unknown>)[name]
}
