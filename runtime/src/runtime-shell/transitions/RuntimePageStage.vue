<!-- 文件功能：将项目 RouterView 接入统一过渡宿主，提供真实页面导出节点。 -->
<template>
  <router-view v-slot="{ Component, route }">
    <PageTransitionHost
      :node="wrapPage(Component, route.path, route.query.runtimeCaptureTicket)" :page-key="route.path"
      :page-number="Number(route.meta.pageNumber) || undefined"
      :config="resolvePageTransition(route.meta.transition)" :disabled="disabled || session.suppressTransition.value"
      @started="handleStarted" @settled="handleSettled" @error="handleError" />
  </router-view>
</template>

<script setup lang="ts">
import { h, onBeforeUnmount, type VNode } from 'vue'
import { useRouter } from 'vue-router'
import { getRuntimeSession } from '@/core/router/runtime-session'
import { resolvePageTransition } from '@/core/utils/page-transition'
import { buildPageContentScaleStyles } from '@/core/utils/page-scale'
import type { TransitionSettledEvent, TransitionStartedEvent } from '@/core/types/page-transition'
import PageTransitionHost from './PageTransitionHost.vue'

defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{
  settled: [event: TransitionSettledEvent]
  started: [event: TransitionStartedEvent]
}>()
const router = useRouter()
const session = getRuntimeSession(router)
let latestSettled: TransitionSettledEvent | null = null

/** 新过渡立即作废旧回执，避免快速回到同一路径时误把旧稳定页当作已经完成。 */
function handleStarted(event: TransitionStartedEvent): void {
  session.transitionSettled.value = null
  latestSettled = null
  emit('started', event)
}

/** 把整页过渡完成信号写入会话并向上转发；只代表过渡完成，不代表资源就绪。 */
function handleSettled(event: TransitionSettledEvent): void {
  session.transitionSettled.value = event
  latestSettled = session.transitionSettled.value
  emit('settled', event)
}

/** 过渡层重挂会重新编号；只撤销本宿主留下的回执，不覆盖新宿主已经提交的结果。 */
onBeforeUnmount(() => {
  if (session.transitionSettled.value === latestSettled) session.transitionSettled.value = null
})

/** 为页面创建独立内容根节点，保持导出选择器和设计字号兼容。 */
function wrapPage(component: VNode | undefined, path: string, captureTicket: unknown): VNode | undefined {
  return component ? h('div', {
    class: 'runtime-page-print-source',
    'data-runtime-route-path': path,
    'data-runtime-capture-ticket': typeof captureTicket === 'string' ? captureTicket : undefined,
    style: { ...buildPageContentScaleStyles(), width: '100%', height: '100%' },
  }, [component]) : undefined
}

/** 目标组件失败时恢复原页面；模式上下文由统一导航层保留。 */
function handleError(path: string, error: unknown): void {
  console.error('[runtime-transition] 页面渲染失败', error)
  session.navigationError.value = '页面加载失败，请重试或选择其他页面。'
  if (path && path !== router.currentRoute.value.path) void router.replace(path)
}
</script>

<style>
/*
 * 页面根节点由 h() 在过渡宿主中创建，不再携带 ResponsiveLayout 的 scoped 属性。
 * 保持页面根与设计画布同尺寸，否则可视化编辑 iframe 中的点击坐标会落到视口容器。
 */
.runtime-page-print-source {
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.runtime-page-print-source > * {
  width: 100%;
  height: 100%;
}
</style>
