<!-- 文件功能：提供两个工作区域之间可键盘和指针调整的分割面板。 -->
<template>
  <div class="grid min-h-0 min-w-0" :class="orientation === 'horizontal' ? 'h-full' : 'w-full'" :style="gridStyle">
    <div class="min-h-0 min-w-0 overflow-hidden"><slot name="first" /></div>
    <div
      class="group relative z-[var(--ui-z-base)] flex items-center justify-center bg-[rgb(var(--ui-border))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--ui-border-focus))]"
      :class="orientation === 'horizontal' ? 'cursor-col-resize' : 'cursor-row-resize'"
      role="separator"
      tabindex="0"
      :aria-orientation="orientation === 'horizontal' ? 'vertical' : 'horizontal'"
      :aria-valuemin="minSize"
      :aria-valuemax="maxSize"
      :aria-valuenow="size"
      aria-label="调整面板大小"
      @pointerdown="startResize"
      @keydown="handleKeydown"
    >
      <span class="rounded-full bg-[rgb(var(--ui-border-strong))] opacity-0 transition-opacity group-hover:opacity-100 group-focus:opacity-100" :class="orientation === 'horizontal' ? 'h-8 w-1' : 'h-1 w-8'" />
    </div>
    <div class="min-h-0 min-w-0 overflow-hidden"><slot name="second" /></div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

type SplitOrientation = 'horizontal' | 'vertical'

const props = withDefaults(defineProps<{
  /** 第一个面板占容器的百分比，传入后使用受控模式。 */
  modelValue?: number
  /** 未受控时第一个面板的初始百分比。 */
  defaultSize?: number
  /** 第一个面板允许的最小百分比。 */
  minSize?: number
  /** 第一个面板允许的最大百分比。 */
  /** 分割方向；horizontal 表示左右布局。 */
  maxSize?: number
  orientation?: SplitOrientation
  /** 键盘每次调整的百分比。 */
  step?: number
}>(), {
  modelValue: undefined,
  defaultSize: 32,
  minSize: 20,
  maxSize: 80,
  orientation: 'horizontal',
  step: 5,
})

const emit = defineEmits<{
  /** 第一个面板比例变化时回传，值范围由 minSize/maxSize 限制。 */
  'update:modelValue': [value: number]
}>()

const localSize = ref(clamp(props.defaultSize))
let activeSeparator: HTMLElement | null = null
let cleanupResize: (() => void) | undefined
const size = computed(() => clamp(props.modelValue ?? localSize.value))
const gridStyle = computed(() => props.orientation === 'horizontal'
  ? { gridTemplateColumns: `${size.value}fr 1px minmax(0, ${100 - size.value}fr)` }
  : { gridTemplateRows: `${size.value}fr 1px minmax(0, ${100 - size.value}fr)` })

watch(() => props.modelValue, value => {
  if (value !== undefined) localSize.value = clamp(value)
})

/** 将任意候选比例收敛到组件声明的边界。 */
function clamp(value: number): number {
  return Math.min(props.maxSize, Math.max(props.minSize, Math.round(value)))
}

/** 更新本地与受控状态，保证所有输入路径采用相同边界。 */
function updateSize(value: number) {
  const nextSize = clamp(value)
  localSize.value = nextSize
  emit('update:modelValue', nextSize)
}

/** 根据分割条的指针位置换算第一个面板比例。 */
function handlePointerMove(event: PointerEvent) {
  const container = activeSeparator?.parentElement
  if (!container) return
  const rect = container.getBoundingClientRect()
  const coordinate = props.orientation === 'horizontal' ? event.clientX - rect.left : event.clientY - rect.top
  const total = props.orientation === 'horizontal' ? rect.width : rect.height
  if (total > 0) updateSize((coordinate / total) * 100)
}

/** 开始拖动并在窗口级别监听，确保指针离开分割条后仍可完成调整。 */
function startResize(event: PointerEvent) {
  cleanupResize?.()
  const separator = event.currentTarget as HTMLElement
  activeSeparator = separator
  separator.setPointerCapture?.(event.pointerId)
  const move = (moveEvent: PointerEvent) => handlePointerMove(moveEvent)
  const stop = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
    activeSeparator = null
    cleanupResize = undefined
  }
  cleanupResize = stop
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop, { once: true })
}

/** 让键盘用户以稳定步进调整分割条，Home/End 跳至允许边界。 */
function handleKeydown(event: KeyboardEvent) {
  const decreaseKeys = props.orientation === 'horizontal' ? ['ArrowLeft'] : ['ArrowUp']
  const increaseKeys = props.orientation === 'horizontal' ? ['ArrowRight'] : ['ArrowDown']
  if (decreaseKeys.includes(event.key)) {
    event.preventDefault()
    updateSize(size.value - props.step)
  } else if (increaseKeys.includes(event.key)) {
    event.preventDefault()
    updateSize(size.value + props.step)
  } else if (event.key === 'Home') {
    event.preventDefault()
    updateSize(props.minSize)
  } else if (event.key === 'End') {
    event.preventDefault()
    updateSize(props.maxSize)
  }
}

/** 组件卸载时清理窗口级拖动监听，避免遗留无主事件处理器。 */
onBeforeUnmount(() => cleanupResize?.())
</script>
