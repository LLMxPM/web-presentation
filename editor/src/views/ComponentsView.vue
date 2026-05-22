<!-- 文件功能：提供工作空间级组件库页面，左侧浏览组件库，右侧承载组件预览、编辑与 Runtime Kit 预览工作台。 -->
<template>
  <div data-testid="components-view" class="flex h-full min-h-0 flex-col gap-4">
    <PageTitleBar class="shrink-0" :title="workspaceTitle">
      <template #actions>
        <BaseButton
          variant="ghost"
          :disabled="!workspaceId || importValidatePending || importPackagePending"
          @click="openImportFilePicker"
        >
          <Upload class="h-3.5 w-3.5" />
          导入组件
        </BaseButton>
        <BaseButton :disabled="!workspaceId" @click="handleCreateWorkspaceComponent">
          <Plus class="h-3.5 w-3.5" />
          新建组件
        </BaseButton>
      </template>
    </PageTitleBar>
    <input
      ref="importFileInputRef"
      class="hidden"
      type="file"
      accept=".zip,application/zip"
      @change="handleImportFileSelected"
    />

    <div class="grid min-h-0 flex-1 grid-cols-[430px_minmax(0,1fr)] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <ComponentLibraryPanel
        v-model="componentPanelVisible"
        :workspace-id="workspaceId"
        :closable="false"
        :selected-component-id="selectedComponent?.id ?? null"
        v-model:batch-selected-component-ids="batchSelectedComponentIds"
        :export-package-pending="exportPackagePending"
        :import-package-pending="importValidatePending || importPackagePending"
        :show-create-import-actions="false"
        :selected-runtime-kit-name="selectedRuntimeKitItem?.name ?? null"
        :refresh-key="componentListRefreshKey"
        @workspace-component-selected="handleWorkspaceComponentSelected"
        @create-workspace-component="handleCreateWorkspaceComponent"
        @export-workspace-components="handleExportSelectedComponents"
        @import-workspace-components="openImportFilePicker"
        @runtime-kit-preview-selected="handleRuntimeKitPreviewSelected"
        @runtime-kit-doc-selected="handleRuntimeKitDocSelected"
        @refresh-requested="refreshComponentList"
      />

      <main class="min-w-0 overflow-hidden border-l border-slate-200 bg-slate-50/70 p-5">
        <WorkspaceComponentWorkbench
          v-if="activeWorkbench === 'workspace'"
          :workspace-id="workspaceId"
          :component="selectedComponent"
          :create-token="createComponentToken"
          simplified-preview
          @component-saved="handleWorkspaceComponentSaved"
          @component-published="handleWorkspaceComponentSaved"
          @request-list-refresh="refreshComponentList"
        />

        <ComponentPreviewWorkbench
          v-else-if="activeWorkbench === 'runtime-kit'"
          :source="runtimeKitPreviewSource"
          :refresh-key="runtimeKitPreviewRefreshKey"
          :title="selectedRuntimeKitItem?.display_name || 'Runtime Kit 组件预览'"
          :subtitle="selectedRuntimeKitItem?.import_path || ''"
          simplified
          class="h-full rounded-2xl border border-slate-200 bg-white shadow-sm"
        />

        <section v-else class="flex h-full items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white px-8 text-center">
          <div class="max-w-sm">
            <p class="text-sm font-bold text-slate-600">请选择左侧组件</p>
            <p class="mt-2 text-xs leading-6 text-slate-400">
              工作空间组件会在右侧打开预览和编辑，Runtime Kit 可预览能力也会在这里展示。
            </p>
          </div>
        </section>
      </main>
    </div>

    <RuntimeKitCapabilityDocDialog
      v-model="runtimeKitDocDialogVisible"
      :item="runtimeKitDocItem"
    />

    <BaseDialog v-model="importDialogVisible" title="导入组件" width="720px">
      <div class="space-y-4">
        <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p class="text-sm font-bold text-slate-700">{{ importFile?.name || '未选择文件' }}</p>
          <p v-if="importValidation" class="mt-1 text-xs text-slate-500">
            组件 {{ importValidation.components.length }} 个，资源 {{ importValidation.assets.length }} 个，字体 {{ importValidation.fonts.length }} 个
          </p>
        </div>

        <div v-if="importValidation?.errors.length" class="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3">
          <p class="mb-2 text-sm font-bold text-rose-700">预检未通过</p>
          <ul class="space-y-1 text-xs leading-5 text-rose-700">
            <li v-for="error in importValidation.errors" :key="error">{{ error }}</li>
          </ul>
        </div>

        <div v-if="importValidation && importValidation.valid" class="space-y-3">
          <section class="rounded-xl border border-slate-200 bg-white p-4">
            <h4 class="text-sm font-bold text-slate-700">组件</h4>
            <div class="mt-2 max-h-40 space-y-2 overflow-y-auto">
              <div v-for="component in importValidation.components" :key="`${component.source_component_code}-${component.source_version_no}`" class="flex items-center justify-between gap-3 text-xs">
                <span class="font-semibold text-slate-700">{{ component.name }}</span>
                <span class="font-mono text-slate-400">{{ component.import_name }}</span>
              </div>
            </div>
          </section>

          <section class="grid gap-3 lg:grid-cols-2">
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">资源</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-slate-500">
                <p v-if="importValidation.assets.length === 0">无资源</p>
                <p v-for="asset in importValidation.assets" :key="asset.name">
                  {{ asset.name }} · {{ resolveImportActionText(asset.action) }}
                </p>
              </div>
            </div>
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">字体</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-slate-500">
                <p v-if="importValidation.fonts.length === 0">无字体</p>
                <p v-for="font in importValidation.fonts" :key="font.asset_name">
                  {{ font.asset_name }} · {{ resolveImportActionText(font.action) }}
                </p>
              </div>
            </div>
          </section>
        </div>
      </div>

      <template #footer>
        <BaseButton variant="ghost" @click="closeImportDialog">取消</BaseButton>
        <BaseButton
          variant="primary"
          :disabled="!importValidation?.valid || !importFile"
          :loading="importPackagePending"
          @click="handleConfirmImportPackage"
        >
          确认导入
        </BaseButton>
      </template>
    </BaseDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { Plus, Upload } from 'lucide-vue-next'

