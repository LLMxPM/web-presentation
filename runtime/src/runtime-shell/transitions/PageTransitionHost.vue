<!-- 文件功能：双层页面过渡宿主，合并快速导航并隔离画布缩放与内容动画。 -->
<template>
  <div
    ref="root" class="page-transition-host" :data-transition-state="phase"
    :data-transition-effect="activeConfig.effect" :style="hostStyles">
    <div
      v-for="(frame, index) in frames" :key="frame.path" class="page-transition-layer"
      :class="layerClass(index)" :inert="phase !== 'idle' && index === 0 && frames.length > 1"
      :aria-hidden="frames.length > 1 && index === 0 ? true : undefined">
      <FrameContent :node="frame.node" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { cloneVNode, computed, defineComponent, nextTick, onBeforeUnmount, onErrorCaptured, ref, shallowRef, watch, type PropType, type VNode } from 'vue'
import type { PageTransitionConfig } from '@/core/types/page-transition'

interface Frame { path: string; node: VNode; pageNumber?: number }
const props = defineProps<{
  node?: VNode
  pageKey: string
  pageNumber?: number
  config: PageTransitionConfig
  disabled?: boolean
}>()
const emit = defineEmits<{ error: [path: string, error: unknown]; settled: [path: string] }>()
const root = ref<HTMLElement>()
const frames = shallowRef<Frame[]>([])
const phase = ref<'idle' | 'preparing' | 'running'>('idle')
const activeConfig = shallowRef<PageTransitionConfig>({ effect: 'none', durationMs: 0 })
const direction = ref(1)
let pending: Frame | undefined
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
let disposed = false
const media = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : undefined
const reducedMotion = ref(media?.matches ?? false)

/** 渲染冻结的页面 VNode；避免父级路由更新替换离场页内容。 */
const FrameContent = defineComponent({
  props: { node: { type: Object as PropType<VNode>, required: true } },
  setup: frameProps => () => cloneVNode(frameProps.node),
})
const hostStyles = computed(() => ({ '--transition-duration': `${activeConfig.value.durationMs}ms`, '--transition-direction': direction.value }))

/** 根据当前阶段为两层分配固定的进出效果。 */
function layerClass(index: number): string[] {
  if (frames.value.length < 2) return []
  return [index === 0 ? 'leaving' : 'entering', activeConfig.value.effect, phase.value]
}

/** 完成本次过渡，确保仅保留目标层，再处理最新待切换页。 */
function finish(): void {
  clearTimeout(timer)
  generation += 1
  frames.value = frames.value.slice(-1)
  phase.value = 'idle'
  if (frames.value[0]) emit('settled', frames.value[0].path)
  const target = pending
  pending = undefined
  if (target && target.path !== frames.value[0]?.path) void show(target)
}

/** 准备新页并在下一绘制帧启动 CSS；离场媒体在此处暂停。 */
async function show(target: Frame): Promise<void> {
  if (disposed) return
  if (phase.value !== 'idle') { pending = target; return }
  const previous = frames.value[0]
  if (previous && previous.path === target.path) {
    previous.node = target.node
    emit('settled', target.path)
    return
  }
  if (!previous || props.disabled || reducedMotion.value || props.config.effect === 'none') {
    frames.value = [target]
    emit('settled', target.path)
    return
  }
  direction.value = previous.pageNumber != null && target.pageNumber != null && target.pageNumber < previous.pageNumber ? -1 : 1
  activeConfig.value = { ...props.config }
  frames.value = [previous, target]
  phase.value = 'preparing'
  const token = ++generation
  await nextTick()
  root.value?.querySelectorAll<HTMLMediaElement>('.leaving audio, .leaving video').forEach(element => element.pause())
  // 强制读取布局，确保进入层起始状态已提交；后台窗口也由计时器保证收尾。
  root.value?.getBoundingClientRect()
  timer = setTimeout(finish, activeConfig.value.durationMs + 100)
  requestAnimationFrame(() => {
    if (token === generation && !disposed) phase.value = 'running'
  })
}

/** 捕获目标页渲染异常，保留上一稳定页并通知调用方恢复地址。 */
onErrorCaptured(error => {
  const previous = frames.value[0]
  clearTimeout(timer)
  generation += 1
  pending = undefined
  frames.value = previous ? [previous] : []
  phase.value = 'idle'
  emit('error', previous?.path || '', error)
  return false
})

watch(() => [props.pageKey, props.node] as const, () => {
  if (props.node) void show({ path: props.pageKey, node: cloneVNode(props.node, { key: props.pageKey }), pageNumber: props.pageNumber })
}, { immediate: true })
watch(() => props.disabled || reducedMotion.value, disabled => { if (disabled && phase.value !== 'idle') finish() })
/** 用户改变减少动态效果偏好时立即收尾。 */
function onMotionChange(event: MediaQueryListEvent): void { reducedMotion.value = event.matches }
media?.addEventListener('change', onMotionChange)
onBeforeUnmount(() => { disposed = true; generation += 1; clearTimeout(timer); media?.removeEventListener('change', onMotionChange) })
</script>

<style scoped>
.page-transition-host { position: relative; width: 100%; height: 100%; overflow: hidden; isolation: isolate; }
.page-transition-layer { position: absolute; inset: 0; width: 100%; height: 100%; }
.page-transition-layer.leaving, .page-transition-layer.entering { transition: transform var(--transition-duration) ease-in-out, opacity var(--transition-duration) ease-in-out; }
.leaving { pointer-events: none; }
.entering { z-index: 1; }
.entering.fade.preparing { opacity: 0; }
.leaving.fade.running { opacity: 0; }
.entering.push.preparing { transform: translateX(calc(100% * var(--transition-direction))); }
.leaving.push.running { transform: translateX(calc(-100% * var(--transition-direction))); }
</style>
