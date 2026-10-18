// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file */

/**
 * 文件用途：验证响应式布局在不同菜单模式下的配置透传与底部缩略图切换行为。
 */

import { createApp, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

type MockMenuMode = 'text' | 'preview' | 'bottom-preview'

/**
 * 从未知对象中读取可选记录结构。
 * @param value 待解析值
 * @returns 可索引对象；无效时返回 null
 */
function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : null
}

/**
 * 读取页面配置中的宽度，用于测试桩输出。
 * @param pageConfig 页面配置对象
 * @returns 页面宽度；不存在时返回 unknown
 */
function getMockPageWidth(pageConfig: unknown): number | 'unknown' {
  const width = asRecord(pageConfig)?.width
  return typeof width === 'number' ? width : 'unknown'
}

/**
 * 将应用配置对象转成便于断言的标题:菜单模式文本。
 * @param appConfig 应用配置对象
 * @returns 文本摘要
 */
function formatMockAppConfig(appConfig: unknown): string {
  const configRecord = asRecord(appConfig)
  const title = typeof configRecord?.title === 'string' ? configRecord.title : 'unknown'
  const features = asRecord(configRecord?.features)
  const menuMode = typeof features?.menuMode === 'string' ? features.menuMode : 'unknown'
  return `${title}:${menuMode}`
}

const {
  sidebarPropSpy,
  sidePreviewPropSpy,
  bottomStripPropSpy,
  mockMenuMode,
  mockPageConfig,
  mockNavigableRoutes,
  mockNavigationState,
  nextPageSpy,
  previousPageSpy,
  gotoPageSpy,
  firstPageSpy,
  lastPageSpy,
  mockRouteConfigs,
} = vi.hoisted(() => ({
  sidebarPropSpy: vi.fn(),
  sidePreviewPropSpy: vi.fn(),
  bottomStripPropSpy: vi.fn(),
  mockMenuMode: {
    value: 'preview' as MockMenuMode,
  },
  mockPageConfig: {
    value: {
      width: 1920,
      height: 1080,
      baseFontSize: '20px',
      iconDefaultStrokeWidth: 2,
    },
  },
  mockNavigableRoutes: {
    value: [] as Array<{ path: string; name: string; pageNumber: number }>,
  },
  mockNavigationState: {
    value: { canGoNext: false, canGoPrevious: false },
  },
  nextPageSpy: vi.fn(),
  previousPageSpy: vi.fn(),
  gotoPageSpy: vi.fn(async () => true),
  firstPageSpy: vi.fn(async () => true),
  lastPageSpy: vi.fn(async () => true),
  mockRouteConfigs: {
    value: [] as Array<Record<string, unknown>>,
  },
}))

vi.mock('@/core/utils/config', async () => {
  const appConfigRef = {}
  const appPageConfigRef = {}

  Object.defineProperty(appConfigRef, 'value', {
    get() {
      return {
        app: {
          icon: 'slider',
          title: '测试标题',
          description: '测试描述',
          features: {
            showPdfExportButton: false,
            menuMode: mockMenuMode.value,
          },
          page: {
            width: mockPageConfig.value.width,
            height: mockPageConfig.value.height,
            baseFontSize: mockPageConfig.value.baseFontSize,
            iconDefaultStrokeWidth: mockPageConfig.value.iconDefaultStrokeWidth,
          },
        },
      }
    },
  })

  Object.defineProperty(appPageConfigRef, 'value', {
    get() {
      return {
        width: mockPageConfig.value.width,
        height: mockPageConfig.value.height,
        baseFontSize: mockPageConfig.value.baseFontSize,
        iconDefaultStrokeWidth: mockPageConfig.value.iconDefaultStrokeWidth,
      }
    },
  })

  return {
    DEFAULT_PAGE_CONFIG: {
      width: 1920,
      height: 1080,
      baseFontSize: '20px',
      iconDefaultStrokeWidth: 2,
    },
    appConfig: appConfigRef,
    appPageConfig: appPageConfigRef,
    routeConfigs: mockRouteConfigs,
    playbackConfig: { value: { supported: false, autoStart: false, loop: false } },
    loadIconConfig: vi.fn().mockResolvedValue({ icons: [] }),
  }
})

