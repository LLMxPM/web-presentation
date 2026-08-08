<!-- 文件功能：提供可沿左侧垂直拖拽的 AI 形象入口，点击展开智能体对话面板并持久化拖拽位置。 -->
<template>
  <Transition name="agent-trigger">
    <button
      v-if="!expanded"
      ref="triggerEl"
      type="button"
      data-testid="agent-floating-trigger"
      class="agent-trigger"
      :class="{
        'agent-trigger--dragging': isDragging,
      }"
      :style="triggerStyle"
      aria-label="打开内容助手"
      aria-expanded="false"
      @pointerdown="handlePointerDown"
      @pointermove="handlePointerMove"
      @pointerup="handlePointerUp"
      @pointercancel="handlePointerUp"
      @click="handleClick"
    >
      <span class="agent-trigger__surface" aria-hidden="true">
        <img class="agent-trigger__companion" :src="aiCompanionUrl" alt="">
      </span>
      <span class="agent-trigger__label" aria-hidden="true">
        点击开始创作
      </span>
    </button>
  </Transition>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import aiCompanionUrl from '@/assets/agent/ai-companion.png'

interface Props {
  /** 智能体对话面板是否已展开；展开期间隐藏形象入口。 */
  expanded: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:expanded': [expanded: boolean]
}>()

/** 全局持久化的形象顶部坐标 key（单位 px，相对视口）。 */
const STORAGE_KEY = 'web-presentation:agent-floating-trigger-top'
const TRIGGER_SIZE = 72
const VERTICAL_GAP = 16
const DRAG_THRESHOLD = 5

const triggerEl = ref<HTMLButtonElement | null>(null)
const isDragging = ref(false)
const topPx = ref(loadStoredTop())
let pointerDown = false
let startClientY = 0
let startTopPx = 0
let moved = false

const triggerStyle = computed(() => ({ top: `${topPx.value}px` }))

/** 顶部可移动范围下限：避开 56px 顶栏并保留间距。 */
function minTop(): number {
  return 56 + VERTICAL_GAP
}

/** 底部可移动范围上限：保留间距防止贴边。 */
function maxTop(): number {
  return Math.max(minTop(), window.innerHeight - TRIGGER_SIZE - VERTICAL_GAP)
}

/** 读取上次拖拽位置并按当前视口约束；无记录时落在视口上部 1/3 处。 */
function loadStoredTop(): number {
  const stored = Number.parseFloat(window.localStorage.getItem(STORAGE_KEY) ?? '')
  if (!Number.isFinite(stored)) {
    return clamp(window.innerHeight * 0.3)
  }
  return clamp(stored)
}

/** 将像素坐标限制在可移动范围内。 */
function clamp(value: number): number {
  return Math.min(Math.max(value, minTop()), maxTop())
}

function persistTop(): void {
  window.localStorage.setItem(STORAGE_KEY, String(Math.round(topPx.value)))
}

function handlePointerDown(event: PointerEvent): void {
  if (event.button !== 0) {
    return
  }
  pointerDown = true
  moved = false
  startClientY = event.clientY
  startTopPx = topPx.value
  triggerEl.value?.setPointerCapture?.(event.pointerId)
}

function handlePointerMove(event: PointerEvent): void {
  if (!pointerDown) {
    return
  }
  const deltaY = event.clientY - startClientY
  if (!moved && Math.abs(deltaY) < DRAG_THRESHOLD) {
    return
  }
  moved = true
  isDragging.value = true
  topPx.value = clamp(startTopPx + deltaY)
}

function handlePointerUp(): void {
  if (!pointerDown) {
    return
  }
  pointerDown = false
  isDragging.value = false
  if (moved) {
    persistTop()
  }
}

function handleClick(): void {
  if (moved) {
    moved = false
    return
  }
  emit('update:expanded', true)
}

function handleWindowResize(): void {
  topPx.value = clamp(topPx.value)
}

onMounted(() => {
  topPx.value = loadStoredTop()
  window.addEventListener('resize', handleWindowResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleWindowResize)
})
</script>

<style scoped>
.agent-trigger {
  position: fixed;
  left: 10px;
  z-index: var(--ui-z-dock);
  width: 72px;
  height: 72px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  transition: transform 0.18s ease;
}

.agent-trigger:hover {
  transform: translateX(4px) scale(1.025);
}

.agent-trigger:focus-visible {
  outline: 2px solid rgb(var(--ui-border-focus));
  outline-offset: 3px;
}

.agent-trigger--dragging {
  transform: scale(1.055);
  cursor: grabbing;
}

.agent-trigger__surface {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  filter: drop-shadow(0 7px 9px rgb(var(--ui-overlay) / 0.2));
  transition: filter 0.18s ease;
}

.agent-trigger:hover .agent-trigger__surface,
.agent-trigger:focus-visible .agent-trigger__surface {
  filter: drop-shadow(0 9px 12px rgb(var(--ui-overlay) / 0.26));
}

.agent-trigger__companion {
  position: relative;
  width: 72px;
  height: 72px;
  object-fit: contain;
  pointer-events: none;
  transform: scaleX(-1);
}

.agent-trigger__label {
  position: absolute;
  top: 50%;
  left: 85px;
  display: flex;
  width: max-content;
  align-items: center;
  gap: 4px;
  padding: 5px 8px;
  border: 1px solid rgb(var(--ui-border));
  border-radius: var(--ui-radius-md);
  background: rgb(var(--ui-surface-raised));
  box-shadow: var(--ui-shadow-popover);
  color: rgb(var(--ui-text));
  font-size: 12px;
  font-weight: 600;
  line-height: 15px;
  opacity: 0;
  pointer-events: none;
  transform: translate(-4px, -50%);
  transition: opacity 0.14s ease, transform 0.14s ease;
  white-space: nowrap;
}

.agent-trigger__label span {
  color: rgb(var(--ui-text-muted));
  font-size: 10px;
  font-weight: 400;
}

.agent-trigger:hover .agent-trigger__label,
.agent-trigger:focus-visible .agent-trigger__label {
  opacity: 1;
  transform: translate(0, -50%);
}

.agent-trigger--dragging .agent-trigger__label {
  opacity: 0;
}

.agent-trigger-enter-active,
.agent-trigger-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.agent-trigger-enter-from,
.agent-trigger-leave-to {
  opacity: 0;
  transform: scale(0.8);
}

@media (prefers-reduced-motion: reduce) {
  .agent-trigger,
  .agent-trigger__surface,
  .agent-trigger__label {
    transition: none;
  }
}

@media (max-width: 959px) {
  .agent-trigger {
    display: none;
  }
}
</style>
