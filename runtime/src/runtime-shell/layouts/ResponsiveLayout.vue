<!--
  文件用途：运行时主布局，负责整项目预览的导航、全屏、翻页与 PDF 导出。
-->

<template>
  <div
    class="responsive-layout" v-bind="executionAttrs"
    :class="{ 'responsive-layout--fullscreen': isFullscreen }" :style="layoutStyles">
    <PlaybackHostBridge
      v-if="isFullscreen"
      :initial-auto-advance="playbackAutoStart"
      :presenter-available="shouldShowPresenterButton"
      @presenter="openPresenterMode"
      @exit="exitSlideshow"
    />
    <!-- 响应式侧边栏 -->
    <div v-if="isSidebarMenuVisible" class="sidebar-wrapper">
      <ResponsiveSidebar
v-if="effectiveMenuMode === 'text'" :navigation-items="processedNavigationItems"
        :app-config="sidebarAppConfig" @collapse-change="handleCollapseChange" />
      <SidePreviewStrip
v-else-if="effectiveMenuMode === 'preview'" :navigation-items="processedNavigationItems"
        :app-config="sidebarAppConfig" :mode-toggle-available="canTogglePreviewMenuMode"
        :card-mode-available="shouldShowCardModeButton" @collapse-change="handleCollapseChange"
        @toggle-menu-mode="toggleMenuMode" @open-card-mode="openCardMode" />
    </div>

    <!-- 主内容区域 -->
    <main
class="main-content" :class="{
      'main-content--collapsed': isCollapsed,
      'main-content--fullscreen': isFullscreen,
      'main-content--bottom-preview': isBottomPreviewMode
    }" :style="mainContentStyles">
      <div v-if="!isFullscreen" class="top-right-controls">
        <!-- 进入放映：全屏即放映 -->
        <button class="fullscreen-button" title="进入放映" @click.stop="enterSlideshow">
          <Maximize2 :size="20" />
        </button>
      </div>

      <!-- 页面导航按钮（仅预览态；视图切换与卡片入口在缩略图栏内） -->
      <div v-if="!isFullscreen && shouldShowTopRightPageControls" class="page-navigation-buttons">
        <!-- PDF导出按钮 -->
        <button
v-if="shouldShowPdfExportButton" class="nav-button nav-button--export"
          title="导出" @click.stop="showExportDialog">
          <FileDown :size="16" />
        </button>

        <!-- 演讲模式按钮：预览态可直接进入，观众窗口按项目默认模式起步 -->
        <button
v-if="shouldShowPresenterButton" class="nav-button nav-button--presenter"
          title="演讲模式 (Shift+P)" @click.stop="openPresenterMode">
          <Monitor :size="16" />
        </button>

        <template v-if="!isBottomPreviewMode">
          <!-- 上一页按钮 -->
          <button
class="nav-button nav-button--previous" :class="{
            'nav-button--disabled': !canGoPrevious
          }" :aria-disabled="!canGoPrevious" :title="canGoPrevious ? `上一页 ${getPageTitle(previousPage)}` : '当前已经是首页'"
            @click.stop="handlePreviousPageAction">
            <ChevronLeft :size="16" />
          </button>

          <!-- 下一页按钮 -->
          <button
class="nav-button nav-button--next" :class="{
            'nav-button--disabled': !canGoNext
          }" :aria-disabled="!canGoNext" :title="canGoNext ? `下一页 ${getPageTitle(nextPage)}` : '当前已经是末页'"
            @click.stop="handleNextPageAction">
            <ChevronRightIcon :size="16" />
          </button>
        </template>
      </div>

      <transition name="page-boundary-hint">
        <div v-if="pageBoundaryMessage" class="page-boundary-hint" role="status" aria-live="polite">
          {{ pageBoundaryMessage }}
        </div>
      </transition>

      <!-- 页面内容 -->
      <div class="page-content-wrapper">
        <div v-if="isBottomPreviewMode && !isFullscreen" class="canvas-navigation-buttons">
          <button
class="nav-button nav-button--canvas nav-button--canvas-left" :class="{
            'nav-button--disabled': !canGoPrevious
          }" :style="canvasPreviousButtonStyle" :aria-disabled="!canGoPrevious"
            :title="canGoPrevious ? `上一页 ${getPageTitle(previousPage)}` : '当前已经是首页'"
            @click.stop="handlePreviousPageAction">
            <ChevronLeft :size="18" />
          </button>

          <button