vi.mock('@/runtime-shell/layouts/BottomPreviewStrip.vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    default: defineComponent({
      name: 'BottomPreviewStripStub',
      props: {
        navigationItems: {
          type: Array,
          default: () => [],
        },
        pageConfig: {
          type: Object,
          default: () => ({}),
        },
        appConfig: {
          type: Object,
          default: () => ({}),
        },
        modeToggleAvailable: {
          type: Boolean,
          default: false,
        },
        cardModeAvailable: {
          type: Boolean,
          default: false,
        },
      },
      emits: ['collapsed-change', 'toggle-menu-mode', 'open-card-mode'],
      setup(props, { emit }) {
        bottomStripPropSpy(props.pageConfig)

        return () => h(
          'div',
          { 'data-testid': 'bottom-preview-strip-stub' },
          [
            `bottom:${getMockPageWidth(props.pageConfig)}`,
            props.modeToggleAvailable
              ? h('button', {
                'data-testid': 'bottom-stub-toggle-menu-mode',
                onClick: () => emit('toggle-menu-mode'),
              })
              : null,
            props.cardModeAvailable
              ? h('button', {
                'data-testid': 'bottom-stub-open-card-mode',
                onClick: () => emit('open-card-mode'),
              })
              : null,
          ],
        )
      },
    }),
  }
})

vi.mock('@/runtime-shell/layouts/ResponsiveSidebar.vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    default: defineComponent({
      name: 'ResponsiveSidebarStub',
      props: {
        navigationItems: {
          type: Array,
          default: () => [],
        },
        appConfig: {
          type: Object,
          required: true,
        },
      },
      setup(props) {
        sidebarPropSpy(props.appConfig)

        return () => h(
          'div',
          { 'data-testid': 'responsive-sidebar-stub' },
          formatMockAppConfig(props.appConfig),
        )
      },
    }),
  }
})

vi.mock('@/runtime-shell/layouts/SidePreviewStrip.vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    default: defineComponent({
      name: 'SidePreviewStripStub',
      props: {
        navigationItems: {
          type: Array,
          default: () => [],
        },
        appConfig: {
          type: Object,
          required: true,
        },
        modeToggleAvailable: {
          type: Boolean,
          default: false,
        },
        cardModeAvailable: {
          type: Boolean,
          default: false,
        },
      },
      emits: ['collapse-change', 'toggle-menu-mode', 'open-card-mode'],
      setup(props, { emit }) {
        sidePreviewPropSpy(props.appConfig)

        return () => h(
          'div',
          { 'data-testid': 'side-preview-strip-stub' },
          [
            formatMockAppConfig(props.appConfig),
            props.modeToggleAvailable
              ? h('button', {
                'data-testid': 'side-stub-toggle-menu-mode',
                onClick: () => emit('toggle-menu-mode'),
              })
              : null,
            props.cardModeAvailable
              ? h('button', {
                'data-testid': 'side-stub-open-card-mode',
                onClick: () => emit('open-card-mode'),
              })
              : null,
          ],
        )
      },
    }),
  }
})

vi.mock('@runtime-kit/internal/components/viewport/ScaledCanvasViewport.vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    default: defineComponent({
      name: 'ScaledCanvasViewportStub',
      setup(_, { slots }) {
        return () => h('div', { 'data-testid': 'fixed-ratio-container-stub' }, slots.default?.())
      },
    }),
  }
})

vi.mock('@/runtime-shell/layouts/CardModePanel.vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    default: defineComponent({
      name: 'CardModePanelStub',
      props: {
        pages: {
          type: Array,
          default: () => [],
        },
        currentPath: {
          type: String,
          default: '',
        },
      },
      emits: ['close', 'select'],
      setup() {
        return () => h('div', { 'data-testid': 'card-mode' })
      },
    }),
  }
})

vi.mock('@/runtime-shell/export/ExportDialog.vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    default: defineComponent({
      name: 'ExportDialogStub',
      props: {
        visible: {
          type: Boolean,
          default: false,
        },
      },
      setup() {
        return () => h('div', { 'data-testid': 'export-dialog-stub' })
      },
    }),
  }
})

vi.mock('@/runtime-shell/feedback/ErrorBoundary.vue', async () => {
  const { defineComponent, h } = await import('vue')

  return {
    default: defineComponent({
      name: 'ErrorBoundaryStub',
      setup(_, { slots }) {
        return () => h('div', { 'data-testid': 'error-boundary-stub' }, slots.default?.())
      },
    }),
  }
})

