<!-- 文件功能：以精简序列展示页面结构的顺序、隐藏与放映摘要，支持多选、筛选、拖动和键盘排序。 -->
<template>
  <section class="flex min-h-0 min-w-0 flex-col rounded-2xl border border-border bg-surface">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
      <div class="flex min-w-0 items-center gap-2">
        <h5 class="truncate text-sm font-bold text-text-strong">页面与放映顺序</h5>
        <span class="shrink-0 text-[11px] text-text-muted">{{ routes.length }} 个顶层节点</span>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <UiSegmentedControl
          :model-value="filter"
          :options="filterOptions"
          class="w-[210px]"
          aria-label="筛选页面"
          @update:model-value="updateFilter"
        />
        <UiButton variant="secondary" size="sm" @click="emit('add-group')">新增分组</UiButton>
      </div>
    </div>

    <div v-if="filter !== 'all'" class="border-b border-border bg-canvas/60 px-3 py-1.5 text-[11px] text-text-muted">
      筛选状态下不可拖动排序。
    </div>

    <div v-if="routes.length === 0" class="flex flex-1 items-center justify-center px-6 py-12 text-center">
      <div>
        <div class="text-base font-semibold text-text-emphasis">当前项目还没有页面结构</div>
        <p class="mt-2 text-sm text-text-muted">从左侧页面池添加页面，或先创建一个分组。</p>
        <UiButton variant="secondary" size="sm" class="mt-4" @click="emit('add-group')">新增分组</UiButton>
      </div>
    </div>

    <div v-else class="min-h-0 flex-1 overflow-y-auto" role="listbox" aria-label="页面与放映顺序">
      <div class="route-table-grid sticky top-0 z-10 border-b border-border bg-canvas px-2.5 py-2 text-[11px] font-semibold text-text-muted">
        <span class="flex items-center justify-center">
          <UiCheckbox
            :model-value="headerCheckboxValue"
            aria-label="全选可见节点"
            @update:model-value="toggleAll"
          />
        </span>
        <span></span>
        <span>页面 / 路径</span>
        <span>放映</span>
      </div>

      <div
        v-for="row in rows"
        :key="row.key"
        class="route-row route-table-grid px-2.5 py-1.5 text-[11px]"
        :class="[
          selectedKey === row.key ? 'route-row--selected' : '',
          dragOverKey === row.key ? 'route-row--drag-over' : '',
          row.kind === 'child' ? 'route-row--child' : '',
        ]"
        role="option"
        :aria-selected="selectedKey === row.key"
        tabindex="0"
        :draggable="filter === 'all'"
        @click="emit('select', row.key)"
        @keydown.enter.prevent="emit('select', row.key)"
        @keydown.alt.up.prevent="moveSelected(-1)"
        @keydown.alt.down.prevent="moveSelected(1)"
        @dragstart="handleDragStart(row, $event)"
        @dragover="handleDragOver(row, $event)"
        @drop="handleDrop(row, $event)"
        @dragend="clearDragState"
      >
        <span class="flex items-center justify-center" @click.stop>
          <UiCheckbox
            :model-value="selectedKeys.has(row.key)"
            :aria-label="`选择 ${row.title}`"
            @update:model-value="toggleKey(row.key)"
          />
        </span>

        <span class="flex cursor-grab items-center justify-center text-text-disabled active:cursor-grabbing" title="拖动排序">
          <GripVertical class="h-3.5 w-3.5" />
        </span>

        <div class="min-w-0" :class="{ 'route-row__page--child': row.kind === 'child' }">
          <div class="flex min-w-0 items-center gap-1.5">
            <UiIconButton
              v-if="row.kind === 'group'"
              :label="isGroupCollapsed(row.key) ? '展开分组' : '收起分组'"
              variant="ghost"
              size="xs"
              class="shrink-0"
              @click.stop="toggleGroup(row.key)"
            >
              <ChevronRight v-if="isGroupCollapsed(row.key)" class="h-3.5 w-3.5" />
              <ChevronDown v-else class="h-3.5 w-3.5" />
            </UiIconButton>
            <span class="shrink-0 font-mono text-text-disabled">{{ row.displayIndex }}</span>
            <span class="truncate text-xs font-medium text-text-strong" :title="row.title">{{ row.title }}</span>
            <span v-if="row.kind === 'group'" class="route-badge">分组</span>
            <span v-if="row.hidden" class="route-badge route-badge--hidden">隐藏</span>
          </div>
          <div class="mt-0.5 truncate font-mono text-[11px] text-text-disabled" :title="row.path">{{ row.path }}</div>
        </div>

        <span
          class="route-chip"
          :class="row.kind === 'group' ? 'route-chip--group' : row.overridden ? 'route-chip--override' : ''"
          :title="row.chipTitle"
        >
          {{ row.chip }}
        </span>
      </div>

      <div v-if="rows.length === 0" class="px-4 py-10 text-center text-sm text-text-disabled">
        没有符合当前筛选条件的页面。
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronDown, ChevronRight, GripVertical } from '@lucide/vue'

