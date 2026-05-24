<!-- 文件功能：承载工作空间组件右侧工作台，负责预览/编辑/新建状态切换、草稿保存、发布和版本历史。 -->
<template>
  <section class="h-full min-h-0 overflow-hidden bg-white">
    <div v-if="activeMode === 'empty' || activeMode === 'create'" class="flex h-full items-center justify-center bg-slate-50/70 p-6">
      <div class="max-w-sm rounded-xl border border-dashed border-slate-200 bg-white px-7 py-8 text-center">
        <Layers class="mx-auto mb-3 h-10 w-10 text-slate-300" />
        <p class="text-sm font-bold text-slate-600">{{ activeMode === 'create' ? '正在新建组件草稿' : '请选择组件' }}</p>
        <p class="mt-2 text-xs leading-6 text-slate-400">
          {{ activeMode === 'create' ? '请在弹窗中完成基础信息、预览配置和源码编辑。' : '点击左侧工作空间组件后会在这里打开预览，也可以新建组件草稿。' }}
        </p>
      </div>
    </div>

    <ComponentPreviewWorkbench
      v-else
      ref="previewWorkbenchRef"
      :source="previewSource"
      :refresh-key="previewRefreshKey"
      :title="previewTitle"
      :simplified="simplifiedPreview"
      @preview-refreshed="previewLoading = false"
    >
      <template #title>
        <div class="component-preview-title-inline flex min-w-0 items-center gap-2 overflow-hidden">
          <h3 class="min-w-[6rem] flex-1 truncate text-sm font-bold text-slate-900">{{ previewTitle }}</h3>
          <span v-if="currentComponent?.code" class="component-preview-title-code max-w-[7.5rem] shrink truncate rounded-full bg-white px-2 py-0.5 text-[10px] font-mono font-bold text-slate-500 ring-1 ring-slate-200">
            {{ currentComponent.code }}
          </span>
          <span v-if="currentVersionLabel" class="shrink-0 rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-black text-indigo-600">
            {{ currentVersionLabel }}
          </span>
        </div>
      </template>

      <template #component-actions="slotProps">
        <BaseButton v-if="currentComponent" variant="ghost" size="sm" @click="openVersionHistoryFromPreview(slotProps?.closeFullPreview)">
          <History class="h-3.5 w-3.5" />
          发布历史
        </BaseButton>
        <BaseButton
          v-if="currentComponent && !slotProps?.insideFullPreview"
          variant="ghost"
          size="sm"
          :disabled="currentComponent.current_version_no <= 0"
          title="查看引用页面和引用组件"
          @click="openReferenceFromPreview(slotProps?.closeFullPreview)"
        >
          <Link2 class="h-3.5 w-3.5" />
          引用
        </BaseButton>
        <BaseButton variant="secondary" size="sm" @click="switchToEditModeFromPreview(slotProps?.closeFullPreview)">
          编辑组件
        </BaseButton>
        <BaseButton
          v-if="currentComponent"
          variant="primary"
          size="sm"
          :disabled="!canPublish"
          @click="openReleaseFromPreview(slotProps?.closeFullPreview)"
        >
          <Rocket class="h-3.5 w-3.5" />
          发布
        </BaseButton>
      </template>
    </ComponentPreviewWorkbench>

    <ComponentPreviewDialog
      :model-value="editorDialogVisible"
      width="1600px"
      close-label="关闭组件编辑"
      @update:model-value="handleEditorDialogVisibleChange"
    >
      <ComponentEditorPane
        :form="draft.form"
        :errors="draft.errors"
        :mode="activeMode === 'create' ? 'create' : 'edit'"
        :editor-theme="editorTheme"
        :saving="saving"
        :preview-loading="previewLoading"
        :can-publish="canPublish"
        :can-view-history="Boolean(currentComponent)"
        class="h-full"
        @update:form="draft.replaceForm"
        @update:editor-theme="editorTheme = $event"
        @preview-draft="handlePreviewDraft"
        @save-draft="handleSaveDraft"
        @publish="openReleaseDialog"
        @cancel-edit="handleCancelEdit"
        @open-version-history="openVersionHistoryDialog"
        @open-schema-help="showSchemaHelp = true"
      />
    </ComponentPreviewDialog>

    <ComponentVersionHistoryDialog
      v-model="versionHistoryVisible"
      :loading="versionHistoryLoading"
      :versions="componentVersions"
      :panel="versionHistoryPanel"
      :panel-title="versionHistoryPanelTitle"
      :panel-subtitle="versionHistoryPanelSubtitle"
      :draft-content="draft.form.content"
      :version-content-map="versionContentMap"
      :preview-frame-url="versionPreviewFrameUrl"
      :editor-theme="editorTheme"
      :previewing-version-no="previewingVersionNo"
      :loading-content-version-no="loadingContentVersionNo"
      :restoring-version-no="restoringVersionNo"
      @preview-version="toggleVersionPreview"
      @diff-version="toggleVersionDiff"
      @restore-version="restoreVersionToDraft"
    />

    <ComponentReferenceDialog
      v-model="referenceDialogVisible"
      :component="currentComponent"
      :references="componentReferences"
      :loading="referenceLoading"
      :upgrading="referenceUpgrading"
      @refresh="refreshComponentReferences"
      @upgrade="handleUpgradeComponentReferences"
    />

    <ComponentReleaseDialog
      v-model="releaseDialogVisible"
      v-model:release-name="releaseDraftName"
      v-model:change-note="releaseDraftNote"
      :loading="publishing"
      @submit="submitReleaseDialog"
    />

    <BaseDialog v-model="showSchemaHelp" title="Preview Schema 配置指南" width="760px">
      <div class="space-y-4 text-sm leading-7 text-slate-600">
        <p>
          <code class="font-bold text-indigo-600">previewSchema</code>
          用于声明预览时可调的 props、slots、mocks 与 presets，必须是 JSON 对象。
        </p>
        <pre class="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700"><code>{
  "props": {
    "title": { "type": "string", "label": "标题", "default": "示例标题" }
  },
  "presets": [
    { "key": "default", "label": "默认", "props": { "title": "示例标题" } }
  ]
}</code></pre>
      </div>
    </BaseDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { History, Layers, Link2, Rocket } from '@lucide/vue'

