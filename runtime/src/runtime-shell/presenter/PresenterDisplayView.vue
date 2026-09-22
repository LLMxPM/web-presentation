<!--
  文件用途：Runtime 演讲模式观众窗口，全屏仅展示当前演讲页。
-->

<template>
  <div class="presenter-display-screen">
    <div v-if="currentPage" class="presenter-display-screen__content">
      <PresenterPageStage />
    </div>
    <div v-else class="presenter-display-screen__waiting">
      等待演讲者控制台同步页面。
    </div>

    <section
      v-if="shouldShowFullscreenPrompt"
      class="presenter-display-screen__fullscreen-panel"
      aria-label="观众窗口全屏设置"
    >
      <div class="presenter-display-screen__fullscreen-copy">
        <p class="presenter-display-screen__fullscreen-kicker">观众窗口</p>
        <h2>选择全屏屏幕</h2>
      </div>

      <div v-if="screenOptions.length > 0" class="presenter-display-screen__screen-list">
        <button
          v-for="option in screenOptions"
          :key="option.id"
          class="presenter-display-screen__screen-button"
          type="button"
          :data-screen-index="option.index"
          @click="enterFullscreenOnScreen(option.screen)"
        >
          <span>{{ option.label }}</span>
          <small>{{ option.description }}</small>
        </button>
      </div>

      <button
        v-else-if="isScreenDetectionSupported"
        class="presenter-display-screen__fullscreen-action"
        type="button"
        title="授权检测屏幕"
        data-testid="presenter-display-detect-screens"
        :disabled="isScreenDetectionPending"
        @click="requestScreenOptions"
      >
        {{ isScreenDetectionPending ? '正在检测屏幕' : '授权检测屏幕' }}
      </button>

      <button
        v-else
        class="presenter-display-screen__fullscreen-action"
        type="button"
        title="当前窗口全屏"
        @click="enterCurrentWindowFullscreen"
      >
        当前窗口全屏
      </button>

      <button
        v-if="screenOptions.length > 0"
        class="presenter-display-screen__fallback-action"
        type="button"
        @click="enterCurrentWindowFullscreen"
      >
        当前窗口全屏
      </button>
    </section>

    <p v-if="fullscreenMessage" class="presenter-display-screen__warning">
      {{ fullscreenMessage }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import PresenterPageStage from './PresenterPageStage.vue'
import { usePresenterController } from '@/runtime-shell/presenter/usePresenterController'

interface PresenterDetailedScreen {
  availLeft: number
  availTop: number
  availWidth: number
  availHeight: number
  isPrimary?: boolean
  label?: string
}

interface PresenterScreenDetails {
  currentScreen?: PresenterDetailedScreen
  screens: PresenterDetailedScreen[]
}

interface PresenterWindowWithScreenDetails extends Window {
  getScreenDetails?: () => Promise<PresenterScreenDetails>
}

interface PresenterFullscreenOptions extends FullscreenOptions {
  screen?: PresenterDetailedScreen
}

interface PresenterFullscreenElement extends HTMLElement {
  requestFullscreen: (options?: PresenterFullscreenOptions) => Promise<void>
}

interface PresenterScreenOption {
  id: string
  index: number
  label: string
  description: string
  screen: PresenterDetailedScreen
}

const route = useRoute()
const channelId = computed(() => String(route.query.channel || ''))
const initialPath = computed(() => String(route.query.route || route.path))
const isInFullscreen = ref(false)
const isFullscreenPromptDismissed = ref(false)
const isScreenDetectionPending = ref(false)
const screenOptions = ref<PresenterScreenOption[]>([])
const fullscreenMessage = ref('')
const shouldShowFullscreenPrompt = computed(() => !isInFullscreen.value && !isFullscreenPromptDismissed.value)
const isScreenDetectionSupported = computed(() => typeof getScreenDetailsApi() === 'function')

const {
  currentPage,
  goPrevious,
  goNext,
  postDisplayStatus,
} = usePresenterController({
  role: 'display',
  channelId: channelId.value,
  initialPath: initialPath.value,
})

/**
 * 请求观众窗口授权检测屏幕，并把可选屏幕展示给用户。
 * 必须由观众页内的点击触发，否则浏览器不会弹出窗口管理授权。
 */
async function requestScreenOptions(): Promise<void> {
  const getScreenDetails = getScreenDetailsApi()
  if (!getScreenDetails) {
    fullscreenMessage.value = '当前浏览器不支持屏幕选择，请使用当前窗口全屏。'
    return
  }

  isScreenDetectionPending.value = true
  fullscreenMessage.value = ''
  try {
    const details = await getScreenDetails()
    const validScreens = Array.isArray(details.screens)
      ? details.screens.filter(isValidDetailedScreen)
      : []
    if (validScreens.length === 0) {
      fullscreenMessage.value = '没有检测到可用屏幕，请使用当前窗口全屏。'
      return
    }
    screenOptions.value = validScreens.map((screen, index) => buildScreenOption(screen, index, details.currentScreen))
  } catch {
    fullscreenMessage.value = '未获得屏幕检测授权，请在观众窗口授权后重试，或使用当前窗口全屏。'
  } finally {
    isScreenDetectionPending.value = false
  }
}

/**
 * 在用户选择的屏幕上全屏。
 * @param screen 目标屏幕
 */
async function enterFullscreenOnScreen(screen: PresenterDetailedScreen): Promise<boolean> {
  return enterFullscreen(screen)
}

/**
 * 在当前窗口所在屏幕全屏。
 * @returns 是否触发成功
 */
async function enterCurrentWindowFullscreen(): Promise<boolean> {
  return enterFullscreen()
}

/**
 * 尝试把当前观众窗口切到全屏。
 * 必须由观众页内的点击触发，否则浏览器会因缺少用户手势而拒绝。
 * @param screen 可选的目标屏幕
 * @returns 是否触发成功
 */
async function enterFullscreen(screen?: PresenterDetailedScreen): Promise<boolean> {
  if (isInFullscreen.value) {
    return true
  }
  if (!document.documentElement.requestFullscreen) {
    fullscreenMessage.value = '当前环境不支持全屏 API，请使用浏览器快捷键 F11。'
    return false
  }

  try {
    await requestDocumentFullscreen(screen)
    return true
  } catch {
    fullscreenMessage.value = screen
      ? '浏览器未能在所选屏幕全屏，请重试或使用当前窗口全屏。'
      : '浏览器阻止了全屏，请点击按钮或按 F11。'
    return false
  }
}

/**
 * 调用全屏 API；传入 screen 时使用 Window Management API 的指定屏幕全屏能力。
 * @param screen 可选的目标屏幕
 */
async function requestDocumentFullscreen(screen?: PresenterDetailedScreen): Promise<void> {
  const fullscreenElement = document.documentElement as PresenterFullscreenElement
  if (screen) {
    await fullscreenElement.requestFullscreen({ screen })
    return
  }
  await fullscreenElement.requestFullscreen()
}

/**
 * 获取当前浏览器的屏幕检测 API。
 * @returns 可调用的屏幕检测函数；不支持时为空
 */
function getScreenDetailsApi(): (() => Promise<PresenterScreenDetails>) | undefined {
  return (window as PresenterWindowWithScreenDetails).getScreenDetails
}

/**
 * 构建屏幕选择按钮展示数据。
 * @param screen 屏幕详情
 * @param index 屏幕序号
 * @param currentScreen 当前窗口所在屏幕
 * @returns 屏幕展示选项
 */
function buildScreenOption(
  screen: PresenterDetailedScreen,
  index: number,
  currentScreen?: PresenterDetailedScreen,
): PresenterScreenOption {
  const badges = [
    screen.isPrimary ? '主屏' : '',
    currentScreen && isSameDetailedScreen(screen, currentScreen) ? '当前窗口' : '',
  ].filter(Boolean)
  const fallbackLabel = `屏幕 ${index + 1}`
  const baseLabel = screen.label?.trim() || fallbackLabel

  return {
    id: `${index}-${screen.availLeft}-${screen.availTop}-${screen.availWidth}-${screen.availHeight}`,
    index,
    label: badges.length > 0 ? `${baseLabel} · ${badges.join(' · ')}` : baseLabel,
    description: `${Math.round(screen.availWidth)} x ${Math.round(screen.availHeight)} · ${Math.round(screen.availLeft)}, ${Math.round(screen.availTop)}`,
    screen,
  }
}

/**
 * 校验浏览器返回的屏幕详情是否可用于全屏选择。
 * @param screen 屏幕详情
 * @returns 是否有效
 */
function isValidDetailedScreen(screen: PresenterDetailedScreen): boolean {
  return Number.isFinite(screen.availLeft)
    && Number.isFinite(screen.availTop)
    && Number.isFinite(screen.availWidth)
    && Number.isFinite(screen.availHeight)
    && screen.availWidth > 0
    && screen.availHeight > 0
}

/**
 * 判断两个屏幕是否为同一块显示器。
 * @param left 左侧屏幕
 * @param right 右侧屏幕
 * @returns 是否相同
 */
function isSameDetailedScreen(left: PresenterDetailedScreen, right: PresenterDetailedScreen): boolean {
  return left.availLeft === right.availLeft
    && left.availTop === right.availTop
    && left.availWidth === right.availWidth
    && left.availHeight === right.availHeight
}

function updateFullscreenState(): void {
  isInFullscreen.value = Boolean(document.fullscreenElement)
  if (isInFullscreen.value) {
    isFullscreenPromptDismissed.value = true
    fullscreenMessage.value = ''
  } else {
    isFullscreenPromptDismissed.value = false
  }
  postDisplayStatus(isInFullscreen.value ? 'fullscreen' : 'windowed', isInFullscreen.value)
}

/**
 * 处理浏览器级全屏快捷键。
 * @param event 键盘事件
 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'F11') {
    isFullscreenPromptDismissed.value = true
    fullscreenMessage.value = ''
    return
  }

  if (isKeyboardTargetInteractive(event.target)) {
    return
  }

  if (event.key === 'PageDown' || event.key === 'ArrowRight' || event.key === ' ') {
    event.preventDefault()
    goNext()
    return
  }
  if (event.key === 'PageUp' || event.key === 'ArrowLeft') {
    event.preventDefault()
    goPrevious()
  }
}

/**
 * 判断键盘事件目标是否应保留原生交互。
 * @param target 事件目标
 * @returns 是否为输入或按钮类交互元素
 */
function isKeyboardTargetInteractive(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false
  }
  return target.tagName === 'INPUT'
    || target.tagName === 'TEXTAREA'
    || target.tagName === 'BUTTON'
    || target.isContentEditable
}

