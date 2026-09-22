<!--
  文件用途：页面预览组件，支持只读缩略壳层与可交互的编辑器单页预览。
  主要职责：
  1. 根据页面逻辑路径加载本地内建页或远程发布页模块；
  2. 使用项目配置指定的页面画布按比例缩放；
  3. 供侧边栏缩略图、演讲小窗、卡片模式与 Editor 单页预览复用。
-->

<template>
  <div
    :ref="setContainerRef"
    class="w-full h-full flex items-center justify-center overflow-hidden"
    :data-runtime-view-preview-state="previewState"
    :data-runtime-view-preview-message="previewStateMessage"
  >
    <ScaledCanvasViewport
      :is-fullscreen="false"
      :scale="scale"
      :design-width="effectiveDesignWidth"
      :design-height="effectiveDesignHeight"
    >
      <div
        v-bind="inert ? { inert: true } : {}"
        class="runtime-view-preview-source"
        :style="previewContentStyles"
      >
        <div v-if="previewState === 'loading'" class="runtime-view-preview-placeholder">
          正在加载页面预览...
        </div>
        <div v-else-if="previewState === 'empty'" class="runtime-view-preview-placeholder">
          未找到可预览页面
        </div>
        <div v-else-if="previewState === 'error'" class="runtime-view-preview-placeholder runtime-view-preview-placeholder--error">
          {{ previewStateMessage || '页面预览加载失败' }}
        </div>
        <component :is="previewComponent" v-else-if="previewComponent" :key="refreshKey" />
      </div>
    </ScaledCanvasViewport>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, shallowRef, watch, type Component } from 'vue'

import ScaledCanvasViewport from '@runtime-kit/internal/components/viewport/ScaledCanvasViewport.vue'
import { appPageConfig } from '@/core/utils/config'
import { buildPageContentScaleStyles } from '@/core/utils/page-scale'
import { createRafResizeObserver } from '@/core/utils/resize-observer'
import { importViewModule } from '@/core/utils/view-module'

interface Props {
  filePath: string
  designWidth?: number
  designHeight?: number
  scaleLimit?: number
  refreshToken?: number
  /** 是否将预览内容设为 inert。缩略图默认拦截交互；Editor 主预览需关闭以允许文字选中。 */
  inert?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  designWidth: undefined,
  designHeight: undefined,
  scaleLimit: 3,
  refreshToken: 0,
  inert: true
})

const emit = defineEmits<{
  'state-change': [payload: { state: 'loading' | 'ready' | 'error' | 'empty'; message: string }]
}>()

const previewComponent = shallowRef<Component | null>(null)
const containerRef = ref<HTMLElement | null>(null)
const scale = ref(1)
const refreshKey = ref(0)
const previewState = ref<'loading' | 'ready' | 'error' | 'empty'>('loading')
const previewStateMessage = ref('')
let resizeObserver: ResizeObserver | null = null

/**
 * 当前生效的设计宽度；优先使用组件入参，否则回退到项目配置。
 */
const effectiveDesignWidth = computed(() => props.designWidth || appPageConfig.value.width)

/**
 * 当前生效的设计高度；优先使用组件入参，否则回退到项目配置。
 */
const effectiveDesignHeight = computed(() => props.designHeight || appPageConfig.value.height)

/**
 * 单页预览内容作用域样式。
 * @returns 与整项目预览一致的字号和间距变量
 */
const previewContentStyles = computed(() => (
  buildPageContentScaleStyles()
))

/**
 * 记录预览容器并监听尺寸变化。
 * @param element 容器 DOM 引用
 */
function setContainerRef(element: Element | null): void {
  containerRef.value = element instanceof HTMLElement ? element : null
  bindResizeObserver()
}

/**
 * 绑定尺寸监听器并立即计算一次缩放比例。
 */
function bindResizeObserver(): void {
  resizeObserver?.disconnect()
  computeScale()
  if (!containerRef.value) {
    return
  }

  resizeObserver = createRafResizeObserver(() => computeScale())
  resizeObserver.observe(containerRef.value)
}

/**
 * 根据容器大小计算缩放比例。
 */
function computeScale(): void {
  if (!containerRef.value) {
    return
  }

  const availableWidth = containerRef.value.clientWidth
  const availableHeight = containerRef.value.clientHeight
  const scaleX = availableWidth / effectiveDesignWidth.value
  const scaleY = availableHeight / effectiveDesignHeight.value
  scale.value = Math.min(scaleX, scaleY, props.scaleLimit)
}

/**
 * 加载预览页面模块。
 */
async function loadPreviewComponent(): Promise<void> {
  setPreviewState('loading')
  emitPreviewState()
  previewComponent.value = null
  if (!props.filePath) {
    setPreviewState('empty', '未找到可预览页面')
    emitPreviewState()
    refreshKey.value += 1
    return
  }

  try {
    const module = await importViewModule(props.filePath)
    if (!module?.default) {
      setPreviewState('error', '页面模块缺少默认导出')
      return
    }
    previewComponent.value = module.default
    setPreviewState('ready')
  } catch (error) {
    console.error('缩略预览加载失败：', error)
    setPreviewState('error', error instanceof Error ? error.message : `页面加载失败：${props.filePath}`)
  } finally {
    refreshKey.value += 1
    await nextTick()
    computeScale()
    emitPreviewState()
  }
}

/**
 * 统一更新预览状态。
 * @param state 最新状态
 * @param message 可展示的状态说明
 */
function setPreviewState(state: 'loading' | 'ready' | 'error' | 'empty', message = ''): void {
  previewState.value = state
  previewStateMessage.value = message
}

/** 在 DOM 状态提交后把当前预览状态通知给宿主页。 */
function emitPreviewState(): void {
  emit('state-change', { state: previewState.value, message: previewStateMessage.value })
}

watch(() => props.filePath, () => {
  loadPreviewComponent()
}, { immediate: true })

watch(() => props.refreshToken, () => {
  loadPreviewComponent()
})

watch([effectiveDesignWidth, effectiveDesignHeight], () => {
  computeScale()
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})
</script>

<style scoped>
.runtime-view-preview-source {
  width: 100%;
  height: 100%;
  overflow: auto;
}

.runtime-view-preview-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  box-sizing: border-box;
  color: #64748b;
  background: #f8fafc;
  font-size: 14px;
  text-align: center;
}

.runtime-view-preview-placeholder--error {
  color: #b91c1c;
  background: #fef2f2;
}
</style>