import {
  exportComponentPackage,
  getComponent,
  getWorkspace,
  importComponentPackage,
  validateComponentPackageImport,
} from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import ComponentPreviewWorkbench from '@/components/component-preview/ComponentPreviewWorkbench.vue'
import type { ComponentPreviewWorkbenchSource } from '@/components/component-preview/component-preview-workbench'
import RuntimeKitCapabilityDocDialog from '@/components/component-preview/RuntimeKitCapabilityDocDialog.vue'
import WorkspaceComponentWorkbench from '@/components/component-preview/WorkspaceComponentWorkbench.vue'
import PageTitleBar from '@/components/layout/PageTitleBar.vue'
import ComponentLibraryPanel from '@/components/project/ComponentLibraryPanel.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import { componentAgentContextKey } from '@/composables/component-agent-context'
import type {
  ComponentShareImportValidationResult,
  RuntimeKitComponentCapabilityItem,
  WorkspaceComponentItem,
} from '@/types/api'
import { Message } from '@/utils/message'

type ActiveWorkbench = 'empty' | 'workspace' | 'runtime-kit'

interface AgentComponentMutationDetail {
  workspaceId?: number | null
  projectId?: number | null
  pageId?: number | null
  componentId?: number | null
  toolName?: string
  result?: unknown
}

const route = useRoute()
const router = useRouter()

const componentPanelVisible = ref(true)
const selectedComponent = ref<WorkspaceComponentItem | null>(null)
const selectedRuntimeKitItem = ref<RuntimeKitComponentCapabilityItem | null>(null)
const runtimeKitDocItem = ref<RuntimeKitComponentCapabilityItem | null>(null)
const runtimeKitDocDialogVisible = ref(false)
const activeWorkbench = ref<ActiveWorkbench>('empty')
const componentListRefreshKey = ref(0)
const createComponentToken = ref(0)
const runtimeKitPreviewRefreshKey = ref(0)
const batchSelectedComponentIds = ref<number[]>([])
const exportPackagePending = ref(false)
const importValidatePending = ref(false)
const importPackagePending = ref(false)
const importDialogVisible = ref(false)
const importFileInputRef = ref<HTMLInputElement | null>(null)
const importFile = ref<File | null>(null)
const importValidation = ref<ComponentShareImportValidationResult | null>(null)
const componentAgentContext = inject(componentAgentContextKey, null)
const workspaceId = computed(() => Number.parseInt(route.params.workspaceId as string, 10))

componentAgentContext?.setSelectedComponent(null)

const workspaceQuery = useQuery(
  computed(() => ({
    queryKey: ['workspace', workspaceId.value],
    queryFn: () => getWorkspace(workspaceId.value),
    enabled: Number.isFinite(workspaceId.value),
  })),
)

const workspaceTitle = computed(() => {
  const workspaceName = workspaceQuery.data.value?.name
  return workspaceName ? `${workspaceName} · 组件库` : '组件库'
})
const runtimeKitPreviewSource = computed<ComponentPreviewWorkbenchSource | null>(() => {
  if (!selectedRuntimeKitItem.value) {
    return null
  }
  return {
    kind: 'runtime-kit',
    workspaceId: workspaceId.value,
    item: selectedRuntimeKitItem.value,
  }
})

