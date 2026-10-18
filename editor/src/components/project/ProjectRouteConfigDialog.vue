<!-- 文件功能：页面结构弹窗容器，负责加载数据、汇总放映时长、脏检查、保存与从选中页放映。 -->
<template>
  <UiDialog
    :open="modelValue"
    :title="project ? `页面结构 · ${project.name}` : '页面结构'"
    size="canvas"
    body-preset="editor"
    @update:open="handleVisibleChange"
  >
    <template #header-extra>
      <span
        v-if="isDirty"
        class="rounded-full border border-warning-border bg-warning-muted px-2.5 py-1 text-[11px] font-semibold text-warning-strong"
      >
        未保存
      </span>
    </template>

    <div v-if="project" class="flex h-full min-h-0 flex-col gap-3">
      <div v-if="!routeEditorLoading" class="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-border bg-canvas/60 px-3 py-2">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-text-muted">
          <span>
            <strong class="font-semibold text-text-emphasis">{{ summary.pageCount }}</strong> 页 ·
            {{ summary.groupCount }} 分组 ·
            {{ summary.hiddenCount }} 隐藏
          </span>
          <span>
            预计 <strong class="font-semibold text-text-emphasis">{{ formatDurationMs(summary.estimate.totalMs) }}</strong>
          </span>
          <span v-if="summaryHint" class="text-text-disabled">{{ summaryHint }}</span>
        </div>
        <ProjectSlideshowDefaultsSummary
          :settings="projectDefaults"
          editable
          compact
          @edit="handleOpenProjectSettings"
        />
      </div>

      <div v-if="routeEditorLoading" class="flex flex-1 items-center justify-center rounded-2xl border border-dashed border-border bg-canvas/50 px-6 py-12 text-center text-sm text-text-disabled">
        正在加载页面和页面结构...
      </div>

      <ProjectRouteWorkbench
        v-else
        v-model="draftRoutes"
        :pages="routePages"
        :page-meta="pageMeta"
        :defaults="projectDefaults"
        :capabilities="capabilities"
        :selected-key="selectedKey"
        :filter="filter"
        :selected-keys="selectedKeys"
        class="min-h-0 flex-1"
        @update:selected-key="selectedKey = $event"
        @update:filter="filter = $event"
        @update:selected-keys="selectedKeys = $event"
        @present="handleSave"
      />
    </div>

    <div v-else class="py-10 text-center text-sm text-text-disabled">
      当前没有可编辑的项目。
    </div>

    <template #footer>
      <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        <span class="text-[11px] leading-4 text-text-muted">整树保存 · 影响目录、链接与放映顺序</span>
        <div class="flex justify-end gap-2">
          <UiButton variant="ghost" @click="handleVisibleChange(false)">取消</UiButton>
          <UiButton variant="primary" :loading="loading" :disabled="!project" @click="handleSave()">
            保存页面结构
          </UiButton>
        </div>
      </div>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { getProjectRoutes, listPages } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import { useSlideshowCapabilities } from '@/composables/useSlideshowCapabilities'
import ProjectRouteWorkbench from '@/components/project/ProjectRouteWorkbench.vue'
import ProjectSlideshowDefaultsSummary from '@/components/project/ProjectSlideshowDefaultsSummary.vue'
import { DEFAULT_SLIDESHOW_SETTINGS } from '@/components/project/project-slideshow-values'
import { UiButton, UiDialog } from '@/components/ui'
import type { PageItem, ProjectItem, ProjectRouteItemWrite, ProjectRouteTreeItem } from '@/types/api'
import { mapRouteTreeToWriteItems, normalizeProjectRouteOrders, validateProjectRoutes } from '@/utils/project-route'
import type {
  ProjectRouteSummary,
  RoutePageMeta,
  RouteSlideshowFilter,
} from '@/utils/project-route-slideshow'
import {
  formatDurationMs,
  summarizeProjectRoutes,
} from '@/utils/project-route-slideshow'
import { Message, createConfirm } from '@/utils/message'

