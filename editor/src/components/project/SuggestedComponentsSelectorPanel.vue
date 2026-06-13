<!-- 文件功能：提供可嵌入的建议组件双栏选择面板，维护有序已选组件与工作空间已发布组件候选。 -->
<template>
  <div v-if="workspaceId" class="grid h-full min-h-0 grid-rows-[minmax(220px,0.95fr)_minmax(0,1.05fr)] gap-2 overflow-hidden lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)] lg:grid-rows-1">
    <section class="flex h-full min-h-0 flex-col rounded-lg border border-indigo-100 bg-indigo-50/40 p-3">
      <div class="flex shrink-0 items-center justify-between gap-2">
        <div class="flex min-w-0 items-center gap-2">
          <Layers class="h-4 w-4 shrink-0 text-indigo-600" />
          <h4 class="truncate text-sm font-bold text-indigo-700">{{ selectedTitle }}</h4>
        </div>
        <span class="rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-indigo-600">
          {{ selectedComponentIds.length }}
        </span>
      </div>
      <p
        v-if="unavailableSelectedComponents.length"
        class="mt-3 rounded-md border border-rose-100 bg-white px-3 py-2 text-xs leading-5 text-rose-600"
      >
        有 {{ unavailableSelectedComponents.length }} 个建议组件已不可用，请移除后保存。
      </p>

      <div v-if="loading" class="flex min-h-0 flex-1 items-center justify-center text-sm font-semibold text-slate-400">
        <RefreshCw class="mr-2 h-4 w-4 animate-spin" />
        正在加载
      </div>
      <div v-else-if="selectedComponentSummaries.length" class="component-column-scroll mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
        <article
          v-for="component in selectedComponentSummaries"
          :key="component.id"
          class="flex w-full min-w-0 items-center justify-between gap-2 rounded-md border px-3 py-2 text-left transition"
          :class="isComponentUnavailable(component) ? 'border-rose-200 bg-rose-50/60 hover:border-rose-300' : 'border-indigo-200 bg-white hover:border-indigo-300'"
        >
          <span class="min-w-0 text-left">
            <span class="block truncate text-xs font-bold text-slate-800">{{ component.name }}</span>
            <span class="mt-0.5 block truncate font-mono text-[11px] text-slate-400">{{ component.import_name }}</span>
            <span v-if="isComponentUnavailable(component)" class="mt-1 block text-[11px] font-semibold leading-4 text-rose-600">
              {{ component.unavailable_reason || '组件已不可用，请移除后保存。' }}
            </span>
          </span>
          <span class="inline-flex shrink-0 items-center gap-1">
            <span
              class="rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
              :class="isComponentUnavailable(component) ? 'bg-rose-100 text-rose-600' : 'bg-indigo-50 text-indigo-600'"
            >
              {{ component.component_type }}
            </span>
            <button
              type="button"
              class="rounded-md p-1 text-indigo-500 transition hover:bg-indigo-50 hover:text-indigo-700"
              :aria-label="`移除组件 ${component.name}`"
              :title="`移除 ${component.name}`"
              @click="removeComponent(component.id)"
            >
              <X class="h-3.5 w-3.5" />
            </button>
          </span>
        </article>
      </div>
      <p v-else class="mt-3 flex min-h-0 flex-1 items-center justify-center text-xs text-slate-400">{{ selectedEmptyText }}</p>
    </section>

    <section class="flex h-full min-h-0 flex-col rounded-lg border border-slate-200 bg-white p-3">
      <div class="grid shrink-0 grid-cols-[minmax(0,1fr)_auto_auto] gap-2">
        <BaseInput
          :model-value="componentKeyword"
          placeholder="按组件名称、引用名或说明搜索"
          @update:model-value="componentKeyword = String($event)"
          @keyup.enter="loadAvailableComponents"
        />
        <BaseButton
          variant="secondary"
          :loading="componentOptionsLoading"
          custom-class="h-11 min-w-[80px] whitespace-nowrap"
          @click="loadAvailableComponents"
        >
          <template #icon>
            <Search class="h-4 w-4" />
          </template>
          搜索
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="sm"
          :loading="componentOptionsLoading"
          custom-class="h-11 min-w-[64px] whitespace-nowrap"
          @click="loadAvailableComponents"
        >
          <template #icon>
            <RefreshCw class="h-4 w-4" />
          </template>
          刷新
        </BaseButton>
      </div>

      <div class="mt-3 flex shrink-0 flex-wrap gap-1.5">
        <button
          v-for="tab in componentTypeTabs"
          :key="tab.key"
          type="button"
          class="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-semibold transition"
          :class="activeComponentTypeTab === tab.key ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
          @click="activeComponentTypeTab = tab.key"
        >
          <span>{{ tab.label }}</span>
          <span class="rounded-full px-1 text-[10px]" :class="activeComponentTypeTab === tab.key ? 'bg-white/20 text-white' : 'bg-white text-slate-500'">
            {{ tab.count }}
          </span>
        </button>
      </div>

      <div v-if="componentOptionsLoading" class="mt-3 flex min-h-0 flex-1 items-center justify-center text-sm font-semibold text-slate-400">
        <RefreshCw class="mr-2 h-4 w-4 animate-spin" />
        正在加载组件
      </div>
      <div v-else-if="activeTabComponents.length" class="component-column-scroll mt-3 grid min-h-0 flex-1 content-start gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
        <article
          v-for="component in activeTabComponents"
          :key="component.id"
          class="flex min-h-16 min-w-0 items-stretch justify-between gap-1 rounded-md border text-left transition"
          :class="componentOptionClass(component.id)"
        >
          <button
            type="button"
            class="flex min-w-0 flex-1 items-center justify-between gap-2 px-3 py-2 text-left"
            @click="toggleComponent(component)"
          >
            <span class="min-w-0 text-left">
              <span class="block truncate text-xs font-bold">{{ component.name }}</span>
              <span class="mt-0.5 block truncate font-mono text-[11px] opacity-70">{{ component.import_name }}</span>
              <span v-if="component.summary" class="mt-0.5 block truncate text-[11px] opacity-70">{{ component.summary }}</span>
            </span>
            <Check v-if="isSelected(component.id)" class="h-4 w-4 shrink-0" />
            <Plus v-else class="h-4 w-4 shrink-0" />
          </button>
          <button
            type="button"
            class="mr-2 flex h-8 w-8 shrink-0 items-center justify-center self-center rounded-md text-slate-400 transition hover:bg-white hover:text-indigo-600 disabled:cursor-wait disabled:opacity-60"
            :aria-label="`预览组件 ${component.name}`"
            :title="`预览 ${component.name}`"
            @click.stop="openComponentPreview(component)"
          >
            <Eye class="h-4 w-4" />
          </button>
        </article>
      </div>
      <p v-else class="mt-3 flex min-h-0 flex-1 items-center justify-center text-xs text-slate-400">没有匹配的已发布组件</p>
    </section>
  </div>

  <div v-else class="flex min-h-[180px] items-center justify-center text-center text-sm text-slate-400">
    {{ unavailableText }}
  </div>

  <ComponentPreviewDialog v-model="previewDialogVisible" size="workbench">
    <ComponentPreviewWorkbench
      :source="previewSource"
      :refresh-key="previewRefreshKey"
      :title="previewComponent?.name || '组件预览'"
      :subtitle="previewSubtitle"
      class="h-full"
    >
      <template #actions>
        <BaseCloseButton label="关闭组件预览" @click="previewDialogVisible = false" />
      </template>
    </ComponentPreviewWorkbench>
  </ComponentPreviewDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Eye, Layers, Plus, RefreshCw, Search, X } from '@lucide/vue'

