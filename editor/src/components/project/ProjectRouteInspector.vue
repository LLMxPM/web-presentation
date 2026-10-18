<!-- 文件功能：页面结构右侧检查器，编辑选中节点的基础信息、路径、显示状态与放映覆盖。 -->
<template>
  <aside class="flex min-h-0 min-w-0 flex-col rounded-2xl border border-border bg-surface">
    <template v-if="selection && item">
      <header class="border-b border-border px-3 py-2.5">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <h5 class="truncate text-sm font-bold text-text-strong">{{ headerTitle }}</h5>
            <div class="mt-0.5 truncate font-mono text-[11px] text-text-disabled" :title="selection.fullPath">{{ selection.fullPath }}</div>
          </div>
          <span v-if="item.hidden" class="route-badge route-badge--hidden shrink-0">隐藏</span>
        </div>
        <p class="mt-1 text-[11px] text-text-muted">{{ sequenceSummary }}</p>
      </header>

      <div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3">
        <section class="space-y-2">
          <h6 class="text-[11px] font-semibold uppercase tracking-wide text-text-muted">基础</h6>

          <UiFormField v-if="isGroup" label="分组标题">
            <template #default="field">
              <UiInput
                :model-value="groupTitle"
                placeholder="分组标题"
                :input-id="field.inputId"
                @update:model-value="handleGroupTitleInput"
              />
            </template>
          </UiFormField>

          <UiFormField v-else label="页面">
            <template #default>
              <UiCombobox
                :model-value="item.page_id ?? null"
                :options="pageOptions"
                placeholder="选择页面"
                empty-text="暂无可选页面"
                size="compact"
                @update:model-value="handlePageChange"
              />
            </template>
          </UiFormField>

          <label class="flex items-start gap-2 rounded-ui-md border border-border px-2.5 py-2">
            <UiCheckbox :model-value="!item.hidden" @update:model-value="handleHiddenChange" />
            <span class="min-w-0">
              <span class="block text-xs font-medium text-text-emphasis">在目录和放映中显示</span>
              <span class="mt-0.5 block text-[11px] leading-4 text-text-muted">隐藏后不显示在目录，也不参与自动/手动翻页。</span>
            </span>
          </label>

          <div>
            <UiButton
              variant="ghost"
              size="xs"
              content-align="between"
              class="w-full"
              @click="showAdvanced = !showAdvanced"
            >
              <span class="flex shrink-0 items-center gap-1">
                <ChevronRight class="h-3.5 w-3.5 transition-transform" :class="{ 'rotate-90': showAdvanced }" />
                高级 · 访问路径
              </span>
              <span class="min-w-0 truncate font-mono text-text-disabled">{{ item.route }}</span>
            </UiButton>
            <div v-if="showAdvanced" class="mt-2 space-y-2 rounded-ui-md border border-border bg-canvas/50 p-2.5">
              <UiFormField label="Route 片段">
                <template #default="field">
                  <UiInput
                    :model-value="routeInput"
                    placeholder="例如 home、chapter-1"
                    :input-id="field.inputId"
                    @update:model-value="routeInput = String($event)"
                    @blur="commitRoute"
                    @keydown.enter.prevent="commitRoute"
                  />
                </template>
              </UiFormField>
              <p class="text-[11px] text-text-muted">完整路径 <span class="font-mono text-text-emphasis">{{ selection.fullPath }}</span></p>
              <p class="text-[11px] leading-4 text-warning-strong">修改路径会影响已分享链接；子页路径随分组路径一起变化。</p>
              <p v-if="routeError" class="text-[11px] text-danger">{{ routeError }}</p>
            </div>
          </div>
        </section>

        <section v-if="!isGroup" class="space-y-2 border-t border-border pt-3">
          <div class="flex items-center justify-between gap-2">
            <h6 class="text-[11px] font-semibold uppercase tracking-wide text-text-muted">放映</h6>
            <UiButton
              v-if="hasOverride"
              variant="ghost"
              size="xs"
              @click="handleResetSlideshow"
            >
              恢复继承
            </UiButton>
          </div>
          <ProjectRouteSlideshowForm
            :transition="item.transition ?? null"
            :advance="item.advance ?? null"
            :defaults="defaults"
            :capabilities="capabilities"
            @update:transition="handleTransitionUpdate"
            @update:advance="handleAdvanceUpdate"
          />
        </section>

        <section v-else class="space-y-2 border-t border-border pt-3">
          <div class="flex items-center justify-between gap-2">
            <h6 class="text-[11px] font-semibold uppercase tracking-wide text-text-muted">本章</h6>
            <span class="text-[11px] text-text-muted">{{ groupChildren.length }} 个子页</span>
          </div>

          <div v-if="groupChildRows.length > 0" class="space-y-1">
            <UiButton
              v-for="child in groupChildRows"
              :key="child.key"
              variant="ghost"
              size="xs"
              content-align="between"
              class="w-full"
              :title="child.title"
              @click="emit('select-node', child.key)"
            >
              <span class="flex min-w-0 items-center gap-1.5">
                <span class="truncate text-xs text-text-emphasis">{{ child.title }}</span>
                <span v-if="child.hidden" class="route-badge route-badge--hidden">隐藏</span>
              </span>
              <span class="route-chip shrink-0" :class="child.overridden ? 'route-chip--override' : ''">{{ child.chip }}</span>
            </UiButton>
          </div>
          <p v-else class="text-[11px] text-text-disabled">本章还没有子页，可从下方添加。</p>

          <UiButton
            variant="secondary"
            size="sm"
            class="w-full"
            :disabled="groupChildren.length === 0"
            @click="handleBatchChapter"
          >
            批量设置本章
          </UiButton>

          <div class="rounded-ui-md border border-dashed border-border p-2">
            <UiCombobox
              :model-value="childPageId"
              :options="pageOptions"
              placeholder="选择页面"
              empty-text="暂无可选页面"
              size="compact"
              @update:model-value="handleChildPageChange"
            />
            <UiButton
              size="sm"
              class="mt-2 w-full"
              :disabled="childPageId == null"
              @click="handleAddChild"
            >
              添加子页
            </UiButton>
          </div>
        </section>
      </div>

      <footer class="space-y-2 border-t border-border p-3">
        <div class="flex items-center gap-2">
          <UiButton variant="primary" size="sm" class="min-w-0 flex-1" :disabled="!canPresent" @click="handlePresent">
            {{ isGroup ? '保存并从本章放映' : '保存并从这里放映' }}
          </UiButton>
          <UiButton variant="danger" size="sm" class="shrink-0" @click="handleDelete">
            删除{{ isGroup ? '分组' : '此页' }}
          </UiButton>
        </div>
        <p v-if="item.hidden" class="text-center text-[11px] leading-4 text-warning-strong">已隐藏，不参与放映序列；取消隐藏后可从这里放映。</p>
        <p v-else class="text-center text-[11px] leading-4 text-text-disabled">保存后按当前页生成新的只读放映快照。</p>
      </footer>
    </template>

    <div v-else class="flex flex-1 items-center justify-center px-5 py-10 text-center">
      <div>
        <div class="text-sm font-semibold text-text-emphasis">选择一个页面查看设置</div>
        <p class="mt-2 text-xs leading-5 text-text-muted">点击中间序列中的行，可编辑页面、显示状态、路径和逐页放映覆盖。</p>
        <p class="mt-3 text-[11px] leading-5 text-text-disabled">多选后可批量设置；选中分组可应用到本章。</p>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronRight } from '@lucide/vue'