const props = withDefaults(defineProps<{
  modelValue: boolean
  project: ProjectItem | null
  loading?: boolean
}>(), {
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [payload: { routes: ProjectRouteItemWrite[]; entryRoute?: string | null }]
  'open-project-settings': []
}>()

const routePages = ref<PageItem[]>([])
const pageMeta = ref<Map<number, RoutePageMeta>>(new Map())
const draftRoutes = ref<ProjectRouteItemWrite[]>([])
const routeEditorLoading = ref(false)
const routeLoadToken = ref(0)
const selectedKey = ref<string | null>(null)
const filter = ref<RouteSlideshowFilter>('all')
const selectedKeys = ref<Set<string>>(new Set())
const initialSnapshot = ref('')
const closeConfirming = ref(false)
const { capabilities, load: loadSlideshowCapabilities } = useSlideshowCapabilities()

const projectDefaults = computed(() => props.project?.slideshow ?? DEFAULT_SLIDESHOW_SETTINGS)
const summary = computed<ProjectRouteSummary>(() => summarizeProjectRoutes(draftRoutes.value, projectDefaults.value))
const isDirty = computed(() => serializeRoutes(draftRoutes.value) !== initialSnapshot.value)
const summaryHint = computed(() => {
  const parts: string[] = []
  if (summary.value.estimate.manualCount > 0) {
    parts.push(`${summary.value.estimate.manualCount} 个手动页未计停留时间`)
  }
  if (summary.value.estimate.mediaCount > 0) {
    parts.push(`${summary.value.estimate.mediaCount} 个媒体页按兜底停留估算`)
  }
  if (summary.value.hiddenCount > 0) {
    parts.push('隐藏页不参与放映')
  }
  return parts.join('；')
})

/** 拦截弹窗关闭，存在未保存修改时先确认。 */
function handleVisibleChange(value: boolean): void {
  if (value) {
    emit('update:modelValue', true)
    return
  }
  void requestClose()
}

/** 关闭前检查草稿；保存中或重复确认时不关闭。 */
async function requestClose(): Promise<void> {
  if (props.loading || closeConfirming.value) {
    return
  }
  if (!isDirty.value) {
    emit('update:modelValue', false)
    return
  }
  closeConfirming.value = true
  const confirmed = await createConfirm(
    '页面结构有未保存的修改，关闭后将丢失。确定放弃这些修改吗？',
    '放弃未保存的修改？',
    { dangerous: true, confirmLabel: '放弃并关闭', cancelLabel: '继续编辑' },
  )
  closeConfirming.value = false
  if (confirmed) {
    emit('update:modelValue', false)
  }
}

/** 提交整棵路由树；entryRoute 存在时由父组件保存后直接打开放映。 */
function handleSave(entryRoute?: string | null): void {
  if (props.loading) {
    return
  }
  const validationErrors = validateProjectRoutes(draftRoutes.value)
  if (validationErrors.length > 0) {
    Message.error(validationErrors[0])
    return
  }
  emit('save', {
    routes: draftRoutes.value,
    entryRoute: entryRoute ?? null,
  })
}

/** 跳转到项目设置前，先处理未保存草稿，避免静默丢失。 */
async function handleOpenProjectSettings(): Promise<void> {
  if (isDirty.value) {
    const confirmed = await createConfirm(
      '页面结构有未保存的修改，打开项目设置将丢失这些修改。确定继续吗？',
      '打开项目设置？',
      { dangerous: true, confirmLabel: '继续打开', cancelLabel: '继续编辑' },
    )
    if (!confirmed) {
      return
    }
  }
  emit('update:modelValue', false)
  emit('open-project-settings')
}

/** 加载页面列表、路由树和页面标题元数据。 */
async function loadRouteEditorData(project: ProjectItem): Promise<void> {
  const currentToken = routeLoadToken.value + 1
  routeLoadToken.value = currentToken
  routeEditorLoading.value = true

  try {
    const [pagesResponse, routesResponse] = await Promise.all([
      listPages({ page: 1, page_size: 100, project_id: project.id, status: 'active' }),
      getProjectRoutes(project.id),
    ])

    if (routeLoadToken.value !== currentToken) {
      return
    }

    routePages.value = pagesResponse.items
    pageMeta.value = buildPageMeta(pagesResponse.items, routesResponse.routes)
    draftRoutes.value = mapRouteTreeToWriteItems(routesResponse.routes)
    initialSnapshot.value = serializeRoutes(draftRoutes.value)
    selectedKey.value = null
    filter.value = 'all'
    selectedKeys.value = new Set()
  } catch (error) {
    if (routeLoadToken.value !== currentToken) {
      return
    }

    routePages.value = []
    pageMeta.value = new Map()
    draftRoutes.value = []
    initialSnapshot.value = serializeRoutes([])
    selectedKey.value = null
    selectedKeys.value = new Set()
    Message.error(getErrorMessage(error, '加载页面结构失败。'))
  } finally {
    if (routeLoadToken.value === currentToken) {
      routeEditorLoading.value = false
    }
  }
}

/** 合并活动页面与路由响应中的页面标题，覆盖已归档但仍被引用的页面。 */
function buildPageMeta(pages: PageItem[], routes: ProjectRouteTreeItem[]): Map<number, RoutePageMeta> {
  const result = new Map<number, RoutePageMeta>()
  pages.forEach(page => {
    result.set(page.id, { id: page.id, title: page.title, code: page.code })
  })
  const appendRoutePage = (pageId: number | null, title: string | null, code: string | null): void => {
    if (pageId == null || result.has(pageId)) {
      return
    }
    result.set(pageId, {
      id: pageId,
      title: title || `页面 #${pageId}`,
      code: code || '',
    })
  }
  routes.forEach(routeItem => {
    appendRoutePage(routeItem.page_id, routeItem.page_title, routeItem.page_code)
    routeItem.children.forEach(child => {
      appendRoutePage(child.page_id, child.page_title, child.page_code)
    })
  })
  return result
}

/** 统一序列化草稿，忽略 order 的临时差异。 */
function serializeRoutes(routes: ProjectRouteItemWrite[]): string {
  return JSON.stringify(normalizeProjectRouteOrders(routes))
}

watch(
  () => [props.modelValue, props.project] as const,
  ([visible, currentProject]) => {
    if (visible && currentProject) {
      void loadRouteEditorData(currentProject)
      void loadSlideshowCapabilities()
    }
  },
  { immediate: true },
)
</script>