class="nav-button nav-button--canvas nav-button--canvas-right" :class="{
            'nav-button--disabled': !canGoNext
          }" :style="canvasNextButtonStyle" :aria-disabled="!canGoNext"
            :title="canGoNext ? `下一页 ${getPageTitle(nextPage)}` : '当前已经是末页'"
            @click.stop="handleNextPageAction">
            <ChevronRightIcon :size="18" />
          </button>
        </div>

        <ScaledCanvasViewport
:is-fullscreen="isFullscreen" :scale="scaleRatio" :design-width="pageViewport.width"
          :design-height="pageViewport.height">
          <ErrorBoundary>
            <RuntimePageStage :disabled="isCardModeVisible" />
          </ErrorBoundary>
        </ScaledCanvasViewport>
      </div>

    </main>

    <div
v-if="isBottomPreviewMode && !isFullscreen" class="bottom-preview-wrapper" :class="{
      'bottom-preview-wrapper--collapsed': isBottomStripCollapsed
    }">
      <BottomPreviewStrip
:collapsed="isBottomStripCollapsed" :navigation-items="processedNavigationItems"
        :page-config="pageViewport" :app-config="layoutAppConfig"
        :mode-toggle-available="canTogglePreviewMenuMode" :card-mode-available="shouldShowCardModeButton"
        @collapsed-change="handleBottomStripCollapsedChange"
        @toggle-menu-mode="toggleMenuMode" @open-card-mode="openCardMode" />
    </div>

    <!-- 导出对话框 -->
    <ExportDialog v-if="!isFullscreen" v-model:visible="isExportDialogVisible" @export-error="handleExportError" />

    <transition name="card-mode-fade">
      <CardModePanel
        v-if="isCardModeVisible && !isFullscreen"
        :pages="cardModePages"
        :current-path="router.currentRoute.value.path"
        @close="isCardModeVisible = false"
        @select="selectCardPage"
      />
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getRuntimeSession, switchRuntimeMode } from '@/core/router/runtime-session'
import { executionAttributes, provideRuntimeExecutionScope } from '@/core/execution/execution-scope'
import { readRuntimePreference, writeRuntimePreference } from '@/core/utils/runtime-preferences'
import {
  Maximize2,
  ChevronLeft,
  ChevronRight as ChevronRightIcon,
  FileDown,
  Monitor
} from '@lucide/vue'
import ResponsiveSidebar from '@/runtime-shell/layouts/ResponsiveSidebar.vue'
import SidePreviewStrip from '@/runtime-shell/layouts/SidePreviewStrip.vue'
import BottomPreviewStrip from '@/runtime-shell/layouts/BottomPreviewStrip.vue'
import CardModePanel from '@/runtime-shell/layouts/CardModePanel.vue'
import ScaledCanvasViewport from '@runtime-kit/internal/components/viewport/ScaledCanvasViewport.vue'
import ExportDialog from '@/runtime-shell/export/ExportDialog.vue'
import PlaybackHostBridge from '@/runtime-shell/playback/PlaybackHostBridge.vue'
import RuntimePageStage from '@/runtime-shell/transitions/RuntimePageStage.vue'
import ErrorBoundary from '@/runtime-shell/feedback/ErrorBoundary.vue'
import { useMenu } from '@/core/composables/useMenu'
import { usePageNavigation } from '@/core/composables/usePageNavigation'
import { PDFExportService } from '@/core/services/PDFExportService'
import { appConfig as runtimeAppConfig, appPageConfig, playbackConfig, routeConfigs, type RuntimeMenuMode } from '@/core/utils/config'
import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'
import {
  createPresenterChannelId,
  normalizePresenterRoutePath,
} from '@/runtime-shell/presenter/presenter-url'
import { buildPresenterPages, writePresenterInitialNavigateMessage } from '@/runtime-shell/presenter/usePresenterController'
import { openPresenterDisplayWindow } from '@/runtime-shell/presenter/presenter-window'
import {
  isEditableKeyboardTarget,
  resolveKeyboardCommand,
  type KeyboardContext,
} from '@/runtime-shell/keyboard/keyboard-map'

// 应用配置已迁移到 @/config/app.config.ts

/**
 * 响应式状态
 */
const router = useRouter()
const session = getRuntimeSession(router)
const isCollapsed = session.collapsed
// 只有根元素全屏才是放映；视频等页面内元素全屏不改变放映壳。
const isFullscreen = ref(document.fullscreenElement === document.documentElement)
// 缩放容器已抽取到独立组件处理窗口尺寸
const isExportDialogVisible = ref(false)
const isCardModeVisible = computed({
  get: () => session.mode.value === 'cards',
  set: value => { void switchRuntimeMode(router, value ? 'cards' : 'normal') },
})
// 卡片模式的主画布被卡片面板覆盖，收紧为交互预览，禁止自动推进与自动播放。
const execution = provideRuntimeExecutionScope(computed(() => isCardModeVisible.value ? 'interactive-preview' : 'presentation'))
const executionAttrs = computed(() => executionAttributes(execution.value))
const pageBoundaryMessage = ref('')
let pageBoundaryMessageTimer: number | undefined