import { UiButton, UiCheckbox, UiCombobox, UiFormField, UiInput } from '@/components/ui'
import type {
  PageItem,
  ProjectRouteChildWrite,
  ProjectRouteItemWrite,
  SlideshowAdvance,
  SlideshowCapabilities,
  SlideshowSettings,
  SlideshowTransition,
} from '@/types/api'
import type { SelectPrimitive } from '@/components/ui/select'
import type {
  RouteNodePatch,
  RouteNodeSelection,
  RoutePageMeta,
} from '@/utils/project-route-slideshow'
import {
  formatRouteSlideshowSummary,
  getRouteSequenceNumber,
  hasSlideshowOverride,
} from '@/utils/project-route-slideshow'
import { isValidProjectRouteSegment } from '@/utils/project-route'
import { createConfirm } from '@/utils/message'
import ProjectRouteSlideshowForm from './ProjectRouteSlideshowForm.vue'

const props = withDefaults(defineProps<{
  selection: RouteNodeSelection | null
  routes: ProjectRouteItemWrite[]
  pages: PageItem[]
  pageMeta: Map<number, RoutePageMeta>
  defaults: SlideshowSettings
  capabilities?: SlideshowCapabilities | null
}>(), {
  capabilities: null,
})

const emit = defineEmits<{
  'update-node': [payload: { key: string; patch: RouteNodePatch }]
  'delete-node': [key: string]
  present: [entryRoute: string]
  'open-batch': [keys: string[]]
  'add-child': [payload: { groupKey: string; pageId: number }]
  'select-node': [key: string]
}>()