import { UiButton, UiCheckbox, UiIconButton, UiSegmentedControl } from '@/components/ui'
import type {
  ProjectRouteChildWrite,
  ProjectRouteItemWrite,
  SlideshowSettings,
} from '@/types/api'
import type {
  RoutePageMeta,
  RouteSlideshowFilter,
} from '@/utils/project-route-slideshow'
import {
  formatRouteSlideshowSummary,
  getRouteFullPath,
  hasSlideshowOverride,
} from '@/utils/project-route-slideshow'
import {
  cloneProjectRoutes,
  normalizeProjectRouteOrders,
} from '@/utils/project-route'

interface RouteRow {
  key: string
  kind: 'group' | 'page' | 'child'
  routeIndex: number
  childIndex?: number
  displayIndex: string
  title: string
  path: string
  hidden: boolean
  overridden: boolean
  chip: string
  chipTitle: string
}

type DragSource =
  | { kind: 'root'; routeIndex: number }
  | { kind: 'child'; routeIndex: number; childIndex: number }
  | null

const props = defineProps<{
  routes: ProjectRouteItemWrite[]
  pageMeta: Map<number, RoutePageMeta>
  defaults: SlideshowSettings
  filter: RouteSlideshowFilter
  selectedKeys: Set<string>
  selectedKey: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [routes: ProjectRouteItemWrite[]]
  'update:filter': [filter: RouteSlideshowFilter]
  'update:selectedKeys': [keys: Set<string>]
  select: [key: string]
  'add-group': []
}>()

const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '已覆盖', value: 'overridden' },
  { label: '隐藏', value: 'hidden' },
]
const collapsedGroups = ref<Set<string>>(new Set())
const dragSource = ref<DragSource>(null)
const dragOverKey = ref<string | null>(null)

const rows = computed<RouteRow[]>(() => {
  const result: RouteRow[] = []
  props.routes.forEach((item, routeIndex) => {
    const rootKey = item.route_type === 'group' ? `group:${item.route}` : `page:${item.route}`
    if (item.route_type === 'group') {
      const children = item.children ?? []
      const showGroup = props.filter === 'all'
        || (props.filter === 'hidden' && (item.hidden || children.some(child => child.hidden)))
        || (props.filter === 'overridden' && children.some(child => hasSlideshowOverride(child)))
      if (!showGroup) {
        return
      }
      result.push({
        key: rootKey,
        kind: 'group',
        routeIndex,
        displayIndex: String(routeIndex + 1).padStart(2, '0'),
        title: item.group_title || '未命名分组',
        path: getRouteFullPath(null, item.route),
        hidden: item.hidden,
        overridden: false,
        chip: `本章 ${children.length} 页`,
        chipTitle: `分组包含 ${children.length} 个子页`,
      })
      if (isGroupCollapsed(rootKey)) {
        return
      }
      children.forEach((child, childIndex) => {
        if (!matchesFilter(child, item.hidden)) {
          return
        }
        result.push(buildChildRow(item, child, routeIndex, childIndex))
      })
      return
    }
    if (!matchesFilter(item, false)) {
      return
    }
    result.push({
      key: rootKey,
      kind: 'page',
      routeIndex,
      displayIndex: String(routeIndex + 1).padStart(2, '0'),
      title: resolvePageTitle(item.page_id),
      path: getRouteFullPath(null, item.route),
      hidden: item.hidden,
      overridden: hasSlideshowOverride(item),
      chip: formatRouteSlideshowSummary(item, props.defaults).label,
      chipTitle: resolveChipTitle(item),
    })
  })
  return result
})

