<!--
  文件用途：Runtime 演讲者控制台，展示当前页、演讲者备注、下一页预览和平铺导航。
-->

<template>
  <div class="presenter-console">
    <header class="presenter-console__header">
      <div class="presenter-console__title">
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-500">演讲者控制台</p>
        <h1 class="truncate text-xl font-bold text-slate-950">
          {{ currentPage?.title || '未找到页面' }}
        </h1>
      </div>

      <div class="presenter-console__header-actions">
        <span class="presenter-console__display-status" :class="displayStatusClass">
          观众窗口：{{ displayStatusLabel }}
        </span>
        <button type="button" class="presenter-console__button" :class="{ 'presenter-console__button--active': viewMode === 'focus' }" @click="viewMode = 'focus'">
          单页
        </button>
        <button type="button" class="presenter-console__button" :class="{ 'presenter-console__button--active': viewMode === 'grid' }" @click="viewMode = 'grid'">
          平铺
        </button>
        <button type="button" class="presenter-console__button" @click="openDisplayWindow">
          <Monitor class="h-3.5 w-3.5" />
          观众窗口
        </button>
        <div v-if="viewMode === 'grid'" class="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5">
          <span class="text-xs text-slate-500">页面大小</span>
          <input
            class="w-32 accent-indigo-600"
            type="range"
            min="140"
            max="420"
            step="10"
            :value="tileSize"
            @input="handleTileSizeInput"
          />
          <span class="w-10 text-right text-xs font-semibold text-slate-600">{{ tileSize }}</span>
        </div>
        <button type="button" class="presenter-console__button presenter-console__button--danger" @click="exitPresenterMode">
          <LogOut class="h-3.5 w-3.5" />
          退出
        </button>
      </div>
    </header>

    <main v-if="currentPage" class="presenter-console__body">
      <section v-if="viewMode === 'focus'" class="presenter-console__focus">
        <div class="presenter-console__current">
          <div class="presenter-console__preview-shell">
            <div class="presenter-console__preview-content" inert aria-hidden="true">
              <ViewPreview :file-path="currentPage.componentPath" />
            </div>
            <div class="presenter-console__preview-shield" aria-hidden="true"></div>
          </div>
        </div>

        <aside class="presenter-console__side">
          <section class="presenter-console__panel presenter-console__next">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-sm font-bold text-slate-900">下一页</h2>
              <span v-if="nextPage" class="text-xs text-slate-400">{{ nextPage.pageNumber }}</span>
            </div>
            <button v-if="nextPage" type="button" class="presenter-console__next-frame" @click="navigateTo(nextPage.path)">
              <div class="presenter-console__preview-shell">
                <div class="presenter-console__preview-content" inert aria-hidden="true">
                  <ViewPreview :file-path="nextPage.componentPath" />
                </div>
                <div class="presenter-console__preview-shield" aria-hidden="true"></div>
              </div>
            </button>
            <div v-else class="presenter-console__empty">已经是最后一页</div>
          </section>

          <section class="presenter-console__panel presenter-console__notes-panel">
            <div class="flex items-center justify-between gap-2">
              <h2 class="text-sm font-bold text-slate-900">当前页备注</h2>
              <span class="text-xs text-slate-400">{{ currentPage.pageNumber }} / {{ pages.length }}</span>
            </div>
            <div class="presenter-console__notes">
              {{ currentPage.speakerNotes || '当前页面没有填写演讲者备注。' }}
            </div>
            <div class="presenter-console__notes-footer">
              <PresenterTimerPanel :current-path="currentPath" />
              <nav class="presenter-console__page-controls" aria-label="演讲翻页">
                <button
                  type="button"
                  class="presenter-console__page-button"
                  :disabled="!canGoPrevious"
                  @click="goPrevious"
                >
                  <ChevronLeft class="h-4 w-4" />
                  <span>上一页</span>
                </button>
                <div class="presenter-console__page-indicator">
                  {{ currentPage.pageNumber }} / {{ pages.length }}
                </div>
                <button
                  type="button"
                  class="presenter-console__page-button presenter-console__page-button--primary"
                  :disabled="!canGoNext"
                  @click="goNext"
                >
                  <span>下一页</span>
                  <ChevronRight class="h-4 w-4" />
                </button>
              </nav>
            </div>
          </section>
        </aside>
      </section>

      <PresenterPageGrid
        v-else
        :pages="pages"
        :current-path="currentPath"
        :tile-size="tileSize"
        @navigate="navigateTo"
      />
    </main>

    <div v-else class="presenter-console__fallback">
      当前项目没有可演讲页面。
    </div>

    <p v-if="!channelSupported" class="presenter-console__warning">
      当前浏览器不支持 BroadcastChannel，观众窗口无法联动。
    </p>

    <p v-else-if="displayWindowMessage" class="presenter-console__warning">
      {{ displayWindowMessage }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { switchRuntimeMode } from '@/core/router/runtime-session'
import { ChevronLeft, ChevronRight, LogOut, Monitor } from '@lucide/vue'

import ViewPreview from '@/runtime-shell/preview/ViewPreview.vue'
import PresenterPageGrid from '@/runtime-shell/presenter/PresenterPageGrid.vue'
import PresenterTimerPanel from '@/runtime-shell/presenter/PresenterTimerPanel.vue'
import { usePresenterController } from '@/runtime-shell/presenter/usePresenterController'
import { openPresenterDisplayWindow } from '@/runtime-shell/presenter/presenter-window'

const route = useRoute()
const router = useRouter()
const channelId = computed(() => String(route.query.channel || ''))
const initialPath = computed(() => String(route.query.route || route.path))
const displayWindowMessage = ref(route.query.displayBlocked === '1'
  ? '浏览器拦截了观众窗口，请允许弹窗后点击“观众窗口”重试。'
  : '')

const {
  pages,
  currentPath,
  currentPage,
  nextPage,
  canGoPrevious,
  canGoNext,
  displayStatus,
  viewMode,
  tileSize,
  channelSupported,
  navigateTo,
  goPrevious,
  goNext,
  setTileSize,
  postClose,
  postState,
} = usePresenterController({
  role: 'console',
  channelId: channelId.value,
  initialPath: initialPath.value,
})

const displayStatusLabel = computed(() => {
  switch (displayStatus.value.state) {
    case 'connected':
      return '已连接'
    case 'windowed':
      return '窗口模式'
    case 'fullscreen':
      return '全屏中'
    case 'closed':
      return '已关闭'
    default:
      return '未连接'
  }
})

const displayStatusClass = computed(() => ({
  'presenter-console__display-status--ok': displayStatus.value.state === 'connected' || displayStatus.value.state === 'windowed',
  'presenter-console__display-status--fullscreen': displayStatus.value.state === 'fullscreen',
  'presenter-console__display-status--closed': displayStatus.value.state === 'closed',
}))

/**
 * 处理平铺尺寸输入。
 * @param event 输入事件
 */
function handleTileSizeInput(event: Event): void {
  const target = event.target as HTMLInputElement
  setTileSize(Number(target.value))
}

/**
 * 从控制台补开观众展示窗口。
 */
function openDisplayWindow(): void {
  const displayWindow = openPresenterDisplayWindow(channelId.value, currentPath.value)
  if (!displayWindow) {
    displayWindowMessage.value = '浏览器拦截了观众窗口，请允许弹窗后重试。'
    return
  }
  displayWindowMessage.value = ''
  postState()
}

/**
 * 退出演讲模式，关闭观众窗口并回到进入演讲模式前的页面。
 */
function exitPresenterMode(): void {
  postClose()
  void switchRuntimeMode(router, 'normal')
}

/**
 * 处理控制台快捷键。
 * @param event 键盘事件
 */
function handleKeydown(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null
  if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable) {
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

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.presenter-console {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #f8fafc;
  color: #0f172a;
}

.presenter-console__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  min-height: 3rem;
  padding: 0.5rem 1.25rem;
  border-bottom: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.92);
}