const showAdvanced = ref(false)
const routeInput = ref('')
const routeError = ref('')
const childPageId = ref<SelectPrimitive | null>(null)

const item = computed(() => props.selection?.item ?? null)
const isGroup = computed(() => props.selection?.routeType === 'group')
const groupTitle = computed(() => {
  if (!props.selection || props.selection.routeType !== 'group') {
    return ''
  }
  return (props.selection.item as ProjectRouteItemWrite).group_title ?? ''
})
const hasOverride = computed(() => item.value ? hasSlideshowOverride(item.value) : false)
const headerTitle = computed(() => {
  if (!item.value) {
    return ''
  }
  if (isGroup.value) {
    return groupTitle.value || '未命名分组'
  }
  return props.pageMeta.get(item.value.page_id ?? -1)?.title ?? '未绑定页面'
})
const groupChildren = computed<ProjectRouteChildWrite[]>(() => {
  if (!props.selection || !isGroup.value) {
    return []
  }
  return props.routes[props.selection.routeIndex]?.children ?? []
})
const groupChildRows = computed(() => {
  if (!props.selection) {
    return []
  }
  const parent = props.routes[props.selection.routeIndex]
  return groupChildren.value.map((child, index) => ({
    key: `child:${parent?.route ?? ''}/${child.route}`,
    title: props.pageMeta.get(child.page_id)?.title ?? '未绑定页面',
    hidden: child.hidden,
    overridden: hasSlideshowOverride(child),
    chip: formatRouteSlideshowSummary(child, props.defaults).label,
    index,
  }))
})
const sequenceNumber = computed(() => {
  return props.selection ? getRouteSequenceNumber(props.routes, props.selection.key) : null
})
const playablePageCount = computed(() => {
  let count = 0
  for (const routeItem of props.routes) {
    if (routeItem.hidden) {
      continue
    }
    if (routeItem.route_type === 'group') {
      count += (routeItem.children ?? []).filter(child => !child.hidden).length
      continue
    }
    count += 1
  }
  return count
})
const sequenceSummary = computed(() => {
  if (!item.value) {
    return ''
  }
  if (item.value.hidden) {
    return '已隐藏，不参与自动放映序列'
  }
  if (isGroup.value) {
    return `本章 ${groupChildren.value.length} 个子页，具体放映设置在子页上调整`
  }
  if (sequenceNumber.value == null) {
    return `共 ${playablePageCount.value} 个可放映页`
  }
  return `第 ${sequenceNumber.value} 页 / 共 ${playablePageCount.value} 页`
})
const pageOptions = computed(() => {
  const activePages = props.pages
    .filter(page => page.status === 'active')
    .sort((left, right) => left.title.localeCompare(right.title, 'zh-CN'))
  const options = activePages.map(page => ({
    label: page.title,
    value: page.id,
    description: page.code,
    keywords: [page.code, page.title, ...(page.summary ? [page.summary] : [])],
  }))
  const currentPageId = item.value?.page_id ?? null
  if (currentPageId != null && !options.some(option => option.value === currentPageId)) {
    const meta = props.pageMeta.get(currentPageId)
    options.unshift({
      label: meta ? `${meta.title}（已归档）` : `页面 #${currentPageId}`,
      value: currentPageId,
      description: meta?.code ?? '',
      keywords: [meta?.code ?? '', meta?.title ?? ''],
    })
  }
  return options
})
const entryRoute = computed(() => {
  if (!props.selection) {
    return ''
  }
  if (!isGroup.value) {
    return props.selection.fullPath
  }
  for (const child of groupChildren.value) {
    if (!child.hidden) {
      return `/${props.selection.item.route}/${child.route}`.replace(/\/+/g, '/')
    }
  }
  return ''
})
const canPresent = computed(() => {
  if (!entryRoute.value || entryRoute.value === '/') {
    return false
  }
  return !item.value?.hidden
})

watch(
  () => props.selection?.key,
  () => {
    routeInput.value = String(props.selection?.item.route ?? '')
    routeError.value = ''
    showAdvanced.value = false
    childPageId.value = null
  },
  { immediate: true },
)

watch(
  () => props.selection?.item.route,
  route => {
    routeInput.value = String(route ?? '')
  },
)

/** 更新页面绑定。 */
function handlePageChange(value: SelectPrimitive | SelectPrimitive[] | null): void {
  const pageId = normalizeSelectionValue(Array.isArray(value) ? (value[0] ?? null) : value)
  if (pageId == null || !props.selection) {
    return
  }
  emit('update-node', { key: props.selection.key, patch: { page_id: pageId } })
}

