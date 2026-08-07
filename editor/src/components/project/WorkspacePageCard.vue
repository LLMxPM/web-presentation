<!-- 文件功能：渲染工作空间全部页面弹窗中的页面卡片，并提供统一的悬浮信息和快捷操作。 -->
<template>
  <article data-testid="workspace-page-card" class="page-card group group/card">
    <div class="page-card-preview" :style="{ aspectRatio: screenshotAspectRatio }">
      <a
        :href="pagePath"
        class="absolute inset-0 z-10 h-full w-full cursor-pointer bg-transparent text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-border-focus"
        :aria-label="`查看页面详情：${page.title}`"
        @click.prevent="emit('open', page)"
      >
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
      </a>

      <div class="page-card-overlay" aria-hidden="true">
        <span class="truncate text-xs font-semibold text-text-on-inverse/85">
          {{ page.project_name || '未归属项目' }}
        </span>
      </div>

      <div class="page-card-actions">
        <UiIconButton
          label="复制页面"
          size="sm"
          variant="secondary"
          title="复制页面"
          @click.stop="emit('copy', page)"
        >
          <Copy class="h-3.5 w-3.5" />
        </UiIconButton>
        <UiIconButton
          label="更新截图"
          size="sm"
          variant="secondary"
          title="更新截图"
          :disabled="screenshotPending || screenshotDisabled"
          @click.stop="emit('screenshot', page)"
        >
          <LoaderCircle v-if="screenshotPending" class="h-3.5 w-3.5 animate-spin" />
          <Camera v-else class="h-3.5 w-3.5" />
        </UiIconButton>
        <UiIconButton
          label="下载截图"
          size="sm"
          variant="secondary"
          title="下载截图"
          :disabled="screenshotPending"
          @click.stop="emit('download', page)"
        >
          <LoaderCircle v-if="screenshotPending" class="h-3.5 w-3.5 animate-spin" />
          <Download v-else class="h-3.5 w-3.5" />
        </UiIconButton>
        <UiIconButton
          label="归档页面"
          size="sm"
          variant="secondary"
          title="归档页面"
          :disabled="archivePending"
          @click.stop="emit('archive', page)"
        >
          <Archive class="h-3.5 w-3.5" />
        </UiIconButton>
      </div>
    </div>

    <div class="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-2 p-3">
      <UiButton
        variant="ghost"
        size="xs"
        content-align="start"
        class="min-w-0 text-left text-sm font-bold leading-tight text-text transition-colors hover:text-accent"
        :title="`复制页面名称：${page.title}`"
        :aria-label="`复制页面名称：${page.title}`"
        @click.stop="emit('copy-name', page)"
      >
        <span class="block min-w-0 truncate">{{ page.title }}</span>
      </UiButton>
      <UiButton
        variant="ghost"
        size="xs"
        class="min-w-0 max-w-36"
        :title="`复制页面编码：${page.code}`"
        :aria-label="`复制页面编码：${page.code}`"
        @click.stop="emit('copy-code', page)"
      >
        <span class="block truncate font-mono text-[10px] font-semibold uppercase tracking-widest text-text-disabled">
          {{ page.code }}
        </span>
      </UiButton>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Archive, Camera, Copy, Download, Layout, LoaderCircle } from '@lucide/vue'

import { UiButton, UiIconButton } from '@/components/ui'
import type { PageItem } from '@/types/api'
import { buildPageDetailPath } from '@/utils/workspace-routes'

const props = withDefaults(defineProps<{
  page: PageItem
  screenshotAspectRatio?: string
  screenshotPending?: boolean
  screenshotDisabled?: boolean
  archivePending?: boolean
}>(), {
  screenshotAspectRatio: '16 / 9',
  screenshotPending: false,
  screenshotDisabled: false,
  archivePending: false,
})

const pagePath = computed(() => (
  props.page.workspace_id && props.page.project_id
    ? buildPageDetailPath(props.page.workspace_id, props.page.project_id, props.page.id)
    : '#'
))

const emit = defineEmits<{
  open: [page: PageItem]
  copy: [page: PageItem]
  'copy-name': [page: PageItem]
  'copy-code': [page: PageItem]
  screenshot: [page: PageItem]
  download: [page: PageItem]
  archive: [page: PageItem]
}>()
</script>

<style scoped>
.page-card {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  border: 1px solid rgb(var(--ui-border));
  border-radius: var(--ui-radius-lg);
  background: rgb(var(--ui-surface));
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.04);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.page-card:hover,
.page-card:focus-within {
  border-color: rgb(var(--ui-accent-border));
  box-shadow: 0 10px 24px rgb(15 23 42 / 0.08);
  transform: translateY(-0.125rem);
}

.page-card-preview {
  position: relative;
  overflow: hidden;
  background: rgb(var(--ui-surface-muted));
}

.page-card-overlay {
  pointer-events: none;
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: flex-end;
  padding: 3rem 0.75rem 0.75rem;
  background: linear-gradient(to top, rgb(var(--ui-overlay) / 0.92), rgb(var(--ui-overlay) / 0.08) 72%);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.page-card-actions {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  z-index: 30;
  display: flex;
  gap: 0.25rem;
  opacity: 0;
  transform: translateY(-0.25rem);
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.page-card:hover .page-card-overlay,
.page-card:focus-within .page-card-overlay,
.page-card:hover .page-card-actions,
.page-card:focus-within .page-card-actions {
  opacity: 1;
}

.page-card:hover .page-card-actions,
.page-card:focus-within .page-card-actions {
  transform: translateY(0);
}
</style>
