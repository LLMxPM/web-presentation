<!-- 文件功能：渲染工作空间首页的项目入口卡片，统一承载项目信息、快捷操作和稳定布局。 -->
<template>
  <article
    data-testid="project-card"
    class="project-card-surface group"
    role="button"
    tabindex="0"
    @click="emit('open', project.id)"
    @keydown.enter="emit('open', project.id)"
    @keydown.space.prevent="emit('open', project.id)"
  >
    <div class="flex min-h-full flex-col p-4 sm:p-5">
      <div class="flex items-start gap-3">
        <div class="flex min-w-0 flex-1 items-start gap-3">
          <div class="project-card-avatar" aria-hidden="true">{{ projectInitial }}</div>
          <div class="min-w-0 flex-1 pt-0.5">
            <div class="flex min-w-0 flex-wrap items-center gap-2">
              <h3
                class="min-w-0 flex-1 truncate text-lg font-black leading-tight text-slate-900 transition-colors group-hover:text-indigo-700"
                :title="project.name"
              >
                {{ project.name }}
              </h3>
              <span class="project-card-code">{{ project.code }}</span>
            </div>
            <p class="mt-1.5 line-clamp-2 min-h-[2.5rem] text-sm font-medium leading-5 text-slate-500">
              {{ project.description || '此项目尚未添加具体功能说明。' }}
            </p>
          </div>
        </div>

        <div class="project-card-actions">
          <button
            type="button"
            class="project-card-action project-card-action-primary"
            :disabled="exportPending || exportDisabled"
            :class="exportPending ? 'project-card-action-busy' : ''"
            :aria-label="exportPending ? '项目导出预检中' : '导出项目'"
            :title="exportPending ? '项目导出预检中' : '导出项目'"
            @click.stop="emit('export-template', project)"
            @keydown.stop
          >
            <Download class="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            class="project-card-action project-card-action-warning"
            :disabled="archivePending"
            :aria-label="archivePending ? '项目归档中' : '归档项目'"
            :title="archivePending ? '项目归档中' : '归档项目'"
            @click.stop="emit('archive', project)"
            @keydown.stop
          >
            <Archive class="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <dl class="mt-4 grid grid-cols-3 gap-2">
        <div class="project-card-meta">
          <dt>画布</dt>
          <dd>{{ canvasLabel }}</dd>
        </div>
        <div class="project-card-meta">
          <dt>主题</dt>
          <dd>{{ themeLabel }}</dd>
        </div>
        <div class="project-card-meta">
          <dt>基准字号</dt>
          <dd>{{ baseFontSizeLabel }}</dd>
        </div>
      </dl>

      <div class="mt-auto flex items-center justify-between gap-3 border-t border-slate-100 pt-4">
        <div class="flex min-w-0 items-center gap-2 text-[11px] font-bold text-slate-400">
          <Calendar class="h-3.5 w-3.5 shrink-0" />
          <span class="truncate">更新于 {{ formatDateTime(project.updated_at) }}</span>
        </div>
        <span class="project-card-enter">
          <span>打开项目</span>
          <ChevronRight class="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
        </span>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Archive, Calendar, ChevronRight, Download } from '@lucide/vue'

import type { ProjectItem } from '@/types/api'
import { formatDateTime } from '@/utils/format'

const props = withDefaults(defineProps<{
  project: ProjectItem
  themeName?: string | null
  themeLoading?: boolean
  exportPending?: boolean
  exportDisabled?: boolean
  archivePending?: boolean
}>(), {
  themeName: null,
  themeLoading: false,
  exportPending: false,
  exportDisabled: false,
  archivePending: false,
})

const emit = defineEmits<{
  open: [projectId: number]
  'export-template': [project: ProjectItem]
  archive: [project: ProjectItem]
}>()

const projectInitial = computed(() => (
  props.project.name.trim().charAt(0) || props.project.code.trim().charAt(0) || 'P'
).toUpperCase())