/** 更新分组标题。 */
function handleGroupTitleInput(value: string | number): void {
  if (!props.selection) {
    return
  }
  emit('update-node', { key: props.selection.key, patch: { group_title: String(value) } })
}

/** 复选框表达“显示”，写模型使用 hidden，语义在这里反转一次。 */
function handleHiddenChange(value: boolean | 'indeterminate'): void {
  if (!props.selection) {
    return
  }
  emit('update-node', { key: props.selection.key, patch: { hidden: value !== true } })
}

/** 提交路径修改，并在前端先做格式与同级重复校验。 */
function commitRoute(): void {
  if (!props.selection) {
    return
  }
  const nextRoute = routeInput.value.trim()
  const currentRoute = props.selection.item.route
  if (nextRoute === currentRoute) {
    routeError.value = ''
    return
  }
  if (!nextRoute) {
    routeError.value = 'Route 不能为空。'
    return
  }
  if (!isValidProjectRouteSegment(nextRoute)) {
    routeError.value = '只能使用单段相对片段，例如 home、chapter-1 或 PAGE_01。'
    return
  }
  const conflict = hasSiblingRouteConflict(nextRoute, props.selection)
  if (conflict) {
    routeError.value = '同一级已存在相同 Route，请换一个。'
    return
  }
  routeError.value = ''
  emit('update-node', { key: props.selection.key, patch: { route: nextRoute } })
}

/** 检查同级路由片段是否重复。 */
function hasSiblingRouteConflict(nextRoute: string, selection: RouteNodeSelection): boolean {
  if (selection.scope === 'root') {
    return props.routes.some((routeItem, index) => index !== selection.routeIndex && routeItem.route === nextRoute)
  }
  const siblings = props.routes[selection.routeIndex]?.children ?? []
  return siblings.some((child, index) => index !== selection.childIndex && child.route === nextRoute)
}

function handleTransitionUpdate(value: SlideshowTransition | null): void {
  if (!props.selection) {
    return
  }
  emit('update-node', { key: props.selection.key, patch: { transition: value } })
}

function handleAdvanceUpdate(value: SlideshowAdvance | null): void {
  if (!props.selection) {
    return
  }
  emit('update-node', { key: props.selection.key, patch: { advance: value } })
}

/** 清除两组覆盖，等价于显式提交 null。 */
function handleResetSlideshow(): void {
  if (!props.selection) {
    return
  }
  emit('update-node', { key: props.selection.key, patch: { transition: null, advance: null } })
}

/** 分组批量设置只传子页键，避免把分组本身写成覆盖。 */
function handleBatchChapter(): void {
  if (!props.selection) {
    return
  }
  emit('open-batch', groupChildRows.value.map(child => child.key))
}

function handleChildPageChange(value: SelectPrimitive | SelectPrimitive[] | null): void {
  childPageId.value = Array.isArray(value) ? (value[0] ?? null) : value
}

function handleAddChild(): void {
  if (!props.selection || childPageId.value == null) {
    return
  }
  const pageId = normalizeSelectionValue(childPageId.value)
  if (pageId == null) {
    return
  }
  emit('add-child', { groupKey: props.selection.key, pageId })
  childPageId.value = null
}

/** 从当前节点开始放映；分组取第一个可见子页。 */
function handlePresent(): void {
  if (!canPresent.value) {
    return
  }
  emit('present', entryRoute.value)
}

/** 删除前确认；删除分组会同时移除本章子页。 */
async function handleDelete(): Promise<void> {
  if (!props.selection || !item.value) {
    return
  }
  const title = headerTitle.value
  const message = isGroup.value
    ? `删除分组「${title}」会同时移除本章的 ${groupChildren.value.length} 个子页，保存后生效。`
    : `从页面结构中移除「${title}」？保存后生效。`
  const confirmed = await createConfirm(message, isGroup.value ? '删除分组' : '删除页面', {
    dangerous: true,
    confirmLabel: '删除',
    cancelLabel: '取消',
  })
  if (!confirmed) {
    return
  }
  emit('delete-node', props.selection.key)
}

/** 把选择器值收敛为页面 ID。 */
function normalizeSelectionValue(value: SelectPrimitive | null): number | null {
  if (value == null) {
    return null
  }
  const pageId = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(pageId) ? pageId : null
}
</script>

<style scoped>
.route-badge {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  border-radius: 4px;
  padding: 1px 4px;
  font-size: 11px;
  line-height: 1.4;
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
</style>
