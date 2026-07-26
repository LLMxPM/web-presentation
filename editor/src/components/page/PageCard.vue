<!-- 文件功能：渲染项目页面列表中的单张页面卡片，统一承载截图、路由信息、选择与卡片操作入口。 -->
<template>
  <article
    data-testid="page-card"
    class="group/card relative isolate flex cursor-pointer flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-sm transition-all duration-300 hover:-translate-y-1 hover:border-accent-border hover:shadow-md"
    :class="selected ? 'border-accent-border ring-2 ring-accent-muted' : ''"
    @click="emit('open', page.id)"
  >
    <div class="relative overflow-hidden bg-surface-muted" :style="{ aspectRatio: screenshotAspectRatio }">
      <img
        v-if="page.screenshot_url"
        :src="page.screenshot_url"
        :alt="`${page.title} 截图`"
        class="h-full w-full object-cover transition-transform duration-300 group-hover/card:scale-[1.02]"
        loading="lazy"
      >
      <div v-else class="flex h-full w-full flex-col items-center justify-center gap-1.5 text-text-disabled">
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
          <span v-if="isDuplicate" class="shrink-0 rounded-full bg-warning-muted px-1.5 py-0.5 text-warning-strong">
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
            <UiCheckbox
              :data-testid="selectionTestId"
              :model-value="selected"
              class="sr-only"
              @update:model-value="handleSelectChange"
            />
            <span class="page-card-select-box">
              <Check v-if="selected" class="h-3 w-3" />
            </span>
          </label>
        </div>
      </div>

      <CardActionBar>
        <UiIconButton
          v-if="mode === 'routed'"
          label="管理路由"
          size="sm"
          variant="secondary"
          title="管理路由"
          @click.stop="emit('open-route-config')"
        >
          <RouteIcon class="h-3.5 w-3.5" />
        </UiIconButton>
        <UiIconButton
          v-else
          label="加入顶层路由"
          size="sm"
          variant="secondary"
          title="加入顶层路由"
          :disabled="routePending"
          @click.stop="emit('add-route', page)"
        >
          <RouteIcon class="h-3.5 w-3.5" />
        </UiIconButton>
        <UiIconButton
          label="复制到其他项目"
          size="sm"
          variant="secondary"
          title="复制到其他项目"
          @click.stop="emit('copy-page', page)"
        >
          <Copy class="h-3.5 w-3.5" />
        </UiIconButton>
        <UiIconButton
          label="更新截图"
          data-testid="page-card-screenshot"
          size="sm"
          variant="secondary"
          title="更新截图"
          :disabled="screenshotDisabled"
          @click.stop="emit('save-screenshot', page)"
        >
          <LoaderCircle v-if="screenshotPending" class="h-3.5 w-3.5 animate-spin" />
          <Camera v-else class="h-3.5 w-3.5" />
        </UiIconButton>
        <UiIconButton
          label="归档页面"
          size="sm"
          variant="secondary"
          title="归档页面"
          :disabled="archivePending"
          @click.stop="emit('archive-page', page)"
        >
          <Archive class="h-3.5 w-3.5" />
        </UiIconButton>
      </CardActionBar>
    </div>

    <div class="p-3">
      <div class="flex min-w-0 items-center gap-2">
        <h3
          class="truncate text-sm font-bold leading-tight text-text transition-colors group-hover/card:text-accent"
          :title="page.title"
        >
          {{ page.title }}
        </h3>
        <button
          type="button"
          class="shrink-0 cursor-pointer font-mono text-[10px] font-semibold uppercase tracking-widest text-text-disabled transition-colors hover:text-accent"
          title="复制页面名称和编码"
          aria-label="复制页面名称和编码"
          @click.stop="handleCopyPageIdentity"
        >
          {{ page.code }}
        </button>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Archive, Camera, Check, Copy, Layout, LoaderCircle, Route as RouteIcon } from '@lucide/vue'

import CardActionBar from '@/components/patterns/CardActionBar.vue'
import { UiCheckbox, UiIconButton } from '@/components/ui'
import type { PageItem } from '@/types/api'
import { Message } from '@/utils/message'

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
 * 复制页面名称和编码到剪贴板，便于在对话或文档中引用页面。
 */
async function handleCopyPageIdentity(): Promise<void> {
  const identityText = `${props.page.title} ${props.page.code}`
  try {
    await navigator.clipboard.writeText(identityText)
    Message.success(`已复制：${identityText}`)
  } catch {
    Message.error('复制失败，请检查浏览器剪贴板权限。')
  }
}

/**
 * 将页面选择变更上抛给列表视图，保留原有的批量选择状态来源。
 * @param checked 当前复选框值
 */
function handleSelectChange(checked: boolean | 'indeterminate'): void {
  emit('select-change', props.page.id, { target: { checked: checked === true } } as unknown as Event)
}
</script>

<style scoped>
.page-card-select {
  display: inline-flex;
  height: 1.5rem;
  width: 1.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 9999px;
  border: 1px solid rgb(var(--ui-border-strong));
  background: rgb(var(--ui-surface) / 0.95);
  color: rgb(var(--ui-text-muted));
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.08);
  backdrop-filter: blur(6px);
  cursor: pointer;
  transition: all 0.18s ease;
}

.page-card-select:hover,
.page-card-select-active {
  border-color: rgb(var(--ui-accent-border));
  background: rgb(var(--ui-surface-selected) / 0.96);
  color: rgb(var(--ui-accent));
  opacity: 1;
  transform: translateY(-1px);
}

.page-card-select-active {
  background: rgb(var(--ui-accent) / 0.96);
  color: rgb(var(--ui-text-inverse));
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
  border: 1px solid rgb(var(--ui-success-border));
  background: rgb(var(--ui-surface) / 0.95);
  padding: 0.25rem 0.5rem;
  font-size: 0.625rem;
  font-weight: 700;
  color: rgb(var(--ui-success-strong));
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
  border: 1px solid rgb(var(--ui-warning-border));
  background: rgb(var(--ui-warning-muted) / 0.96);
  font-size: 0.625rem;
  font-weight: 800;
  color: rgb(var(--ui-warning-strong));
  box-shadow: 0 1px 3px rgb(15 23 42 / 0.12);
}
</style>
