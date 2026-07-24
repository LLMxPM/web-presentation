<!-- 文件功能：以树表格形式展示并编辑项目路由节点，支持拖动排序、页面替换与顶层/子级页面维护。 -->
<template>
  <section class="flex flex-col rounded-2xl border border-slate-200 bg-white p-3 xl:h-[620px] xl:min-h-0">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <div>
        <h5 class="text-sm font-bold text-slate-900">路由编排</h5>
      </div>
      <div class="flex items-center gap-2">
        <div class="w-72">
          <SearchableSelect :model-value="rootSelection" :options="pageOptions" placeholder="选择顶层页面" empty-text="暂无可选页面"
            @update:model-value="updateRootSelection" />
        </div>
        <UiButton variant="secondary" size="sm"
          @click="handleAddRootPage">
          添加页面
        </UiButton>
        <UiButton variant="secondary" size="sm"
          @click="handleAddGroup">
          新增分组
        </UiButton>
      </div>
    </div>

    <div v-if="routes.length === 0"
      class="mt-4 flex flex-1 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-6 py-12 text-center">
      <div>
        <div class="text-base font-semibold text-slate-700">当前项目还没有路由</div>
        <p class="mt-2 text-sm text-slate-500">可直接添加顶层页面，或先创建分组。</p>
      </div>
    </div>

    <div v-else class="mt-4 rounded-2xl border border-slate-200 xl:min-h-0 xl:flex-1 xl:overflow-hidden">
      <div class="overflow-x-auto xl:h-full xl:overflow-auto">
        <table class="min-w-full w-full table-fixed border-collapse text-sm text-slate-700">
          <colgroup>
            <col style="width: 9%">
            <col style="width: 11%">
            <col style="width: 35%">
            <col style="width: 24%">
            <col style="width: 9%">
            <col style="width: 12%">
          </colgroup>
          <thead class="sticky top-0 z-10 bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <tr>
              <th class="h-11 px-3 text-left whitespace-nowrap">拖动</th>
              <th class="h-11 px-3 text-left whitespace-nowrap">节点</th>
              <th class="h-11 px-2 text-left whitespace-nowrap">标题 / 页面</th>
              <th class="h-11 px-2 text-left whitespace-nowrap">Route</th>
              <th class="h-11 px-3 text-center whitespace-nowrap">显示</th>
              <th class="h-11 px-3 text-left whitespace-nowrap">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-200 bg-white">
            <template v-for="(routeItem, routeIndex) in routes" :key="buildRouteKey(routeItem, routeIndex)">
              <tr class="align-middle transition"
                :class="[resolveDragRowClass('root', routeIndex, null), routeItem.hidden ? 'opacity-45' : 'opacity-100']"
                draggable="true" @dragstart="handleRootDragStart(routeIndex)"
                @dragover.prevent="handleRootDragOver(routeIndex)" @drop.prevent="handleRootDrop(routeIndex)"
                @dragend="clearDragState">
                <td class="px-3 py-2">
                  <UiIconButton label="拖动排序" title="拖动排序" variant="secondary" class="cursor-grab active:cursor-grabbing">
                    <GripVertical class="h-4 w-4" />
                  </UiIconButton>
                </td>
                <td class="px-3 py-2">
                  <div class="flex h-9 items-center gap-1.5 font-semibold text-slate-900">
                    <FolderTree v-if="routeItem.route_type === 'group'" class="h-4 w-4 text-slate-500" />
                    <FileText v-else class="h-4 w-4 text-slate-500" />
                    <span>{{ routeItem.route_type === 'group' ? '分组' : '页面' }}</span>
                  </div>
                </td>
                <td class="px-2 py-2">
                  <div v-if="routeItem.route_type === 'group'" class="min-w-0">
                    <UiInput :model-value="routeItem.group_title ?? ''" placeholder="分组标题"
                      @update:model-value="updateRootField(routeIndex, 'group_title', String($event))" />
                  </div>
                  <div v-else class="min-w-0">
                    <SearchableSelect :model-value="routeItem.page_id ?? null" :options="pageOptions" placeholder="选择页面"
                      empty-text="暂无可选页面" size="compact" @update:model-value="replaceRootPage(routeIndex, $event)" />
                  </div>
                </td>
                <td class="px-2 py-2">
                  <UiInput :model-value="routeItem.route" placeholder="route"
                    @update:model-value="updateRootField(routeIndex, 'route', String($event))" />
                </td>
                <td class="px-3 py-2 text-center">
                  <label class="inline-flex h-9 items-center justify-center">
                    <UiCheckbox :model-value="!routeItem.hidden"
                      @update:model-value="updateRootField(routeIndex, 'hidden', !$event)" />
                  </label>
                </td>
                <td class="px-3 py-2">
                  <div class="flex h-9 items-center justify-start">
                    <UiButton variant="danger" size="sm"
                      @click="removeRoot(routeIndex)">
                      删除
                    </UiButton>
                  </div>
                </td>
              </tr>

              <template v-if="routeItem.route_type === 'group'">
                <tr v-for="(childRoute, childIndex) in routeItem.children ?? []"
                  :key="`${buildRouteKey(routeItem, routeIndex)}-${childIndex}-${childRoute.page_id}`"
                  class="align-middle bg-slate-50/40 transition"
                  :class="[resolveDragRowClass('child', routeIndex, childIndex), childRoute.hidden ? 'opacity-45' : 'opacity-100']"
                  draggable="true" @dragstart="handleChildDragStart(routeIndex, childIndex)"
                  @dragover.prevent="handleChildDragOver(routeIndex, childIndex)"
                  @drop.prevent="handleChildDrop(routeIndex, childIndex)" @dragend="clearDragState">
                  <td class="px-3 py-2">
                    <UiIconButton label="拖动排序" title="拖动排序" variant="secondary" class="ml-4 cursor-grab active:cursor-grabbing">
                      <GripVertical class="h-4 w-4" />
                    </UiIconButton>
                  </td>
                  <td class="px-3 py-2">
                    <div class="flex h-9 items-center gap-1.5 pl-1 font-medium text-slate-700">
                      <CornerDownRight class="h-4 w-4 text-slate-400" />
                      <span>子页</span>
                    </div>
                  </td>
                  <td class="px-2 py-2">
                    <div class="min-w-0">
                      <SearchableSelect :model-value="childRoute.page_id" :options="pageOptions" placeholder="选择页面"
                        empty-text="暂无可选页面" size="compact" @update:model-value="replaceChildPage(routeIndex, childIndex, $event)" />
                    </div>
                  </td>
                  <td class="px-2 py-2">
                    <UiInput :model-value="childRoute.route" placeholder="route"
                      @update:model-value="updateChildField(routeIndex, childIndex, 'route', String($event))" />
                  </td>
                  <td class="px-3 py-2 text-center">
                    <label class="inline-flex h-9 items-center justify-center">
                    <UiCheckbox :model-value="!childRoute.hidden"
                      @update:model-value="updateChildField(routeIndex, childIndex, 'hidden', !$event)" />
                    </label>
                  </td>
                  <td class="px-3 py-2">
                    <div class="flex h-9 items-center justify-start">
                      <UiButton variant="danger" size="sm"
                        @click="removeChild(routeIndex, childIndex)">
                        删除
                      </UiButton>
                    </div>
                  </td>
                </tr>

                <tr class="bg-slate-50/60">
                  <td class="px-3 py-2">
                    <div class="flex h-9 items-center pl-4 text-slate-400">
                      <Plus class="h-4 w-4" />
                    </div>
                  </td>
                  <td class="px-3 py-2">
                    <div class="flex h-9 items-center font-medium text-slate-500">添加子页</div>
                  </td>
                  <td class="px-2 py-2">
                    <div class="min-w-0">
                      <SearchableSelect :model-value="groupSelectionMap[routeIndex] ?? null" :options="pageOptions"
                        placeholder="选择页面" empty-text="暂无可选页面" size="compact"
                        @update:model-value="updateGroupSelection(routeIndex, $event)" />
                    </div>
                  </td>
                  <td class="px-2 py-2">
                    <div class="h-9 rounded-xl border border-transparent"></div>
                  </td>
                  <td class="px-3 py-2">
                    <div class="h-9"></div>
                  </td>
                  <td class="px-3 py-2">
                    <div class="flex h-9 items-center justify-start">
                      <UiButton size="sm"
                        @click="handleAddChild(routeIndex)">
                        添加
                      </UiButton>
                    </div>
                  </td>
                </tr>
              </template>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { CornerDownRight, FileText, FolderTree, GripVertical, Plus } from '@lucide/vue'

