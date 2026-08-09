<!-- 文件功能：在 Run 终态后展示本轮工具新增/修改的项目与页面快捷卡片，便于用户一键打开。 -->
<template>
  <section
    class="rounded-ui-md border border-border bg-surface-hover px-2 py-1.5"
    aria-label="本轮涉及的项目与页面"
  >
    <div class="mb-1.5 flex items-center gap-1.5 px-0.5">
      <span class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-ui-sm bg-info-muted text-info-strong">
        <FolderOpen class="h-3 w-3" />
      </span>
      <p class="min-w-0 flex-1 truncate text-xs font-medium text-text-muted">
        本轮涉及 · {{ items.length }} 项
      </p>
    </div>
    <div class="flex flex-col gap-1">
      <button
        v-for="item in items"
        :key="`${item.resourceType}-${item.id}`"
        type="button"
        class="entity-summary-row flex min-h-control-sm w-full min-w-0 items-center gap-2 rounded-ui-md border border-border bg-surface px-2 text-left transition hover:border-border-strong hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-focus disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="!canOpen(item)"
        :title="resolveTitle(item)"
        :aria-label="resolveAriaLabel(item)"
        @click="openEntity(item)"
      >
        <span
          class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-ui-sm"
          :class="item.resourceType === 'project' ? 'bg-info-muted text-info-strong' : 'bg-success-muted text-success-strong'"
        >
          <FolderKanban v-if="item.resourceType === 'project'" class="h-3.5 w-3.5" />
          <FileText v-else class="h-3.5 w-3.5" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block truncate text-xs font-semibold text-text-secondary">{{ resolveDisplayName(item) }}</span>
          <span class="block truncate text-[11px] text-text-muted">{{ resolveSubtitle(item) }}</span>
        </span>
        <UiBadge :tone="effectTone(item.effect)" size="sm">{{ effectLabel(item.effect) }}</UiBadge>
        <ChevronRight class="h-3.5 w-3.5 shrink-0 text-text-muted" />
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useQueryClient } from '@tanstack/vue-query'
import { ChevronRight, FileText, FolderKanban, FolderOpen } from '@lucide/vue'
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getPage, getProject } from '@/api/catalog'
import type { AgentEntityChangeItem } from '@/components/agent/agent-entity-change-summary'
import { UiBadge } from '@/components/ui'
import type { PageItem, ProjectItem } from '@/types/api'
import { buildPageDetailPath, buildProjectPagesPath } from '@/utils/workspace-routes'
import { Message } from '@/utils/message'

const props = defineProps<{
  items: AgentEntityChangeItem[]
}>()

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

interface EntityDisplayDetail {
  name: string
  code: string
  projectId: number | null
  state: 'ready' | 'error'
}

const entityDetails = ref<Record<string, EntityDisplayDetail>>({})
let loadSequence = 0

watch(
  () => props.items.map(item => entityKey(item)).join('|'),
  () => void loadEntityDetails(),
  { immediate: true },
)

/** 使用详情接口加载权威名称和编码，并借助查询缓存避免历史卡片重复请求。 */
async function loadEntityDetails(): Promise<void> {
  const sequence = ++loadSequence
  const entries = await Promise.all(props.items.map(async (item) => {
    try {
      let detail: EntityDisplayDetail
      if (item.resourceType === 'project') {
        const project = await queryClient.fetchQuery<ProjectItem>({
          queryKey: ['project', item.id],
          queryFn: () => getProject(item.id),
          staleTime: 60_000,
        })
        detail = { name: project.name, code: project.code, projectId: project.id, state: 'ready' }
      } else {
        const page = await queryClient.fetchQuery<PageItem>({
          queryKey: ['page', item.id],
          queryFn: () => getPage(item.id),
          staleTime: 60_000,
        })
        detail = { name: page.title, code: page.code, projectId: page.project_id, state: 'ready' }
      }
      return [entityKey(item), detail] as const
    } catch {
      return [entityKey(item), {
        name: item.name?.trim() || '',
        code: '',
        projectId: item.projectId,
        state: 'error',
      }] as const
    }
  }))
  if (sequence === loadSequence) {
    entityDetails.value = Object.fromEntries(entries)
  }
}

