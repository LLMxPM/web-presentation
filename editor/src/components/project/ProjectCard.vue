<!-- 文件功能：以首个页面截图为主体渲染项目卡片，并提供悬浮信息、快捷操作与身份复制。 -->
<template>
  <article data-testid="project-card" class="project-card group/card">
    <div class="project-card-preview">
      <img
        v-if="project.first_page_screenshot_url"
        :src="project.first_page_screenshot_url"
        :alt="`${project.name} 首个页面截图`"
        class="h-full w-full object-cover transition-transform duration-300 group-hover/card:scale-[1.015]"
        loading="lazy"
      >
      <div v-else class="flex h-full w-full flex-col items-center justify-center gap-2 text-text-disabled">
        <Presentation class="h-7 w-7" />
        <span class="text-xs font-semibold">{{ placeholderText }}</span>
      </div>

      <a
        :href="projectPath"
        class="absolute inset-0 z-10 h-full w-full bg-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-border-focus"
        :aria-label="`打开项目：${project.name}`"
        @click.prevent="emit('open', project.id)"
      />

      <div class="project-card-route-count" aria-hidden="true">
        路由页面 {{ project.routed_page_count }} / {{ project.total_page_count }}
      </div>

      <div class="project-card-overlay" aria-hidden="true">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-on-inverse/75">
          <span>{{ project.page_width }}×{{ project.page_height }}</span>
          <span>更新于 {{ formatDateTime(project.updated_at) }}</span>
        </div>
      </div>

      <div class="project-card-actions">
        <UiIconButton
          label="预览项目"
          size="sm"
          variant="secondary"
          :disabled="previewPending"
          :loading="previewPending"
          :title="previewPending ? '正在生成项目预览' : '预览项目'"
          @click.stop="emit('preview', project)"
        >
          <Play class="h-3.5 w-3.5" />
        </UiIconButton>
        <UiIconButton
          label="导出项目"
          size="sm"
          variant="secondary"
          :disabled="exportPending || exportDisabled"
          :loading="exportPending"
          :title="exportPending ? '项目导出预检中' : '导出项目'"
          @click.stop="emit('export-template', project)"
        >
          <Download class="h-3.5 w-3.5" />
        </UiIconButton>
        <UiIconButton
          label="归档项目"
          size="sm"
          variant="secondary"
          :disabled="archivePending"
          :loading="archivePending"
          :title="archivePending ? '项目归档中' : '归档项目'"
          @click.stop="emit('archive', project)"
        >
          <Archive class="h-3.5 w-3.5" />
        </UiIconButton>
      </div>
    </div>

    <div class="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-2 p-3">
      <div class="min-w-0">
        <UiButton
          variant="ghost"
          size="xs"
          content-align="start"
          class="min-w-0 w-full"
          :title="`复制项目名称：${project.name}`"
          :aria-label="`复制项目名称：${project.name}`"
          @click="copyText(project.name, '项目名称')"
        >
          <span class="block min-w-0 max-w-full truncate text-sm font-bold">{{ project.name }}</span>
        </UiButton>
      </div>
      <UiButton
        variant="ghost"
        size="xs"
        class="max-w-36"
        :title="`复制项目编码：${project.code}`"
        :aria-label="`复制项目编码：${project.code}`"
        @click="copyText(project.code, '项目编码')"
      >
        <span class="truncate font-mono text-[10px] font-semibold uppercase tracking-widest text-text-disabled">
          {{ project.code }}
        </span>
      </UiButton>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Archive, Download, Play, Presentation } from '@lucide/vue'

import { UiButton, UiIconButton } from '@/components/ui'
import type { ProjectItem } from '@/types/api'
import { formatDateTime } from '@/utils/format'
import { Message } from '@/utils/message'
import { buildProjectPagesPath } from '@/utils/workspace-routes'

const props = withDefaults(defineProps<{
  project: ProjectItem
  previewPending?: boolean
  exportPending?: boolean
  exportDisabled?: boolean
  archivePending?: boolean
}>(), {
  previewPending: false,
  exportPending: false,
  exportDisabled: false,
  archivePending: false,
})

const emit = defineEmits<{
  open: [projectId: number]
  preview: [project: ProjectItem]
  'export-template': [project: ProjectItem]
  archive: [project: ProjectItem]
}>()

const placeholderText = computed(() => props.project.first_page_title ? '首个页面暂无截图' : '项目暂无页面')
const projectPath = computed(() => buildProjectPagesPath(props.project.workspace_id, props.project.id))

/**
 * 复制项目名称或编码，复制按钮与打开项目入口互不干扰。
 * @param value 需要写入剪贴板的文本
 * @param label 面向用户的字段名称
 */
async function copyText(value: string, label: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value)
    Message.success(`${label}已复制。`)
  } catch {
    Message.error('复制失败，请检查浏览器剪贴板权限。')
  }
}
</script>

<style scoped>
.project-card {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  border: 1px solid rgb(var(--ui-border));
  border-radius: var(--ui-radius-lg);
  background: rgb(var(--ui-surface));
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.04);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.project-card:hover,
.project-card:focus-within {
  border-color: rgb(var(--ui-accent-border));
  box-shadow: 0 10px 24px rgb(15 23 42 / 0.08);
  transform: translateY(-0.125rem);
}

.project-card-preview {
  position: relative;
  aspect-ratio: 2 / 1;
  overflow: hidden;
  background: rgb(var(--ui-surface-muted));
}

.project-card-overlay {
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

.project-card-route-count {
  pointer-events: none;
  position: absolute;
  top: 0.75rem;
  left: 0.75rem;
  z-index: 30;
  border-radius: 9999px;
  border: 1px solid rgb(var(--ui-border-strong) / 0.9);
  background: rgb(var(--ui-surface) / 0.96);
  padding: 0.25rem 0.5rem;
  color: rgb(var(--ui-text));
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1rem;
  box-shadow: 0 2px 6px rgb(15 23 42 / 0.2);
  opacity: 0;
  transform: translateY(-0.25rem);
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.project-card-actions {
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

.project-card:hover .project-card-overlay,
.project-card:focus-within .project-card-overlay,
.project-card:hover .project-card-route-count,
.project-card:focus-within .project-card-route-count,
.project-card:hover .project-card-actions,
.project-card:focus-within .project-card-actions {
  opacity: 1;
}

.project-card:hover .project-card-actions,
.project-card:focus-within .project-card-actions {
  transform: translateY(0);
}

.project-card:hover .project-card-route-count,
.project-card:focus-within .project-card-route-count {
  transform: translateY(0);
}
</style>
