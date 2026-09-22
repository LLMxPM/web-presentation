<!--
  文件用途：运行时主布局，负责整项目预览的导航、全屏、翻页与 PDF 导出。
-->

<template>
  <div class="responsive-layout" :class="{ 'responsive-layout--fullscreen': isFullscreen }" :style="layoutStyles">
    <!-- 响应式侧边栏 -->
    <div
v-if="isSidebarMenuVisible" class="sidebar-wrapper" :class="{
      'sidebar-wrapper--fullscreen': isFullscreen,
      'sidebar-wrapper--fullscreen-hover': isFullscreen && isSidebarHovered
    }" @mouseenter="handleSidebarMouseEnter" @mouseleave="handleSidebarMouseLeave">
      <ResponsiveSidebar
v-if="effectiveMenuMode === 'text'" :navigation-items="processedNavigationItems"
        :app-config="sidebarAppConfig" @collapse-change="handleCollapseChange" />
      <SidePreviewStrip
v-else-if="effectiveMenuMode === 'preview'" :navigation-items="processedNavigationItems"
        :app-config="sidebarAppConfig" @collapse-change="handleCollapseChange" />
    </div>

    <!-- 全屏模式下的左侧悬停触发区域 -->
    <div
v-if="isFullscreen && isSidebarMenuVisible" class="fullscreen-sidebar-trigger"
      @mouseenter="handleSidebarMouseEnter" @mouseleave="handleSidebarMouseLeave"></div>

    <!-- 全屏模式下的底栏悬停触发区域 -->
    <div
v-if="isFullscreen && isBottomPreviewMode" class="fullscreen-bottom-preview-trigger"
      @mouseenter="handleBottomPreviewMouseEnter" @mouseleave="handleBottomPreviewMouseLeave"></div>

    <!-- 主内容区域 -->
    <main
class="main-content" :class="{
      'main-content--collapsed': isCollapsed,
      'main-content--fullscreen': isFullscreen,
      'main-content--bottom-preview': isBottomPreviewMode
    }" :style="mainContentStyles">
      <!-- 全屏模式下的右上角悬停触发区域 -->
      <div
v-if="isFullscreen" class="fullscreen-button-trigger" @mouseenter="handleFullscreenButtonMouseEnter"
        @mouseleave="handleFullscreenButtonMouseLeave"></div>

      <div
class="top-right-controls" :class="{
        'top-right-controls--fullscreen': isFullscreen,
        'top-right-controls--visible': isTopRightControlsVisible
      }" @mouseenter="handleFullscreenButtonMouseEnter" @mouseleave="handleFullscreenButtonMouseLeave">
        <!-- 全屏切换按钮 -->
        <button
class="fullscreen-button" :class="{
          'fullscreen-button--fullscreen': isFullscreen
        }" :title="isFullscreen ? '退出全屏' : '进入全屏'" @click.stop="toggleFullscreen">
          <Minimize2 v-if="isFullscreen" :size="20" />
          <Maximize2 v-else :size="20" />
        </button>
      </div>

      <!-- 页面导航按钮 -->
      <div
v-if="shouldShowTopRightPageControls || canTogglePreviewMenuMode" class="page-navigation-buttons" :class="{
        'page-navigation-buttons--fullscreen': isFullscreen,
        'page-navigation-buttons--visible': isTopRightControlsVisible
      }" @mouseenter="handleFullscreenButtonMouseEnter" @mouseleave="handleFullscreenButtonMouseLeave">
        <!-- 预览模式切换按钮 -->
        <button
v-if="canTogglePreviewMenuMode" class="nav-button nav-button--mode"
          :class="{ 'nav-button--fullscreen': isFullscreen }" :title="menuModeToggleTitle" @click.stop="toggleMenuMode">
          <PanelLeft v-if="currentMenuMode === 'bottom-preview'" :size="16" />
          <PanelBottom v-else :size="16" />
        </button>

        <!-- PDF导出按钮 -->
        <button