/** 当前键盘上下文：全屏即放映，卡片遮罩优先于预览。 */
const keyboardContext = computed<KeyboardContext>(() => {
  if (isFullscreen.value) {
    return 'slideshow'
  }
  return isCardModeVisible.value ? 'cards' : 'preview'
})

/** 数字跳页缓冲：总页数超过 9 时等待后续数字，否则立即跳转。 */
let gotoPageBuffer = ''
let gotoPageTimer: number | undefined
const GOTO_PAGE_BUFFER_DURATION = 600

/**
 * 固定比例缩放配置
 */
// 侧边栏宽度（与容器旧逻辑保持一致）
const SIDEBAR_EXPANDED_WIDTH = 280
const SIDEBAR_COLLAPSED_WIDTH = 80
// 非全屏主内容区域的内边距合计（与样式 padding: 2rem 保持一致 -> 2rem * 2 = 64）
const PADDING_SIZE = 64
const BOTTOM_PREVIEW_RAIL_HEIGHT = 208
const BOTTOM_PREVIEW_COLLAPSED_HEIGHT = 36
const BOTTOM_PREVIEW_BOTTOM_OFFSET = 16
const BOTTOM_PREVIEW_PAGE_GAP = 0
const BOTTOM_PREVIEW_SIDE_CONTROL_SPACE = 104
const CANVAS_NAV_BUTTON_SIZE = 44
const CANVAS_NAV_BUTTON_GAP = 24
const PAGE_BOUNDARY_TOAST_DURATION = 1600

/**
 * 当前路由和路由器
 */
/**
 * 使用菜单系统
 */
const { menuConfig } = useMenu()

/**
 * 使用页面导航系统
 */
const {
  previousPage,
  nextPage,
  canGoPrevious,
  canGoNext,
  totalPages,
  goToPreviousPage,
  goToNextPage,
  goToPageNumber,
  goToFirstPage,
  goToLastPage,
  getPageTitle,
  getAllNavigableRoutes
} = usePageNavigation()

/**
 * 使用主题系统
 */
const { themeStyles } = useTheme()

/**
 * 计算属性：是否显示PDF导出按钮
 */
const layoutAppConfig = computed(() => runtimeAppConfig.value.app)

/**
 * 当前配置声明的菜单模式。
 * @returns 合法的菜单模式；未知值统一回退到 text
 */
const configuredMenuMode = computed<RuntimeMenuMode>(() => {
  const menuMode = layoutAppConfig.value.features?.menuMode
  if (menuMode === 'preview' || menuMode === 'bottom-preview' || menuMode === 'text') {
    return menuMode
  }
  return 'text'
})

/**
 * 当前运行时生效的菜单模式。
 */
const savedMenuMode = readRuntimePreference('menuMode', configuredMenuMode.value)
const currentMenuMode = ref<RuntimeMenuMode>(['text', 'preview', 'bottom-preview'].includes(savedMenuMode) ? savedMenuMode as RuntimeMenuMode : configuredMenuMode.value)
watch(currentMenuMode, value => writeRuntimePreference('menuMode', value))
const isBottomStripCollapsed = session.bottomCollapsed

/** 进入放映时的初始自动推进模式，来自项目 auto_start。 */
const playbackAutoStart = computed(() => playbackConfig.value.autoStart)

/**
 * 当前布局实际使用的菜单模式；全屏放映不显示任何预览导航。
 */
const effectiveMenuMode = computed<RuntimeMenuMode>(() => currentMenuMode.value)

/**
 * 是否允许在侧栏预览与底部缩略图之间切换。
 */
const canTogglePreviewMenuMode = computed(() => {
  return configuredMenuMode.value === 'preview' || configuredMenuMode.value === 'bottom-preview'
})

/**
 * 当前是否处于底部缩略图模式。
 */
const isBottomPreviewMode = computed(() => effectiveMenuMode.value === 'bottom-preview')

/**
 * 当前是否需要显示左侧边栏。
 */
const isSidebarMenuVisible = computed(() => {
  return !isFullscreen.value && effectiveMenuMode.value !== 'bottom-preview'
})

/**
 * 当前底栏实际占用的高度。
 * @returns 展开态为完整缩略图高度，收起态仅保留折叠把手
 */
