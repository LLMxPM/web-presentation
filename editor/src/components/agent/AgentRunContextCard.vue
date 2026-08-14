<!-- 文件功能：在每轮智能体消息开头展示该 Run 固化的工作焦点与项目范围，焦点可点击跳转到对应页面。 -->
<template>
  <section class="flex min-w-0 items-center gap-2 rounded-ui-md border border-border-muted bg-surface-muted/70 px-2.5 py-1.5 text-[11px]" aria-label="本轮工作上下文">
    <span class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-ui-sm bg-info-muted text-info-strong">
      <Crosshair class="h-3 w-3" />
    </span>
    <span class="shrink-0 font-semibold text-text-secondary">本轮</span>
    <span class="h-3 w-px shrink-0 bg-border" />
    <button
      type="button"
      class="group/focus flex min-w-0 cursor-pointer items-center gap-1 text-text-muted transition hover:text-info-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus disabled:cursor-not-allowed disabled:text-text-muted disabled:hover:text-text-muted"
      :title="focusButtonTitle"
      :aria-label="focusButtonLabel"
      :disabled="!canOpenFocus || opening"
      @click="openFocus"
    >
      <span class="truncate">
        焦点 <strong class="font-semibold text-text-emphasis">{{ focusLabel }}</strong>
      </span>
      <ChevronRight class="h-3 w-3 shrink-0 opacity-0 transition group-hover/focus:opacity-100" />
    </button>
    <span class="h-3 w-px shrink-0 bg-border" />
    <span class="min-w-0 flex-1 truncate text-text-muted" :title="scopeTitle">
      范围 <strong class="font-semibold text-text-emphasis">{{ scopeLabel }}</strong>
    </span>
  </section>
</template>

<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import { ChevronRight, Crosshair } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getPage } from '@/api/catalog'
import { buildScopeRouteLocation } from '@/components/agent/agent-session-scope'
import type { AgentRunContextSummary, AgentScopeContext, PageItem } from '@/types/api'
import { Message } from '@/utils/message'
import { buildPageDetailPath } from '@/utils/workspace-routes'

const props = defineProps<{
  context: AgentRunContextSummary
}>()

const router = useRouter()
const queryClient = useQueryClient()
const opening = ref(false)

const focusLabel = computed(() => formatFocus(props.context.focus, false))
const focusButtonTitle = computed(() => {
  const detail = `工作焦点：${formatFocus(props.context.focus, true)}`
  return canOpenFocus.value ? `点击跳转到${detail}` : `${detail}（缺少跳转参数）`
})
const focusButtonLabel = computed(() => `跳转到本轮焦点：${formatFocus(props.context.focus, false)}`)

/** 焦点是否具备跳转参数；页面焦点缺所属项目时可在点击时按需补齐。 */
const canOpenFocus = computed(() => {
  const focus = props.context.focus
  if (!focus.workspace_id) {
    return false
  }
  if (focus.scope_type === 'page') {
    return Boolean(focus.page_id)
  }
  return Boolean(buildScopeRouteLocation(focus))
})

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

/** 跳转到焦点对应页面；页面焦点缺少所属项目时先按需读取页面详情补齐。 */
async function openFocus(): Promise<void> {
  if (opening.value) {
    return
  }
  opening.value = true
  try {
    const route = await resolveFocusRoute()
    if (!route) {
      Message.warning('缺少跳转参数，无法打开本轮焦点。')
      return
    }
    void router.push(route)
  } finally {
    opening.value = false
  }
}

/** 生成焦点跳转路由；页面焦点缺少所属项目时按需补齐。 */
async function resolveFocusRoute(): Promise<string | null> {
  const focus = props.context.focus
  if (focus.scope_type === 'page' && focus.page_id && !focus.project_id) {
    const projectId = await loadPageProjectId(focus.page_id)
    if (!projectId) {
      return null
    }
    return buildPageDetailPath(focus.workspace_id, projectId, focus.page_id)
  }
  return buildScopeRouteLocation(focus)
}

/** 通过页面详情接口补齐所属项目 ID，优先复用查询缓存。 */
async function loadPageProjectId(pageId: number): Promise<number | null> {
  try {
    const page = await queryClient.fetchQuery<PageItem>({
      queryKey: ['page', pageId],
      queryFn: () => getPage(pageId),
      staleTime: 60_000,
    })
    return page.project_id
  } catch {
    return null
  }
}

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