import {
  getComponentVersionContent,
  getComponentReferences,
  listComponentVersions,
  publishComponent,
  restoreComponentVersionToDraft,
  upgradeComponentReferences,
} from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import { createComponentVersionPreviewArtifact } from '@/api/preview'
import ComponentEditorPane from '@/components/component-preview/ComponentEditorPane.vue'
import ComponentPreviewDialog from '@/components/component-preview/ComponentPreviewDialog.vue'
import ComponentPreviewWorkbench from '@/components/component-preview/ComponentPreviewWorkbench.vue'
import ComponentReferenceDialog from '@/components/component-preview/ComponentReferenceDialog.vue'
import type { ComponentPreviewWorkbenchSource } from '@/components/component-preview/component-preview-workbench'
import ComponentReleaseDialog from '@/components/component-preview/ComponentReleaseDialog.vue'
import ComponentVersionHistoryDialog from '@/components/component-preview/ComponentVersionHistoryDialog.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import { useWorkspaceComponentDraft } from '@/composables/useWorkspaceComponentDraft'
import type {
  PreviewArtifactResponse,
  WorkspaceComponentItem,
  WorkspaceComponentReferenceUpgradePayload,
  WorkspaceComponentReferenceUpgradeResponse,
  WorkspaceComponentReferences,
  WorkspaceComponentVersionContent,
  WorkspaceComponentVersionListItem,
} from '@/types/api'
import type { EditorThemeMode } from '@/types/monaco'
import { getDefaultEditorTheme } from '@/utils/monaco'
import { createConfirm, Message } from '@/utils/message'

type WorkbenchMode = 'empty' | 'preview' | 'edit' | 'create'
type CloseFullPreviewHandler = (() => void) | undefined

const props = defineProps<{
  workspaceId: number | null
  component: WorkspaceComponentItem | null
  createToken: number
  simplifiedPreview?: boolean
}>()

const emit = defineEmits<{
  'component-saved': [component: WorkspaceComponentItem]
  'component-published': [component: WorkspaceComponentItem]
  'request-list-refresh': []
}>()

