<!-- 文件功能：提供 components 页面左侧组件库列表，负责工作空间组件与 Runtime Kit 能力的浏览、选择和轻量操作。 -->
<template>
  <LibrarySidebarPanel
    :model-value="modelValue"
    title="组件库"
    show-search
    :show-close="closable"
    v-model:search-value="searchKeyword"
    search-placeholder="搜索组件名称、引用名、编码、类型或说明..."
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #icon>
      <Layers class="h-5 w-5 text-indigo-600" />
    </template>

    <template #actions>
      <button
        v-if="readOnly && workspaceId"
        type="button"
        class="flex items-center gap-1 rounded-lg p-1.5 text-xs font-bold text-indigo-600 transition-colors hover:bg-indigo-50"
        title="打开完整组件库页面"
        @click="openComponentLibraryPage"
      >
        <ArrowUpRight class="h-4 w-4" />
        <span class="hidden lg:inline">组件管理</span>
      </button>
      <button
        v-if="!readOnly && componentPanelTab === 'workspace' && batchSelectedComponentIds.length > 0"
        type="button"
        class="flex items-center gap-1 rounded-lg p-1.5 text-xs font-bold text-indigo-600 transition-colors hover:bg-indigo-50"
        :disabled="exportPackagePending"
        title="导出已勾选组件"
        @click="emitExportRequest"
      >
        <Download class="h-4 w-4" />
        <span class="hidden lg:inline">导出组件</span>
      </button>
      <button
        v-if="!readOnly && componentPanelTab === 'workspace' && batchSelectedComponentIds.length === 0"
        type="button"
        class="flex items-center gap-1 rounded-lg p-1.5 text-xs font-bold text-indigo-600 transition-colors hover:bg-indigo-50"
        :disabled="loading"
        title="刷新组件列表"
        @click="emitRefreshRequest"
      >
        <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" />
        <span class="hidden lg:inline">刷新</span>
      </button>
      <button
        v-if="showCreateImportActions && !readOnly && componentPanelTab === 'workspace'"
        type="button"
        class="flex items-center gap-1 rounded-lg p-1.5 text-xs font-bold text-indigo-600 transition-colors hover:bg-indigo-50"
        :disabled="importPackagePending"
        title="导入组件离线包"
        @click="emitImportRequest"
      >
        <Upload class="h-4 w-4" />
        <span class="hidden lg:inline">导入组件</span>
      </button>
      <button
        v-if="showCreateImportActions && !readOnly && componentPanelTab === 'workspace'"
        type="button"
        class="flex items-center gap-1 rounded-lg p-1.5 text-xs font-bold text-indigo-600 transition-colors hover:bg-indigo-50"
        title="新建组件"
        @click="emitCreateRequest"
      >
        <Plus class="h-4 w-4" />
        <span class="hidden lg:inline">新建</span>
      </button>
    </template>

    <div class="shrink-0 border-b border-slate-50 bg-slate-50/50 px-4 pb-2">
      <LibrarySegmentedControl
        :model-value="componentPanelTab"
        :options="componentPanelOptions"
        :columns="2"
        @update:model-value="handleSelectComponentPanelTab"
      />
      <div v-if="!readOnly && componentPanelTab === 'workspace'" class="mt-2 flex items-center justify-between gap-2 text-[11px]">
        <span class="font-bold text-slate-400">已选择 {{ batchSelectedComponentIds.length }} 个可导出组件</span>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="font-bold text-indigo-600 hover:text-indigo-700 disabled:text-slate-300"
            :disabled="filteredExportableComponentIds.length === 0"
            @click="selectAllFilteredPublished"
          >
            全选已发布
          </button>
          <button
            type="button"
            class="font-bold text-slate-500 hover:text-slate-700 disabled:text-slate-300"
            :disabled="batchSelectedComponentIds.length === 0"
            @click="clearBatchSelection"
          >
            清空
          </button>
        </div>
      </div>
    </div>

    <RuntimeKitCapabilityList
      v-if="componentPanelTab === 'runtime-kit'"
      class="min-h-0 flex-1"
      :keyword="searchKeyword"
      :selected-name="selectedRuntimeKitName"
      @runtime-kit-preview-selected="emit('runtime-kit-preview-selected', $event)"
      @runtime-kit-doc-selected="emit('runtime-kit-doc-selected', $event)"
    />

    <div v-else-if="loading" class="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-6">
      <div class="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent"></div>
      <span class="text-sm font-bold text-slate-400">正在加载组件...</span>
    </div>

    <div v-else class="relative min-h-0 flex-1 overflow-y-auto p-4 pb-24">
      <div
        v-if="filteredComponents.length === 0"
        class="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-100 bg-slate-50 px-4 py-12 text-center"
      >
        <Box class="mb-3 h-10 w-10 text-slate-300" />
        <p class="text-sm font-semibold text-slate-500">{{ searchKeyword ? '未找到相关组件' : '暂无共享组件' }}</p>
      </div>

      <div v-else class="space-y-3">
        <article
          v-for="component in filteredComponents"
          :key="component.id"
          class="group relative flex cursor-pointer flex-col rounded-xl border bg-white p-4 transition-all hover:border-indigo-300 hover:shadow-sm"
          :class="resolveComponentCardClass(component)"
          @click="selectWorkspaceComponent(component)"
        >
          <div class="mb-2.5 flex items-start justify-between gap-2">
            <label
              v-if="!readOnly"
              class="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center"
              :title="canBatchSelectComponent(component) ? '选择导出组件' : '组件发布后才能导出'"
              @click.stop
            >
              <input
                type="checkbox"
                class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
                :checked="isBatchSelected(component.id)"
                :disabled="!canBatchSelectComponent(component)"
                @change="toggleBatchComponent(component)"
              />
            </label>
            <div class="min-w-0 flex-1">
              <div class="mb-1.5 flex flex-wrap items-center gap-2">
                <h3 class="truncate text-sm font-bold text-slate-800 transition-colors group-hover:text-indigo-600">
                  {{ component.name }}
                </h3>
                <div class="flex items-center gap-1.5">
                  <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-black uppercase tracking-tight text-slate-500">
                    {{ component.component_type }}
                  </span>
                  <span
                    class="rounded px-1.5 py-0.5 text-[10px] font-black tracking-tight"
                    :class="resolveComponentVersionBadgeClass(component)"
                  >
                    {{ resolveComponentVersionBadgeText(component) }}
                  </span>
                </div>
              </div>
              <div class="inline-flex max-w-full rounded border border-slate-100 bg-slate-50 px-1.5 py-0.5">
                <span class="truncate font-mono text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  {{ component.code }}
                </span>
              </div>
              <div class="mt-1 inline-flex max-w-full rounded border border-indigo-100 bg-indigo-50 px-1.5 py-0.5">
                <span class="truncate font-mono text-[10px] font-bold text-indigo-500">
                  {{ component.import_name }}
                </span>
              </div>
            </div>
            <div class="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
              <button
                type="button"
                :disabled="!canCopyWorkspaceComponentImport(component)"
                class="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-indigo-50 hover:text-indigo-600 disabled:cursor-not-allowed disabled:text-slate-300 disabled:hover:bg-transparent"
                :title="canCopyWorkspaceComponentImport(component) ? '复制 import 语句' : '发布后可复制 import 语句'"
                @click.stop="copyComponentImportStatement(component)"
              >
                <Copy class="h-3.5 w-3.5" />
              </button>
              <button
                v-if="!readOnly"
                type="button"
                class="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-600"
                title="删除组件"
                @click.stop="handleDelete(component)"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <p v-if="component.summary" class="mb-3 line-clamp-2 text-[11px] leading-relaxed text-slate-500">
            {{ component.summary }}
          </p>

          <div class="mt-auto flex items-center justify-between border-t border-slate-50 pt-2.5 text-[10px] font-bold text-slate-400">
            <div class="flex items-center gap-1.5">
              <Calendar class="h-3 w-3 text-slate-300" />
              <span>已更新于 {{ formatDateTime(component.updated_at) }}</span>
            </div>
          </div>
        </article>
      </div>
    </div>
  </LibrarySidebarPanel>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowUpRight, Box, Calendar, Copy, Download, Layers, Plus, RefreshCw, Trash2, Upload } from 'lucide-vue-next'