const effectiveBottomPreviewRailHeight = computed(() => {
  return isBottomStripCollapsed.value ? BOTTOM_PREVIEW_COLLAPSED_HEIGHT : BOTTOM_PREVIEW_RAIL_HEIGHT
})

/**
 * 侧边栏渲染时实际使用的菜单模式。
 * @returns 仅返回 ResponsiveSidebar 可识别的 text / preview
 */
const sidebarMenuMode = computed<'text' | 'preview'>(() => {
  return effectiveMenuMode.value === 'preview' ? 'preview' : 'text'
})

/**
 * 传递给侧边栏的应用配置。
 * 关键约束：
 * 1. 侧边栏只识别 text / preview 两种布局；
 * 2. 底部缩略图模式隐藏侧边栏，因此需要在显示侧边栏时同步成 preview。
 */
const sidebarAppConfig = computed(() => ({
  ...layoutAppConfig.value,
  features: {
    ...(layoutAppConfig.value.features || {}),
    menuMode: sidebarMenuMode.value,
  },
}))

/**
 * 布局层 CSS 变量，统一同步主题样式与缩略图占位尺寸。
 */
const layoutStyles = computed(() => ({
  ...themeStyles.value,
  '--bottom-preview-rail-height': `${effectiveBottomPreviewRailHeight.value}px`,
  '--bottom-preview-shell-height': `${effectiveBottomPreviewRailHeight.value}px`,
  '--bottom-preview-side-space': `${BOTTOM_PREVIEW_SIDE_CONTROL_SPACE}px`,
  '--bottom-preview-reserved-gap': `${BOTTOM_PREVIEW_BOTTOM_OFFSET + BOTTOM_PREVIEW_PAGE_GAP}px`,
}))

/**
 * 主内容区样式。
 * 关键约束：
 * 1. 非全屏底栏模式下必须让出底栏壳体和间距；
 * 2. 全屏态保持原始高度，不为底栏悬浮层预留空间。
 */
const mainContentStyles = computed(() => {
  if (!isBottomPreviewMode.value || isFullscreen.value) {
    return undefined
  }

  const reservedHeight = effectiveBottomPreviewRailHeight.value + BOTTOM_PREVIEW_BOTTOM_OFFSET + BOTTOM_PREVIEW_PAGE_GAP
  return {
    height: `calc(100vh - ${reservedHeight}px)`,
  }
})

/**
 * 计算属性：是否显示 PDF 导出按钮。
 * 关键约束：
 * 1. 模板不要直接读取导入的 ref；
 * 2. 统一在本地 computed 中解包，避免生产构建后把 ref 本体传给子组件。
 */
const shouldShowPdfExportButton = computed(() => {
  return layoutAppConfig.value.features?.showPdfExportButton ?? true
})

/**
 * 是否显示演讲模式入口。
 * @returns 当前项目存在可导航页面时允许进入演讲模式
 */
const shouldShowPresenterButton = computed(() => {
  return getAllNavigableRoutes().length > 0
})

/**
 * 是否显示卡片模式入口。
 * @returns 当前项目是否存在可展示的页面卡片
 */
const shouldShowCardModeButton = computed(() => {
  return buildPresenterPages(routeConfigs.value).length > 0
})

/**
 * 卡片模式使用与演讲者模式一致的页面目录，保证两种浏览入口的页面顺序一致。
 */
const cardModePages = computed(() => buildPresenterPages(routeConfigs.value))

/**
 * 是否显示右上角的二级操作区。
 * 关键约束：视图切换与卡片入口已移入缩略图栏，这里只保留导出、演讲和翻页。
 */
const shouldShowTopRightPageControls = computed(() => {
  return shouldShowPdfExportButton.value
    || shouldShowPresenterButton.value
    || !isBottomPreviewMode.value
})

/**
 * 当前项目的页面画布尺寸。
 */
const pageViewport = computed(() => appPageConfig.value)

/**
 * 页面内容作用域样式。
 * 关键约束：覆盖页面内 Tailwind 字号基准，不影响运行时侧栏、弹窗等外壳 UI。
 */


/**
 * 底部缩略图模式下上一页按钮的位置。
 * @returns 与画布左侧边缘保持固定间距的定位样式
 */
const canvasPreviousButtonStyle = computed(() => {
  const halfCanvasWidth = (pageViewport.value.width * scaleRatio.value) / 2

  return {
    left: `max(1rem, calc(50% - ${halfCanvasWidth}px - ${CANVAS_NAV_BUTTON_SIZE + CANVAS_NAV_BUTTON_GAP}px))`,
  }
})

