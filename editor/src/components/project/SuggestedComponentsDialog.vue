<!-- 文件功能：提供样式与项目共用的建议组件选择弹窗，维护有序已发布组件列表。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    :title="title"
    width="980px"
    body-class="h-[min(78vh,720px)] px-6 py-5 overflow-hidden"
    @update:model-value="handleVisibleChange"
  >
    <div v-if="workspaceId && targetId" class="grid h-full min-h-0 gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)]">
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

        <div v-if="loading" class="flex min-h-0 flex-1 items-center justify-center text-sm font-semibold text-slate-400">
          <RefreshCw class="mr-2 h-4 w-4 animate-spin" />
          正在加载
        </div>
        <div v-else-if="selectedComponentSummaries.length" class="component-column-scroll mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          <article
            v-for="component in selectedComponentSummaries"
            :key="component.id"
            class="flex w-full min-w-0 items-center justify-between gap-2 rounded-md border border-indigo-200 bg-white px-3 py-2 text-left transition hover:border-indigo-300"
          >
            <span class="min-w-0 text-left">
              <span class="block truncate text-xs font-bold text-slate-800">{{ component.name }}</span>
              <span class="mt-0.5 block truncate font-mono text-[11px] text-slate-400">{{ component.import_name }}</span>
            </span>
            <span class="inline-flex shrink-0 items-center gap-1">
              <span class="rounded-full bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-600">
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
        <p v-else class="mt-3 flex min-h-0 flex-1 items-center justify-center text-xs text-slate-400">未选择组件</p>
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
              @click="toggleComponent(component.id)"
            >
              <span class="min-w-0 text-left">
                <span class="block truncate text-xs font-bold">{{ component.name }}</span>
                <span class="mt-0.5 block truncate font-mono text-[11px] opacity-70">{{ component.import_name }}</span>
                <span v-if="component.summary" class="mt-0.5 block truncate text-[11px] opacity-70">{{ component.summary }}</span>
              </span>
              <Check v-if="isSelected(component.id)" class="h-4 w-4 shrink-0" />
              <Plus v-else class="h-4 w-4 shrink-0" />
            </button>
          </article>
        </div>
        <p v-else class="mt-3 flex min-h-0 flex-1 items-center justify-center text-xs text-slate-400">没有匹配的已发布组件</p>
      </section>
    </div>

    <div v-else class="py-10 text-center text-sm text-slate-400">
      {{ unavailableText }}
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="ghost" :disabled="loading || saving || !targetId" @click="loadDialogData">恢复当前值</BaseButton>
      <BaseButton variant="primary" :loading="saving" :disabled="!workspaceId || !targetId" @click="saveSelection">
        保存组件
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Layers, Plus, RefreshCw, Search, X } from '@lucide/vue'

import { listComponents } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import { workspaceComponentTypeValues } from '@/composables/useWorkspaceComponentDraft'
import type {
  SuggestedComponentItem,
  SuggestedComponentsResponse,
  WorkspaceComponentItem,
  WorkspaceComponentType,
} from '@/types/api'
import { Message } from '@/utils/message'

type ComponentTypeTabKey = 'all' | WorkspaceComponentType
type ComponentSummary = Pick<SuggestedComponentItem, 'id' | 'code' | 'name' | 'import_name' | 'component_type' | 'summary' | 'current_version_no'>

const props = withDefaults(defineProps<{
  modelValue: boolean
  workspaceId: number | null
  targetId: number | null
  title: string
  selectedTitle?: string
  unavailableText: string
  loadSuggestedComponents: (targetId: number) => Promise<SuggestedComponentsResponse>
  updateSuggestedComponents: (targetId: number, componentIds: number[]) => Promise<SuggestedComponentsResponse>
  loadErrorMessage: string
  saveErrorMessage: string
  successMessage: string
}>(), {
  selectedTitle: '已选组件',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [items: SuggestedComponentItem[]]
}>()

const loading = ref(false)
const saving = ref(false)
const componentOptionsLoading = ref(false)
const componentOptions = ref<WorkspaceComponentItem[]>([])
const savedComponents = ref<SuggestedComponentItem[]>([])
const selectedComponentIds = ref<number[]>([])
const componentKeyword = ref('')
const activeComponentTypeTab = ref<ComponentTypeTabKey>('all')

const selectedComponentIdSet = computed(() => new Set(selectedComponentIds.value))
const componentOptionSummaryById = computed(() => {
  const result = new Map<number, ComponentSummary>()
  for (const component of componentOptions.value) {
    result.set(component.id, toComponentSummary(component))
  }
  for (const component of savedComponents.value) {
    if (!result.has(component.id)) {
      result.set(component.id, component)
    }
  }
  return result
})
const selectedComponentSummaries = computed(() => selectedComponentIds.value
  .map(id => componentOptionSummaryById.value.get(id))
  .filter((component): component is ComponentSummary => !!component))
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

watch(
  () => [props.modelValue, props.workspaceId, props.targetId] as const,
  ([visible]) => {
    if (visible) {
      void loadDialogData()
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
 * 同步弹窗可见状态。
 * @param value 目标可见状态
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 并行读取已保存建议组件与可选已发布组件。
 */
async function loadDialogData(): Promise<void> {
  if (!props.workspaceId || !props.targetId) {
    return
  }
  loading.value = true
  try {
    await Promise.all([loadSavedComponents(), loadAvailableComponents()])
  } finally {
    loading.value = false
  }
}

/**
 * 读取当前对象已保存的建议组件。
 */
async function loadSavedComponents(): Promise<void> {
  if (!props.targetId) {
    return
  }
  try {
    const response = await props.loadSuggestedComponents(props.targetId)
    savedComponents.value = response.items
    selectedComponentIds.value = response.items.map(component => component.id)
  } catch (error) {
    Message.error(getErrorMessage(error, props.loadErrorMessage))
  }
}

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
 * @param componentId 组件 ID
 */
function toggleComponent(componentId: number): void {
  if (selectedComponentIdSet.value.has(componentId)) {
    removeComponent(componentId)
    return
  }
  selectedComponentIds.value = [...selectedComponentIds.value, componentId]
}

/**
 * 从已选列表移除组件。
 * @param componentId 组件 ID
 */
function removeComponent(componentId: number): void {
  selectedComponentIds.value = selectedComponentIds.value.filter(id => id !== componentId)
}

/**
 * 判断组件是否已选择。
 * @param componentId 组件 ID
 */
function isSelected(componentId: number): boolean {
  return selectedComponentIdSet.value.has(componentId)
}

/**
 * 保存当前建议组件选择。
 */
async function saveSelection(): Promise<void> {
  if (!props.targetId) {
    return
  }
  saving.value = true
  try {
    const response = await props.updateSuggestedComponents(props.targetId, selectedComponentIds.value)
    savedComponents.value = response.items
    selectedComponentIds.value = response.items.map(component => component.id)
    emit('saved', response.items)
    handleVisibleChange(false)
    Message.success(props.successMessage)
  } catch (error) {
    Message.error(getErrorMessage(error, props.saveErrorMessage))
  } finally {
    saving.value = false
  }
}

/**
 * 转换完整组件为弹窗内部摘要。
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