onMounted(() => {
  updateFullscreenState()
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('fullscreenchange', updateFullscreenState)
  window.addEventListener('beforeunload', handleBeforeUnload)
})

onUnmounted(() => {
  postDisplayStatus('closed', false)
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('fullscreenchange', updateFullscreenState)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

/**
 * 在窗口即将关闭时上报关闭状态。
 */
function handleBeforeUnload(): void {
  postDisplayStatus('closed', false)
}
</script>

<style scoped>
.presenter-display-screen {
  position: fixed;
  inset: 0;
  z-index: 10000;
  width: 100vw;
  height: 100vh;
  background: #050709;
  overflow: hidden;
}

.presenter-display-screen__content {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.presenter-display-screen__preview {
  width: 100%;
  height: 100%;
}

.presenter-display-screen__waiting {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.75);
  font-size: 14px;
}

.presenter-display-screen__fullscreen-panel {
  position: fixed;
  top: 50%;
  left: 50%;
  z-index: 10001;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.55);
  border-radius: 8px;
  width: min(560px, calc(100vw - 3rem));
  padding: 1rem;
  transform: translate(-50%, -50%);
  color: rgba(255, 255, 255, 0.95);
  background: rgba(15, 23, 42, 0.82);
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(12px);
}

.presenter-display-screen__fullscreen-copy {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.presenter-display-screen__fullscreen-kicker {
  color: rgba(226, 232, 240, 0.72);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
}

.presenter-display-screen__fullscreen-copy h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.35;
}

.presenter-display-screen__screen-list {
  display: grid;
  gap: 0.625rem;
  max-height: min(45vh, 360px);
  overflow: auto;
}

.presenter-display-screen__screen-button,
.presenter-display-screen__fullscreen-action,
.presenter-display-screen__fallback-action {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(226, 232, 240, 0.36);
  border-radius: 8px;
  min-height: 3rem;
  padding: 0.75rem 1rem;
  color: rgba(255, 255, 255, 0.95);
  background: rgba(30, 41, 59, 0.88);
  font-size: 15px;
  font-weight: 800;
  cursor: pointer;
}

.presenter-display-screen__screen-button {
  flex-direction: column;
  align-items: flex-start;
}

.presenter-display-screen__screen-button small {
  margin-top: 0.25rem;
  color: rgba(203, 213, 225, 0.78);
  font-size: 12px;
  font-weight: 700;
}

.presenter-display-screen__fullscreen-action {
  background: #4f46e5;
}

.presenter-display-screen__fallback-action {
  min-height: 2.5rem;
  color: rgba(226, 232, 240, 0.9);
  background: rgba(15, 23, 42, 0.72);
  font-size: 13px;
}

.presenter-display-screen__screen-button:hover,
.presenter-display-screen__fullscreen-action:hover,
.presenter-display-screen__fallback-action:hover {
  border-color: rgba(255, 255, 255, 0.72);
  background: rgba(51, 65, 85, 0.95);
}

.presenter-display-screen__fullscreen-action:hover {
  background: #4338ca;
}

.presenter-display-screen__fullscreen-action:disabled {
  cursor: progress;
  opacity: 0.64;
}

.presenter-display-screen__warning {
  position: fixed;
  right: 1rem;
  left: 1rem;
  bottom: 0.875rem;
  text-align: center;
  color: rgba(255, 255, 255, 0.75);
  font-size: 12px;
}
</style>