/**
 * 底部缩略图模式下下一页按钮的位置。
 * @returns 与画布右侧边缘保持固定间距的定位样式
 */
const canvasNextButtonStyle = computed(() => {
  const halfCanvasWidth = (pageViewport.value.width * scaleRatio.value) / 2

  return {
    right: `max(1rem, calc(50% - ${halfCanvasWidth}px - ${CANVAS_NAV_BUTTON_SIZE + CANVAS_NAV_BUTTON_GAP}px))`,
  }
})

/**
 * 计算属性：处理后的导航项
 */
const processedNavigationItems = computed(() => {
  try {
    return menuConfig?.value?.items || []
  } catch (error) {
    console.warn('获取导航项时出错:', error)
    return []
  }
})

/**
 * 计算属性：缩放比例和样式
 */
// 缩放计算迁移至布局组件，由容器组件仅负责应用传入的缩放比例

/**
 * 窗口尺寸变化处理
 */
/**
 * 屏幕尺寸
 */
const screenWidth = ref(window.innerWidth)
const screenHeight = ref(window.innerHeight)

/**
 * 窗口尺寸变化处理
 * 功能：更新屏幕尺寸以触发缩放计算
 */
const handleResize = (): void => {
  screenWidth.value = window.innerWidth
  screenHeight.value = window.innerHeight
}

/**
 * 处理侧边栏折叠状态变化
 */
const handleCollapseChange = (collapsed: boolean): void => {
  isCollapsed.value = collapsed
}

/**
 * 切换菜单显示模式。
 * 关键约束：仅允许 preview 与 bottom-preview 之间互切。
 */
const toggleMenuMode = (): void => {
  if (!canTogglePreviewMenuMode.value) {
    return
  }

  currentMenuMode.value = currentMenuMode.value === 'bottom-preview' ? 'preview' : 'bottom-preview'
}

/**
 * 同步底栏收起状态。
 * @param collapsed 底栏是否收起
 */
const handleBottomStripCollapsedChange = (collapsed: boolean): void => {
  isBottomStripCollapsed.value = collapsed
}

/**
 * 展示翻页边界提示。
 * @param message 当前需要展示的首页/末页提示文案
 */
const showPageBoundaryMessage = (message: string): void => {
  if (pageBoundaryMessageTimer !== undefined) {
    window.clearTimeout(pageBoundaryMessageTimer)
  }

  pageBoundaryMessage.value = message
  pageBoundaryMessageTimer = window.setTimeout(() => {
    pageBoundaryMessage.value = ''
    pageBoundaryMessageTimer = undefined
  }, PAGE_BOUNDARY_TOAST_DURATION)
}

/**
 * 执行上一页动作。
 * 关键约束：边界页仍允许按钮点击，用布局内提示明确当前已在首页。
 */
const handlePreviousPageAction = async (): Promise<void> => {
  if (!canGoPrevious.value) {
    showPageBoundaryMessage('当前已经是首页')
    return
  }

  await goToPreviousPage()
}

/**
 * 执行下一页动作。
 * 关键约束：边界页仍允许按钮点击，用布局内提示明确当前已在末页。
 */
const handleNextPageAction = async (): Promise<void> => {
  if (!canGoNext.value) {
    showPageBoundaryMessage('当前已经是末页')
    return
  }

  await goToNextPage()
}

/**
 * 进入全屏放映。
 * 关键约束：全屏请求必须由 Runtime 窗口内的用户手势触发；失败时留在预览并提示。
 */
const enterSlideshow = async (): Promise<void> => {
  if (document.fullscreenElement === document.documentElement) return
  try {
    await document.documentElement.requestFullscreen()
    isFullscreen.value = document.fullscreenElement === document.documentElement
    if (!isFullscreen.value) {
      showPageBoundaryMessage('浏览器未进入全屏，仍在预览。')
    }
  } catch (error) {
    console.error('进入全屏放映失败:', error)
    isFullscreen.value = false
    showPageBoundaryMessage('无法进入全屏放映，请允许浏览器全屏后重试。')
  }
}

/**
 * 退出全屏并结束本次放映。
 */
const exitSlideshow = async (): Promise<void> => {
  if (!document.fullscreenElement) {
    isFullscreen.value = false
    return
  }
  try {
    if (typeof document.exitFullscreen === 'function') {
      await document.exitFullscreen()
    }
    isFullscreen.value = document.fullscreenElement === document.documentElement
  } catch (error) {
    console.error('退出全屏放映失败:', error)
    showPageBoundaryMessage('退出全屏失败，请按 Esc 或使用浏览器退出全屏。')
  }
}

