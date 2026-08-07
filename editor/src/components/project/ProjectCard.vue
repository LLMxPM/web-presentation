<!-- 文件功能：以首个页面截图为主体渲染项目卡片，并提供悬浮信息、快捷操作与身份复制。 -->
<template>
  <article data-testid="project-card" class="project-card group/card">
    <div class="project-card-identity">
      <UiButton
        variant="ghost"
        size="xs"
        content-align="start"
        class="min-w-0 flex-1"
        :title="`复制项目名称：${project.name}`"
        :aria-label="`复制项目名称：${project.name}`"
        @click="copyText(project.name, '项目名称')"
      >
        <span class="block min-w-0 max-w-full truncate text-sm font-bold">{{ project.name }}</span>
      </UiButton>
      <UiButton
        variant="ghost"
        size="xs"
        class="min-w-0 max-w-36"
        :title="`复制项目编码：${project.code}`"
        :aria-label="`复制项目编码：${project.code}`"
        @click="copyText(project.code, '项目编码')"
      >
        <span class="block truncate font-mono text-[10px] font-semibold uppercase tracking-widest">
          {{ project.code }}
        </span>
      </UiButton>
    </div>

    <div
      class="project-card-preview"
      :class="!project.first_page_screenshot_url && project.first_page_title ? 'project-card-preview-missing' : ''"
    >
      <img
        v-if="project.first_page_screenshot_url"
        :src="project.first_page_screenshot_url"
        :alt="`${project.name} 首个页面截图`"
        class="h-full w-full object-cover transition-transform duration-300 group-hover/card:scale-[1.015]"
        loading="lazy"
      >
      <div
        v-else
        data-testid="project-card-placeholder"
        class="flex h-full w-full flex-col items-center justify-center gap-2"
        :class="project.first_page_title ? 'text-warning-strong' : 'text-text-disabled'"
      >
        <ImageOff v-if="project.first_page_title" class="h-7 w-7" />
        <Presentation v-else class="h-7 w-7" />
        <span class="text-xs font-semibold">{{ placeholderText }}</span>
        <span class="text-[10px]" :class="project.first_page_title ? 'text-warning-strong/75' : 'text-text-muted'">
          {{ project.first_page_title ? '打开项目后更新封面截图' : '进入项目后创建第一个页面' }}
        </span>
      </div>

      <a
        :href="projectPath"
        class="absolute inset-0 z-10 h-full w-full bg-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-border-focus"
        :aria-label="`打开项目：${project.name}`"
        @click.prevent="emit('open', project.id)"
      />

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

    <div class="project-card-summary">
      <div class="project-card-meta" aria-label="项目概览">
        <span class="project-card-meta-primary">
          <RouteIcon class="h-3 w-3" />
          已编排 {{ project.routed_page_count }} / {{ project.total_page_count }} 页
        </span>
        <span>{{ project.page_width }}×{{ project.page_height }}</span>
        <span class="ml-auto min-w-0 truncate" :title="`更新于 ${formatDateTime(project.updated_at)}`">
          {{ formatDateTime(project.updated_at) }}
        </span>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Archive, Download, ImageOff, Play, Presentation, Route as RouteIcon } from '@lucide/vue'

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
  border: 1px solid rgb(var(--ui-accent-border));
  border-radius: var(--ui-radius-lg);
  background: rgb(var(--ui-surface-muted));
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
  margin: 0.5rem;
  aspect-ratio: 2 / 1;
  overflow: hidden;
  border: 1px solid rgb(var(--ui-border-muted));
  border-radius: var(--ui-radius-md);
  background: rgb(var(--ui-surface-muted));
}

.project-card-preview-missing {
  border-color: rgb(var(--ui-warning-border));
  background: rgb(var(--ui-warning-muted));
}

.project-card-identity {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  min-width: 0;
  border-bottom: 1px solid rgb(var(--ui-accent-border));
  background: rgb(var(--ui-accent-muted));
  padding: 0.375rem 0.5rem;
  color: rgb(var(--ui-accent-hover));
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

.project-card:hover .project-card-actions,
.project-card:focus-within .project-card-actions {
  opacity: 1;
}

.project-card:hover .project-card-actions,
.project-card:focus-within .project-card-actions {
  transform: translateY(0);
}

.project-card-summary {
  padding: 0.625rem 0.75rem;
  border-top: 1px solid rgb(var(--ui-accent-border));
  background: rgb(var(--ui-surface));
}

.project-card-meta {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0.75rem;
  color: rgb(var(--ui-text-muted));
  font-size: 0.625rem;
  line-height: 1rem;
}

.project-card-meta-primary {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  gap: 0.25rem;
  color: rgb(var(--ui-text-secondary));
  font-weight: 700;
}
</style>