import { deleteComponent, listComponents } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import RuntimeKitCapabilityList from '@/components/component-preview/RuntimeKitCapabilityList.vue'
import LibrarySegmentedControl from '@/components/project/LibrarySegmentedControl.vue'
import LibrarySidebarPanel from '@/components/project/LibrarySidebarPanel.vue'
import type { RuntimeKitComponentCapabilityItem, WorkspaceComponentItem } from '@/types/api'
import { buildWorkspaceComponentImportUsage } from '@/utils/component-import'
import { formatDateTime } from '@/utils/format'
import { createConfirm, Message } from '@/utils/message'
import { buildWorkspaceComponentsPath } from '@/utils/workspace-routes'

type ComponentPanelTab = 'workspace' | 'runtime-kit'

const props = withDefaults(defineProps<{
  modelValue: boolean
  workspaceId: number | null
  readOnly?: boolean
  closable?: boolean
  selectedComponentId?: number | null
  batchSelectedComponentIds?: number[]
  exportPackagePending?: boolean
  importPackagePending?: boolean
  showCreateImportActions?: boolean
  selectedRuntimeKitName?: string | null
  refreshKey?: number
}>(), {
  readOnly: false,
  closable: true,
  selectedComponentId: null,
  batchSelectedComponentIds: () => [],
  exportPackagePending: false,
  importPackagePending: false,
  showCreateImportActions: true,
  selectedRuntimeKitName: null,
  refreshKey: 0,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:batchSelectedComponentIds': [value: number[]]
  'workspace-component-selected': [value: WorkspaceComponentItem | null]
  'create-workspace-component': []
  'export-workspace-components': []
  'import-workspace-components': []
  'runtime-kit-preview-selected': [item: RuntimeKitComponentCapabilityItem]
  'runtime-kit-doc-selected': [item: RuntimeKitComponentCapabilityItem]
  'refresh-requested': []
}>()

const router = useRouter()
const loading = ref(false)
const components = ref<WorkspaceComponentItem[]>([])
const searchKeyword = ref('')
const componentPanelTab = ref<ComponentPanelTab>('workspace')
const componentPanelOptions = [
  { label: '工作空间组件', value: 'workspace' },
  { label: '内建能力', value: 'runtime-kit' },
]

const filteredComponents = computed(() => {
  const keyword = normalizeSearchKeyword(searchKeyword.value)
  if (!keyword) return components.value
  return components.value.filter(component => isComponentMatchedByKeyword(component, keyword))
})
const filteredExportableComponentIds = computed(() => (
  filteredComponents.value
    .filter(canBatchSelectComponent)
    .map(component => component.id)
))

watch(() => [props.modelValue, props.workspaceId, props.refreshKey], async ([visible, workspaceId]) => {
  if (visible && workspaceId) {
    await fetchComponents(workspaceId as number)
  }
}, { immediate: true })

/**
 * 手动刷新左侧工作空间组件列表，供父组件通过 ref 调用。
 */
async function refresh(): Promise<void> {
  if (props.workspaceId) {
    await fetchComponents(props.workspaceId)
  }
}

/**
 * 拉取当前工作空间组件列表。
 * @param workspaceId 工作空间主键
 */
async function fetchComponents(workspaceId: number): Promise<void> {
  loading.value = true
  try {
    const response = await listComponents({ page: 1, page_size: 100, workspace_id: workspaceId })
    components.value = response.items
    pruneBatchSelection()
  } catch (error) {
    Message.error(getErrorMessage(error, '加载组件失败'))
  } finally {
    loading.value = false
  }
}

/**
 * 切换组件库展示页签。
 * @param value 分段控件值
 */
function handleSelectComponentPanelTab(value: string): void {
  componentPanelTab.value = value === 'runtime-kit' ? 'runtime-kit' : 'workspace'
}

/**
 * 新建入口会清空当前选择，并让右侧工作台进入创建状态。
 */
function emitCreateRequest(): void {
  emit('workspace-component-selected', null)
  emit('create-workspace-component')
}

/**
 * 请求父级导出当前勾选组件。
 */
function emitExportRequest(): void {
  if (props.batchSelectedComponentIds.length === 0) {
    return
  }
  emit('export-workspace-components')
}

/**
 * 请求父级重新拉取组件库列表。
 */
function emitRefreshRequest(): void {
  emit('refresh-requested')
}

/**
 * 请求父级打开组件分享包导入。
 */
function emitImportRequest(): void {
  emit('import-workspace-components')
}

/**
 * 选择工作空间组件并交给右侧工作台打开预览。
 * @param component 当前组件
 */
function selectWorkspaceComponent(component: WorkspaceComponentItem): void {
  emit('workspace-component-selected', component)
}

/**
 * 切换组件批量导出选择状态。
 * @param component 当前组件
 */
function toggleBatchComponent(component: WorkspaceComponentItem): void {
  if (!canBatchSelectComponent(component)) {
    return
  }
  const selectedSet = new Set(props.batchSelectedComponentIds)
  if (selectedSet.has(component.id)) {
    selectedSet.delete(component.id)
  } else {
    selectedSet.add(component.id)
  }
  emit('update:batchSelectedComponentIds', Array.from(selectedSet))
}

/**
 * 选中当前筛选结果中全部已发布组件。
 */
function selectAllFilteredPublished(): void {
  const selectedSet = new Set(props.batchSelectedComponentIds)
  for (const componentId of filteredExportableComponentIds.value) {
    selectedSet.add(componentId)
  }
  emit('update:batchSelectedComponentIds', Array.from(selectedSet))
}

/**
 * 清空批量导出选择。
 */
function clearBatchSelection(): void {
  emit('update:batchSelectedComponentIds', [])
}

/**
 * 列表刷新后移除已不存在或不可导出的组件选择。
 */
function pruneBatchSelection(): void {
  if (props.readOnly || props.batchSelectedComponentIds.length === 0) {
    return
  }
  const exportableIds = new Set(components.value.filter(canBatchSelectComponent).map(component => component.id))
  const nextIds = props.batchSelectedComponentIds.filter(componentId => exportableIds.has(componentId))
  if (nextIds.length !== props.batchSelectedComponentIds.length) {
    emit('update:batchSelectedComponentIds', nextIds)
  }
}

/**
 * 从只读侧栏跳转到完整组件库页面。
 */
function openComponentLibraryPage(): void {
  if (!props.workspaceId) {
    return
  }
  emit('update:modelValue', false)
  void router.push(buildWorkspaceComponentsPath(props.workspaceId))
}

/**
 * 删除组件并刷新列表；如果删除的是当前选择，同时清空右侧工作台。
 * @param component 待删除组件
 */
async function handleDelete(component: WorkspaceComponentItem): Promise<void> {
  if (props.readOnly) {
    return
  }
  const confirmed = await createConfirm(`确认删除组件 "${component.name}" 吗？此操作为软删除。`, '确认删除')
  if (!confirmed) return

  try {
    await deleteComponent(component.id)
    Message.success('已删除')
    if (props.selectedComponentId === component.id) {
      emit('workspace-component-selected', null)
    }
    await refresh()
    emit('refresh-requested')
  } catch (error) {
    Message.error(getErrorMessage(error, '删除失败'))
  }
}

/**
 * 判断工作空间组件是否已经有可引用的正式版本。
 * @param component 待判断组件
 */
function canCopyWorkspaceComponentImport(component: WorkspaceComponentItem): boolean {
  return buildWorkspaceComponentImportUsage(component) !== null
}

function canBatchSelectComponent(component: WorkspaceComponentItem): boolean {
  return component.current_version_no > 0
}

function isBatchSelected(componentId: number): boolean {
  return props.batchSelectedComponentIds.includes(componentId)
}

/**
 * 复制工作空间组件 import 语句。
 * @param component 待复制组件
 */
async function copyComponentImportStatement(component: WorkspaceComponentItem): Promise<void> {
  const usage = buildWorkspaceComponentImportUsage(component)
  if (!usage) {
    Message.error('组件发布后才能复制 import 语句。')
    return
  }

  try {
    await navigator.clipboard.writeText(usage.importStatement)
    Message.success('import 语句已复制到剪贴板。')
  } catch {
    Message.error('复制 import 语句失败，请检查浏览器剪贴板权限。')
  }
}

function resolveComponentVersionBadgeText(component: WorkspaceComponentItem): string {
  if (component.current_version_no <= 0) {
    return '未发布'
  }
  return component.has_unpublished_changes
    ? `v${component.current_version_no} + 草稿`
    : `v${component.current_version_no} 已发布`
}

function resolveComponentVersionBadgeClass(component: WorkspaceComponentItem): string {
  if (component.current_version_no <= 0) {
    return 'bg-slate-100 text-slate-500'
  }
  return component.has_unpublished_changes
    ? 'bg-amber-50 text-amber-600'
    : 'bg-indigo-50 text-indigo-600'
}

function resolveComponentCardClass(component: WorkspaceComponentItem): string {
  if (props.selectedComponentId === component.id) {
    return 'border-indigo-400 ring-1 ring-indigo-200'
  }
  if (isBatchSelected(component.id)) {
    return 'border-emerald-300 ring-1 ring-emerald-100'
  }
  return 'border-slate-200'
}

function normalizeSearchKeyword(keyword: string): string {
  return keyword.trim().toLowerCase()
}

function isComponentMatchedByKeyword(component: WorkspaceComponentItem, keyword: string): boolean {
  return [
    component.name,
    component.import_name,
    component.code,
    component.component_type,
    component.summary || '',
    component.status,
    `v${component.current_version_no}`,
  ].some(value => String(value || '').toLowerCase().includes(keyword))
}

defineExpose({
  refresh,
})
</script>