/** 提示目标页码不存在。 */
function showMissingPage(pageNumber: number): void {
  showPageBoundaryMessage(`没有第 ${pageNumber} 页`)
}

/**
 * 清除数字跳页缓冲，不执行跳转。
 * 关键约束：用户在缓冲期间改按其他键时，视为放弃本次输入。
 */
function resetGotoPageBuffer(): void {
  if (gotoPageTimer !== undefined) {
    window.clearTimeout(gotoPageTimer)
    gotoPageTimer = undefined
  }
  gotoPageBuffer = ''
}

/** 提交数字跳页缓冲；页码越界时给出提示。 */
async function commitGotoPageBuffer(): Promise<void> {
  const raw = gotoPageBuffer
  resetGotoPageBuffer()
  if (!raw) {
    return
  }
  const pageNumber = Number(raw)
  const jumped = await goToPageNumber(pageNumber)
  if (!jumped) {
    showMissingPage(pageNumber)
  }
}

/**
 * 处理数字键跳页。
 * 关键约束：总页数不超过 9 时立即跳转；超过 9 时缓冲 600ms，支持输入两位数。
 * @param digit 数字键对应的值
 */
function handleGotoPageDigit(digit: number): void {
  if (totalPages.value <= 9) {
    if (digit === 0) {
      return
    }
    void goToPageNumber(digit).then((jumped) => {
      if (!jumped) {
        showMissingPage(digit)
      }
    })
    return
  }
  if (gotoPageBuffer.length >= 2) {
    gotoPageBuffer = ''
  }
  gotoPageBuffer += String(digit)
  showPageBoundaryMessage(`跳转到第 ${gotoPageBuffer} 页…`)
  if (gotoPageTimer !== undefined) {
    window.clearTimeout(gotoPageTimer)
  }
  gotoPageTimer = window.setTimeout(() => {
    void commitGotoPageBuffer()
  }, GOTO_PAGE_BUFFER_DURATION)
}

/**
 * 键盘事件处理。
 * 键位映射统一来自 keyboard-map，这里只负责上下文判断与动作执行。
 */
const handleKeydown = (event: KeyboardEvent): void => {
  if (isEditableKeyboardTarget(event.target)) {
    return
  }

  const command = resolveKeyboardCommand(event, keyboardContext.value)
  if (!command) {
    return
  }

  // 焦点停留在按钮/链接上时，空格保留原生激活；其余键仍用于放映控制。
  const target = event.target as HTMLElement
  const interactiveTarget = target.tagName === 'BUTTON' || target.tagName === 'A'
  if (command.action === 'next-page' && event.key === ' ' && interactiveTarget) {
    return
  }

  if (command.action === 'goto-page') {
    event.preventDefault()
    handleGotoPageDigit(command.pageNumber ?? 0)
    return
  }

  // 数字缓冲期间按下其他键时，视为放弃本次跳页输入，避免异步跳转与翻页竞争。
  resetGotoPageBuffer()
  event.preventDefault()

  switch (command.action) {
    case 'next-page':
      void handleNextPageAction()
      break
    case 'previous-page':
      void handlePreviousPageAction()
      break
    case 'first-page':
      void goToFirstPage().then((jumped) => {
        if (!jumped) {
          showPageBoundaryMessage('当前没有可放映页面')
        }
      })
      break
    case 'last-page':
      void goToLastPage().then((jumped) => {
        if (!jumped) {
          showPageBoundaryMessage('当前没有可放映页面')
        }
      })
      break
    case 'open-card-mode':
      openCardMode()
      break
    case 'enter-slideshow':
      void enterSlideshow()
      break
    case 'open-presenter':
      openPresenterMode()
      break
    case 'close-card-mode':
      isCardModeVisible.value = false
      break
  }
}

/**
 * 全屏状态变化监听。
 * 关键约束：其他元素全屏期间保持当前放映状态，退出到无全屏元素才算结束放映。
 */
const handleFullscreenChange = (): void => {
  const element = document.fullscreenElement
  if (element === document.documentElement) {
    isFullscreen.value = true
    isCardModeVisible.value = false
    isExportDialogVisible.value = false
    return
  }
  if (!element) {
    isFullscreen.value = false
  }
}

/**
 * 显示导出对话框
 */
const showExportDialog = (): void => {
  isExportDialogVisible.value = true
}

/**
 * 打开卡片模式。
 */
const openCardMode = (): void => {
  if (shouldShowCardModeButton.value) {
    isCardModeVisible.value = true
  }
}

/**
 * 从卡片模式跳转到指定页面，关闭卡片面板并进入全屏模式。
 * @param path 目标页面路径
 */
