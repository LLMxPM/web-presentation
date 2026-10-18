<!-- 文件功能：页面结构工作区，组合页面池、放映序列和右侧检查器，并协调批量覆盖。 -->
<template>
  <div class="route-workbench min-h-0">
    <aside class="page-pool flex min-h-0 flex-col rounded-2xl border border-border bg-canvas/60 p-3">
      <div class="flex items-center justify-between gap-2">
        <h5 class="text-sm font-bold text-text-strong">页面池</h5>
        <span class="rounded-full border border-border bg-surface px-2 py-0.5 text-[11px] font-semibold text-text-muted">{{ pages.length }}</span>
      </div>

      <div class="mt-3">
        <label class="text-[11px] text-text-muted">添加到</label>
        <UiSelect
          :model-value="targetKey"
          :options="targetOptions"
          class="mt-1"
          aria-label="页面添加位置"
          @update:model-value="handleTargetChange"
        />
      </div>

      <div class="mt-2">
        <SimpleSearchBar v-model="pageKeyword" placeholder="搜索页面标题或编码" />
      </div>

      <div class="mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto pr-0.5">
        <article
          v-for="page in filteredPages"
          :key="page.id"
          class="rounded-xl border border-border bg-surface px-2.5 py-2"
        >
          <div class="flex items-center justify-between gap-1.5">
            <span class="truncate text-xs font-semibold text-text-strong" :title="page.title">{{ page.title }}</span>
            <UiButton size="xs" variant="secondary" class="shrink-0" @click="addPage(page)">添加</UiButton>
          </div>
          <div class="mt-0.5 flex items-center justify-between gap-1.5">
            <span class="truncate font-mono text-[11px] text-text-disabled" :title="page.code">{{ page.code }}</span>
            <span
              class="shrink-0 text-[11px]"
              :class="getPageUsageCount(page.id) > 0 ? 'text-success-strong' : 'text-text-disabled'"
            >
              {{ getPageUsageCount(page.id) > 0 ? `已用 ${getPageUsageCount(page.id)}` : '未用' }}
            </span>
          </div>
          <div
            class="mt-0.5 truncate text-[11px]"
            :class="getPageUsageCount(page.id) > 0 ? 'text-text-muted' : 'text-text-disabled'"
            :title="getPageUsageText(page.id)"
          >
            {{ getPageUsageCount(page.id) > 0 ? getPageUsageText(page.id) : '未加入放映序列' }}
          </div>
        </article>

        <div v-if="filteredPages.length === 0" class="rounded-xl border border-dashed border-border bg-surface px-3 py-8 text-center text-[11px] text-text-disabled">
          没有匹配的页面。
        </div>
      </div>

      <p class="mt-2 text-[11px] leading-4 text-text-disabled">选择上方目标后，页面会追加到顶层或对应分组末尾。</p>
    </aside>

    <div class="sequence-panel flex min-h-0 min-w-0 flex-col gap-2">
      <div
        v-if="selectedKeys.size > 0"
        class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-surface-selected px-3 py-2"
      >
        <span class="text-xs text-text-emphasis">
          已选 {{ selectedKeys.size }} 项 · {{ selectedPageCount }} 页
        </span>
        <div class="flex items-center gap-2">
          <UiButton
            size="sm"
            variant="secondary"
            :disabled="selectedPageCount === 0"
            @click="openBatchForSelection"
          >
            批量放映设置
          </UiButton>
          <UiButton size="sm" variant="ghost" @click="clearSelection">清除选择</UiButton>
        </div>
      </div>

      <ProjectRouteSequenceTable
        :routes="modelValue"
        :page-meta="pageMeta"
        :defaults="defaults"
        :filter="filter"
        :selected-keys="selectedKeys"
        :selected-key="selectedKey"
        class="min-h-0 flex-1"
        @update:model-value="emit('update:modelValue', $event)"
        @update:filter="emit('update:filter', $event)"
        @update:selected-keys="emit('update:selectedKeys', $event)"
        @select="emit('update:selectedKey', $event)"
        @add-group="addGroup"
      />
    </div>

    <ProjectRouteInspector
      class="inspector"
      :selection="selection"
      :routes="modelValue"
      :pages="pages"
      :page-meta="pageMeta"
      :defaults="defaults"
      :capabilities="capabilities"
      @update-node="handleUpdateNode"
      @delete-node="handleDeleteNode"
      @present="emit('present', $event)"
      @open-batch="openBatch"
      @add-child="handleAddChild"
      @select-node="emit('update:selectedKey', $event)"
    />

    <ProjectRouteBatchSlideshowDialog
      v-model:open="batchDialogOpen"
      :item-count="batchItemCount"
      :page-count="batchPageCount"
      :defaults="defaults"
      :capabilities="capabilities"
      @apply="handleApplyBatch"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import { UiButton, UiSelect } from '@/components/ui'