import SearchableSelect from '@/components/ui/SearchableSelect.vue'
import { UiButton, UiCheckbox, UiIconButton, UiInput } from '@/components/ui'
import type { SelectOption, SelectPrimitive } from '@/components/ui/select'
import type { PageItem, ProjectRouteChildWrite, ProjectRouteItemWrite } from '@/types/api'
import {
  buildPageRouteSlug,
  buildUniqueRoute,
  cloneProjectRoutes,
  normalizeProjectRouteOrders,
} from '@/utils/project-route'
import { Message } from '@/utils/message'

type DragTarget =
  | { kind: 'root'; routeIndex: number }
  | { kind: 'child'; routeIndex: number; childIndex: number }
  | null

const props = defineProps<{
  modelValue: ProjectRouteItemWrite[]
  pages: PageItem[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ProjectRouteItemWrite[]]
}>()

const rootSelection = ref<SelectPrimitive | null>(null)
const groupSelectionMap = reactive<Record<number, SelectPrimitive | null>>({})
const dragSource = ref<DragTarget>(null)
const dragOverTarget = ref<DragTarget>(null)

const routes = computed(() => props.modelValue ?? [])
const pageMap = computed(() => new Map(props.pages.map(page => [page.id, page])))
const pageOptions = computed<SelectOption[]>(() => [...props.pages]
  .sort((left, right) => left.title.localeCompare(right.title, 'zh-CN'))
  .map(page => ({
    label: page.title,
    value: page.id,
    description: page.code,
    keywords: [page.code, page.title, ...(page.summary ? [page.summary] : [])],
  })))