const headerCheckboxValue = computed<boolean | 'indeterminate'>(() => {
  if (rows.value.length === 0) {
    return false
  }
  const selectedCount = rows.value.filter(row => props.selectedKeys.has(row.key)).length
  if (selectedCount === 0) {
    return false
  }
  return selectedCount === rows.value.length ? true : 'indeterminate'
})

/** 判断子页是否符合当前筛选；隐藏分组下保留全部子页作为上下文。 */
function matchesFilter(item: ProjectRouteChildWrite | ProjectRouteItemWrite, parentHidden: boolean): boolean {
  if (props.filter === 'all') {
    return true
  }
  if (props.filter === 'hidden') {
    return parentHidden || item.hidden
  }
  return hasSlideshowOverride(item)
}

/** 生成子页行。 */
function buildChildRow(
  parent: ProjectRouteItemWrite,
  child: ProjectRouteChildWrite,
  routeIndex: number,
  childIndex: number,
): RouteRow {
  return {
    key: `child:${parent.route}/${child.route}`,
    kind: 'child',
    routeIndex,
    childIndex,
    displayIndex: `${routeIndex + 1}.${childIndex + 1}`,
    title: resolvePageTitle(child.page_id),
    path: getRouteFullPath(parent.route, child.route),
    hidden: child.hidden,
    overridden: hasSlideshowOverride(child),
    chip: formatRouteSlideshowSummary(child, props.defaults).label,
    chipTitle: resolveChipTitle(child),
  }
}

/** 从页面元数据读取标题，避免依赖页面池是否加载完成。 */
function resolvePageTitle(pageId: number | null | undefined): string {
  if (pageId == null) {
    return '未绑定页面'
  }
  return props.pageMeta.get(pageId)?.title ?? '未绑定页面'
}

/** 为行内摘要补充完整说明。 */
function resolveChipTitle(item: ProjectRouteChildWrite | ProjectRouteItemWrite): string {
  const summary = formatRouteSlideshowSummary(item, props.defaults)
  return summary.overridden ? '本页覆盖了项目默认放映设置' : '本页继承项目默认放映设置'
}

function updateFilter(value: string): void {
  emit('update:filter', value as RouteSlideshowFilter)
}

function isGroupCollapsed(key: string): boolean {
  return collapsedGroups.value.has(key)
}

/** 折叠分组只影响表格展示，不修改路由数据。 */
function toggleGroup(key: string): void {
  const next = new Set(collapsedGroups.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  collapsedGroups.value = next
}

function toggleKey(key: string): void {
  const next = new Set(props.selectedKeys)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  emit('update:selectedKeys', next)
}

/** 全选只作用于当前可见行，避免筛选状态下误选隐藏项。 */
function toggleAll(value: boolean | 'indeterminate'): void {
  const next = new Set(props.selectedKeys)
  if (value === true) {
    rows.value.forEach(row => next.add(row.key))
  } else {
    rows.value.forEach(row => next.delete(row.key))
  }
  emit('update:selectedKeys', next)
}

function handleDragStart(row: RouteRow, event: DragEvent): void {
  if (props.filter !== 'all') {
    event.preventDefault()
    return
  }
  dragSource.value = row.kind === 'child'
    ? { kind: 'child', routeIndex: row.routeIndex, childIndex: row.childIndex as number }
    : { kind: 'root', routeIndex: row.routeIndex }
  event.dataTransfer?.setData('text/plain', row.key)
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
  }
}

function handleDragOver(row: RouteRow, event: DragEvent): void {
  const source = dragSource.value
  if (!source || props.filter !== 'all') {
    return
  }
  const allowed = source.kind === 'root'
    ? row.kind !== 'child'
    : row.kind === 'child' && row.routeIndex === source.routeIndex
  if (!allowed) {
    return
  }
  event.preventDefault()
  dragOverKey.value = row.key
}