v-if="shouldShowPdfExportButton" class="nav-button nav-button--export" :class="{
          'nav-button--fullscreen': isFullscreen
        }" title="导出" @click.stop="showPDFExportDialog">
          <FileDown :size="16" />
        </button>

        <!-- 演讲模式按钮 -->
        <button
          v-if="shouldShowPresenterButton"
          class="nav-button nav-button--presenter"
          :class="{ 'nav-button--fullscreen': isFullscreen }"
          title="演讲模式 (Shift+P)"
          @click.stop="openPresenterMode"
        >
          <Monitor :size="16" />
        </button>

        <!-- 卡片模式按钮 -->
        <button
          v-if="shouldShowCardModeButton"
          class="nav-button nav-button--cards"
          :class="{ 'nav-button--fullscreen': isFullscreen }"
          title="卡片模式"
          @click.stop="openCardMode"
        >
          <LayoutGrid :size="16" />
        </button>

        <template v-if="!isBottomPreviewMode">
          <!-- 上一页按钮 -->
          <button
class="nav-button nav-button--previous" :class="{
            'nav-button--disabled': !canGoPrevious,
            'nav-button--fullscreen': isFullscreen
          }" :aria-disabled="!canGoPrevious" :title="canGoPrevious ? `上一页 ${getPageTitle(previousPage)}` : '当前已经是首页'"
            @click.stop="handlePreviousPageAction">
            <ChevronLeft :size="16" />
          </button>

          <!-- 下一页按钮 -->
          <button
class="nav-button nav-button--next" :class="{
            'nav-button--disabled': !canGoNext,
            'nav-button--fullscreen': isFullscreen
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
        <div v-if="isBottomPreviewMode" class="canvas-navigation-buttons">
          <button
class="nav-button nav-button--canvas nav-button--canvas-left" :class="{
            'nav-button--disabled': !canGoPrevious,
            'nav-button--fullscreen': isFullscreen
          }" :style="canvasPreviousButtonStyle" :aria-disabled="!canGoPrevious"
            :title="canGoPrevious ? `上一页 ${getPageTitle(previousPage)}` : '当前已经是首页'"
            @click.stop="handlePreviousPageAction">
            <ChevronLeft :size="18" />
          </button>

          <button
class="nav-button nav-button--canvas nav-button--canvas-right" :class="{
            'nav-button--disabled': !canGoNext,
            'nav-button--fullscreen': isFullscreen
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
v-if="isBottomPreviewMode" class="bottom-preview-wrapper" :class="{
      'bottom-preview-wrapper--collapsed': isBottomStripCollapsed,
      'bottom-preview-wrapper--fullscreen': isFullscreen,
      'bottom-preview-wrapper--fullscreen-hover': isFullscreen && isBottomPreviewHovered
    }" @mouseenter="handleBottomPreviewMouseEnter" @mouseleave="handleBottomPreviewMouseLeave">
      <BottomPreviewStrip
:collapsed="isBottomStripCollapsed" :navigation-items="processedNavigationItems"
        :page-config="pageViewport" :app-config="layoutAppConfig" @collapsed-change="handleBottomStripCollapsedChange" />
    </div>

    <!-- PDF导出对话框 -->
    <PDFExportDialog