/**
 * 向父组件同步新的路由草稿，并统一重建 order 字段。
 * @param nextRoutes 最新路由树
 */
function emitRoutes(nextRoutes: ProjectRouteItemWrite[]): void {
  emit('update:modelValue', normalizeProjectRouteOrders(nextRoutes))
}

/**
 * 克隆当前路由树，避免直接修改入参引用。
 */
function cloneRoutes(): ProjectRouteItemWrite[] {
  return cloneProjectRoutes(routes.value)
}

/**
 * 根据顶层选择结果新增页面节点。
 */
function handleAddRootPage(): void {
  const pageId = normalizeSelectionValue(rootSelection.value)
  if (pageId == null) {
    Message.warning('请先选择要添加的顶层页面。')
    return
  }

  const page = pageMap.value.get(pageId)
  if (!page) {
    return
  }

  const nextRoutes = cloneRoutes()
  nextRoutes.push({
    route_type: 'page',
    route: buildUniqueRoute(buildPageRouteSlug(page), nextRoutes.map(item => item.route)),
    order: 0,
    hidden: false,
    page_id: page.id,
    children: [],
  })
  rootSelection.value = null
  emitRoutes(nextRoutes)
}

/**
 * 新增顶层分组节点。
 */
function handleAddGroup(): void {
  const nextRoutes = cloneRoutes()
  nextRoutes.push({
    route_type: 'group',
    route: buildUniqueRoute('group', nextRoutes.map(item => item.route)),
    order: 0,
    hidden: false,
    group_title: '新分组',
    children: [],
  })
  emitRoutes(nextRoutes)
}

/**
 * 在指定分组下新增子页面。
 * @param routeIndex 顶层分组索引
 */
