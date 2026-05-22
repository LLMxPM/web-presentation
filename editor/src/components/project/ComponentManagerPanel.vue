<!-- 文件功能：提供全局组件库只读侧边栏，并复用 components 页面预览工作台展示组件预览。 -->
<template>
  <ComponentLibraryPanel
    :model-value="modelValue"
    :workspace-id="workspaceId"
    :read-only="true"
    :closable="closable"
    :selected-component-id="selectedComponent?.id ?? null"
    :selected-runtime-kit-name="selectedRuntimeKitItem?.name ?? null"
    :refresh-key="componentListRefreshKey"
    @update:model-value="emit('update:modelValue', $event)"
    @workspace-component-selected="handleWorkspaceComponentSelected"
    @runtime-kit-preview-selected="handleRuntimeKitPreviewSelected"
    @runtime-kit-doc-selected="handleRuntimeKitDocSelected"
  />

  <ComponentPreviewDialog v-model="previewDialogVisible" width="1520px">
    <ComponentPreviewWorkbench
      :source="previewSource"
      :refresh-key="previewRefreshKey"
      :title="previewTitle"
      :subtitle="previewSubtitle"
      class="h-full"
    >
      <template #actions>
        <BaseButton variant="ghost" size="sm" aria-label="关闭组件预览" @click="closePreviewDialog">
          <X class="h-3.5 w-3.5" />
          关闭
        </BaseButton>
      </template>
    </ComponentPreviewWorkbench>
  </ComponentPreviewDialog>

  <RuntimeKitCapabilityDocDialog
    v-model="runtimeKitDocDialogVisible"
    :item="runtimeKitDocItem"
  />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

import { getComponent } from '@/api/catalog'
import ComponentPreviewDialog from '@/components/component-preview/ComponentPreviewDialog.vue'
import ComponentPreviewWorkbench from '@/components/component-preview/ComponentPreviewWorkbench.vue'
import type { ComponentPreviewWorkbenchSource } from '@/components/component-preview/component-preview-workbench'
import RuntimeKitCapabilityDocDialog from '@/components/component-preview/RuntimeKitCapabilityDocDialog.vue'
import ComponentLibraryPanel from '@/components/project/ComponentLibraryPanel.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import type { RuntimeKitComponentCapabilityItem, WorkspaceComponentItem } from '@/types/api'

const props = withDefaults(defineProps<{
  modelValue: boolean
  workspaceId: number | null
  readOnly?: boolean
  closable?: boolean
}>(), {
  readOnly: true,
  closable: true,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'component-selected', value: WorkspaceComponentItem | null): void
}>()

const selectedComponent = ref<WorkspaceComponentItem | null>(null)
const selectedRuntimeKitItem = ref<RuntimeKitComponentCapabilityItem | null>(null)
const runtimeKitDocItem = ref<RuntimeKitComponentCapabilityItem | null>(null)
const previewDialogVisible = ref(false)
const runtimeKitDocDialogVisible = ref(false)
const previewRefreshKey = ref(0)
const componentListRefreshKey = ref(0)

interface AgentComponentMutationDetail {
  workspaceId?: number | null
  componentId?: number | null
  toolName?: string
  result?: unknown
}

const previewSource = computed<ComponentPreviewWorkbenchSource | null>(() => {
  if (selectedComponent.value) {
    return {
      kind: 'workspace-draft',
      workspaceId: selectedComponent.value.workspace_id ?? props.workspaceId,
      componentId: selectedComponent.value.id,
      componentName: selectedComponent.value.name,
      content: selectedComponent.value.content,
      previewSchema: selectedComponent.value.preview_schema,
      isDraftPreview: selectedComponent.value.current_version_no <= 0 || selectedComponent.value.has_unpublished_changes,
      componentType: selectedComponent.value.component_type,
    }
  }

  if (selectedRuntimeKitItem.value) {
    return {
      kind: 'runtime-kit',
      workspaceId: props.workspaceId,
      item: selectedRuntimeKitItem.value,
    }
  }

  return null
})

const previewTitle = computed(() => {
  if (selectedComponent.value) {
    return selectedComponent.value.name
  }
  return selectedRuntimeKitItem.value?.display_name || '组件预览'
})
const previewSubtitle = computed(() => {
  if (selectedComponent.value) {
    return resolveWorkspaceComponentSubtitle(selectedComponent.value)
  }
  return selectedRuntimeKitItem.value?.import_path || ''
})

watch(
  () => [props.modelValue, props.workspaceId],
  ([visible], previousValue) => {
    const workspaceChanged = Boolean(previousValue && props.workspaceId !== previousValue[1])
    if (!visible || workspaceChanged) {
      clearSelection()
    }
  },
)

/**
 * 选择工作空间组件并打开只读预览弹窗。
 * @param component 组件列表当前选择项
 */
function handleWorkspaceComponentSelected(component: WorkspaceComponentItem | null): void {
  selectedComponent.value = component
  selectedRuntimeKitItem.value = null
  runtimeKitDocDialogVisible.value = false
  emit('component-selected', component)
  if (!component) {
    closePreviewDialog()
    return
  }
  previewRefreshKey.value += 1
  previewDialogVisible.value = true
}

/**
 * 智能体修改组件库时，刷新侧边栏列表并同步当前预览组件。
 */
function handleGlobalAgentComponentUpdated(event: Event): void {
  const detail = (event as CustomEvent<AgentComponentMutationDetail>).detail
  if (detail?.workspaceId && detail.workspaceId !== props.workspaceId) return
  if (props.modelValue) {
    componentListRefreshKey.value += 1
  }
  void refreshSelectedComponentAfterAgentMutation(detail)
}