const selectCardPage = async (path: string): Promise<void> => {
  await router.push({
    path,
    query: { ...router.currentRoute.value.query, runtimeMode: 'normal' },
  })
  await enterSlideshow()
}

/**
 * 打开演讲模式；主窗口退出全屏放映，观众窗口接管唯一调度。
 */
const openPresenterMode = (): void => {
  if (!shouldShowPresenterButton.value) {
    showPageBoundaryMessage('当前项目没有可演讲页面')
    return
  }

  // 先停住本窗口推进和媒体，再把当前页和自动/手动模式交给观众窗口。
  session.pausePlayback?.()
  const autoAdvance = session.playbackAutoAdvance?.() ?? playbackConfig.value.autoStart
  void exitSlideshow()
  const currentPath = normalizePresenterRoutePath(router.currentRoute.value.path)
  const channelId = createPresenterChannelId()
  const displayWindow = openPresenterDisplayWindow(channelId, currentPath, autoAdvance)
  writePresenterInitialNavigateMessage(channelId, currentPath, autoAdvance)

  const presenterQuery: Record<string, string> = {
    channel: channelId,
    route: currentPath,
  }
  if (!displayWindow) {
    presenterQuery.displayBlocked = '1'
  }

  void router.push({
    path: currentPath,
    query: { ...router.currentRoute.value.query, ...presenterQuery, route: undefined, runtimeMode: 'presenter' },
  })
}

/**
 * 处理导出错误事件
 * @param error 错误信息
 */
const handleExportError = (error: Error): void => {
  console.error('导出失败:', error)
}

/**
 * 组件挂载
 */
onMounted(() => {
  // 设置PDF导出服务的路由实例
  const pdfExportService = PDFExportService.getInstance()
  pdfExportService.setRouter(router)
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('keydown', handleKeydown)

  // 初始化窗口尺寸并监听变化，用于缩放计算
  handleResize()
  window.addEventListener('resize', handleResize)
})

watch(
  configuredMenuMode,
  (menuMode) => {
    if (!readRuntimePreference('menuMode', '')) currentMenuMode.value = menuMode
  },
  { immediate: true }
)

/**
 * 监听侧边栏状态变化，重新计算缩放比例
 */
watch([isCollapsed, isFullscreen], () => {
  // 状态变化时触发重新计算
  // 缩放比例会通过计算属性自动更新
}, { immediate: true })

/**
 * 组件卸载
 */
onUnmounted(() => {
  if (pageBoundaryMessageTimer !== undefined) {
    window.clearTimeout(pageBoundaryMessageTimer)
  }
  resetGotoPageBuffer()

  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  document.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', handleResize)
})

/**
 * 计算缩放比例
 * 说明：根据屏幕尺寸与布局占位计算最适合的等比缩放比例，最大不超过3倍
 */
const scaleRatio = computed(() => {
  const sidebarWidth = isSidebarMenuVisible.value
    ? (isCollapsed.value ? SIDEBAR_COLLAPSED_WIDTH : SIDEBAR_EXPANDED_WIDTH)
    : 0
  const reservedBottomHeight = isBottomPreviewMode.value
    ? (isFullscreen.value ? 0 : effectiveBottomPreviewRailHeight.value + BOTTOM_PREVIEW_BOTTOM_OFFSET + BOTTOM_PREVIEW_PAGE_GAP)
    : 0
  const reservedSideWidth = isBottomPreviewMode.value && !isFullscreen.value
    ? BOTTOM_PREVIEW_SIDE_CONTROL_SPACE * 2
    : 0
  let availableWidth: number
  let availableHeight: number

  if (isFullscreen.value) {
    availableWidth = screenWidth.value - reservedSideWidth
    availableHeight = screenHeight.value - reservedBottomHeight
  } else {
    availableWidth = screenWidth.value - sidebarWidth - PADDING_SIZE - reservedSideWidth
    availableHeight = screenHeight.value - PADDING_SIZE - reservedBottomHeight
  }

  const scaleX = availableWidth / pageViewport.value.width
  const scaleY = availableHeight / pageViewport.value.height
  return Math.min(scaleX, scaleY, 3)
})
</script>

<style scoped>
/* 响应式布局容器 - 固定比例模式 */
.responsive-layout {
  position: relative;
  display: flex;
  height: 100vh;
  background-color: #f8fafc;
  transition: background-color 0.3s ease;
  overflow: hidden;
}

/* 全屏模式下的布局 */
.responsive-layout--fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 9999;
  background: white;
}