vi.mock('@/core/composables/useMenu', async () => {
  const { computed } = await import('vue')

  return {
    useMenu: () => ({
      menuConfig: computed(() => ({
        items: [],
      })),
    }),
  }
})

vi.mock('@/core/composables/usePageNavigation', async () => {
  const { computed } = await import('vue')

  return {
    usePageNavigation: () => ({
      previousPage: computed(() => null),
      nextPage: computed(() => null),
      canGoPrevious: computed(() => mockNavigationState.value.canGoPrevious),
      canGoNext: computed(() => mockNavigationState.value.canGoNext),
      totalPages: computed(() => mockNavigableRoutes.value.length),
      goToPreviousPage: previousPageSpy,
      goToNextPage: nextPageSpy,
      goToPageNumber: gotoPageSpy,
      goToFirstPage: firstPageSpy,
      goToLastPage: lastPageSpy,
      getPageTitle: vi.fn(() => '测试页面'),
      getAllNavigableRoutes: vi.fn(() => mockNavigableRoutes.value),
    }),
  }
})

vi.mock('@runtime-kit/public/composables/theme/useTheme.v1', async () => {
  const { computed } = await import('vue')

  return {
    useTheme: () => ({
      themeStyles: computed(() => ({
        '--theme-font-size-base': mockPageConfig.value.baseFontSize,
      })),
    }),
  }
})

vi.mock('@/core/services/PDFExportService', () => ({
  PDFExportService: {
    getInstance() {
      return {
        setRouter: vi.fn(),
      }
    },
  },
}))

vi.mock('@lucide/vue', async () => {
  const { defineComponent, h } = await import('vue')

  const createIconStub = (name: string) => defineComponent({
    name,
    setup() {
      return () => h('span', { 'data-testid': name })
    },
  })

  return {
    Maximize2: createIconStub('Maximize2Stub'),
    Minimize2: createIconStub('Minimize2Stub'),
    ChevronLeft: createIconStub('ChevronLeftStub'),
    ChevronRight: createIconStub('ChevronRightStub'),
    FileDown: createIconStub('FileDownStub'),
    Monitor: createIconStub('MonitorStub'),
    PanelLeft: createIconStub('PanelLeftStub'),
    PanelBottom: createIconStub('PanelBottomStub'),
    LayoutGrid: createIconStub('LayoutGridStub'),
    Timer: createIconStub('TimerStub'),
    Hand: createIconStub('HandStub'),
    Play: createIconStub('PlayStub'),
    RotateCcw: createIconStub('RotateCcwStub'),
  }
})

import ResponsiveLayout from './ResponsiveLayout.vue'

afterEach(() => {
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    value: null,
  })
  mockMenuMode.value = 'preview'
  mockPageConfig.value = {
    width: 1920,
    height: 1080,
    baseFontSize: '20px',
    iconDefaultStrokeWidth: 2,
  }
  sidebarPropSpy.mockReset()
  sidePreviewPropSpy.mockReset()
  bottomStripPropSpy.mockReset()
  mockNavigableRoutes.value = []
  mockRouteConfigs.value = []
  mockNavigationState.value = { canGoNext: false, canGoPrevious: false }
  nextPageSpy.mockReset()
  previousPageSpy.mockClear()
  gotoPageSpy.mockClear()
  firstPageSpy.mockClear()
  lastPageSpy.mockClear()
  localStorage.clear()
  document.body.innerHTML = ''
  // 键盘用例会临时补齐 jsdom 缺失的全屏 API，避免污染后续用例。
  Reflect.deleteProperty(document.documentElement, 'requestFullscreen')
})