const canvasLabel = computed(() => `${props.project.page_width}×${props.project.page_height}`)
const themeLabel = computed(() => {
  if (!props.project.theme_key) {
    return '未设置'
  }
  return props.themeName || (props.themeLoading ? '加载中' : '未命名主题')
})
const baseFontSizeLabel = computed(() => props.project.base_font_size || '-')
</script>

<style scoped>
.project-card-surface {
  position: relative;
  isolation: isolate;
  display: flex;
  min-height: 13.75rem;
  cursor: pointer;
  overflow: hidden;
  border: 1px solid rgb(226 232 240);
  border-radius: 1rem;
  background: rgb(255 255 255);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.04);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.project-card-surface::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 0.25rem;
  background: rgb(79 70 229 / 0.78);
  opacity: 0.72;
  transition: opacity 0.2s ease, width 0.2s ease;
}

.project-card-surface:hover {
  transform: translateY(-0.25rem);
  border-color: rgb(165 180 252);
  box-shadow: 0 14px 30px rgb(15 23 42 / 0.08);
}

.project-card-surface:hover::before {
  width: 0.375rem;
  opacity: 1;
}

.project-card-surface:focus-visible {
  outline: none;
  border-color: rgb(99 102 241);
  box-shadow: 0 0 0 3px rgb(199 210 254 / 0.75), 0 14px 30px rgb(15 23 42 / 0.08);
}

.project-card-avatar {
  display: inline-flex;
  width: 2.5rem;
  height: 2.5rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border: 1px solid rgb(224 231 255);
  border-radius: 0.75rem;
  background: rgb(238 242 255);
  color: rgb(67 56 202);
  font-size: 1rem;
  font-weight: 900;
  line-height: 1;
}

.project-card-code {
  display: inline-flex;
  max-width: 9rem;
  min-height: 1.25rem;
  flex: 0 1 auto;
  align-items: center;
  overflow: hidden;
  border-radius: 9999px;
  background: rgb(248 250 252);
  padding: 0.15rem 0.5rem;
  color: rgb(148 163 184);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.625rem;
  font-weight: 800;
  letter-spacing: 0;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}

.project-card-actions {
  display: inline-flex;
  flex: 0 0 auto;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.375rem;
}

.project-card-action {
  display: inline-flex;
  width: 2rem;
  height: 2rem;
  flex: 0 0 2rem;
  align-items: center;
  justify-content: center;
  border: 1px solid rgb(226 232 240);
  border-radius: 0.625rem;
  background: rgb(255 255 255);
  color: rgb(100 116 139);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.05);
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease;
}

.project-card-action:hover {
  transform: translateY(-1px);
}

.project-card-action:disabled {
  cursor: not-allowed;
  opacity: 0.48;
  transform: none;
}

.project-card-action-primary:hover {
  border-color: rgb(199 210 254);
  background: rgb(238 242 255);
  color: rgb(67 56 202);
}

.project-card-action-warning:hover {
  border-color: rgb(252 211 77);
  background: rgb(255 251 235);
  color: rgb(180 83 9);
}

.project-card-action-busy {
  color: rgb(79 70 229);
}

.project-card-action-busy svg {
  animation: project-action-pulse 1s ease-in-out infinite;
}

.project-card-meta {
  min-width: 0;
  border: 1px solid rgb(241 245 249);
  border-radius: 0.625rem;
  background: rgb(248 250 252 / 0.72);
  padding: 0.5rem 0.625rem;
}

.project-card-meta dt {
  color: rgb(148 163 184);
  font-size: 0.625rem;
  font-weight: 800;
  line-height: 1rem;
}

.project-card-meta dd {
  margin-top: 0.125rem;
  overflow: hidden;
  color: rgb(51 65 85);
  font-size: 0.75rem;
  font-weight: 800;
  line-height: 1rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-card-enter {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 0.25rem;
  color: rgb(79 70 229);
  font-size: 0.75rem;
  font-weight: 800;
  white-space: nowrap;
}

@keyframes project-action-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.45;
  }
}
</style>
