<!-- 文件功能：渲染项目页面列表中的单张页面卡片，统一承载截图、路由信息、选择与卡片操作入口。 -->
<template>
  <article
    data-testid="page-card"
    class="group/card relative isolate flex cursor-pointer flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition-all duration-300 hover:-translate-y-1 hover:border-indigo-300 hover:shadow-md"
    :class="selected ? 'border-indigo-400 ring-2 ring-indigo-100' : ''"
    @click="emit('open', page.id)"
  >
    <div class="relative overflow-hidden bg-slate-100" :style="{ aspectRatio: screenshotAspectRatio }">
      <img
        v-if="page.screenshot_url"
        :src="page.screenshot_url"
        :alt="`${page.title} 截图`"
        class="h-full w-full object-cover transition-transform duration-300 group-hover/card:scale-[1.02]"
        loading="lazy"
      >
      <div v-else class="flex h-full w-full flex-col items-center justify-center gap-1.5 text-slate-400">
        <Layout class="h-6 w-6" />
        <span class="text-[10px] font-semibold tracking-wide">尚未保存截图</span>
      </div>

      <span v-if="showStaleBadge" class="page-card-stale-ribbon">
        <span>旧截图</span>
      </span>

      <div
        class="page-card-topbar"
        :class="[
          mode === 'unrouted' ? 'page-card-topbar-end' : '',
          selected ? 'page-card-topbar-active' : '',
        ]"
      >
        <div v-if="mode === 'routed'" class="page-card-route-path">
          <RouteIcon class="h-3 w-3 shrink-0" />
          <span class="min-w-0 truncate">{{ routePath }}</span>
          <span v-if="isDuplicate" class="shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-amber-700">
            重复 {{ duplicateIndex }}/{{ duplicateTotal }}
          </span>
        </div>

        <div class="page-card-top-actions">
          <label
            class="page-card-select"
            :class="selected ? 'page-card-select-active' : ''"
            title="选择页面"
            aria-label="选择页面"
            @click.stop
          >
            <input
              :data-testid="selectionTestId"
              type="checkbox"
              class="sr-only"
              :checked="selected"
              @change="handleSelectChange"
            >
            <span class="page-card-select-box">
              <Check v-if="selected" class="h-3 w-3" />
            </span>
          </label>
        </div>
      </div>

      <div
        class="pointer-events-none absolute inset-x-2 bottom-2 z-20 flex translate-y-1 justify-end gap-1 opacity-0 transition-all group-hover/card:pointer-events-auto group-hover/card:translate-y-0 group-hover/card:opacity-100"
      >
        <button
          v-if="mode === 'routed'"
          type="button"
          class="page-card-action"
          title="管理路由"
          aria-label="管理路由"
          @click.stop="emit('open-route-config')"
        >
          <RouteIcon class="h-3.5 w-3.5" />
        </button>
        <button
          v-else
          type="button"
          class="page-card-action"
          title="加入顶层路由"
          aria-label="加入顶层路由"
          :disabled="routePending"
          @click.stop="emit('add-route', page)"
        >
          <RouteIcon class="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          class="page-card-action"
          title="复制到其他项目"
          aria-label="复制到其他项目"
          @click.stop="emit('copy-page', page)"
        >
          <Copy class="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          data-testid="page-card-screenshot"
          class="page-card-action"
          title="更新截图"
          aria-label="更新截图"
          :disabled="screenshotDisabled"
          @click.stop="emit('save-screenshot', page)"
        >
          <LoaderCircle v-if="screenshotPending" class="h-3.5 w-3.5 animate-spin" />
          <Camera v-else class="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          class="page-card-action text-amber-600 hover:bg-amber-50"
          title="归档页面"
          aria-label="归档页面"
          :disabled="archivePending"
          @click.stop="emit('archive-page', page)"
        >
          <Archive class="h-3.5 w-3.5" />
        </button>
      </div>
    </div>

    <div class="p-3">
      <div class="flex min-w-0 items-center gap-2">
        <h3
          class="truncate text-sm font-bold leading-tight text-slate-800 transition-colors group-hover/card:text-indigo-600"
          :title="page.title"
        >
          {{ page.title }}
        </h3>
        <div class="shrink-0 font-mono text-[10px] font-semibold uppercase tracking-widest text-slate-400">
          {{ page.code }}
        </div>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Archive, Camera, Check, Copy, Layout, LoaderCircle, Route as RouteIcon } from '@lucide/vue'