v-model:visible="isPDFExportDialogVisible" @export-start="handlePDFExportStart"
      @export-complete="handlePDFExportComplete" @export-error="handlePDFExportError" />

    <transition name="card-mode-fade">
      <CardModePanel
        v-if="isCardModeVisible"
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
import { readRuntimePreference, writeRuntimePreference } from '@/core/utils/runtime-preferences'
import {
  Maximize2,
  Minimize2,
  ChevronLeft,
  ChevronRight as ChevronRightIcon,
  FileDown,
  LayoutGrid,
  Monitor,
  PanelLeft,
  PanelBottom
} from '@lucide/vue'
import ResponsiveSidebar from '@/runtime-shell/layouts/ResponsiveSidebar.vue'
import SidePreviewStrip from '@/runtime-shell/layouts/SidePreviewStrip.vue'
import BottomPreviewStrip from '@/runtime-shell/layouts/BottomPreviewStrip.vue'
import CardModePanel from '@/runtime-shell/layouts/CardModePanel.vue'
import ScaledCanvasViewport from '@runtime-kit/internal/components/viewport/ScaledCanvasViewport.vue'
import PDFExportDialog from '@/runtime-shell/pdf/PDFExportDialog.vue'
import RuntimePageStage from '@/runtime-shell/transitions/RuntimePageStage.vue'
import ErrorBoundary from '@/runtime-shell/feedback/ErrorBoundary.vue'
import { useMenu } from '@/core/composables/useMenu'
import { usePageNavigation } from '@/core/composables/usePageNavigation'
import { PDFExportService } from '@/core/services/PDFExportService'
import { appConfig as runtimeAppConfig, appPageConfig, routeConfigs, type RuntimeMenuMode } from '@/core/utils/config'
import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'
import {
  createPresenterChannelId,
  normalizePresenterRoutePath,
} from '@/runtime-shell/presenter/presenter-url'
import { buildPresenterPages, writePresenterInitialNavigateMessage } from '@/runtime-shell/presenter/usePresenterController'
import { openPresenterDisplayWindow } from '@/runtime-shell/presenter/presenter-window'

// 应用配置已迁移到 @/config/app.config.ts

/**
 * 响应式状态
 */
const router = useRouter()
const session = getRuntimeSession(router)
const isCollapsed = session.collapsed
const isFullscreen = ref(Boolean(document.fullscreenElement))
// 缩放容器已抽取到独立组件处理窗口尺寸
const isSidebarHovered = ref(false)
const isFullscreenButtonHovered = ref(false)
const isPDFExportDialogVisible = ref(false)
const isCardModeVisible = computed({
  get: () => session.mode.value === 'cards',
  set: value => { void switchRuntimeMode(router, value ? 'cards' : 'normal') },
})
const pageBoundaryMessage = ref('')
let pageBoundaryMessageTimer: number | undefined
// 正在导出PDF的状态
const isExportingPdf = ref(false)

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
  goToPreviousPage,
  goToNextPage,
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
const isBottomPreviewHovered = ref(false)

/**
 * 当前布局实际使用的菜单模式。
 * @returns 全屏放映时底部缩略图模式临时按侧边预览渲染，退出全屏后恢复原模式
 */
const effectiveMenuMode = computed<RuntimeMenuMode>(() => {
  if (isFullscreen.value && currentMenuMode.value === 'bottom-preview') {
    return 'preview'
  }

  return currentMenuMode.value
})

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
const isSidebarMenuVisible = computed(() => effectiveMenuMode.value !== 'bottom-preview')

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
 */
const shouldShowTopRightPageControls = computed(() => {
  return shouldShowPdfExportButton.value
    || shouldShowPresenterButton.value
    || shouldShowCardModeButton.value
    || !isBottomPreviewMode.value
})

/**
 * 全屏态右上角控制是否可见。
 */