/* 侧边栏包装器 */
.sidebar-wrapper {
  position: relative;
  z-index: 100;
}

/* 主内容区域 - 固定比例缩放模式 */
.main-content {
  position: relative;
  width: 100vw;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: margin-left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  background: #f8fafc;
  padding: 2rem;
  box-sizing: border-box;
}

.main-content--bottom-preview {
  align-items: stretch;
}

.top-right-controls {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 103;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.fullscreen-button {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  color: rgba(0, 0, 0, 0.6);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  backdrop-filter: blur(8px);
}

/* 按钮悬停效果 */
.fullscreen-button:hover {
  opacity: 1;
  transform: scale(1.05);
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(0, 0, 0, 0.9);
  color: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* 页面导航按钮 */
.page-navigation-buttons {
  position: fixed;
  top: 4rem;
  right: 1rem;
  z-index: 101;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.page-boundary-hint {
  position: fixed;
  top: 1.25rem;
  left: 50%;
  z-index: 140;
  max-width: min(420px, calc(100vw - 2rem));
  transform: translateX(-50%);
  padding: 0.625rem 0.875rem;
  border: 1px solid rgba(30, 64, 175, 0.18);
  border-radius: 0.5rem;
  background: rgba(239, 246, 255, 0.96);
  color: #1e3a8a;
  font-size: 13px;
  line-height: 1.4;
  text-align: center;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(10px);
  pointer-events: none;
}

.page-boundary-hint-enter-active,
.page-boundary-hint-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.page-boundary-hint-enter-from,
.page-boundary-hint-leave-to {
  opacity: 0;
  transform: translate(-50%, -6px);
}

/* 导航按钮样式 */
.nav-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 6px;
  color: rgba(0, 0, 0, 0.6);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  backdrop-filter: blur(8px);
}

.nav-button:hover:not(.nav-button--disabled) {
  transform: scale(1.05);
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(0, 0, 0, 0.9);
  color: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.nav-button--disabled {
  opacity: 0.3;
  cursor: not-allowed;
  transform: none !important;
}

.nav-button--disabled:hover {
  background: rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(0, 0, 0, 0.1);
  color: rgba(0, 0, 0, 0.6);
  box-shadow: none;
}

/* 主内容区域全屏状态 */
.main-content--fullscreen {
  margin-left: 0;
  width: 100vw;
  height: 100vh;
  position: relative;
  z-index: 99;
  padding: 0;
  /* 全屏模式下不设置padding，让内容完全占满屏幕 */
  /* 在全屏模式下保持居中对齐 */
  justify-content: center;
  align-items: center;
}

/* 页面内容 - 固定比例缩放容器 */
.page-content-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.runtime-page-print-source {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.runtime-page-print-source > * {
  width: 100%;
  height: 100%;
}

.canvas-navigation-buttons {
  position: absolute;
  inset: 0;
  z-index: 102;
  pointer-events: none;
}

/* 底部缩略图模式下的画布翻页按钮：使用 top 计算垂直居中，禁用 hover 缩放与位移动画，避免鼠标划入时下移导致失焦 */
.nav-button--canvas {
  position: absolute;
  top: calc(50% - 22px);
  width: 44px;
  height: 44px;
  border-radius: 999px;
  transform: none;
  pointer-events: auto;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.12);
}

.nav-button--canvas:hover:not(.nav-button--disabled) {
  transform: none;
}

.bottom-preview-wrapper {
  position: absolute;
  left: 1rem;
  right: 1rem;
  bottom: 1rem;
  height: var(--bottom-preview-shell-height);
  box-sizing: border-box;
  z-index: 102;
  padding: 0.625rem;
  border-radius: 1.25rem;
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid rgba(148, 163, 184, 0.28);
  box-shadow: 0 22px 40px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(18px);
}

.bottom-preview-wrapper--collapsed {
  left: 50%;
  right: auto;
  height: var(--bottom-preview-shell-height);
  transform: translateX(-50%);
  padding: 0;
  background: transparent;
  border: none;
  box-shadow: none;
  backdrop-filter: none;
}

/* --- 卡片模式淡入淡出动画 --- */
.card-mode-fade-enter-active,
.card-mode-fade-leave-active {
  transition: opacity 0.18s ease-out;
}

.card-mode-fade-enter-from,
.card-mode-fade-leave-to {
  opacity: 0;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .page-content-wrapper {
    padding: 1rem;
  }

  .bottom-preview-wrapper {
    left: 0.75rem;
    right: 0.75rem;
    bottom: 0.75rem;
  }

  .bottom-preview-wrapper--collapsed {
    left: 50%;
    right: auto;
  }
}
</style>