import type { PageItem } from '@/types/api'

const props = withDefaults(defineProps<{
  page: PageItem
  mode: 'routed' | 'unrouted'
  selected: boolean
  selectionTestId: string
  screenshotAspectRatio: string
  screenshotDisabled: boolean
  screenshotPending: boolean
  archivePending: boolean
  routePending?: boolean
  routePath?: string
  duplicateIndex?: number
  duplicateTotal?: number
  isDuplicate?: boolean
}>(), {
  routePending: false,
  routePath: '',
  duplicateIndex: 1,
  duplicateTotal: 1,
  isDuplicate: false,
})

const emit = defineEmits<{
  open: [pageId: number]
  'select-change': [pageId: number, event: Event]
  'open-route-config': []
  'copy-page': [page: PageItem]
  'save-screenshot': [page: PageItem]
  'archive-page': [page: PageItem]
  'add-route': [page: PageItem]
}>()

// 是否显示过期截图标识；该标识以右上角斜标常驻，不再占用 hover 工具条布局。
const showStaleBadge = computed(() => Boolean(props.page.screenshot_url && !props.page.screenshot_is_latest))

/**
 * 将页面选择变更上抛给列表视图，保留原有的批量选择状态来源。
 * @param event 复选框变更事件
 */
function handleSelectChange(event: Event): void {
  emit('select-change', props.page.id, event)
}
</script>

<style scoped>
.page-card-action {
  display: inline-flex;
  height: 1.875rem;
  width: 1.875rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  background: rgb(255 255 255 / 0.95);
  color: rgb(71 85 105);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
  transition: all 0.2s ease;
}

.page-card-action:hover {
  border-color: rgb(199 210 254);
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}

.page-card-action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.page-card-select {
  display: inline-flex;
  height: 1.5rem;
  width: 1.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid rgb(203 213 225);
  background: rgb(255 255 255 / 0.95);
  color: rgb(100 116 139);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
  backdrop-filter: blur(6px);
  cursor: pointer;
  transition: all 0.18s ease;
}

.page-card-select:hover,
.page-card-select-active {
  border-color: rgb(129 140 248);
  background: rgb(238 242 255 / 0.96);
  color: rgb(79 70 229);
  opacity: 1;
  transform: translateY(-1px);
}

.page-card-select-active {
  background: rgb(79 70 229 / 0.96);
  color: white;
}

.page-card-select-box {
  display: inline-flex;
  height: 0.875rem;
  width: 0.875rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid currentColor;
}

.page-card-topbar {
  pointer-events: none;
  position: absolute;
  inset: 0.5rem 0.5rem auto;
  z-index: 30;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  opacity: 0;
  transform: translateY(-0.25rem);
  transition: all 0.2s ease;
}

.group\/card:hover .page-card-topbar,
.page-card-topbar-active {
  pointer-events: auto;
  opacity: 1;
  transform: translateY(0);
}

.page-card-topbar-end {
  justify-content: flex-end;
}

.page-card-route-path {
  display: inline-flex;
  min-width: 0;
  max-width: calc(100% - 2rem);
  min-height: 1.5rem;
  align-items: center;
  gap: 0.375rem;
  border-radius: 9999px;
  border: 1px solid rgb(167 243 208);
  background: rgb(255 255 255 / 0.95);
  padding: 0.25rem 0.5rem;
  font-size: 0.625rem;
  font-weight: 700;
  color: rgb(4 120 87);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
  backdrop-filter: blur(6px);
}

.page-card-top-actions {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.375rem;
}

.page-card-stale-ribbon {
  pointer-events: none;
  position: absolute;
  top: 0;
  right: 0;
  z-index: 20;
  height: 4.5rem;
  width: 4.5rem;
  overflow: hidden;
}

.page-card-stale-ribbon > span {
  position: absolute;
  top: 0.7rem;
  right: -1.75rem;
  display: inline-flex;
  height: 1.25rem;
  width: 6.25rem;
  align-items: center;
  justify-content: center;
  transform: rotate(45deg);
  border: 1px solid rgb(253 230 138);
  background: rgb(255 251 235 / 0.96);
  font-size: 0.625rem;
  font-weight: 800;
  color: rgb(180 83 9);
  box-shadow: 0 1px 3px rgb(15 23 42 / 0.12);
}
</style>