/**
 * 组件被修改或删除时同步当前选中项，避免预览继续展示旧草稿。
 */
async function refreshSelectedComponentAfterAgentMutation(detail?: AgentComponentMutationDetail): Promise<void> {
  const currentComponent = selectedComponent.value
  if (!currentComponent) {
    return
  }
  const componentId = resolveComponentIdFromDetail(detail)
  if (componentId && componentId !== currentComponent.id) {
    return
  }
  if (detail?.toolName === 'delete_component') {
    clearSelection()
    return
  }
  const updatedComponent = resolveComponentFromDetail(detail) ?? await fetchComponent(componentId ?? currentComponent.id)
  if (!updatedComponent) {
    return
  }
  selectedComponent.value = updatedComponent
  emit('component-selected', updatedComponent)
  previewRefreshKey.value += 1
}

/**
 * 选择 Runtime Kit 可预览能力并打开同一个预览弹窗。
 * @param item Runtime Kit 能力条目
 */
function handleRuntimeKitPreviewSelected(item: RuntimeKitComponentCapabilityItem): void {
  selectedComponent.value = null
  selectedRuntimeKitItem.value = item
  runtimeKitDocDialogVisible.value = false
  emit('component-selected', null)
  previewRefreshKey.value += 1
  previewDialogVisible.value = true
}

/**
 * 打开 Runtime Kit doc-only 能力说明弹窗，不创建 iframe 预览。
 * @param item Runtime Kit 能力条目
 */
function handleRuntimeKitDocSelected(item: RuntimeKitComponentCapabilityItem): void {
  selectedComponent.value = null
  selectedRuntimeKitItem.value = null
  previewDialogVisible.value = false
  runtimeKitDocItem.value = item
  runtimeKitDocDialogVisible.value = true
  emit('component-selected', null)
}

/**
 * 关闭预览弹窗但保留列表选择，方便用户重新刷新同一项预览。
 */
function closePreviewDialog(): void {
  previewDialogVisible.value = false
}

/**
 * 清理侧边栏选择与弹窗状态。
 */
function clearSelection(): void {
  selectedComponent.value = null
  selectedRuntimeKitItem.value = null
  runtimeKitDocItem.value = null
  previewDialogVisible.value = false
  runtimeKitDocDialogVisible.value = false
  emit('component-selected', null)
}

/**
 * 优先使用工具结果里的完整组件对象。
 */
function resolveComponentFromDetail(detail?: AgentComponentMutationDetail): WorkspaceComponentItem | null {
  const resultRecord = normalizeMutationResultRecord(detail?.result)
  const component = resultRecord && isRecord(resultRecord.component) ? resultRecord.component : null
  return isWorkspaceComponentItem(component) ? component : null
}

/**
 * 从事件详情或工具结果中提取组件 ID。
 */
function resolveComponentIdFromDetail(detail?: AgentComponentMutationDetail): number | null {
  const detailId = normalizePositiveNumber(detail?.componentId)
  if (detailId !== null) {
    return detailId
  }
  const resultRecord = normalizeMutationResultRecord(detail?.result)
  const directId = normalizePositiveNumber(resultRecord?.component_id)
  if (directId !== null) {
    return directId
  }
  const component = resultRecord && isRecord(resultRecord.component) ? resultRecord.component : null
  return normalizePositiveNumber(component?.id)
}

/**
 * 工具结果缺少完整组件时，从后端读取详情。
 */
async function fetchComponent(componentId: number): Promise<WorkspaceComponentItem | null> {
  try {
    return await getComponent(componentId)
  } catch (error) {
    console.warn('Failed to refresh selected component after agent mutation', error)
    return null
  }
}

/**
 * 工具结果可能是对象或 JSON 字符串，这里归一成普通对象。
 */
function normalizeMutationResultRecord(result: unknown): Record<string, unknown> | null {
  if (typeof result === 'string') {
    const trimmed = result.trim()
    if (!trimmed.startsWith('{')) {
      return null
    }
    try {
      const parsed = JSON.parse(trimmed) as unknown
      return isRecord(parsed) ? parsed : null
    } catch {
      return null
    }
  }
  return isRecord(result) ? result : null
}

/**
 * 粗略校验工具结果中的组件对象是否可直接进入预览。
 */
function isWorkspaceComponentItem(value: unknown): value is WorkspaceComponentItem {
  return isRecord(value)
    && normalizePositiveNumber(value.id) !== null
    && normalizePositiveNumber(value.workspace_id) !== null
    && typeof value.name === 'string'
    && typeof value.import_name === 'string'
    && typeof value.content === 'string'
}

function normalizePositiveNumber(value: unknown): number | null {
  const normalized = Number(value)
  return Number.isFinite(normalized) && normalized > 0 ? normalized : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 生成工作空间组件预览副标题，帮助识别当前预览版本状态。
 * @param component 工作空间组件
 */
function resolveWorkspaceComponentSubtitle(component: WorkspaceComponentItem): string {
  const versionLabel = component.current_version_no <= 0
    ? '未发布'
    : component.has_unpublished_changes
      ? `v${component.current_version_no} + 草稿`
      : `v${component.current_version_no} 已发布`
  return `${component.code} · ${versionLabel}`
}

onMounted(() => {
  window.addEventListener('agent:component-updated', handleGlobalAgentComponentUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('agent:component-updated', handleGlobalAgentComponentUpdated)
})
</script>