/** 生成项目与页面详情缓存的稳定键。 */
function entityKey(item: AgentEntityChangeItem): string {
  return `${item.resourceType}-${item.id}`
}

/** 解析当前路由工作空间，优先实体上的 workspaceId。 */
function resolveWorkspaceId(item: AgentEntityChangeItem): number | null {
  if (item.workspaceId && item.workspaceId > 0) {
    return item.workspaceId
  }
  const fromRoute = Number(route.params.workspaceId)
  return Number.isFinite(fromRoute) && fromRoute > 0 ? fromRoute : null
}

/** 是否具备打开目标页所需的最小导航参数。 */
function canOpen(item: AgentEntityChangeItem): boolean {
  const workspaceId = resolveWorkspaceId(item)
  if (!workspaceId) {
    return false
  }
  if (item.resourceType === 'project') {
    return item.id > 0
  }
  const projectId = entityDetails.value[entityKey(item)]?.projectId ?? item.projectId
  return Boolean(projectId && projectId > 0 && item.id > 0)
}

/** 展示后端返回的权威名称；加载期间可短暂沿用工具结果，但不暴露内部 ID。 */
function resolveDisplayName(item: AgentEntityChangeItem): string {
  const detail = entityDetails.value[entityKey(item)]
  const name = detail?.name?.trim() || item.name?.trim()
  if (name) {
    return name
  }
  if (!detail) {
    return item.resourceType === 'project' ? '正在读取项目信息…' : '正在读取页面信息…'
  }
  return item.resourceType === 'project' ? '项目名称暂不可用' : '页面名称暂不可用'
}

/** 副标题展示业务类型与编码，不把数据库 ID 暴露给用户。 */
function resolveSubtitle(item: AgentEntityChangeItem): string {
  const detail = entityDetails.value[entityKey(item)]
  const typeLabel = item.resourceType === 'project' ? '项目' : '页面'
  if (detail?.code) {
    return `${typeLabel} · ${detail.code}`
  }
  return detail?.state === 'error' ? `${typeLabel} · 编码暂不可用` : `${typeLabel} · 正在读取名称与编码`
}

function resolveTitle(item: AgentEntityChangeItem): string {
  return canOpen(item) ? `打开${resolveDisplayName(item)}` : '缺少导航参数，暂无法打开'
}

function resolveAriaLabel(item: AgentEntityChangeItem): string {
  return `${effectLabel(item.effect)}${item.resourceType === 'project' ? '项目' : '页面'}：${resolveDisplayName(item)}`
}

function effectLabel(effect: AgentEntityChangeItem['effect']): string {
  if (effect === 'create') return '新增'
  if (effect === 'archive') return '归档'
  return '修改'
}

function effectTone(effect: AgentEntityChangeItem['effect']): 'success' | 'neutral' | 'warning' {
  if (effect === 'create') return 'success'
  if (effect === 'archive') return 'warning'
  return 'neutral'
}

/** 跳转项目页面列表或页面详情；参数不足时提示用户。 */
function openEntity(item: AgentEntityChangeItem) {
  const workspaceId = resolveWorkspaceId(item)
  if (!workspaceId) {
    Message.warning('缺少工作空间信息，无法打开。')
    return
  }
  if (item.resourceType === 'project') {
    void router.push(buildProjectPagesPath(workspaceId, item.id))
    return
  }
  const projectId = entityDetails.value[entityKey(item)]?.projectId ?? item.projectId
  if (!projectId) {
    Message.warning('缺少所属项目，无法打开页面。')
    return
  }
  void router.push(buildPageDetailPath(workspaceId, projectId, item.id))
}
</script>
