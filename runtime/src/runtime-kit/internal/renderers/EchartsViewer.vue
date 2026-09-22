<!--
  文件用途：ECharts 配置渲染器，负责将 option 文本或对象渲染为真实图表。
-->
<template>
  <section ref="surfaceRef" class="echarts-viewer" :style="surfaceStyle" v-bind="$attrs">
    <div
      ref="chartContainer"
      class="echarts-viewer__canvas"
      :class="{ 'echarts-viewer__canvas--hidden': stateVisible }"
    />

    <div v-if="loading" class="echarts-viewer__state">正在渲染图表...</div>
    <div v-else-if="error" class="echarts-viewer__state echarts-viewer__state--error">
      {{ error }}
    </div>
    <div v-else-if="empty" class="echarts-viewer__state">图表配置为空</div>
  </section>
</template>

<script setup lang="ts">
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createRafResizeObserver } from '@/core/utils/resize-observer'
import { useViewerSurfaceStyle, type ViewerSurfaceProps } from '@runtime-kit/internal/utils/viewer-style'

type EchartsRenderer = 'canvas' | 'svg'
type EchartsOptionRecord = Record<string, unknown>

interface Props extends ViewerSurfaceProps {
  /** ECharts option 文本内容，支持 JSON 或 JS 对象表达式 */
  content?: string | EchartsOptionRecord
  /** 直接传入的 ECharts option 对象，优先级高于 content */
  option?: EchartsOptionRecord
  /** ECharts 主题名称 */
  theme?: string
  /** ECharts 渲染器 */
  renderer?: EchartsRenderer
  /** setOption 时是否不合并旧 option */
  notMerge?: boolean
  /** setOption 时是否延迟更新 */
  lazyUpdate?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  content: '',
  option: undefined,
  theme: '',
  renderer: 'canvas',
  notMerge: true,
  lazyUpdate: false,
})

const surfaceRef = ref<HTMLElement | null>(null)
const chartContainer = ref<HTMLElement | null>(null)
const loading = ref(false)
const error = ref('')
const empty = ref(false)
const surfaceStyle = useViewerSurfaceStyle(props)

let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const stateVisible = computed(() => loading.value || Boolean(error.value) || empty.value)

/**
 * 将 unknown 错误统一转为可展示文案。
 *
 * @param reason 捕获到的错误对象
 * @returns 错误消息
 */
function getErrorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason || '未知错误')
}

/**
 * 解析 option 文本，兼容标准 JSON 与 JS 对象表达式。
 *
 * @param source option 源码文本
 * @returns ECharts option 对象
 */
function parseOptionText(source: string): EchartsOptionRecord {
  const normalizedSource = source.trim().replace(/^export\s+default\s+/, '')
  try {
    const parsed = JSON.parse(normalizedSource)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('ECharts option 必须是对象')
    }
    return parsed as EchartsOptionRecord
  } catch {
    const factory = new Function(`return (${normalizedSource});`)
    const result = factory()
    if (!result || typeof result !== 'object' || Array.isArray(result)) {
      throw new Error('ECharts option 必须是对象')
    }
    return result as EchartsOptionRecord
  }
}

/**
 * 根据 props 解析当前需要渲染的 option。
 *
 * @returns 解析后的 option；内容为空时返回 null
 */
function resolveOption(): EchartsOptionRecord | null {
  if (props.option) {
    return props.option
  }
  if (typeof props.content === 'object' && props.content) {
    return props.content
  }
  const source = String(props.content || '').trim()
  if (!source) {
    return null
  }
  return parseOptionText(source)
}

/**
 * 确保 ECharts 实例已经创建。
 *
 * @returns ECharts 实例
 */
function ensureChart(): echarts.ECharts {
  if (!chartContainer.value) {
    throw new Error('图表容器未挂载')
  }
  if (!chart || chart.isDisposed()) {
    chart = echarts.init(chartContainer.value, props.theme || undefined, {
      renderer: props.renderer,
    })
  }
  return chart
}

/**
 * 释放当前 ECharts 实例。
 */
function disposeChart(): void {
  if (chart && !chart.isDisposed()) {
    chart.dispose()
  }
  chart = null
}

/**
 * 重新计算图表尺寸。
 */
function resize(): void {
  if (chart && !chart.isDisposed()) {
    chart.resize()
  }
}

/**
 * 渲染或刷新当前图表。
 */
async function renderChart(): Promise<void> {
  loading.value = true
  error.value = ''
  empty.value = false

  try {
    await nextTick()
    const option = resolveOption()
    if (!option) {
      empty.value = true
      disposeChart()
      return
    }
    const instance = ensureChart()
    instance.setOption(option, {
      notMerge: props.notMerge,
      lazyUpdate: props.lazyUpdate,
    })
    resize()
  } catch (reason) {
    error.value = `ECharts 渲染失败：${getErrorMessage(reason)}`
    disposeChart()
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.content, props.option, props.notMerge, props.lazyUpdate],
  () => renderChart(),
  { deep: true },
)

watch(
  () => [props.theme, props.renderer],
  () => {
    disposeChart()
    renderChart()
  },
)

onMounted(() => {
  renderChart()
  if (surfaceRef.value) {
    resizeObserver = createRafResizeObserver(() => resize())
    resizeObserver.observe(surfaceRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  disposeChart()
})

defineExpose({
  reload: renderChart,
  resize,
  getInstance: () => chart,
})
</script>

<style scoped>
.echarts-viewer {
  position: relative;
  box-sizing: border-box;
  display: flex;
  overflow: hidden;
}

.echarts-viewer__canvas {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.echarts-viewer__canvas--hidden {
  visibility: hidden;
}

.echarts-viewer__state {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  color: #64748b;
  font-size: 14px;
  text-align: center;
  background: rgba(255, 255, 255, 0.86);
}

.echarts-viewer__state--error {
  color: #dc2626;
}
</style>