import type { SelectPrimitive } from '@/components/ui/select'
import type {
  PageItem,
  ProjectRouteItemWrite,
  SlideshowCapabilities,
  SlideshowSettings,
} from '@/types/api'
import type {
  RouteNodePatch,
  RoutePageMeta,
  RouteSlideshowFilter,
  SlideshowBatchPatch,
} from '@/utils/project-route-slideshow'
import {
  appendGroup,
  appendPageToTarget,
  applySlideshowToKeys,
  buildRouteNodeKey,
  collectLeafKeysForTargets,
  countSelectedPages,
  findRouteNodeByKey,
  getRouteFullPath,
  removeRouteNode,
  updateRouteNode,
} from '@/utils/project-route-slideshow'
import { Message } from '@/utils/message'
import ProjectRouteBatchSlideshowDialog from './ProjectRouteBatchSlideshowDialog.vue'
import ProjectRouteInspector from './ProjectRouteInspector.vue'
import ProjectRouteSequenceTable from './ProjectRouteSequenceTable.vue'

const props = withDefaults(defineProps<{
  modelValue: ProjectRouteItemWrite[]
  pages: PageItem[]
  pageMeta: Map<number, RoutePageMeta>
  defaults: SlideshowSettings
  capabilities?: SlideshowCapabilities | null
  selectedKey: string | null
  filter: RouteSlideshowFilter
  selectedKeys: Set<string>
}>(), {
  capabilities: null,
})

const emit = defineEmits<{
  'update:modelValue': [routes: ProjectRouteItemWrite[]]
  'update:selectedKey': [key: string | null]
  'update:filter': [filter: RouteSlideshowFilter]
  'update:selectedKeys': [keys: Set<string>]
  present: [entryRoute: string]
}>()

const pageKeyword = ref('')
const targetKey = ref('root')
const batchDialogOpen = ref(false)
const batchKeys = ref<string[]>([])
const batchItemCount = ref(0)

const activePages = computed(() => props.pages.filter(page => page.status === 'active'))
const pageBindingMap = computed(() => {
  const result = new Map<number, string[]>()
  for (const item of props.modelValue) {
    if (item.route_type === 'page' && item.page_id != null) {
      appendBinding(result, item.page_id, getRouteFullPath(null, item.route))
      continue
    }
    for (const child of item.children ?? []) {
      appendBinding(result, child.page_id, getRouteFullPath(item.route, child.route))
    }
  }
  return result
})
const filteredPages = computed(() => {
  const keyword = pageKeyword.value.trim().toLowerCase()
  const ordered = [...activePages.value].sort(comparePagePoolOrder)
  if (!keyword) {
    return ordered
  }
  return ordered.filter(page => {
    return [page.title, page.code, page.summary ?? '']
      .some(value => value.toLowerCase().includes(keyword))
  })
})

/** 未加入放映序列的页面排在前面，同组内按标题排序。 */
function comparePagePoolOrder(left: PageItem, right: PageItem): number {
  const leftUsed = getPageUsageCount(left.id) > 0 ? 1 : 0
  const rightUsed = getPageUsageCount(right.id) > 0 ? 1 : 0
  if (leftUsed !== rightUsed) {
    return leftUsed - rightUsed
  }
  return left.title.localeCompare(right.title, 'zh-CN')
}

const targetOptions = computed(() => {
  const groups = props.modelValue.filter(item => item.route_type === 'group')
  return [
    { label: '顶层', value: 'root' },
    ...groups.map(group => ({
      label: group.group_title || group.route || '未命名分组',
      value: `group:${group.route}`,
    })),
  ]
})
const selection = computed(() => findRouteNodeByKey(props.modelValue, props.selectedKey))
const selectedPageCount = computed(() => countSelectedPages(props.modelValue, props.selectedKeys))
const batchPageCount = computed(() => batchKeys.value.length)

watch(
  targetOptions,
  options => {
    if (!options.some(option => option.value === targetKey.value)) {
      targetKey.value = 'root'
    }
  },
)

/** 切换页面池目标；分组被删除后自动回到顶层。 */
function handleTargetChange(value: SelectPrimitive | SelectPrimitive[] | null): void {
  const normalized = Array.isArray(value) ? value[0] : value
  targetKey.value = normalized == null ? 'root' : String(normalized)
}