function handleAddChild(routeIndex: number): void {
  const pageId = normalizeSelectionValue(groupSelectionMap[routeIndex] ?? null)
  const page = pageId == null ? undefined : pageMap.value.get(pageId)
  if (!page) {
    Message.warning('请先选择要添加的子页面。')
    return
  }

  const nextRoutes = cloneRoutes()
  const targetRoute = nextRoutes[routeIndex]
  const nextChildren = [...(targetRoute.children ?? [])]
  nextChildren.push({
    route: buildUniqueRoute(
      buildPageRouteSlug(page),
      nextChildren.map(child => child.route),
    ),
    order: 0,
    hidden: false,
    page_id: page.id,
  })
  targetRoute.children = nextChildren
  groupSelectionMap[routeIndex] = null
  emitRoutes(nextRoutes)
}

/**
 * 删除顶层路由节点。
 * @param routeIndex 顶层索引
 */
function removeRoot(routeIndex: number): void {
  const nextRoutes = cloneRoutes()
  nextRoutes.splice(routeIndex, 1)
  emitRoutes(nextRoutes)
}

/**
 * 删除分组下的子页面节点。
 * @param routeIndex 顶层分组索引
 * @param childIndex 子页面索引
 */
function removeChild(routeIndex: number, childIndex: number): void {
  const nextRoutes = cloneRoutes()
  const nextChildren = [...(nextRoutes[routeIndex].children ?? [])]
  nextChildren.splice(childIndex, 1)
  nextRoutes[routeIndex].children = nextChildren
  emitRoutes(nextRoutes)
}

/**
 * 更新顶层节点字段。
 * @param routeIndex 顶层索引
 * @param field 字段名
 * @param value 新值
 */
function updateRootField<K extends keyof ProjectRouteItemWrite>(routeIndex: number, field: K, value: ProjectRouteItemWrite[K]): void {
  const nextRoutes = cloneRoutes()
  nextRoutes[routeIndex] = {
    ...nextRoutes[routeIndex],
    [field]: value,
  }
  emitRoutes(nextRoutes)
}

/**
 * 更新顶层页面节点关联页面。
 * @param routeIndex 顶层索引
 * @param value 选中的页面值
 */
function replaceRootPage(routeIndex: number, value: SelectPrimitive | SelectPrimitive[] | null): void {
  const pageId = normalizeSelectionValue(Array.isArray(value) ? (value[0] ?? null) : value)
  if (pageId == null) {
    return
  }
  updateRootField(routeIndex, 'page_id', pageId)
}

/**
 * 更新子页面节点字段。
 * @param routeIndex 顶层分组索引
 * @param childIndex 子页面索引
 * @param field 字段名
 * @param value 新值
 */
function updateChildField<K extends keyof ProjectRouteChildWrite>(
  routeIndex: number,
  childIndex: number,
  field: K,
  value: ProjectRouteChildWrite[K],
): void {
  const nextRoutes = cloneRoutes()
  const nextChildren = [...(nextRoutes[routeIndex].children ?? [])]
  nextChildren[childIndex] = {
    ...nextChildren[childIndex],
    [field]: value,
  }
  nextRoutes[routeIndex].children = nextChildren
  emitRoutes(nextRoutes)
}

/**
 * 替换分组下的子页面关联页面。
 * @param routeIndex 顶层分组索引
 * @param childIndex 子页面索引
 * @param value 选中的页面值
 */
function replaceChildPage(routeIndex: number, childIndex: number, value: SelectPrimitive | SelectPrimitive[] | null): void {
  const pageId = normalizeSelectionValue(Array.isArray(value) ? (value[0] ?? null) : value)
  if (pageId == null) {
    return
  }
  updateChildField(routeIndex, childIndex, 'page_id', pageId)
}

/**
 * 更新顶层待添加页面选择结果。
 * @param value 选中的值
 */
function updateRootSelection(value: SelectPrimitive | SelectPrimitive[] | null): void {
  rootSelection.value = Array.isArray(value) ? (value[0] ?? null) : value
}

/**
 * 更新分组当前待添加的页面选择结果。
 * @param routeIndex 顶层分组索引
 * @param value 选中的值
 */
function updateGroupSelection(routeIndex: number, value: SelectPrimitive | SelectPrimitive[] | null): void {
  groupSelectionMap[routeIndex] = Array.isArray(value) ? (value[0] ?? null) : value
}

/**
 * 记录顶层节点拖动起点。
 * @param routeIndex 顶层索引
 */