const draft = useWorkspaceComponentDraft({ workspaceId: () => props.workspaceId })
const activeMode = ref<WorkbenchMode>('empty')
const editorTheme = ref<EditorThemeMode>(getDefaultEditorTheme())
const saving = ref(false)
const publishing = ref(false)
const previewLoading = ref(false)
const previewRefreshKey = ref(0)
const previewWorkbenchRef = ref<InstanceType<typeof ComponentPreviewWorkbench> | null>(null)
const editorDialogVisible = ref(false)
const showSchemaHelp = ref(false)
const releaseDialogVisible = ref(false)
const releaseDraftName = ref('')
const releaseDraftNote = ref('')
const versionHistoryVisible = ref(false)
const versionHistoryLoading = ref(false)
const componentVersions = ref<WorkspaceComponentVersionListItem[]>([])
const versionContentMap = ref<Record<number, WorkspaceComponentVersionContent>>({})
const versionPreviewMap = ref<Record<number, PreviewArtifactResponse>>({})
const versionHistoryPanel = ref<{ mode: 'diff' | 'preview'; versionNo: number } | null>(null)
const previewingVersionNo = ref<number | null>(null)
const loadingContentVersionNo = ref<number | null>(null)
const restoringVersionNo = ref<number | null>(null)
const versionPreviewRefreshToken = ref(0)
const referenceDialogVisible = ref(false)
const referenceLoading = ref(false)
const referenceUpgrading = ref(false)
const componentReferences = ref<WorkspaceComponentReferences | null>(null)

const currentComponent = computed(() => draft.currentComponent.value)
const canPublish = computed(() => Boolean(
  currentComponent.value
  && (currentComponent.value.has_unpublished_changes || draft.hasUnsavedSourceChanges.value),
))
const previewTitle = computed(() => currentComponent.value?.name || draft.form.name || '未保存组件草稿')
const currentVersionLabel = computed(() => {
  const component = currentComponent.value
  if (!component || component.current_version_no <= 0) {
    return '未发布'
  }
  return component.has_unpublished_changes
    ? `v${component.current_version_no} + 草稿`
    : `v${component.current_version_no}`
})
const previewSource = computed<ComponentPreviewWorkbenchSource | null>(() => {
  if (activeMode.value === 'empty') {
    return null
  }
  return {
    kind: 'workspace-draft',
    workspaceId: props.workspaceId,
    componentId: currentComponent.value?.id ?? null,
    componentName: draft.form.name || currentComponent.value?.name || '未保存组件草稿',
    content: draft.form.content,
    previewSchema: draft.form.preview_schema,
    isDraftPreview: !currentComponent.value || currentComponent.value.has_unpublished_changes || draft.hasUnsavedSourceChanges.value,
    componentType: draft.form.component_type,
  }
})
const activeHistoryVersion = computed(() => {
  const versionNo = versionHistoryPanel.value?.versionNo
  if (!versionNo) return null
  return componentVersions.value.find(item => item.version_no === versionNo) ?? null
})
const activeHistoryPreview = computed(() => {
  const versionNo = versionHistoryPanel.value?.versionNo
  if (!versionNo) return null
  return versionPreviewMap.value[versionNo] ?? null
})
const versionPreviewFrameUrl = computed(() => {
  const previewUrl = activeHistoryPreview.value?.preview_url
  if (!previewUrl) return ''
  try {
    const nextUrl = new URL(previewUrl)
    nextUrl.searchParams.set('t', String(versionPreviewRefreshToken.value))
    return nextUrl.toString()
  } catch {
    return previewUrl
  }
})
const versionHistoryPanelTitle = computed(() => {
  if (!versionHistoryPanel.value || !activeHistoryVersion.value) return '发布版本详情'
  return versionHistoryPanel.value.mode === 'diff'
    ? `版本差异 · v${activeHistoryVersion.value.version_no}`
    : `版本预览 · v${activeHistoryVersion.value.version_no}`
})
const versionHistoryPanelSubtitle = computed(() => {
  if (!versionHistoryPanel.value || !activeHistoryVersion.value) {
    return '在左侧选择一个发布版本查看差异或预览。'
  }
  if (versionHistoryPanel.value.mode === 'diff') {
    return '展示所选发布版本与当前草稿之间的源码差异。'
  }
  return activeHistoryVersion.value.release_name || activeHistoryVersion.value.version_label
})

watch(
  () => [
    props.component?.id ?? '',
    props.component?.updated_at ?? '',
    props.component?.current_version_no ?? '',
    props.component?.has_unpublished_changes ? 'dirty' : 'clean',
  ].join(':'),
  () => {
    if (!props.component) {
      if (activeMode.value !== 'create') {
        activeMode.value = 'empty'
      }
      resetReferenceState()
      return
    }
    draft.loadFromComponent(props.component)
    resetVersionHistoryState()
    resetReferenceState()
    activeMode.value = 'preview'
    editorDialogVisible.value = false
    previewRefreshKey.value += 1
  },
  { immediate: true },
)