describe('ResponsiveLayout', () => {
  it('应向侧边栏传递已解包的应用配置对象', async () => {
    mockMenuMode.value = 'text'

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    expect(() => app.mount(host)).not.toThrow()
    await nextTick()

    expect(sidebarPropSpy).toHaveBeenCalled()
    expect(sidebarPropSpy).toHaveBeenCalledWith(expect.objectContaining({
      title: '测试标题',
      features: expect.objectContaining({
        menuMode: 'text',
      }),
    }))
    expect(host.textContent).toContain('测试标题:text')

    app.unmount()
  })

  it('应支持以底部缩略图模式启动并切回侧边预览', async () => {
    mockMenuMode.value = 'bottom-preview'
    mockRouteConfigs.value = [{ path: '/', title: '首页', pageNumber: 1, meta: {} }]

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    app.mount(host)
    await nextTick()

    expect(host.querySelector('[data-testid="bottom-preview-strip-stub"]')).not.toBeNull()
    expect(host.querySelector('[data-testid="responsive-sidebar-stub"]')).toBeNull()
    expect(bottomStripPropSpy).toHaveBeenCalledWith(expect.objectContaining({
      width: 1920,
      height: 1080,
    }))
    expect(host.querySelector('.page-navigation-buttons .nav-button--mode')).toBeNull()
    expect(host.querySelector('.page-navigation-buttons .nav-button--cards')).toBeNull()

    const toggleButton = host.querySelector('[data-testid="bottom-stub-toggle-menu-mode"]') as HTMLButtonElement | null
    expect(toggleButton).not.toBeNull()

    toggleButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()

    expect(host.querySelector('[data-testid="bottom-preview-strip-stub"]')).toBeNull()
    expect(host.querySelector('[data-testid="side-preview-strip-stub"]')).not.toBeNull()
    expect(host.querySelector('[data-testid="side-stub-toggle-menu-mode"]')).not.toBeNull()
    expect(host.querySelector('[data-testid="side-stub-open-card-mode"]')).not.toBeNull()

    host.querySelector<HTMLButtonElement>('[data-testid="side-stub-open-card-mode"]')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise(resolve => window.setTimeout(resolve, 0))
    await nextTick()
    expect(host.querySelector('[data-testid="card-mode"]')).not.toBeNull()
    expect(sidePreviewPropSpy).toHaveBeenCalledWith(expect.objectContaining({
      title: '测试标题',
      features: expect.objectContaining({
        menuMode: 'preview',
      }),
    }))
    expect(host.textContent).toContain('测试标题:preview')

    app.unmount()
  })

  it('进入全屏后隐藏预览导航并挂载放映控制条，退出后恢复预览', async () => {
    mockMenuMode.value = 'bottom-preview'

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    app.mount(host)
    await nextTick()

    expect(host.querySelector('[data-testid="bottom-preview-strip-stub"]')).not.toBeNull()
    expect(host.querySelector('.canvas-navigation-buttons')).not.toBeNull()
    expect(host.querySelector('button[title="进入放映"]')).not.toBeNull()
    expect(host.querySelector('[aria-label="退出放映"]')).toBeNull()

    const previewCanvas = host.querySelector('[data-testid="fixed-ratio-container-stub"]')!
    const previewScale = Number(previewCanvas.getAttribute('scale'))

    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: document.documentElement,
    })
    document.dispatchEvent(new Event('fullscreenchange'))
    await nextTick()

    // 全屏后画布两侧的预览翻页按钮不再渲染，缩放不应继续为它们预留空间。
    const fullscreenCanvas = host.querySelector('[data-testid="fixed-ratio-container-stub"]')!
    const fullscreenScale = Number(fullscreenCanvas.getAttribute('scale'))
    expect(fullscreenScale).toBeGreaterThan(previewScale)
    expect(fullscreenScale).toBeCloseTo(
      Math.min(window.innerWidth / 1920, window.innerHeight / 1080, 3),
      5,
    )

    expect(host.querySelector('[data-testid="bottom-preview-strip-stub"]')).toBeNull()
    expect(host.querySelector('[data-testid="responsive-sidebar-stub"]')).toBeNull()
    expect(host.querySelector('.canvas-navigation-buttons')).toBeNull()
    expect(host.querySelector('.page-navigation-buttons')).toBeNull()
    expect(host.querySelector('.top-right-controls')).toBeNull()
    expect(host.querySelector('.runtime-playback-controls')).not.toBeNull()
    expect(host.querySelector('[aria-label="退出放映"]')).not.toBeNull()

    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: null,
    })
    document.dispatchEvent(new Event('fullscreenchange'))
    await nextTick()

    expect(host.querySelector('.runtime-playback-controls')).toBeNull()
    expect(host.querySelector('[data-testid="bottom-preview-strip-stub"]')).not.toBeNull()
    expect(host.querySelector('button[title="进入放映"]')).not.toBeNull()

    app.unmount()
  })

  it('全屏放映时工具栏按钮聚焦仍响应方向键翻页', async () => {
    mockMenuMode.value = 'preview'
    mockNavigationState.value.canGoNext = true

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    app.mount(host)
    await nextTick()

    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: document.documentElement,
    })
    document.dispatchEvent(new Event('fullscreenchange'))
    await nextTick()

    const exitButton = host.querySelector('[aria-label="退出放映"]') as HTMLButtonElement | null
    expect(exitButton).not.toBeNull()
    exitButton?.focus()
    expect(document.activeElement).toBe(exitButton)

    exitButton?.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }))
    expect(nextPageSpy).not.toHaveBeenCalled()

    exitButton?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
    await nextTick()
    expect(nextPageSpy).toHaveBeenCalledTimes(1)

    app.unmount()
  })

  it('全屏放映控制条可打开演讲模式并进入演讲者控制台', async () => {
    mockMenuMode.value = 'preview'
    mockNavigableRoutes.value = [{ path: '/', name: '首页', pageNumber: 1 }]
    const openMock = vi.spyOn(window, 'open').mockReturnValue({} as Window)

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
        {
          path: '/__presenter',
          component: {
            template: '<div>presenter console</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    app.mount(host)
    await nextTick()

    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: document.documentElement,
    })
    document.dispatchEvent(new Event('fullscreenchange'))
    await nextTick()

    const presenterButton = host.querySelector('button[title="演讲模式 (Shift+P)"]') as HTMLButtonElement | null
    expect(presenterButton).not.toBeNull()

    presenterButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise(resolve => window.setTimeout(resolve, 0))
    await nextTick()

    expect(openMock).toHaveBeenCalledTimes(1)
    expect(String(openMock.mock.calls[0][0])).toContain('runtimeMode=display')
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.query.runtimeMode).toBe('presenter')
    expect(router.currentRoute.value.query.channel).toBeTypeOf('string')
    expect(router.currentRoute.value.query.displayBlocked).toBeUndefined()

    app.unmount()
    openMock.mockRestore()
  })

  it('预览页工具栏可直接进入演讲模式，并按项目默认模式打开观众窗口', async () => {
    mockMenuMode.value = 'preview'
    mockNavigableRoutes.value = [{ path: '/', name: '首页', pageNumber: 1 }]
    const openMock = vi.spyOn(window, 'open').mockReturnValue({} as Window)

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
        {
          path: '/__presenter',
          component: {
            template: '<div>presenter console</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    app.mount(host)
    await nextTick()

    const presenterButton = host.querySelector<HTMLButtonElement>('button.nav-button--presenter')
    expect(presenterButton).not.toBeNull()

    presenterButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await new Promise(resolve => window.setTimeout(resolve, 0))
    await nextTick()

    expect(openMock).toHaveBeenCalledTimes(1)
    const displayUrl = String(openMock.mock.calls[0][0])
    expect(displayUrl).toContain('runtimeMode=display')
    expect(displayUrl).toContain('auto=0')
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.query.runtimeMode).toBe('presenter')

    app.unmount()
    openMock.mockRestore()
  })

  it('翻页到首页或末页边界时应展示提示', async () => {
    mockMenuMode.value = 'preview'

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    app.mount(host)
    await nextTick()

    const previousButton = host.querySelector('.nav-button--previous') as HTMLButtonElement | null
    const nextButton = host.querySelector('.nav-button--next') as HTMLButtonElement | null

    expect(previousButton).not.toBeNull()
    expect(nextButton).not.toBeNull()
    expect(previousButton?.hasAttribute('disabled')).toBe(false)
    expect(nextButton?.hasAttribute('disabled')).toBe(false)
    expect(previousButton?.getAttribute('aria-disabled')).toBe('true')
    expect(nextButton?.getAttribute('aria-disabled')).toBe('true')

    previousButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()
    expect(host.querySelector('.page-boundary-hint')?.textContent).toContain('当前已经是首页')

    nextButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()
    expect(host.querySelector('.page-boundary-hint')?.textContent).toContain('当前已经是末页')

    app.unmount()
  })

  it('应在页面内容作用域注入基础字号与间距变量', async () => {
    mockPageConfig.value = {
      width: 1280,
      height: 720,
      baseFontSize: '20px',
      iconDefaultStrokeWidth: 2,
    }

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    app.mount(host)
    await nextTick()

    const pageSource = host.querySelector('.runtime-page-print-source') as HTMLElement | null
    expect(pageSource).not.toBeNull()
    expect(pageSource?.style.getPropertyValue('--runtime-page-typography-scale')).toBe('')
    expect(pageSource?.style.getPropertyValue('--tw-font-size-base')).toBe(
      'var(--theme-font-size-base, 20px)',
    )
    expect(pageSource?.style.getPropertyValue('--tw-spacing-unit')).toBe('calc(var(--tw-font-size-base) * 0.25)')

    app.unmount()
  })

  it('页面基础字号变化时不应把页面字号变量注入 Runtime shell 容器', async () => {
    mockPageConfig.value = {
      width: 1280,
      height: 720,
      baseFontSize: '30px',
      iconDefaultStrokeWidth: 2,
    }

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    app.mount(host)
    await nextTick()

    const shellRoot = host.querySelector('.responsive-layout') as HTMLElement | null
    const pageSource = host.querySelector('.runtime-page-print-source') as HTMLElement | null
    expect(shellRoot).not.toBeNull()
    expect(pageSource).not.toBeNull()
    expect(shellRoot?.style.getPropertyValue('--theme-font-size-base')).toBe('30px')
    expect(shellRoot?.style.getPropertyValue('--runtime-page-typography-scale')).toBe('')
    expect(shellRoot?.style.getPropertyValue('--tw-font-size-base')).toBe('')
    expect(shellRoot?.style.getPropertyValue('--tw-spacing-unit')).toBe('')
    expect(pageSource?.style.getPropertyValue('--runtime-page-typography-scale')).toBe('')
    expect(pageSource?.style.getPropertyValue('--tw-font-size-base')).toBe(
      'var(--theme-font-size-base, 20px)',
    )

    app.unmount()
  })
})