function handleRootDragStart(routeIndex: number): void {
  dragSource.value = { kind: 'root', routeIndex }
}

/**
 * 记录顶层节点当前悬停位置。
 * @param routeIndex 顶层索引
 */
function handleRootDragOver(routeIndex: number): void {
  if (dragSource.value?.kind !== 'root') {
    return
  }
  dragOverTarget.value = { kind: 'root', routeIndex }
}

/**
 * 完成顶层节点拖动排序。
 * @param routeIndex 目标顶层索引
 */
function handleRootDrop(routeIndex: number): void {
  if (dragSource.value?.kind !== 'root' || dragSource.value.routeIndex === routeIndex) {
    clearDragState()
    return
  }

  const nextRoutes = cloneRoutes()
  const [movedItem] = nextRoutes.splice(dragSource.value.routeIndex, 1)
  if (!movedItem) {
    clearDragState()
    return
  }
  nextRoutes.splice(routeIndex, 0, movedItem)
  clearDragState()
  emitRoutes(nextRoutes)
}

/**
 * 记录子页面拖动起点。
 * @param routeIndex 顶层分组索引
 * @param childIndex 子页面索引
 */
function handleChildDragStart(routeIndex: number, childIndex: number): void {
  dragSource.value = { kind: 'child', routeIndex, childIndex }
}

/**
 * 记录子页面当前悬停位置，仅允许同一分组内排序。
 * @param routeIndex 顶层分组索引
 * @param childIndex 子页面索引
 */
function handleChildDragOver(routeIndex: number, childIndex: number): void {
  if (dragSource.value?.kind !== 'child' || dragSource.value.routeIndex !== routeIndex) {
    return
  }
  dragOverTarget.value = { kind: 'child', routeIndex, childIndex }
}

/**
 * 完成同一分组下的子页面拖动排序。
 * @param routeIndex 顶层分组索引
 * @param childIndex 目标子页面索引
 */
function handleChildDrop(routeIndex: number, childIndex: number): void {
  if (
    dragSource.value?.kind !== 'child'
    || dragSource.value.routeIndex !== routeIndex
    || dragSource.value.childIndex === childIndex
  ) {
    clearDragState()
    return
  }

  const nextRoutes = cloneRoutes()
  const nextChildren = [...(nextRoutes[routeIndex].children ?? [])]
  const [movedItem] = nextChildren.splice(dragSource.value.childIndex, 1)
  if (!movedItem) {
    clearDragState()
    return
  }
  nextChildren.splice(childIndex, 0, movedItem)
  nextRoutes[routeIndex].children = nextChildren
  clearDragState()
  emitRoutes(nextRoutes)
}

/**
 * 清理拖动态。
 */
function clearDragState(): void {
  dragSource.value = null
  dragOverTarget.value = null
}

/**
 * 根据拖动态返回当前行高亮样式。
 * @param kind 目标行类型
 * @param routeIndex 顶层索引
 * @param childIndex 子页面索引
 */
function resolveDragRowClass(kind: 'root' | 'child', routeIndex: number, childIndex: number | null): string {
  if (kind === 'root' && dragOverTarget.value?.kind === 'root' && dragOverTarget.value.routeIndex === routeIndex) {
    return 'bg-indigo-50'
  }
  if (
    kind === 'child'
    && dragOverTarget.value?.kind === 'child'
    && dragOverTarget.value.routeIndex === routeIndex
    && dragOverTarget.value.childIndex === childIndex
  ) {
    return 'bg-indigo-50'
  }
  return ''
}

/**
 * 生成每个顶层节点的稳定 key。
 * @param routeItem 路由节点
 * @param routeIndex 顶层索引
 */
function buildRouteKey(routeItem: ProjectRouteItemWrite, routeIndex: number): string {
  return `${routeItem.route_type}-${routeItem.route}-${routeIndex}`
}

/**
 * 把选择值规范成 number，无法识别时返回 null。
 * @param value 原始选择值
 */
function normalizeSelectionValue(value: SelectPrimitive | null): number | null {
  if (value == null) {
    return null
  }
  const pageId = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(pageId) ? pageId : null
}

</script>