watch(
  () => props.createToken,
  (createToken) => {
    if (createToken <= 0) {
      return
    }
    draft.resetForCreate()
    resetVersionHistoryState()
    resetReferenceState()
    activeMode.value = 'create'
    editorDialogVisible.value = true
  },
)

/**
 * 打开组件编辑弹窗，复用当前草稿表单。
 */
function switchToEditMode(): void {
  activeMode.value = currentComponent.value ? 'preview' : 'create'
  editorDialogVisible.value = true
}

/**
 * 从完整预览弹窗进入编辑时，先关闭完整预览，避免弹窗叠加。
 * @param closeFullPreview 预览工作台传入的完整预览关闭函数
 */
function switchToEditModeFromPreview(closeFullPreview?: CloseFullPreviewHandler): void {
  closeFullPreview?.()
  switchToEditMode()
}

/**
 * 关闭编辑弹窗。已有组件回到预览，新建草稿回到空态。
 */
function handleCancelEdit(): void {
  editorDialogVisible.value = false
  if (currentComponent.value) {
    draft.loadFromComponent(currentComponent.value)
    activeMode.value = 'preview'
    return
  }
  draft.resetForCreate()
  activeMode.value = 'empty'
}

/**
 * 处理编辑弹窗外壳关闭事件，关闭时走统一取消逻辑。
 * @param visible 弹窗是否可见
 */
function handleEditorDialogVisibleChange(visible: boolean): void {
  if (visible) {
    editorDialogVisible.value = true
    return
  }
  handleCancelEdit()
}

/**
 * 从编辑区切回右侧预览，并触发一次草稿预览刷新。
 */
async function handlePreviewDraft(): Promise<void> {
  draft.errors.content = draft.form.content.trim() ? '' : '源码不能为空'
  draft.normalizePreviewSchemaInput()
  if (draft.errors.content || draft.errors.preview_schema) {
    return
  }
  previewLoading.value = true
  activeMode.value = 'preview'
  editorDialogVisible.value = false
  previewRefreshKey.value += 1
  await nextTick()
  await previewWorkbenchRef.value?.refreshCurrentPreview()
}

/**
 * 保存当前草稿，并同步最新组件给父层和左侧列表。
 */
async function handleSaveDraft(): Promise<WorkspaceComponentItem | null> {
  saving.value = true
  const wasEditMode = Boolean(currentComponent.value)
  try {
    const savedComponent = await draft.saveDraft()
    if (!savedComponent) {
      return null
    }
    Message.success(wasEditMode ? '组件草稿已保存。' : '组件草稿已创建。发布后才能被页面或其他组件引用。')
    emit('component-saved', savedComponent)
    emit('request-list-refresh')
    activeMode.value = 'preview'
    editorDialogVisible.value = false
    previewRefreshKey.value += 1
    return savedComponent
  } catch (error) {
    Message.error(getErrorMessage(error, '保存失败'))
    return null
  } finally {
    saving.value = false
  }
}

/**
 * 打开发布确认弹窗，默认发布名指向下一版本。
 */
function openReleaseDialog(): void {
  const component = currentComponent.value
  if (!component) return
  releaseDraftName.value = component.current_version_no > 0
    ? `v${component.current_version_no + 1}`
    : 'v1'
  releaseDraftNote.value = ''
  releaseDialogVisible.value = true
}

/**
 * 提交组件发布；如果存在未保存源码，先保存草稿再发布。
 */
async function submitReleaseDialog(): Promise<void> {
  const component = currentComponent.value
  if (!component || publishing.value) return

  publishing.value = true
  try {
    if (draft.hasUnsavedSourceChanges.value) {
      publishing.value = false
      const savedComponent = await handleSaveDraft()
      publishing.value = true
      if (!savedComponent || draft.hasUnsavedSourceChanges.value) {
        Message.error('草稿保存未完成，暂不能发布。')
        return
      }
    }

    const latestComponent = currentComponent.value
    if (!latestComponent) return
    const published = await publishComponent(latestComponent.id, {
      release_name: releaseDraftName.value.trim() || null,
      change_note: releaseDraftNote.value.trim() || null,
    })
    draft.loadFromComponent(published)
    releaseDialogVisible.value = false
    releaseDraftName.value = ''
    releaseDraftNote.value = ''
    Message.success(`组件已发布为 v${published.current_version_no}。`)
    emit('component-published', published)
    emit('request-list-refresh')
    activeMode.value = 'preview'
    editorDialogVisible.value = false
    previewRefreshKey.value += 1
    await refreshVersionHistory()
  } catch (error) {
    Message.error(getErrorMessage(error, '发布组件版本失败'))
  } finally {
    publishing.value = false
  }
}