import { listComponents } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import ComponentPreviewDialog from '@/components/component-preview/ComponentPreviewDialog.vue'
import ComponentPreviewWorkbench from '@/components/component-preview/ComponentPreviewWorkbench.vue'
import type { ComponentPreviewWorkbenchSource } from '@/components/component-preview/component-preview-workbench'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import { workspaceComponentTypeValues } from '@/composables/useWorkspaceComponentDraft'
import type {
  SuggestedComponentItem,
  WorkspaceComponentItem,
  WorkspaceComponentType,
} from '@/types/api'
import { Message } from '@/utils/message'

type ComponentTypeTabKey = 'all' | WorkspaceComponentType
type ComponentSummary = Pick<
  SuggestedComponentItem,
  'id' | 'code' | 'name' | 'import_name' | 'component_type' | 'summary' | 'current_version_no' | 'available' | 'unavailable_reason'
>

const props = withDefaults(defineProps<{
  modelValue: SuggestedComponentItem[]
  workspaceId: number | null
  selectedTitle?: string
  unavailableText?: string
  selectedEmptyText?: string
  loading?: boolean
}>(), {
  selectedTitle: '已选组件',
  unavailableText: '当前没有可选工作空间。',
  selectedEmptyText: '未选择组件',
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [items: SuggestedComponentItem[]]
}>()

const componentOptionsLoading = ref(false)
const componentOptions = ref<WorkspaceComponentItem[]>([])
const componentKeyword = ref('')
const activeComponentTypeTab = ref<ComponentTypeTabKey>('all')
const previewComponent = ref<WorkspaceComponentItem | null>(null)
const previewDialogVisible = ref(false)
const previewRefreshKey = ref(0)

const selectedComponents = computed(() => props.modelValue ?? [])
const selectedComponentIds = computed(() => selectedComponents.value.map(component => component.id))
const selectedComponentIdSet = computed(() => new Set(selectedComponentIds.value))
const componentOptionSummaryById = computed(() => {
  const result = new Map<number, ComponentSummary>()
  for (const component of componentOptions.value) {
    result.set(component.id, toComponentSummary(component))
  }
  for (const component of selectedComponents.value) {
    if (!result.has(component.id)) {
      result.set(component.id, component)
    }
  }
  return result
})
const selectedComponentSummaries = computed(() => selectedComponentIds.value
  .map(id => componentOptionSummaryById.value.get(id))
  .filter((component): component is ComponentSummary => !!component))
const unavailableSelectedComponents = computed(() => (
  selectedComponentSummaries.value.filter(isComponentUnavailable)
))
const groupedComponentOptions = computed(() => workspaceComponentTypeValues.map(type => ({
  type,
  label: type,
  items: componentOptions.value.filter(component => component.component_type === type),
})))
const componentTypeTabs = computed(() => [
  { key: 'all' as const, label: '全部', count: componentOptions.value.length },
  ...groupedComponentOptions.value.map(group => ({
    key: group.type,
    label: group.label,
    count: group.items.length,
  })),
])
const activeTabComponents = computed(() => {
  if (activeComponentTypeTab.value === 'all') {
    return componentOptions.value
  }
  return componentOptions.value.filter(component => component.component_type === activeComponentTypeTab.value)
})
const previewSource = computed<ComponentPreviewWorkbenchSource | null>(() => {
  if (!previewComponent.value) {
    return null
  }
  return {
    kind: 'workspace-draft',
    workspaceId: previewComponent.value.workspace_id ?? props.workspaceId,
    componentId: previewComponent.value.id,
    componentName: previewComponent.value.name,
    content: previewComponent.value.content,
    previewSchema: previewComponent.value.preview_schema,
    isDraftPreview: previewComponent.value.current_version_no <= 0 || previewComponent.value.has_unpublished_changes,
    componentType: previewComponent.value.component_type,
  }
})
const previewSubtitle = computed(() => {
  if (!previewComponent.value) {
    return ''
  }
  const versionLabel = previewComponent.value.current_version_no <= 0
    ? '未发布'
    : previewComponent.value.has_unpublished_changes
      ? `v${previewComponent.value.current_version_no} + 草稿`
      : `v${previewComponent.value.current_version_no} 已发布`
  return `${previewComponent.value.code} · ${versionLabel}`
})

watch(
  () => props.workspaceId,
  (workspaceId) => {
    componentOptions.value = []
    componentKeyword.value = ''
    activeComponentTypeTab.value = 'all'
    if (workspaceId) {
      void loadAvailableComponents()
    }
  },
  { immediate: true },
)

watch(componentTypeTabs, (tabs) => {
  if (!tabs.some(tab => tab.key === activeComponentTypeTab.value)) {
    activeComponentTypeTab.value = 'all'
  }
})

/**
 * 读取当前工作空间可选已发布组件。
 */
async function loadAvailableComponents(): Promise<void> {
  if (!props.workspaceId) {
    return
  }
  componentOptionsLoading.value = true
  try {
    const response = await listComponents({
      workspace_id: props.workspaceId,
      published_only: true,
      status: 'active',
      page: 1,
      page_size: 100,
      keyword: componentKeyword.value.trim() || undefined,
    })
    componentOptions.value = response.items
  } catch (error) {
    Message.error(getErrorMessage(error, '加载已发布组件失败。'))
  } finally {
    componentOptionsLoading.value = false
  }
}

/**
 * 切换组件选择状态。
 * @param component 工作空间组件
 */
function toggleComponent(component: WorkspaceComponentItem): void {
  if (selectedComponentIdSet.value.has(component.id)) {
    removeComponent(component.id)
    return
  }
  if (selectedComponents.value.length >= 100) {
    Message.warning('建议组件最多选择 100 个。')
    return
  }
  emit('update:modelValue', [...selectedComponents.value, toComponentSummary(component)])
}

/**
 * 从已选列表移除组件。
 * @param componentId 组件 ID
 */
function removeComponent(componentId: number): void {
  emit('update:modelValue', selectedComponents.value.filter(component => component.id !== componentId))
}

/**
 * 判断组件是否已选择。
 * @param componentId 组件 ID
 */
function isSelected(componentId: number): boolean {
  return selectedComponentIdSet.value.has(componentId)
}

/**
 * 打开候选组件预览弹窗。
 * @param component 待预览的候选组件
 */
function openComponentPreview(component: WorkspaceComponentItem): void {
  previewComponent.value = component
  previewRefreshKey.value += 1
  previewDialogVisible.value = true
}

/**
 * 判断已选组件是否已经不再满足建议组件条件。
 * @param component 已选组件摘要
 */
function isComponentUnavailable(component: ComponentSummary): boolean {
  return component.available === false
}

/**
 * 转换完整组件为面板内部摘要。
 * @param component 工作空间组件
 */
function toComponentSummary(component: WorkspaceComponentItem): ComponentSummary {
  return {
    id: component.id,
    code: component.code,
    name: component.name,
    import_name: component.import_name,
    component_type: component.component_type,
    summary: component.summary,
    current_version_no: component.current_version_no,
    available: true,
    unavailable_reason: null,
  }
}

/**
 * 生成组件按钮样式。
 * @param componentId 组件 ID
 */
function componentOptionClass(componentId: number): string {
  if (isSelected(componentId)) {
    return 'border-indigo-200 bg-indigo-50 text-indigo-700'
  }
  return 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
}
</script>

<style scoped>
.component-column-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgb(203 213 225) transparent;
}

.component-column-scroll::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}

.component-column-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.component-column-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgb(203 213 225);
}
</style>