/**
 * 选择工作空间组件，右侧默认进入组件预览并同步智能体组件上下文。
 * @param component 当前组件；为空时清空右侧工作台
 */
function handleWorkspaceComponentSelected(
  component: WorkspaceComponentItem | null,
  options: { syncRoute?: boolean } = {},
): void {
  selectedComponent.value = component
  selectedRuntimeKitItem.value = null
  activeWorkbench.value = component ? 'workspace' : 'empty'
  componentAgentContext?.setSelectedComponent(component)
  if (options.syncRoute !== false) {
    replaceComponentQuery(component?.id ?? null)
  }
}

/**
 * 新建组件时清空选择并让右侧工作台进入创建模式。
 */
function handleCreateWorkspaceComponent(): void {
  selectedComponent.value = null
  selectedRuntimeKitItem.value = null
  activeWorkbench.value = 'workspace'
  createComponentToken.value += 1
  componentAgentContext?.setSelectedComponent(null)
  replaceComponentQuery(null)
}

/**
 * 选择 Runtime Kit 可预览能力，右侧进入只读预览并清空组件智能体上下文。
 * @param item Runtime Kit 能力条目
 */
function handleRuntimeKitPreviewSelected(item: RuntimeKitComponentCapabilityItem): void {
  selectedComponent.value = null
  selectedRuntimeKitItem.value = item
  activeWorkbench.value = 'runtime-kit'
  runtimeKitPreviewRefreshKey.value += 1
  componentAgentContext?.setSelectedComponent(null)
  replaceComponentQuery(null)
}

/**
 * 打开 Runtime Kit doc-only 能力说明弹窗。
 * @param item Runtime Kit 能力条目
 */
function handleRuntimeKitDocSelected(item: RuntimeKitComponentCapabilityItem): void {
  runtimeKitDocItem.value = item
  runtimeKitDocDialogVisible.value = true
}

/**
 * 组件保存或发布后同步父层选中项，保持智能体上下文和右侧标题为最新状态。
 * @param component 最新组件
 */
function handleWorkspaceComponentSaved(component: WorkspaceComponentItem): void {
  selectedComponent.value = component
  selectedRuntimeKitItem.value = null
  activeWorkbench.value = 'workspace'
  componentAgentContext?.setSelectedComponent(component)
  replaceComponentQuery(component.id)
  refreshComponentList()
}

/**
 * 触发左侧组件列表重新加载。
 */
function refreshComponentList(): void {
  componentListRefreshKey.value += 1
}

/**
 * 下载当前选中组件的离线分享包。
 */
async function handleExportSelectedComponents(): Promise<void> {
  if (batchSelectedComponentIds.value.length === 0 || !workspaceId.value) {
    return
  }
  exportPackagePending.value = true
  try {
    const { blob, filename } = await exportComponentPackage({
      workspace_id: workspaceId.value,
      component_ids: batchSelectedComponentIds.value,
    })
    downloadBlob(blob, filename)
    Message.success('组件分享包已生成。')
  } catch (error) {
    Message.error(`导出组件失败：${getErrorMessage(error, '未知原因')}`)
  } finally {
    exportPackagePending.value = false
  }
}

/**
 * 打开本地 Zip 文件选择器。
 */
function openImportFilePicker(): void {
  importFileInputRef.value?.click()
}

/**
 * 选择 Zip 后立即发起预检，并打开导入弹窗展示结果。
 */
async function handleImportFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  if (!file || !workspaceId.value) {
    return
  }
  importFile.value = file
  importValidation.value = null
  importDialogVisible.value = true
  importValidatePending.value = true
  try {
    importValidation.value = await validateComponentPackageImport(workspaceId.value, file)
  } catch (error) {
    Message.error(getErrorMessage(error, '组件分享包预检失败'))
    importDialogVisible.value = false
  } finally {
    importValidatePending.value = false
  }
}

/**
 * 确认导入预检通过的组件分享包。
 */
async function handleConfirmImportPackage(): Promise<void> {
  if (!importFile.value || !workspaceId.value || !importValidation.value?.valid) {
    return
  }
  importPackagePending.value = true
  try {
    const result = await importComponentPackage(workspaceId.value, importFile.value)
    Message.success(`已导入 ${result.imported_components.length} 个组件。`)
    closeImportDialog()
    refreshComponentList()
    if (result.imported_components[0]) {
      handleWorkspaceComponentSelected(result.imported_components[0])
    }
  } catch (error) {
    Message.error(getErrorMessage(error, '导入组件分享包失败'))
  } finally {
    importPackagePending.value = false
  }
}