const isTopRightControlsVisible = computed(() => {
  return !isFullscreen.value || isFullscreenButtonHovered.value
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
  isBottomPreviewHovered.value = false
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
 * 处理底栏悬停进入事件。
 */
const handleBottomPreviewMouseEnter = (): void => {
  if (isFullscreen.value) {
    isBottomPreviewHovered.value = true
  }
}

/**
 * 处理底栏悬停离开事件。
 */
const handleBottomPreviewMouseLeave = (): void => {
  if (isFullscreen.value) {
    isBottomPreviewHovered.value = false
  }
}

/**
 * 处理侧边栏鼠标进入事件
 */
const handleSidebarMouseEnter = (): void => {
  if (isFullscreen.value) {
    isSidebarHovered.value = true
  }
}

/**
 * 处理侧边栏鼠标离开事件
 */
const handleSidebarMouseLeave = (): void => {
  if (isFullscreen.value) {
    isSidebarHovered.value = false
  }
}

/**
 * 处理全屏按钮鼠标进入事件
 */
const handleFullscreenButtonMouseEnter = (): void => {
  if (isFullscreen.value) {
    isFullscreenButtonHovered.value = true
  }
}

/**
 * 处理全屏按钮鼠标离开事件
 */
const handleFullscreenButtonMouseLeave = (): void => {
  if (isFullscreen.value) {
    isFullscreenButtonHovered.value = false
  }
}

/**
 * 预览模式切换按钮提示。
 * @returns 目标模式的完整标题
 */
const menuModeToggleTitle = computed(() => {
  return currentMenuMode.value === 'bottom-preview'
    ? '切换到侧边预览模式'
    : '切换到底部缩略图模式'
})

/**
 * 切换全屏模式
 */
const toggleFullscreen = async (): Promise<void> => {
  try {
    if (!document.fullscreenElement) {
      await document.documentElement.requestFullscreen()
    } else {
      await document.exitFullscreen()
    }
  } catch (error) {
    console.error('全屏API调用失败:', error)
    // 如果全屏API失败，手动重置状态
    isFullscreen.value = !!document.fullscreenElement
  }
}

/**
 * 键盘事件处理
 */
const handleKeydown = (event: KeyboardEvent): void => {
  // F11 键处理（全局有效）
  if (event.key === 'F11') {
    event.preventDefault()
    toggleFullscreen()
    return
  }

  // 防止在输入框等元素中触发
  const target = event.target as HTMLElement
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
    return
  }

  if (isCardModeVisible.value) {
    if (event.key === 'Escape') {
      event.preventDefault()
      isCardModeVisible.value = false
    } else if (event.key === 'ArrowRight' || event.key === 'PageDown') {
      event.preventDefault()
      void handleNextPageAction()
    } else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
      event.preventDefault()
      void handlePreviousPageAction()
    }
    return
  }

  if (event.shiftKey && event.key.toLowerCase() === 'p') {
    event.preventDefault()
    openPresenterMode()
    return
  }

  // 只在全屏模式下处理其他键盘事件
  if (!isFullscreen.value) return

  switch (event.key) {
    case 'PageDown':
    case 'ArrowRight':
    case ' ': // 空格键
      event.preventDefault()
      void handleNextPageAction()
      break
    case 'PageUp':
    case 'ArrowLeft':
      event.preventDefault()
      void handlePreviousPageAction()
      break
  }
}

/**
 * 全屏状态变化监听
 */
const handleFullscreenChange = (): void => {
  isFullscreen.value = !!document.fullscreenElement

  // 退出全屏时重置悬停状态
  if (!isFullscreen.value) {
    isSidebarHovered.value = false
    isFullscreenButtonHovered.value = false
    isBottomPreviewHovered.value = false
  }
}

/**
 * 显示PDF导出对话框
 */
const showPDFExportDialog = (): void => {
  isPDFExportDialogVisible.value = true
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
  if (!document.fullscreenElement) {
    try {
      await document.documentElement.requestFullscreen()
    } catch (error) {
      console.warn('进入全屏失败:', error)
    }
  }
}

/**
 * 打开演讲模式；同步打开观众窗口，同时当前窗口进入演讲者控制台。
 */