/** 按当前目标追加页面，并选中新节点。 */
function addPage(page: PageItem): void {
  const result = appendPageToTarget(props.modelValue, page, targetKey.value)
  emit('update:modelValue', result.routes)
  if (result.key) {
    emit('update:selectedKey', result.key)
  }
}

/** 追加分组并选中，便于立即改名和组织子页。 */
function addGroup(): void {
  const result = appendGroup(props.modelValue)
  emit('update:modelValue', result.routes)
  emit('update:selectedKey', result.key)
}

/** 写回节点字段；路径变化时同步选中键并清空批量选择，避免旧键指向错误节点。 */
function handleUpdateNode(payload: { key: string; patch: RouteNodePatch }): void {
  const next = updateRouteNode(props.modelValue, payload.key, payload.patch)
  emit('update:modelValue', next)
  if (payload.patch.route === undefined) {
    return
  }
  emit('update:selectedKeys', new Set())
  if (props.selectedKey !== payload.key) {
    return
  }
  const previous = findRouteNodeByKey(props.modelValue, payload.key)
  if (!previous) {
    return
  }
  const nextKey = buildRouteNodeKey(
    { scope: previous.scope, routeIndex: previous.routeIndex, childIndex: previous.childIndex },
    next,
  )
  if (nextKey) {
    emit('update:selectedKey', nextKey)
  }
}

/** 删除节点并清理选中状态。 */
function handleDeleteNode(key: string): void {
  const next = removeRouteNode(props.modelValue, key)
  emit('update:modelValue', next)
  if (props.selectedKey === key) {
    emit('update:selectedKey', null)
  }
  const nextSelection = new Set(props.selectedKeys)
  nextSelection.delete(key)
  emit('update:selectedKeys', nextSelection)
}

/** 分组检查器添加子页。 */
function handleAddChild(payload: { groupKey: string; pageId: number }): void {
  const page = props.pages.find(item => item.id === payload.pageId)
  if (!page) {
    Message.warning('所选页面不在当前项目的可用页面列表中。')
    return
  }
  const result = appendPageToTarget(props.modelValue, page, payload.groupKey)
  emit('update:modelValue', result.routes)
  if (result.key) {
    emit('update:selectedKey', result.key)
  }
}

/** 打开多选批量的放映设置。 */
function openBatchForSelection(): void {
  openBatch([...props.selectedKeys])
}

/** 展开分组后打开批量设置，避免把分组本身写成覆盖。 */
function openBatch(keys: string[]): void {
  const leafKeys = collectLeafKeysForTargets(props.modelValue, keys)
  if (leafKeys.length === 0) {
    Message.warning('所选节点下没有可设置放映的页面。')
    return
  }
  batchKeys.value = leafKeys
  batchItemCount.value = keys.length
  batchDialogOpen.value = true
}

/** 应用批量 patch，保留未选择的分组和字段。 */
function handleApplyBatch(patch: SlideshowBatchPatch): void {
  if (batchKeys.value.length === 0) {
    return
  }
  const next = applySlideshowToKeys(props.modelValue, batchKeys.value, patch)
  emit('update:modelValue', next)
  Message.success(`已更新 ${batchKeys.value.length} 个页面的放映设置，保存后生效。`)
  batchKeys.value = []
  batchItemCount.value = 0
}

function clearSelection(): void {
  emit('update:selectedKeys', new Set())
}

function getPageUsageCount(pageId: number): number {
  return pageBindingMap.value.get(pageId)?.length ?? 0
}

function getPageUsageText(pageId: number): string {
  return (pageBindingMap.value.get(pageId) ?? []).join('，')
}

function appendBinding(result: Map<number, string[]>, pageId: number, path: string): void {
  const paths = result.get(pageId) ?? []
  paths.push(path)
  result.set(pageId, paths)
}
</script>

<style scoped>
.route-workbench {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) 320px;
  gap: 0.75rem;
  height: 100%;
}

@media (max-width: 1279px) {
  .route-workbench {
    grid-template-columns: 180px minmax(0, 1fr) 280px;
  }
}

@media (max-width: 1023px) {
  .route-workbench {
    grid-template-columns: 160px minmax(0, 1fr) 260px;
    gap: 0.5rem;
  }
}

@media (max-width: 900px) {
  .route-workbench {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: minmax(0, 1fr) auto;
  }

  .page-pool {
    display: none;
  }

  .inspector {
    max-height: 300px;
  }
}
</style>
