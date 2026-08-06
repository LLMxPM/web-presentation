<!-- 文件功能：在每轮智能体消息开头展示该 Run 固化的工作焦点与项目范围。 -->
<template>
  <section class="flex min-w-0 items-center gap-2 rounded-ui-md border border-border-muted bg-surface-muted/70 px-2.5 py-1.5 text-[11px]" aria-label="本轮工作上下文">
    <span class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-ui-sm bg-info-muted text-info-strong">
      <Crosshair class="h-3 w-3" />
    </span>
    <span class="shrink-0 font-semibold text-text-secondary">本轮</span>
    <span class="h-3 w-px shrink-0 bg-border" />
    <span class="min-w-0 truncate text-text-muted" :title="focusTitle">
      焦点 <strong class="font-semibold text-text-emphasis">{{ focusLabel }}</strong>
    </span>
    <span class="h-3 w-px shrink-0 bg-border" />
    <span class="min-w-0 flex-1 truncate text-text-muted" :title="scopeTitle">
      范围 <strong class="font-semibold text-text-emphasis">{{ scopeLabel }}</strong>
    </span>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Crosshair } from '@lucide/vue'

import type { AgentRunContextSummary, AgentScopeContext } from '@/types/api'

const props = defineProps<{
  context: AgentRunContextSummary
}>()

const focusLabel = computed(() => formatFocus(props.context.focus, false))
const focusTitle = computed(() => `工作焦点：${formatFocus(props.context.focus, true)}`)
const scopeLabel = computed(() => {
  if (props.context.work_scope_mode === 'workspace') return '全部项目'
  if (!props.context.allowed_projects.length) return '未选择项目'
  if (props.context.allowed_projects.length === 1) return formatProject(props.context.allowed_projects[0], false)
  return `${formatProject(props.context.allowed_projects[0], false)} 等 ${props.context.allowed_projects.length} 个项目`
})
const scopeTitle = computed(() => {
  if (props.context.work_scope_mode === 'workspace') return '项目工作范围：工作空间内全部项目'
  if (!props.context.allowed_projects.length) return '项目工作范围：未选择项目'
  return `项目工作范围：${props.context.allowed_projects.map(project => formatProject(project, true)).join('、')}`
})

/** 将焦点名称与 ID 组合展示，名称缺失时仍保留可诊断的明确 ID。 */
function formatFocus(focus: AgentScopeContext, detailed: boolean): string {
  if (focus.page_id) return formatNamedTarget(focus.page_title, '页面', focus.page_id, detailed)
  if (focus.project_id) return formatNamedTarget(focus.project_name, '项目', focus.project_id, detailed)
  if (focus.component_id) return formatNamedTarget(focus.component_name, '组件', focus.component_id, detailed)
  return formatNamedTarget(focus.workspace_name, '工作空间', focus.workspace_id, detailed)
}

/** 格式化工作集项目名称，悬浮详情始终附带 ID。 */
function formatProject(project: AgentRunContextSummary['allowed_projects'][number], detailed: boolean): string {
  return formatNamedTarget(project.name, '项目', project.id, detailed)
}

/** 紧凑态优先名称，详情态同时展示对象类型与 ID。 */
function formatNamedTarget(name: string | null | undefined, type: string, id: number, detailed: boolean): string {
  const normalizedName = name?.trim()
  if (!normalizedName) return `${type} #${id}`
  return detailed ? `${type}“${normalizedName}” #${id}` : normalizedName
}
</script>