.presenter-console__title {
  min-width: 0;
}

.presenter-console__header-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.5rem;
  min-width: 0;
}

.presenter-console__body {
  min-height: 0;
  flex: 1;
  padding: 0.5rem;
}

.presenter-console__focus {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 24vw);
  gap: 0.5rem;
  height: 100%;
}

.presenter-console__current,
.presenter-console__panel {
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  background: white;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  padding: 0.5rem;
}

.presenter-console__current {
  min-height: 0;
  overflow: hidden;
}

.presenter-console__side {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: minmax(220px, 2fr) minmax(0, 3fr);
  min-width: 0;
  min-height: 0;
  gap: 0.5rem;
  overflow: hidden;
}

.presenter-console__panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 0.875rem;
}

.presenter-console__notes {
  flex: 1;
  min-height: 0;
  margin-top: 0.5rem;
  overflow: auto;
  white-space: pre-wrap;
  color: #334155;
  font-size: 0.9375rem;
  line-height: 1.6;
}

.presenter-console__notes-footer {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.presenter-console__next {
  min-height: 0;
}

.presenter-console__next-frame {
  display: block;
  flex: 1;
  width: 100%;
  max-width: 100%;
  min-height: 0;
  margin-top: 0.5rem;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 0.625rem;
  background: #f8fafc;
  cursor: pointer;
}

.presenter-console__empty,
.presenter-console__fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #64748b;
  font-size: 0.875rem;
}

.presenter-console__button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 2rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  background: white;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 700;
  cursor: pointer;
}

.presenter-console__button {
  padding: 0 0.75rem;
}

.presenter-console__display-status {
  display: inline-flex;
  align-items: center;
  height: 2rem;
  border: 1px solid #cbd5e1;
  border-radius: 0.5rem;
  background: #f8fafc;
  padding: 0 0.625rem;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 800;
  white-space: nowrap;
}

.presenter-console__display-status--ok {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #166534;
}

.presenter-console__display-status--fullscreen {
  border-color: #c7d2fe;
  background: #eef2ff;
  color: #3730a3;
}

.presenter-console__display-status--closed {
  border-color: #fecaca;
  background: #fff1f2;
  color: #b91c1c;
}

.presenter-console__button--active {
  border-color: #c7d2fe;
  background: #eef2ff;
  color: #4f46e5;
}

.presenter-console__button--danger {
  border-color: #fecaca;
  background: #fff1f2;
  color: #b91c1c;
}

.presenter-console__button--danger:hover {
  border-color: #fca5a5;
  background: #ffe4e6;
}

.presenter-console__warning {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  max-width: min(420px, calc(100vw - 2rem));
  border: 1px solid #fcd34d;
  border-radius: 0.5rem;
  background: #fffbeb;
  padding: 0.625rem 0.875rem;
  color: #92400e;
  font-size: 0.8125rem;
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.12);
}

.presenter-console__page-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  width: 100%;
}

.presenter-console__page-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  min-width: 5.25rem;
  height: 2rem;
  border: 1px solid #cbd5e1;
  border-radius: 0.5rem;
  background: white;
  color: #334155;
  font-size: 0.75rem;
  font-weight: 800;
  cursor: pointer;
}

.presenter-console__page-button--primary {
  border-color: #4338ca;
  background: #4f46e5;
  color: white;
}

.presenter-console__page-button:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.presenter-console__page-indicator {
  min-width: 3.25rem;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 800;
  text-align: center;
}
</style>
