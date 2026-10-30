<!-- 文件功能：全屏放映控制条，提供翻页、保持/释放、静音、错误状态和退出，不暂停 Scene。 -->
<template>
  <div v-if="errorMessage" class="runtime-playback-error" role="alert">{{ errorMessage }}</div>
  <div ref="controlsElement" class="runtime-playback-controls" role="group" aria-label="放映控制" :data-wake-lock="wakeLockState"
    :class="{ 'runtime-playback-controls--hidden': !controlsShown }">
    <template v-if="snapshot">
      <button type="button" class="runtime-playback-controls__button" aria-label="上一页" :disabled="!canGoPrevious" @click="goPrevious"><ChevronLeft :size="16" /></button>
      <button type="button" class="runtime-playback-controls__button runtime-playback-controls__button--mode" data-testid="playback-hold-toggle"
        :title="snapshot.held ? '释放后重新计算本页停留，页面动画持续播放' : '保持当前页，页面动画持续播放'" :aria-pressed="snapshot.held" @click="toggleHold">
        <Hand v-if="snapshot.held" :size="14" /><Timer v-else :size="14" /><span>{{ snapshot.held ? '释放本页' : '保持本页' }}</span>
      </button>
      <button type="button" class="runtime-playback-controls__button" aria-label="下一页" :disabled="!canGoNext" @click="goNext"><ChevronRight :size="16" /></button>
      <span class="runtime-playback-controls__divider" aria-hidden="true"></span>
      <button type="button" class="runtime-playback-controls__button" :aria-label="muted ? '取消静音' : '静音'" :aria-pressed="muted" data-testid="playback-mute-toggle" @click="toggleMute">
        <VolumeX v-if="muted" :size="14" /><Volume2 v-else :size="14" /><span>{{ muted ? '已静音' : '静音' }}</span>
      </button>
      <span class="runtime-playback-controls__page">{{ snapshot.index + 1 }} / {{ snapshot.total }}</span>
      <span class="runtime-playback-controls__state">{{ stateLabel }}</span>
      <span class="runtime-playback-controls__remaining" data-testid="playback-remaining">{{ remainingLabel }}</span>
      <button v-if="snapshot.state === 'failed'" type="button" class="runtime-playback-controls__button" @click="retry"><RotateCcw :size="14" /><span>重试当前页</span></button>
      <button v-if="snapshot.state === 'ended'" type="button" class="runtime-playback-controls__button" @click="start"><Play :size="14" /><span>重新开始</span></button>
    </template>
    <span v-else class="runtime-playback-controls__state">当前项目未启用有效的放映配置</span>
    <span class="runtime-playback-controls__divider" aria-hidden="true"></span>
    <button v-if="presenterAvailable" type="button" class="runtime-playback-controls__button" title="演讲模式 (Shift+P)" aria-label="进入演讲模式" @click="emit('presenter')"><Monitor :size="14" /></button>
    <button type="button" class="runtime-playback-controls__button" aria-label="退出放映" @click="emit('exit')"><Minimize2 :size="14" /></button>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronLeft, ChevronRight, Hand, Minimize2, Monitor, Play, RotateCcw, Timer, Volume2, VolumeX } from '@lucide/vue'
import { getRuntimeSession } from '@/core/router/runtime-session'
import { isEditableKeyboardTarget } from '@/runtime-shell/keyboard/keyboard-map'
import { usePlaybackHost } from './usePlaybackHost'
import type { DeckState } from './deck-types'

withDefaults(defineProps<{ presenterAvailable?: boolean }>(), { presenterAvailable: false })
const emit = defineEmits<{ presenter: []; exit: [] }>()
const { snapshot, errorMessage, wakeLockState, muted, canGoPrevious, canGoNext,
  start, stop, retry, goPrevious, goNext, toggleHold, toggleMute, refresh } = usePlaybackHost({ startOnMount: true })
const session = getRuntimeSession(useRouter())

/** 快捷键只改变保持或静音，不提供 Scene 暂停。 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.altKey || event.ctrlKey || event.metaKey || event.repeat || isEditableKeyboardTarget(event.target)) return
  if (event.key.toLowerCase() === 'm') { event.preventDefault(); toggleMute() }
}
onMounted(() => { session.stopPlayback = stop; document.addEventListener('keydown', handleKeydown) })
onBeforeUnmount(() => { if (session.stopPlayback === stop) session.stopPlayback = null; document.removeEventListener('keydown', handleKeydown) })
const STATE_LABELS: Record<DeckState, string> = { stopped: '已停止', preparing: '准备中', playing: '放映中', ended: '已结束', blocked: '等待页面恢复', failed: '错误' }
const stateLabel = computed(() => snapshot.value?.suspended ? '后台暂挂' : snapshot.value ? STATE_LABELS[snapshot.value.state] : '')
/** 指针进入窗口底部多高时唤出控制条。 */
const CONTROLS_REVEAL_ZONE_PX = 120
const controlsElement = ref<HTMLElement | null>(null)
/** 进入放映时先展示一次，避免用户找不到退出入口；指针移出底部区域后隐藏。 */
const controlsVisible = ref(true)