describe('ResponsiveLayout 键盘快捷键', () => {
  /** 挂载布局并返回宿主与应用实例。 */
  async function mountLayout(): Promise<{ host: HTMLElement; app: ReturnType<typeof createApp> }> {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: {
            template: '<div>route content</div>',
          },
        },
      ],
    })

    await router.push('/')
    await router.isReady()

    const host = document.createElement('div')
    document.body.appendChild(host)

    const app = createApp(ResponsiveLayout)
    app.use(router)
    app.config.errorHandler = (error) => {
      throw error
    }

    app.mount(host)
    await nextTick()
    return { host, app }
  }

  /** 在 document 上派发一次键盘事件。 */
  function press(key: string, init: KeyboardEventInit = {}): KeyboardEvent {
    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
    document.dispatchEvent(event)
    return event
  }

  it('预览态支持 Home/End、数字跳页、上下键与 F 进入放映', async () => {
    mockNavigationState.value = { canGoNext: true, canGoPrevious: true }
    mockNavigableRoutes.value = [
      { path: '/', name: '首页', pageNumber: 1 },
      { path: '/second', name: '第二页', pageNumber: 2 },
    ]
    const requestFullscreen = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(document.documentElement, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreen,
    })

    const { app } = await mountLayout()

    press('Home')
    expect(firstPageSpy).toHaveBeenCalledTimes(1)

    press('End')
    expect(lastPageSpy).toHaveBeenCalledTimes(1)

    press('2')
    await nextTick()
    expect(gotoPageSpy).toHaveBeenCalledWith(2)

    press('ArrowDown')
    expect(nextPageSpy).toHaveBeenCalledTimes(1)

    press('ArrowUp')
    expect(previousPageSpy).toHaveBeenCalledTimes(1)

    press('f')
    expect(requestFullscreen).toHaveBeenCalledTimes(1)

    app.unmount()
  })

  it('放映态空格与上下键按翻页处理，Home/End 直达首末页', async () => {
    mockNavigationState.value = { canGoNext: true, canGoPrevious: true }
    mockNavigableRoutes.value = [
      { path: '/', name: '首页', pageNumber: 1 },
      { path: '/second', name: '第二页', pageNumber: 2 },
      { path: '/third', name: '第三页', pageNumber: 3 },
    ]
    const { app } = await mountLayout()

    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      value: document.documentElement,
    })
    document.dispatchEvent(new Event('fullscreenchange'))
    await nextTick()

    press(' ')
    expect(nextPageSpy).toHaveBeenCalledTimes(1)

    press('ArrowDown')
    expect(nextPageSpy).toHaveBeenCalledTimes(2)

    press('ArrowUp')
    expect(previousPageSpy).toHaveBeenCalledTimes(1)

    press('Home')
    expect(firstPageSpy).toHaveBeenCalledTimes(1)

    press('End')
    expect(lastPageSpy).toHaveBeenCalledTimes(1)

    app.unmount()
  })
})