/**
 * 打开发布历史弹窗并加载版本列表。
 */
async function openVersionHistoryDialog(): Promise<void> {
  if (!currentComponent.value) return
  versionHistoryVisible.value = true
  await refreshVersionHistory()
}

/**
 * 从预览操作区打开发布历史；完整预览中触发时先关闭完整预览弹窗。
 * @param closeFullPreview 预览工作台传入的完整预览关闭函数
 */
async function openVersionHistoryFromPreview(closeFullPreview?: CloseFullPreviewHandler): Promise<void> {
  closeFullPreview?.()
  await openVersionHistoryDialog()
}

/**
 * 打开引用关系弹窗，并立即读取最新直接引用索引。
 */
async function openReferenceDialog(): Promise<void> {
  if (!currentComponent.value || currentComponent.value.current_version_no <= 0) return
  referenceDialogVisible.value = true
  await refreshComponentReferences()
}

/**
 * 从预览操作区打开引用关系；完整预览中触发时先关闭完整预览弹窗。
 * @param closeFullPreview 预览工作台传入的完整预览关闭函数
 */
async function openReferenceFromPreview(closeFullPreview?: CloseFullPreviewHandler): Promise<void> {
  closeFullPreview?.()
  await openReferenceDialog()
}

/**
 * 从预览操作区打开发布弹窗；完整预览中触发时先关闭完整预览弹窗。
 * @param closeFullPreview 预览工作台传入的完整预览关闭函数
 */
function openReleaseFromPreview(closeFullPreview?: CloseFullPreviewHandler): void {
  closeFullPreview?.()
  openReleaseDialog()
}

/**
 * 重新读取当前组件被页面和其他组件直接引用的情况。
 */
async function refreshComponentReferences(): Promise<void> {
  if (!currentComponent.value) return
  referenceLoading.value = true
  try {
    componentReferences.value = await getComponentReferences(currentComponent.value.id)
  } catch (error) {
    Message.error(getErrorMessage(error, '加载组件引用关系失败'))
  } finally {
    referenceLoading.value = false
  }
}

/**
 * 批量升级弹窗中勾选的页面与组件草稿引用。
 * @param payload 勾选的页面 ID 和组件 ID
 */
async function handleUpgradeComponentReferences(payload: WorkspaceComponentReferenceUpgradePayload): Promise<void> {
  if (!currentComponent.value || referenceUpgrading.value) return
  referenceUpgrading.value = true
  try {
    const result = await upgradeComponentReferences(currentComponent.value.id, payload)
    showReferenceUpgradeResult(result)
    emit('request-list-refresh')
    await refreshComponentReferences()
  } catch (error) {
    Message.error(getErrorMessage(error, '更新引用失败'))
  } finally {
    referenceUpgrading.value = false
  }
}

/**
 * 展示引用批量升级结果，区分成功、跳过和失败。
 */
function showReferenceUpgradeResult(result: WorkspaceComponentReferenceUpgradeResponse): void {
  const updatedCount = result.updated_pages.length + result.updated_components.length
  if (result.failures.length > 0) {
    Message.error(`已更新 ${updatedCount} 项，${result.failures.length} 项失败。`)
    return
  }
  if (updatedCount > 0) {
    const skippedText = result.skipped.length ? `，跳过 ${result.skipped.length} 项` : ''
    Message.success(`已更新 ${result.updated_pages.length} 个页面、${result.updated_components.length} 个组件草稿${skippedText}。`)
    return
  }
  Message.warning(result.skipped.length ? `没有可更新引用，已跳过 ${result.skipped.length} 项。` : '没有可更新引用。')
}