/** 暂停、错误、受阻与结束态保留控制条，保证恢复与退出入口始终可见。 */
const controlsPinned = computed(() => {
  const current = snapshot.value
  if (!current) return true
  return current.held || current.state === 'failed'
    || current.state === 'blocked' || current.state === 'ended'
})
const controlsShown = computed(() => controlsVisible.value || controlsPinned.value)

/** 判断指针是否位于窗口底部的控制条唤出区域。 */
function isPointerInRevealZone(event: PointerEvent): boolean {
  const revealZone = Math.min(CONTROLS_REVEAL_ZONE_PX, window.innerHeight * 0.35)
  return window.innerHeight - event.clientY <= revealZone
}

/** 指针在窗口内移动时按所在区域显示或隐藏控制条。 */
function handlePointerMove(event: PointerEvent): void {
  controlsVisible.value = isPointerInRevealZone(event)
}

/** 触摸或点击同样按落点唤醒控制条。 */
function handlePointerDown(event: PointerEvent): void {
  controlsVisible.value = isPointerInRevealZone(event)
}

/** 指针移出窗口或窗口失焦时收起控制条。 */
function hideControls(): void {
  controlsVisible.value = false
}

/** 键盘聚焦到控制条时保持可见；焦点移出后按指针离开处理。 */
function handleControlsFocusIn(): void {
  controlsVisible.value = true
}

function handleControlsFocusOut(event: FocusEvent): void {
  const nextTarget = event.relatedTarget as Node | null
  if (nextTarget && controlsElement.value?.contains(nextTarget)) return
  controlsVisible.value = false
}

onMounted(() => {
  window.addEventListener('pointermove', handlePointerMove, { passive: true })
  window.addEventListener('pointerdown', handlePointerDown, { passive: true })
  document.documentElement.addEventListener('pointerleave', hideControls)
  window.addEventListener('blur', hideControls)
  const element = controlsElement.value
  element?.addEventListener('focusin', handleControlsFocusIn)
  element?.addEventListener('focusout', handleControlsFocusOut)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerdown', handlePointerDown)
  document.documentElement.removeEventListener('pointerleave', hideControls)
  window.removeEventListener('blur', hideControls)
  const element = controlsElement.value
  element?.removeEventListener('focusin', handleControlsFocusIn)
  element?.removeEventListener('focusout', handleControlsFocusOut)
})

const remainingLabel = computed(() => {
  const value = snapshot.value
  if (!value || ['ended', 'failed', 'stopped'].includes(value.state)) return '—'
  if (value.held) return '保持当前页'
  if (value.advanceMode === 'manual') return '本页手动'
  if (value.waitingForScene) return '等待完成'
  return `${Math.ceil(value.remainingMs / 1000)} 秒`
})
let tickTimer: ReturnType<typeof setInterval> | undefined
/** 控制条只刷新显示，不参与自动推进。 */
function syncTicker(): void {
  clearInterval(tickTimer)
  tickTimer = undefined
  if (snapshot.value && ['playing', 'blocked'].includes(snapshot.value.state) && !snapshot.value.held && !snapshot.value.suspended) tickTimer = setInterval(refresh, 250)
}
watch(() => [snapshot.value?.state, snapshot.value?.held, snapshot.value?.suspended], syncTicker, { immediate: true })
onBeforeUnmount(() => clearInterval(tickTimer))
</script>
<style scoped>
.runtime-playback-error {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  max-width: min(680px, calc(100vw - 32px));
  padding: 12px 20px;
  background: #fff;
  color: #b91c1c;
  border: 1px solid #fecaca;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgb(15 23 42 / 12%);
  font-size: 14px;
  text-align: center;
}

.runtime-playback-controls {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  z-index: 9000;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: calc(100vw - 32px);
  padding: 8px 14px;
  color: #f8fafc;
  background: rgb(15 23 42 / 82%);
  border: 1px solid rgb(148 163 184 / 22%);
  border-radius: 9999px;
  box-shadow: 0 12px 30px rgb(15 23 42 / 28%);
  backdrop-filter: blur(8px);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  transition: opacity 160ms ease, transform 160ms ease;
}

.runtime-playback-controls--hidden {
  opacity: 0;
  transform: translate(-50%, 10px);
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .runtime-playback-controls {
    transition: none;
  }
}

.runtime-playback-controls__button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  color: inherit;
  background: rgb(248 250 252 / 10%);
  border: 0;
  border-radius: 9999px;
  cursor: pointer;
  font-size: 13px;
}

.runtime-playback-controls__button:hover:not(:disabled) {
  background: rgb(248 250 252 / 20%);
}

.runtime-playback-controls__button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.runtime-playback-controls__button--primary {
  background: #2563eb;
}

.runtime-playback-controls__button--primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.runtime-playback-controls__button--mode {
  min-width: 4.25rem;
  justify-content: center;
}

.runtime-playback-controls__button:focus-visible {
  outline: 2px solid #93c5fd;
  outline-offset: 2px;
}

.runtime-playback-controls__divider {
  width: 1px;
  height: 18px;
  background: rgb(148 163 184 / 35%);
}

.runtime-playback-controls__page {
  font-weight: 600;
}

.runtime-playback-controls__state {
  color: #cbd5e1;
}

.runtime-playback-controls__remaining {
  min-width: 4.5em;
  text-align: right;
  color: #e2e8f0;
}
</style>