const openPresenterMode = (): void => {
  if (!shouldShowPresenterButton.value) {
    showPageBoundaryMessage('当前项目没有可演讲页面')
    return
  }

  const currentPath = normalizePresenterRoutePath(router.currentRoute.value.path)
  const channelId = createPresenterChannelId()
  const displayWindow = openPresenterDisplayWindow(channelId, currentPath)
  writePresenterInitialNavigateMessage(channelId, currentPath)

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
 * 处理PDF导出开始事件
 */
const handlePDFExportStart = (): void => {
  isExportingPdf.value = true
}

/**
 * 处理PDF导出完成事件
 * @param result 导出结果
 */
const handlePDFExportComplete = (): void => {
  isExportingPdf.value = false
}

/**
 * 处理PDF导出错误事件
 * @param error 错误信息
 */
const handlePDFExportError = (error: Error): void => {
  console.error('PDF导出失败:', error)
  isExportingPdf.value = false
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
  const reservedSideWidth = isBottomPreviewMode.value ? BOTTOM_PREVIEW_SIDE_CONTROL_SPACE * 2 : 0
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

/* 全屏模式下的侧边栏包装器 */
.sidebar-wrapper--fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  transform: translateX(-100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 100;
}

/* 全屏模式下鼠标悬停时显示侧边栏 */
.sidebar-wrapper--fullscreen-hover {
  transform: translateX(0);
}

/* 全屏模式下侧边栏悬停触发区域 */
.sidebar-wrapper--fullscreen::before {
  content: '';
  position: absolute;
  top: 0;
  right: -20px;
  width: 20px;
  height: 100%;
  background: transparent;
  z-index: 101;
}

/* 全屏模式下的左侧悬停触发区域 */
.fullscreen-sidebar-trigger {
  position: fixed;
  top: 0;
  left: 0;
  width: 20px;
  height: 100vh;
  background: transparent;
  z-index: 101;
  cursor: pointer;
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

.fullscreen-button-trigger {
  position: fixed;
  top: 0;
  right: 0;
  width: 108px;
  height: 180px;
  background: transparent;
  z-index: 101;
  cursor: pointer;
}

.fullscreen-bottom-preview-trigger {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  height: 20px;
  background: transparent;
  z-index: 101;
  cursor: pointer;
}

.top-right-controls {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 103;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.top-right-controls--fullscreen {
  opacity: 0;
  transform: translateY(-4px);
  pointer-events: none;
}

.top-right-controls--visible {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
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

/* 全屏模式下的控制按钮 */
.fullscreen-button--fullscreen {
  z-index: 1;
  background: transparent;
  border: 1px solid transparent;
  color: rgba(255, 255, 255, 0.5);
}

.layout-mode-button {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  height: 32px;
  padding: 0 0.75rem;
  background: rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  color: rgba(0, 0, 0, 0.65);
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  backdrop-filter: blur(8px);
}

.layout-mode-button:hover {
  transform: translateY(-1px);
  background: rgba(0, 0, 0, 0.8);
  border-color: rgba(0, 0, 0, 0.9);
  color: rgba(255, 255, 255, 0.95);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.layout-mode-button--fullscreen {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.72);
}

.layout-mode-button--fullscreen:hover {
  background: rgba(0, 0, 0, 0.8);
  border-color: rgba(0, 0, 0, 0.9);
  color: rgba(255, 255, 255, 0.95);
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

.fullscreen-button--fullscreen:hover {
  opacity: 1;
  transform: scale(1.05);
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(0, 0, 0, 0.9);
  color: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
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
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-navigation-buttons--fullscreen {
  opacity: 0;
  background: transparent;
  border: 1px solid transparent;
  color: rgba(255, 255, 255, 0.5);
  pointer-events: none;
  transform: translateY(-4px);
}

.page-navigation-buttons--visible {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
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

.nav-button--fullscreen {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.5);
}

.nav-button--fullscreen:hover:not(.nav-button--disabled) {
  background: rgba(0, 0, 0, 0.8);
  border: 1px solid rgba(0, 0, 0, 0.9);
  color: rgba(255, 255, 255, 0.95);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
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

.nav-button--fullscreen.nav-button--disabled:hover {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.5);
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

.bottom-preview-wrapper--fullscreen {
  position: fixed;
  bottom: 1rem;
  transform: translateY(calc(100% + 1rem));
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.bottom-preview-wrapper--fullscreen-hover {
  transform: translateY(0);
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

.bottom-preview-wrapper--collapsed.bottom-preview-wrapper--fullscreen {
  transform: translate(-50%, calc(100% + 1rem));
}

.bottom-preview-wrapper--collapsed.bottom-preview-wrapper--fullscreen-hover {
  transform: translate(-50%, 0);
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