/**
 * 关闭导入弹窗并清理临时文件状态。
 */
function closeImportDialog(): void {
  importDialogVisible.value = false
  importFile.value = null
  importValidation.value = null
}

/**
 * 把 Blob 保存为浏览器下载文件。
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/**
 * 展示导入预检中的资源和字体处理动作。
 */
function resolveImportActionText(action: string): string {
  return action === 'reuse' ? '复用' : '新增'
}

/**
 * 接收智能体组件写入事件，刷新列表并同步右侧工作台选中项。
 */
function handleGlobalAgentComponentUpdated(event: Event): void {
  const detail = (event as CustomEvent<AgentComponentMutationDetail>).detail
  if (detail?.workspaceId && detail.workspaceId !== workspaceId.value) return
  void refreshComponentAfterAgentMutation(detail)
}

/**
 * 根据工具写入结果刷新组件状态；删除当前组件时清空右侧工作台。
 * @param detail 智能体工具写回事件详情
 */
async function refreshComponentAfterAgentMutation(detail?: AgentComponentMutationDetail): Promise<void> {
  refreshComponentList()
  const componentId = resolveComponentIdFromDetail(detail)
  if (detail?.toolName === 'delete_component') {
    if (!componentId || selectedComponent.value?.id === componentId) {
      handleWorkspaceComponentSelected(null)
    }
    return
  }

  const component = resolveComponentFromDetail(detail) ?? (await fetchComponentFromDetail(componentId))
  if (!component) {
    return
  }
  handleWorkspaceComponentSelected(component)
}

/**
 * 优先使用工具结果携带的最新组件对象，减少一次网络请求。
 */
function resolveComponentFromDetail(detail: AgentComponentMutationDetail | undefined): WorkspaceComponentItem | null {
  const resultRecord = normalizeMutationResultRecord(detail?.result)
  const component = resultRecord && isRecord(resultRecord.component) ? resultRecord.component : null
  return isWorkspaceComponentItem(component) ? component : null
}

/**
 * 从事件 detail 或工具结果中提取组件 ID。
 */
function resolveComponentIdFromDetail(detail: AgentComponentMutationDetail | undefined): number | null {
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
 * 工具结果未携带完整组件时，从后端读取最新组件详情。
 */
async function fetchComponentFromDetail(componentId: number | null): Promise<WorkspaceComponentItem | null> {
  if (!componentId) {
    return null
  }
  try {
    return await getComponent(componentId)
  } catch (error) {
    console.warn('Failed to refresh component after agent mutation', error)
    return null
  }
}

/**
 * 根据 URL 中的 componentId 恢复右侧组件工作台选中态。
 */
async function syncSelectedComponentFromRoute(): Promise<void> {
  const componentId = resolveComponentIdFromRoute()
  if (!componentId) {
    if (selectedComponent.value) {
      handleWorkspaceComponentSelected(null, { syncRoute: false })
    }
    return
  }

  if (selectedComponent.value?.id === componentId) {
    return
  }

  const component = await fetchComponentFromDetail(componentId)
  if (!component || component.workspace_id !== workspaceId.value) {
    return
  }
  handleWorkspaceComponentSelected(component, { syncRoute: false })
}

/**
 * 从当前路由 query 中读取待打开组件 ID。
 */
function resolveComponentIdFromRoute(): number | null {
  const rawComponentId = route.query.componentId
  const candidate = Array.isArray(rawComponentId) ? rawComponentId[0] : rawComponentId
  return normalizePositiveNumber(candidate)
}

/**
 * 用 replace 同步组件选中态，避免列表点击污染浏览器历史。
 */
function replaceComponentQuery(componentId: number | null): void {
  if (resolveComponentIdFromRoute() === componentId) {
    return
  }
  const nextQuery = { ...route.query }
  if (componentId) {
    nextQuery.componentId = String(componentId)
  } else {
    delete nextQuery.componentId
  }
  void router.replace({ path: route.path, query: nextQuery })
}

/**
 * 工具结果可能是 JSON 字符串或对象，这里归一成对象后再读取字段。
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
 * 判断未知值是否为组件列表项所需的最小结构。
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

onMounted(() => {
  window.addEventListener('agent:component-updated', handleGlobalAgentComponentUpdated)
})

watch(
  () => [workspaceId.value, route.query.componentId] as const,
  () => {
    void syncSelectedComponentFromRoute()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  window.removeEventListener('agent:component-updated', handleGlobalAgentComponentUpdated)
  componentAgentContext?.setSelectedComponent(null)
})
</script>