async function refreshVersionHistory(): Promise<void> {
  if (!currentComponent.value) return
  versionHistoryLoading.value = true
  try {
    componentVersions.value = await listComponentVersions(currentComponent.value.id)
  } catch (error) {
    Message.error(getErrorMessage(error, '加载组件发布历史失败'))
  } finally {
    versionHistoryLoading.value = false
  }
}

async function ensureVersionContent(versionNo: number): Promise<WorkspaceComponentVersionContent> {
  if (!currentComponent.value) {
    throw new Error('缺少当前组件')
  }
  const cached = versionContentMap.value[versionNo]
  if (cached) {
    return cached
  }
  const content = await getComponentVersionContent(currentComponent.value.id, versionNo)
  versionContentMap.value = {
    ...versionContentMap.value,
    [versionNo]: content,
  }
  return content
}

async function ensureVersionPreview(versionNo: number): Promise<PreviewArtifactResponse> {
  if (!currentComponent.value) {
    throw new Error('缺少当前组件')
  }
  const cached = versionPreviewMap.value[versionNo]
  if (cached) {
    return cached
  }
  const preview = await createComponentVersionPreviewArtifact(currentComponent.value.id, versionNo)
  versionPreviewMap.value = {
    ...versionPreviewMap.value,
    [versionNo]: preview,
  }
  return preview
}

async function toggleVersionDiff(versionNo: number): Promise<void> {
  if (versionHistoryPanel.value?.mode === 'diff' && versionHistoryPanel.value.versionNo === versionNo) {
    versionHistoryPanel.value = null
    return
  }

  loadingContentVersionNo.value = versionNo
  try {
    await ensureVersionContent(versionNo)
    versionHistoryPanel.value = { mode: 'diff', versionNo }
  } catch (error) {
    Message.error(getErrorMessage(error, '读取组件发布版本源码失败'))
  } finally {
    loadingContentVersionNo.value = null
  }
}

async function toggleVersionPreview(versionNo: number): Promise<void> {
  if (versionHistoryPanel.value?.mode === 'preview' && versionHistoryPanel.value.versionNo === versionNo) {
    versionHistoryPanel.value = null
    return
  }

  previewingVersionNo.value = versionNo
  try {
    await ensureVersionPreview(versionNo)
    versionPreviewRefreshToken.value = Date.now()
    versionHistoryPanel.value = { mode: 'preview', versionNo }
  } catch (error) {
    Message.error(getErrorMessage(error, '生成组件发布版本预览失败'))
  } finally {
    previewingVersionNo.value = null
  }
}

async function restoreVersionToDraft(versionNo: number): Promise<void> {
  if (!currentComponent.value) return
  const version = componentVersions.value.find(item => item.version_no === versionNo)
  const displayName = version?.release_name || `v${versionNo}`
  const confirmed = await createConfirm(
    `确认将 ${displayName} 恢复到当前草稿吗？外部引用不会变化，直到你再次发布。`,
    '恢复发布版本到草稿',
  )
  if (!confirmed) return

  restoringVersionNo.value = versionNo
  try {
    const restored = await restoreComponentVersionToDraft(currentComponent.value.id, versionNo, {
      change_note: `恢复 ${displayName} 到草稿`,
    })
    draft.loadFromComponent(restored)
    versionContentMap.value = {}
    versionPreviewMap.value = {}
    versionHistoryPanel.value = null
    Message.success('已恢复到草稿，请确认后再发布新版本。')
    emit('component-saved', restored)
    emit('request-list-refresh')
    activeMode.value = 'preview'
    previewRefreshKey.value += 1
    await refreshVersionHistory()
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复组件发布版本失败'))
  } finally {
    restoringVersionNo.value = null
  }
}

/**
 * 清空发布历史临时状态。
 */
function resetVersionHistoryState(): void {
  releaseDialogVisible.value = false
  releaseDraftName.value = ''
  releaseDraftNote.value = ''
  versionHistoryVisible.value = false
  versionHistoryLoading.value = false
  componentVersions.value = []
  versionContentMap.value = {}
  versionPreviewMap.value = {}
  versionHistoryPanel.value = null
  previewingVersionNo.value = null
  loadingContentVersionNo.value = null
  restoringVersionNo.value = null
}

/**
 * 清空引用关系弹窗临时状态。
 */
function resetReferenceState(): void {
  referenceDialogVisible.value = false
  referenceLoading.value = false
  referenceUpgrading.value = false
  componentReferences.value = null
}
</script>