function handleDrop(row: RouteRow, event: DragEvent): void {
  event.preventDefault()
  const source = dragSource.value
  if (!source) {
    return
  }
  if (source.kind === 'root' && row.kind !== 'child') {
    moveRoot(source.routeIndex, row.routeIndex)
  } else if (source.kind === 'child' && row.kind === 'child' && row.routeIndex === source.routeIndex) {
    moveChild(source.routeIndex, source.childIndex, row.childIndex as number)
  }
  clearDragState()
}

function clearDragState(): void {
  dragSource.value = null
  dragOverKey.value = null
}

/** 顶层节点排序。 */
function moveRoot(from: number, to: number): void {
  if (from === to) {
    return
  }
  const next = cloneProjectRoutes(props.routes)
  const [moved] = next.splice(from, 1)
  if (!moved) {
    return
  }
  next.splice(to, 0, moved)
  emit('update:modelValue', normalizeProjectRouteOrders(next))
}

/** 同一分组内的子页排序。 */
function moveChild(routeIndex: number, from: number, to: number): void {
  if (from === to) {
    return
  }
  const next = cloneProjectRoutes(props.routes)
  const children = [...(next[routeIndex]?.children ?? [])]
  const [moved] = children.splice(from, 1)
  if (!moved) {
    return
  }
  children.splice(to, 0, moved)
  next[routeIndex].children = children
  emit('update:modelValue', normalizeProjectRouteOrders(next))
}

/** Alt + 上下方向键移动当前选中行，提供不依赖指针的排序方式。 */
function moveSelected(delta: number): void {
  if (props.filter !== 'all' || !props.selectedKey) {
    return
  }
  const row = rows.value.find(item => item.key === props.selectedKey)
  if (!row) {
    return
  }
  if (row.kind === 'child') {
    const children = props.routes[row.routeIndex]?.children ?? []
    const target = clamp(row.childIndex as number + delta, 0, children.length - 1)
    moveChild(row.routeIndex, row.childIndex as number, target)
    return
  }
  const target = clamp(row.routeIndex + delta, 0, props.routes.length - 1)
  moveRoot(row.routeIndex, target)
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}
</script>

<style scoped>
.route-table-grid {
  display: grid;
  grid-template-columns: 26px 16px minmax(0, 1fr) 96px;
  gap: 0.375rem;
  align-items: center;
}

.route-row {
  position: relative;
  border-top: 0.5px solid rgb(var(--ui-border));
  color: rgb(var(--ui-text));
  cursor: pointer;
  outline: none;
  transition: background-color 0.15s ease;
}

.route-row:first-of-type {
  border-top: 0;
}

.route-row:hover,
.route-row:focus-visible {
  background: rgb(var(--ui-surface-muted));
}

.route-row--selected {
  background: rgb(var(--ui-surface-selected));
}

.route-row--selected::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 2px;
  background: rgb(var(--ui-accent));
}

.route-row--drag-over {
  background: rgb(var(--ui-surface-selected));
  box-shadow: inset 0 0 0 1px rgb(var(--ui-accent));
}

.route-row--child .route-row__page--child {
  padding-left: 0.875rem;
}

.route-badge {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  border-radius: 4px;
  padding: 1px 4px;
  font-size: 11px;
  line-height: 1.4;
  background: rgb(var(--ui-surface-muted));
  color: rgb(var(--ui-text-secondary));
}

.route-badge--hidden {
  background: rgb(var(--ui-warning-muted));
  color: rgb(var(--ui-warning-strong));
}

.route-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 2px 6px;
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
  background: rgb(var(--ui-surface-muted));
  color: rgb(var(--ui-text-secondary));
}

.route-chip--override {
  background: rgb(var(--ui-warning-muted));
  color: rgb(var(--ui-warning-strong));
}

.route-chip--group {
  background: rgb(var(--ui-info-muted));
  color: rgb(var(--ui-info-strong));
}
</style>
