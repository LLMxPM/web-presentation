<!-- 文件功能：提供页面详情查看与 page_content 编辑能力，支持 Monaco 编辑、快捷保存与自动保存配置。 -->
<template>
  <div data-testid="page-detail-view" class="page-detail-view flex h-full min-h-0 flex-col overflow-hidden">
    <div v-if="pageQuery.isFetching.value && !pageDetails"
      class="flex min-h-0 flex-1 flex-col items-center justify-center gap-6">
      <div class="w-16 h-16 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
      <span class="text-slate-400 font-extrabold text-lg animate-pulse tracking-wide">页面代码加载中...</span>
    </div>

    <div v-else-if="pageDetails" class="flex min-h-0 flex-1 flex-col gap-3 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <PageTitleBar
        class="shrink-0"
        :title="pageDetails.title"
        :code="pageDetails.code"
        :meta-items="pageTitleMetaItems"
      >
        <template #title-leading>
          <button
            type="button"
            class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-500 transition-all hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-50"
            title="返回项目页面"
            aria-label="返回项目页面"
            :disabled="!workspaceId || !projectId"
            @click="goToProjectPages"
          >
            <ArrowLeft class="h-4 w-4" />
          </button>
        </template>

        <template #title-actions>
          <button
            type="button"
            class="page-detail-identity-action"
            title="编辑页面名称和描述"
            aria-label="编辑页面名称和描述"
            :disabled="isPageIdentitySaving"
            @click="isPageIdentityDialogOpen = true"
          >
            <SquarePen class="h-3.5 w-3.5" />
          </button>
        </template>

        <template #actions>
          <div class="page-detail-title-actions flex flex-col items-end gap-1">
            <div class="flex items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
              <button
                type="button"
                class="inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition"
                :class="activeDetailPane === 'preview' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
                :disabled="isSaveActionPending"
                @click="handlePreviewPaneSelect"
              >
                <Monitor class="h-4 w-4" />
                预览
              </button>
              <button
                type="button"
                class="inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition"
                :class="activeDetailPane === 'editor' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
                @click="activeDetailPane = 'editor'"
              >
                <Code2 class="h-4 w-4" />
                编辑器
              </button>
              <button
                type="button"
                class="inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-semibold transition"
                :class="activeDetailPane === 'notes' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
                @click="activeDetailPane = 'notes'"
              >
                <FileText class="h-4 w-4" />
                备注
              </button>
            </div>

            <div class="flex flex-wrap items-center justify-end gap-1">
              <template v-if="activeDetailPane === 'preview'">
                <BaseButton
                  variant="ghost"
                  size="sm"
                  :disabled="isSaveActionPending || !previousPageId"
                  @click="goToAdjacentPage(previousPageId)"
                >
                  <ChevronLeft class="h-3.5 w-3.5" />
                  上一页
                </BaseButton>
                <BaseButton
                  variant="ghost"
                  size="sm"
                  :disabled="isSaveActionPending || !nextPageId"
                  @click="goToAdjacentPage(nextPageId)"
                >
                  <ChevronRight class="h-3.5 w-3.5" />
                  下一页
                </BaseButton>
              </template>

              <BaseButton variant="ghost" size="sm" @click="isHistoryModalOpen = true">
                <History class="h-3.5 w-3.5" />
                版本
              </BaseButton>
              <BaseButton v-if="activeDetailPane === 'preview'" variant="ghost" size="sm" @click="isScreenshotDialogOpen = true">
                <Camera class="h-3.5 w-3.5" />
                截图
              </BaseButton>
              <BaseButton variant="ghost" size="sm" @click="isUsageDialogOpen = true">
                <Layers class="h-3.5 w-3.5" />
                资源
              </BaseButton>
              <BaseButton
                v-if="activeDetailPane === 'preview'"
                variant="ghost"
                size="sm"
                :disabled="isSaveActionPending"
                @click="isCopyDialogOpen = true"
              >
                <Copy class="h-3.5 w-3.5" />
                复制
              </BaseButton>
              <BaseButton
                v-if="activeDetailPane === 'editor'"
                variant="primary"
                size="sm"
                :disabled="isSaveActionPending"
                :loading="isSaveActionPending"
                @click="requestSave('manual', undefined, { refreshPreview: false, showNoopMessage: true })"
              >
                <Save class="h-3.5 w-3.5" />
                保存
              </BaseButton>
            </div>
          </div>
        </template>
      </PageTitleBar>

      <div class="min-h-0 flex-1 overflow-hidden">
        <PageDetailPreviewPanel
          v-if="activeDetailPane === 'preview'"
          :preview-enabled="isPreviewEnabled"
          :preview-display-file-name="previewDisplayFileName"
          :preview-url="previewUrl"
          :preview-frame-url="previewFrameUrl"
          :preview-viewport="previewViewport"
          :page-title="pageDetails.title"
        />

        <PageSpeakerNotesPanel
          v-else-if="activeDetailPane === 'notes'"
          v-model="speakerNotesDraft"
          :page-title="pageDetails.title"
          :dirty="isSpeakerNotesDirty"
          :loading="isSpeakerNotesSaving"
          :disabled="isSaveActionPending"
          @save="handleSpeakerNotesSave"
        />

        <PageDetailWorkbenchPanel
          v-else
          v-model="editorCode"
          v-model:active-pane="activeWorkbenchPane"
          v-model:editor-theme="editorTheme"
          v-model:auto-save-delay="autoSaveDelay"
          :workspace-id="workspaceId"
          :project-id="projectId"
          :page-id="pageId"
          :page-title="pageDetails.title"
          :editor-language="editorLanguage"
          :auto-save-options="autoSaveOptions"
          :editor-height="editorHeight"
          @save="handleEditorSave"
          @ready="handleEditorReady"
          @dirty-change="handleDirtyChange"
          @copy-code="copyCode"
        />
      </div>

      <PageScreenshotDialog
        v-model="isScreenshotDialogOpen"
        :page-title="pageDetails.title"
        :screenshot-url="pageDetails.screenshot_url"
        :screenshot-version-no="pageDetails.screenshot_version_no"
        :screenshot-is-latest="pageDetails.screenshot_is_latest"
        :screenshot-updated-at="pageDetails.screenshot_updated_at"
        :screenshot-pending="isScreenshotPending"
        :screenshot-disabled="isScreenshotPending || isSaveActionPending"
        @save-screenshot="handleSaveScreenshot"
      />

      <PageUsageDialog
        v-model="isUsageDialogOpen"
        :component-index-loading="componentIndexQuery.isFetching.value && !pageComponentIndex"
        :used-component-names="usedComponentNames"
        :used-resource-items="usedResourceItems"
      />

      <PageIdentityDialog
        v-model="isPageIdentityDialogOpen"
        :page="pageDetails ?? null"
        :loading="isPageIdentitySaving"
        @submit="handlePageIdentityUpdate"
      />

      <PageCopyToProjectDialog
        v-model="isCopyDialogOpen"
        :page="pageDetails ?? null"
        :workspace-id="workspaceId"
        :current-project-id="projectId"
        :loading="isCopyPending"
        @submit="handleCopyPageToProject"
      />

      <PageVersionHistoryDialog
        v-model="isHistoryModalOpen"
        :loading="versionsQuery.isFetching.value"
        :versions="pageVersions"
        :history-panel="historyPanel"
        :panel-title="historyPanelTitle"
        :panel-subtitle="historyPanelSubtitle"
        :current-content="pageDetails.page_content"
        :version-content-map="versionContentMap"
        :history-panel-preview-frame-url="historyPanelPreviewFrameUrl"
        :editor-language="editorLanguage"
        :editor-theme="editorTheme"
        :previewing-runtime-version-no="previewingRuntimeVersionNo"
        :preview-version-pending="previewVersionMutation.isPending.value"
        :preview-version-no="previewVersionNo"
        :snapshot-pending="snapshotMutation.isPending.value"
        :pending-snapshot-version-no="pendingSnapshotVersionNo"
        :restore-pending="restoreMutation.isPending.value"
        :restoring-version-no="restoringVersionNo"
        @preview-version="toggleVersionPreview"
        @diff-version="toggleVersionDiff"
        @open-snapshot="openSnapshotDialog"
        @restore-version="handleRestoreVersion"
      />

      <PageSnapshotDialog
        v-model="isSnapshotDialogOpen"
        v-model:snapshot-name="snapshotDraftName"
        :version-label="snapshotDialogVersionLabel"
        :loading="snapshotMutation.isPending.value && pendingSnapshotVersionNo === snapshotDialogVersionNo"
        @submit="submitSnapshotDialog"
      />
    </div>

    <div v-else class="flex min-h-0 flex-1 flex-col items-center justify-center gap-8">
      <Frown class="w-24 h-24 text-slate-100" />
      <div class="text-center space-y-2">
        <h3 class="text-2xl font-extrabold text-slate-400">页面路由丢失</h3>
        <p class="text-slate-300 font-bold">找不到此页面的生命周期定义或数据溯源。</p>
      </div>
      <BaseButton variant="secondary" @click="router.back()">返回上一级</BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { ArrowLeft, Camera, ChevronLeft, ChevronRight, Code2, Copy, FileText, Frown, History, Layers, Monitor, Save, SquarePen } from '@lucide/vue'

import { getErrorMessage } from '@/api/http'
import {
  copyPageToProject,
  createPageSnapshot,
  getPage,
  getPageCurrentComponentIndex,
  getPageVersionContent,
  listPages,
  listPageVersions,
  restorePageVersion,
  savePageScreenshot,
  updatePage,
} from '@/api/catalog'
import { createPageVersionPreviewArtifact, createProjectPreviewArtifact } from '@/api/preview'
import PageTitleBar from '@/components/layout/PageTitleBar.vue'
import PageCopyToProjectDialog from '@/components/page/PageCopyToProjectDialog.vue'
import PageIdentityDialog from '@/components/page/PageIdentityDialog.vue'
import PageDetailPreviewPanel from '@/components/page-detail/PageDetailPreviewPanel.vue'
import PageDetailWorkbenchPanel from '@/components/page-detail/PageDetailWorkbenchPanel.vue'
import PageScreenshotDialog from '@/components/page-detail/PageScreenshotDialog.vue'
import PageSnapshotDialog from '@/components/page-detail/PageSnapshotDialog.vue'
import PageSpeakerNotesPanel from '@/components/page-detail/PageSpeakerNotesPanel.vue'
import PageUsageDialog from '@/components/page-detail/PageUsageDialog.vue'
import PageVersionHistoryDialog from '@/components/page-detail/PageVersionHistoryDialog.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import type {
  EditorLanguage,
  EditorSaveReason,
  MonacoEditorExpose,
  MonacoEditorReadyPayload,
  EditorThemeMode,
} from '@/types/monaco'
import type {
  PageCurrentComponentIndex,
  PageCopyToProjectPayload,
  PageFileType,
  PageItem,
  PageVersionContent,
  PageVersionListItem,
  PreviewArtifactResponse,
} from '@/types/api'
import { createConfirm, Message } from '@/utils/message'
import { resolvePageDetailNavigation } from '@/utils/page-detail-navigation'
import { buildPageDetailPath, buildProjectPagesPath } from '@/utils/workspace-routes'

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'
type PageWorkbenchPane = 'editor' | 'assistant'
type PageDetailPane = 'preview' | 'editor' | 'notes'

interface SaveRequestOptions {
  refreshPreview?: boolean
  showNoopMessage?: boolean
  showPreviewSuccessMessage?: boolean
}

interface AgentMutationEventDetail {
  workspaceId?: number | null
  projectId?: number | null
  pageId?: number | null
  componentId?: number | null
  assetId?: number | null
  toolName?: string
  result?: unknown
}

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const DEFAULT_PREVIEW_VIEWPORT: { width: number; height: number } = { width: 1920, height: 1080 }
const SPEAKER_NOTES_MAX_LENGTH = 10000

const workspaceId = computed(() => parseInt(route.params.workspaceId as string, 10))
const projectId = computed(() => parseInt(route.params.projectId as string, 10))
const pageId = computed(() => parseInt(route.params.pageId as string, 10))

const editorTheme = ref<EditorThemeMode>('light')
const autoSaveDelay = ref<number>(0)
const editorCode = ref('')
const fileType = ref<PageFileType>('vue')
const saveStatus = ref<SaveStatus>('idle')
const activeDetailPane = ref<PageDetailPane>('preview')
const activeWorkbenchPane = ref<PageWorkbenchPane>('assistant')
const isEditorDirty = ref(false)
const editorExposeRef = ref<MonacoEditorExpose | null>(null)
const pendingSaveRequest = ref<{ reason: EditorSaveReason; options: SaveRequestOptions } | null>(null)
const lastLoadedPageId = ref<number | null>(null)
const previewInitializedPageId = ref<number | null>(null)

const isHistoryModalOpen = ref(false)
const isScreenshotDialogOpen = ref(false)
const isUsageDialogOpen = ref(false)
const isPageIdentityDialogOpen = ref(false)
const isPageIdentitySaving = ref(false)
const isSpeakerNotesSaving = ref(false)
const isCopyDialogOpen = ref(false)
const isCopyPending = ref(false)
const isPreviewEnabled = ref(true)
const isPreviewPending = ref(false)
const previewUrl = ref('')
const previewFilePath = ref('')
const previewViewport = ref({ ...DEFAULT_PREVIEW_VIEWPORT })
const previewRefreshToken = ref(0)
const pendingSnapshotVersionNo = ref<number | null>(null)
const restoringVersionNo = ref<number | null>(null)
const previewingRuntimeVersionNo = ref<number | null>(null)
const previewVersionNo = ref<number | null>(null)
const historyPanel = ref<{ mode: 'diff' | 'preview'; versionNo: number } | null>(null)
const versionContentMap = ref<Record<number, PageVersionContent>>({})
const versionPreviewLinkMap = ref<Record<number, PreviewArtifactResponse>>({})
const isSnapshotDialogOpen = ref(false)
const snapshotDialogVersionNo = ref<number | null>(null)
const snapshotDraftName = ref('')
const speakerNotesDraft = ref('')
const lastLoadedSpeakerNotesPageId = ref<number | null>(null)

const autoSaveOptions = [
  { label: '关闭', value: 0 },
  { label: '30 秒', value: 30000 },
  { label: '1 分钟', value: 60000 },
  { label: '3 分钟', value: 180000 },
  { label: '5 分钟', value: 300000 },
]

const editorHeight = '100%'
const isSaveActionPending = computed(() => saveMutation.isPending.value || isPreviewPending.value || isSpeakerNotesSaving.value)
const isScreenshotPending = computed(() => screenshotMutation.isPending.value)
const previewDisplayFileName = computed(() => {
  const path = previewFilePath.value.trim()
  if (path) {
    const parts = path.split('/').filter(Boolean)
    return parts[parts.length - 1] ?? ''
  }
  if (!pageDetails.value) return ''
  return `${pageDetails.value.code}.${pageDetails.value.file_type}`
})
const snapshotDialogVersionLabel = computed(() => {
  const versionNo = snapshotDialogVersionNo.value
  if (!versionNo) return ''
  return pageVersions.value.find(item => item.version_no === versionNo)?.version_label ?? `#${versionNo}`
})
const historyPanelVersion = computed(() => {
  const versionNo = historyPanel.value?.versionNo
  if (!versionNo) return null
  return pageVersions.value.find(item => item.version_no === versionNo) ?? null
})
const historyPanelPreviewLink = computed(() => {
  const versionNo = historyPanel.value?.versionNo
  if (!versionNo) return null
  return versionPreviewLinkMap.value[versionNo] ?? null
})
const historyPanelPreviewFrameUrl = computed(() => historyPanelPreviewLink.value?.preview_url || '')
const historyPanelPreviewFileName = computed(() => {
  const filePath = resolvePreviewFilePath(historyPanelPreviewLink.value) ?? ''
  const parts = filePath.split('/').filter(Boolean)
  return parts[parts.length - 1] ?? ''
})
const historyPanelTitle = computed(() => {
  if (!historyPanel.value || !historyPanelVersion.value) return '版本详情'
  return historyPanel.value.mode === 'diff'
    ? `版本差异 · ${historyPanelVersion.value.version_label}`
    : `版本预览 · ${historyPanelVersion.value.version_label}`
})
const historyPanelSubtitle = computed(() => {
  if (!historyPanel.value || !historyPanelVersion.value) {
    return '在左侧选择一个版本查看差异或预览。'
  }
  if (historyPanel.value.mode === 'diff') {
    return '展示所选版本与当前最新版本之间的源码差异。'
  }
  return historyPanelPreviewFileName.value || '正在准备运行时预览...'
})
const previewFrameUrl = computed(() => {
  if (!previewUrl.value) return ''
  const separator = previewUrl.value.includes('?') ? '&' : '?'
  return `${previewUrl.value}${separator}t=${previewRefreshToken.value}`
})

/**
 * 更新 iframe 刷新令牌，避免浏览器复用旧的预览页快照。
 */
function refreshPreviewFrame() {
  previewRefreshToken.value = Date.now()
}

/**
 * 将预览链接同步到右侧 iframe，并刷新展示。
 */
function applyPreviewLink(previewLink: PreviewArtifactResponse) {
  previewUrl.value = previewLink.preview_url
  previewFilePath.value = resolvePreviewFilePath(previewLink) ?? ''
  previewViewport.value = resolvePreviewViewport(previewLink)
  refreshPreviewFrame()
}

/**
 * 从统一预览响应中提取当前入口对应的文件或路由标识，用于页面展示和截图链路复用。
 * @param previewLink 预览响应
 * @returns 页面模块路径或路由字符串
 */
function resolvePreviewFilePath(previewLink: PreviewArtifactResponse | null | undefined): string | null {
  if (!previewLink) {
    return null
  }
  if (previewLink.entry_descriptor?.entry_type === 'module') {
    return previewLink.entry_descriptor.module_path || null
  }
  if (previewLink.entry_descriptor?.entry_type === 'route') {
    return previewLink.entry_descriptor.route || null
  }
  return null
}

/**
 * 归一化后端返回的预览视口尺寸，缺失时回退到默认比例。
 */
function resolvePreviewViewport(previewLink: Pick<PreviewArtifactResponse, 'viewport_width' | 'viewport_height'>) {
  const width = Number(previewLink.viewport_width)
  const height = Number(previewLink.viewport_height)
  return {
    width: Number.isFinite(width) && width > 0 ? width : DEFAULT_PREVIEW_VIEWPORT.width,
    height: Number.isFinite(height) && height > 0 ? height : DEFAULT_PREVIEW_VIEWPORT.height,
  }
}

const pageQuery = useQuery(
  computed(() => ({
    queryKey: ['page', pageId.value],
    queryFn: () => getPage(pageId.value),
    enabled: !!pageId.value,
  })),
)

const componentIndexQuery = useQuery(
  computed(() => ({
    queryKey: ['page-component-index', pageId.value, pageQuery.data.value?.current_version_no ?? 0],
    queryFn: () => getPageCurrentComponentIndex(pageId.value),
    enabled: !!pageId.value,
  })),
)

const versionsQuery = useQuery(
  computed(() => ({
    queryKey: ['page-versions', pageId.value],
    queryFn: () => listPageVersions(pageId.value),
    enabled: !!pageId.value,
  })),
)

const projectPagesQuery = useQuery(
  computed(() => ({
    queryKey: ['pages-by-project', projectId.value, 'active', 'detail-navigation'],
    queryFn: () => listAllProjectActivePages(projectId.value),
    enabled: !!projectId.value,
  })),
)

const pageDetails = computed(() => pageQuery.data.value)
const pageTitleMetaItems = computed(() => {
  const summary = pageDetails.value?.summary?.trim()
  if (!summary) {
    return []
  }
  return [summary]
})
const projectPages = computed<PageItem[]>(() => projectPagesQuery.data.value ?? [])
const pageNavigation = computed(() => resolvePageDetailNavigation(projectPages.value, pageId.value))
const previousPageId = computed(() => pageNavigation.value.previousPageId)
const nextPageId = computed(() => pageNavigation.value.nextPageId)
const pageComponentIndex = computed<PageCurrentComponentIndex | null>(() => componentIndexQuery.data.value ?? null)
const pageVersions = computed<PageVersionListItem[]>(() => versionsQuery.data.value ?? [])
const usedComponentNames = computed(() => pageComponentIndex.value?.components ?? [])
const usedResourceItems = computed(() => pageComponentIndex.value?.resources ?? [])
const editorLanguage = computed<EditorLanguage>(() => 'vue')
const isFileTypeDirty = computed(() => false) // 固定为 vue
const hasPendingChanges = computed(() => isEditorDirty.value)
const isSpeakerNotesDirty = computed(() => {
  return speakerNotesDraft.value !== (pageDetails.value?.speaker_notes ?? '')
})

/**
 * 返回当前页面所属项目的页面列表。
 */
function goToProjectPages(): void {
  void router.push(buildProjectPagesPath(workspaceId.value, projectId.value))
}

/**
 * 按页码分批读取当前项目启用页面，用于详情页预览模式的前后页导航。
 * @param targetProjectId 当前项目 ID
 */
async function listAllProjectActivePages(targetProjectId: number): Promise<PageItem[]> {
  const pageSize = 100
  const items: PageItem[] = []
  let currentPageNo = 1
  let total = 0

  do {
    const response = await listPages({
      page: currentPageNo,
      page_size: pageSize,
      project_id: targetProjectId,
      status: 'active',
      sort_by: 'code',
      sort_order: 'asc',
    })
    items.push(...response.items)
    total = response.total
    currentPageNo += 1
  } while (items.length < total)

  return items
}

/**
 * 跳转到详情页预览模式的相邻页面。
 * @param targetPageId 目标页面 ID
 */
function goToAdjacentPage(targetPageId: number | null): void {
  if (!targetPageId || targetPageId === pageId.value) {
    return
  }
  void router.push(buildPageDetailPath(workspaceId.value, projectId.value, targetPageId))
}

/**
 * 将当前已保存页面复制到同工作空间的另一个项目，并跳转到新页面。
 * @param payload 页面复制配置
 */
async function handleCopyPageToProject(payload: PageCopyToProjectPayload): Promise<void> {
  if (!pageDetails.value || isCopyPending.value) {
    return
  }

  isCopyPending.value = true
  try {
    const copiedPage = await copyPageToProject(pageId.value, payload)
    const nextProjectId = copiedPage.project_id ?? payload.target_project_id
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] }),
      queryClient.invalidateQueries({ queryKey: ['pages-by-project', nextProjectId] }),
      queryClient.invalidateQueries({ queryKey: ['project', nextProjectId] }),
    ])
    isCopyDialogOpen.value = false
    Message.success('页面已复制到目标项目。')
    void router.push(buildPageDetailPath(workspaceId.value, nextProjectId, copiedPage.id))
  } catch (error) {
    Message.error(getErrorMessage(error, '复制页面失败。'))
  } finally {
    isCopyPending.value = false
  }
}

/**
 * 保存页面名称与描述，并同步当前详情和列表缓存。
 * @param payload 页面基础信息
 */
async function handlePageIdentityUpdate(payload: { title: string; summary: string | null }): Promise<void> {
  if (!pageDetails.value || isPageIdentitySaving.value) {
    return
  }

  isPageIdentitySaving.value = true
  try {
    const updatedPage = await updatePage(pageId.value, payload)
    queryClient.setQueryData(['page', pageId.value], updatedPage)
    await queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] })
    isPageIdentityDialogOpen.value = false
    Message.success('页面信息已更新。')
  } catch (error) {
    Message.error(getErrorMessage(error, '更新页面信息失败。'))
  } finally {
    isPageIdentitySaving.value = false
  }
}

/**
 * 保存页面演讲者备注，并同步页面详情、页面列表与版本历史缓存。
 */
async function handleSpeakerNotesSave(): Promise<boolean> {
  if (!pageDetails.value || isSpeakerNotesSaving.value) {
    return false
  }
  if (!isSpeakerNotesDirty.value) {
    Message.info('暂无需要保存的备注。')
    return true
  }
  if (speakerNotesDraft.value.length > SPEAKER_NOTES_MAX_LENGTH) {
    Message.error(`演讲者备注不能超过 ${SPEAKER_NOTES_MAX_LENGTH} 个字符。`)
    return false
  }

  isSpeakerNotesSaving.value = true
  try {
    const updatedPage = await updatePage(pageId.value, {
      speaker_notes: normalizeSpeakerNotesPayload(speakerNotesDraft.value),
      change_note: '更新演讲者备注',
    })
    speakerNotesDraft.value = updatedPage.speaker_notes ?? ''
    queryClient.setQueryData(['page', pageId.value], updatedPage)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] }),
      queryClient.invalidateQueries({ queryKey: ['page-versions', pageId.value] }),
    ])
    previewInitializedPageId.value = null
    Message.success('演讲者备注已保存。')
    return true
  } catch (error) {
    Message.error(getErrorMessage(error, '保存演讲者备注失败。'))
    return false
  } finally {
    isSpeakerNotesSaving.value = false
  }
}

/**
 * 将备注文本转为后端可接受的可空字段，空白文本视为清空备注。
 * @param value 当前输入框内容
 */
function normalizeSpeakerNotesPayload(value: string): string | null {
  return value.trim() ? value : null
}

const saveMutation = useMutation({
  mutationFn: (payload: { pageCode: string; fileType: PageFileType }) => updatePage(pageId.value, {
    page_content: payload.pageCode,
    file_type: payload.fileType,
  }),
})

const snapshotMutation = useMutation({
  mutationFn: (payload: { versionNo: number; snapshotName?: string | null }) => createPageSnapshot(pageId.value, payload.versionNo, {
    snapshot_name: payload.snapshotName,
  }),
})

const restoreMutation = useMutation({
  mutationFn: (payload: { versionNo: number; changeNote?: string | null }) => restorePageVersion(pageId.value, payload.versionNo, {
    change_note: payload.changeNote,
  }),
})

const previewVersionMutation = useMutation({
  mutationFn: (versionNo: number) => getPageVersionContent(pageId.value, versionNo),
})

const screenshotMutation = useMutation({
  mutationFn: (payload: { viewport_width?: number; viewport_height?: number } = {}) => savePageScreenshot(pageId.value, payload),
})

/**
 * 初始化编辑器缓冲区，避免刷新详情数据时覆盖未保存内容。
 */
watch(pageDetails, (page) => {
  if (!page) return

  const isNewPage = lastLoadedPageId.value !== page.id
    if (isNewPage || (!isEditorDirty.value && !isFileTypeDirty.value)) {
    editorCode.value = page.page_content
    fileType.value = page.file_type
    lastLoadedPageId.value = page.id
    saveStatus.value = 'idle'
    historyPanel.value = null
    versionContentMap.value = {}
    versionPreviewLinkMap.value = {}
    editorExposeRef.value?.markClean(page.page_content)
    if (isNewPage) {
      previewUrl.value = ''
      previewFilePath.value = ''
      previewViewport.value = { ...DEFAULT_PREVIEW_VIEWPORT }
      previewRefreshToken.value = 0
      previewInitializedPageId.value = null
      isSnapshotDialogOpen.value = false
      snapshotDialogVersionNo.value = null
      snapshotDraftName.value = ''
    }
  }
}, { immediate: true })

/**
 * 同步页面备注草稿；页面切换时强制重置，普通详情刷新不覆盖本地未保存备注。
 */
watch(pageDetails, (page) => {
  if (!page) return

  const isNewPage = lastLoadedSpeakerNotesPageId.value !== page.id
  if (isNewPage || !isSpeakerNotesDirty.value) {
    speakerNotesDraft.value = page.speaker_notes ?? ''
    lastLoadedSpeakerNotesPageId.value = page.id
  }
}, { immediate: true })

/**
 * 页面首次进入且默认开启预览时，自动拉起一次 Runtime 预览。
 */
watch(
  [pageDetails, isPreviewEnabled],
  ([page, enabled]) => {
    if (!page || !enabled) return
    if (previewInitializedPageId.value === page.id) return
    if (hasPendingChanges.value || isSaveActionPending.value) return

    void (async () => {
      const success = await syncRuntimePreview(page, { showSuccessMessage: false })
      if (success) {
        previewInitializedPageId.value = page.id
      }
    })()
  },
  { immediate: true },
)

watch(isHistoryModalOpen, (opened) => {
  if (!opened) {
    closeHistoryPanel()
  }
})

/**
 * 接收编辑器实例暴露的方法，供页面保存成功后重置脏状态。
 */
function handleEditorReady(payload: MonacoEditorReadyPayload) {
  editorExposeRef.value = payload
  if (pageDetails.value) {
    payload.markClean(pageDetails.value.page_content)
  }
}

/**
 * 同步编辑器脏状态，以驱动页面级保存提示和按钮状态。
 */
function handleDirtyChange(dirty: boolean) {
  isEditorDirty.value = dirty
  if (dirty && saveStatus.value !== 'saving') {
    saveStatus.value = 'idle'
  }
}

/**
 * 统一处理来自编辑器的手动/自动保存事件。
 */
function handleEditorSave(payload: { reason: EditorSaveReason; value: string }) {
  void requestSave(payload.reason, payload.value, { refreshPreview: false, showNoopMessage: payload.reason === 'manual' })
}

/**
 * 从编辑器切换到预览时先保存当前缓冲区，再刷新 Runtime 预览。
 */
async function handlePreviewPaneSelect(): Promise<void> {
  const currentPage = pageDetails.value
  if (!currentPage || isSaveActionPending.value) return
  if (activeDetailPane.value === 'preview') return

  if (activeDetailPane.value === 'notes' && isSpeakerNotesDirty.value) {
    const notesSaved = await handleSpeakerNotesSave()
    if (!notesSaved) {
      return
    }
  }

  const saved = await requestSave('manual', editorCode.value, {
    refreshPreview: false,
    showNoopMessage: false,
  })
  if (!saved) {
    return
  }

  const previewPage = pageQuery.data.value ?? currentPage
  const previewSynced = await syncRuntimePreview(previewPage, { showSuccessMessage: false })
  if (!previewSynced) {
    return
  }
  previewInitializedPageId.value = previewPage.id
  activeDetailPane.value = 'preview'
}
/**
 * 接收智能体建议并写入当前编辑器缓冲区，但不直接持久化到后端。
 */
function handleAgentApplySuggestedContent(content: string) {
  activeDetailPane.value = 'editor'
  activeWorkbenchPane.value = 'editor'
  editorCode.value = content
  isEditorDirty.value = true
  saveStatus.value = 'idle'
}

/**
 * 当智能体已经直接写回页面后，刷新页面详情与相关缓存，保持编辑器状态一致。
 * @param detail 智能体工具写回事件详情
 */
async function handleAgentPageUpdated(detail?: AgentMutationEventDetail) {
  const currentPageId = detail?.pageId ?? pageId.value
  if (currentPageId !== pageId.value) {
    return
  }
  const shouldRefreshPreview = detail?.toolName !== 'get_page_screenshot'

  const latestPage = (await pageQuery.refetch()).data ?? pageDetails.value
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] }),
    queryClient.invalidateQueries({ queryKey: ['page-versions', pageId.value] }),
    queryClient.invalidateQueries({ queryKey: ['page-component-index', pageId.value] }),
  ])

  if (!latestPage) {
    return
  }

  if (!hasPendingChanges.value) {
    syncPageIntoEditor(latestPage)
  } else if (shouldRefreshPreview) {
    Message.warning('页面已由智能体更新，当前编辑器仍保留未保存修改。预览已切换到后端最新版本。')
  }

  if (!shouldRefreshPreview) {
    return
  }

  const previewSynced = await syncRuntimePreview(latestPage, { showSuccessMessage: false })
  if (previewSynced) {
    activeDetailPane.value = 'preview'
    previewInitializedPageId.value = latestPage.id
  }
}

/**
 * 当前项目页面列表或路由由智能体修改后，刷新当前页详情与列表缓存。
 * @param detail 智能体工具写回事件详情
 */
async function handleAgentProjectPagesUpdated(detail?: AgentMutationEventDetail) {
  if (
    detail?.toolName === 'apply_page_edits'
    || detail?.toolName === 'update_page_metadata'
    || detail?.toolName === 'get_page_screenshot'
  ) {
    return
  }
  const currentProjectId = detail?.projectId ?? projectId.value
  if (currentProjectId !== projectId.value) {
    return
  }

  await pageQuery.refetch()
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] }),
    queryClient.invalidateQueries({ queryKey: ['project', projectId.value] }),
  ])
}

/**
 * 接收左侧全局智能体侧边栏派发的页面建议，写入当前 Monaco 缓冲区。
 */
function handleGlobalAgentApplySuggestedContent(event: Event) {
  const detail = (event as CustomEvent<{ pageId?: number | null; content?: string }>).detail
  if (!detail?.content || detail.pageId !== pageId.value) return
  handleAgentApplySuggestedContent(detail.content)
}

/**
 * 接收左侧全局智能体侧边栏派发的页面写回完成通知，刷新当前页面缓存。
 */
function handleGlobalAgentPageUpdated(event: Event) {
  const detail = (event as CustomEvent<AgentMutationEventDetail>).detail
  if (detail?.workspaceId && detail.workspaceId !== workspaceId.value) return
  if (detail?.projectId && detail.projectId !== projectId.value) return
  if (detail?.pageId && detail.pageId !== pageId.value) return
  void handleAgentPageUpdated(detail)
}

/**
 * 接收左侧全局智能体侧边栏派发的项目页面或路由变更通知。
 */
function handleGlobalAgentProjectPagesUpdated(event: Event) {
  const detail = (event as CustomEvent<AgentMutationEventDetail>).detail
  if (detail?.workspaceId && detail.workspaceId !== workspaceId.value) return
  if (detail?.projectId && detail.projectId !== projectId.value) return
  void handleAgentProjectPagesUpdated(detail)
}

/**
 * 接收组件助手写入事件；当前页引用该组件或无法判定时，重建运行时预览。
 */
function handleGlobalAgentComponentUpdated(event: Event) {
  const detail = (event as CustomEvent<AgentMutationEventDetail>).detail
  if (!isAgentMutationInCurrentScope(detail)) return
  if (!shouldRefreshPageForComponentMutation(detail)) return
  void refreshRuntimePreviewAfterAgentDependencyMutation()
}

/**
 * 接收资源助手写入事件；当前页引用该资源或无法判定时，重建运行时预览。
 */
function handleGlobalAgentAssetUpdated(event: Event) {
  const detail = (event as CustomEvent<AgentMutationEventDetail>).detail
  if (!isAgentMutationInCurrentScope(detail)) return
  if (!shouldRefreshPageForAssetMutation(detail)) return
  void refreshRuntimePreviewAfterAgentDependencyMutation()
}

/**
 * 判断全局写入事件是否仍属于当前页面所在范围。
 */
function isAgentMutationInCurrentScope(detail?: AgentMutationEventDetail): boolean {
  if (!detail) {
    return true
  }
  return optionalIdMatches(detail.workspaceId, workspaceId.value)
    && optionalIdMatches(detail.projectId, projectId.value)
    && optionalIdMatches(detail.pageId, pageId.value)
}

/**
 * 组件事件若缺少可判定 import_name，则保守刷新当前页面预览。
 */
function shouldRefreshPageForComponentMutation(detail?: AgentMutationEventDetail): boolean {
  if (!pageComponentIndex.value) {
    return true
  }
  const componentImportName = resolveComponentImportNameFromMutation(detail)
  if (!componentImportName) {
    return true
  }
  const candidates = new Set([componentImportName, normalizeComponentName(componentImportName)])
  return usedComponentNames.value.some(componentName => candidates.has(componentName))
}

/**
 * 资源事件若缺少可判定资源名，则保守刷新当前页面预览。
 */
function shouldRefreshPageForAssetMutation(detail?: AgentMutationEventDetail): boolean {
  if (!pageComponentIndex.value) {
    return true
  }
  const assetName = resolveAssetNameFromMutation(detail)
  if (!assetName) {
    return true
  }
  return usedResourceItems.value.some(item => item.resource_name === assetName)
}

/**
 * 依赖资源或组件被智能体修改后，仅刷新预览和源码索引，不改动页面编辑缓冲区。
 */
async function refreshRuntimePreviewAfterAgentDependencyMutation(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: ['page-component-index', pageId.value] })
  const currentPage = pageDetails.value
  if (!currentPage) {
    return
  }
  const previewSynced = await syncRuntimePreview(currentPage, { showSuccessMessage: false })
  if (previewSynced) {
    previewInitializedPageId.value = currentPage.id
  }
}

/**
 * 从组件工具返回中读取 import_name，用于和当前页组件索引匹配。
 */
function resolveComponentImportNameFromMutation(detail?: AgentMutationEventDetail): string | null {
  const resultRecord = normalizeMutationResultRecord(detail?.result)
  const component = resultRecord && isRecord(resultRecord.component) ? resultRecord.component : null
  return resolveStringField(component, ['import_name', 'importName'])
    ?? resolveStringField(resultRecord, ['import_name', 'importName'])
}

/**
 * 从资源工具返回中读取资源逻辑名，用于和当前页资源索引匹配。
 */
function resolveAssetNameFromMutation(detail?: AgentMutationEventDetail): string | null {
  const resultRecord = normalizeMutationResultRecord(detail?.result)
  const asset = resultRecord && isRecord(resultRecord.asset) ? resultRecord.asset : null
  return resolveStringField(asset, ['name'])
    ?? resolveStringField(resultRecord, ['asset_name', 'name'])
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
 * 可选 ID 为空时表示事件不限定该层级；有值时必须匹配当前路由。
 */
function optionalIdMatches(value: unknown, currentValue: number): boolean {
  if (value === null || value === undefined) {
    return true
  }
  const normalized = Number(value)
  return Number.isFinite(normalized) && normalized === currentValue
}

/**
 * 复用后端页面组件索引的基础组件名归一规则。
 */
function normalizeComponentName(componentName: string): string {
  if (componentName.includes('-')) {
    return componentName.split('-').filter(Boolean).map(part => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`).join('')
  }
  if (componentName.toLowerCase() === 'icon') {
    return 'Icon'
  }
  if (componentName.toLowerCase().startsWith('asset')) {
    return `${componentName.slice(0, 1).toUpperCase()}${componentName.slice(1)}`
  }
  return componentName
}

/**
 * 从对象多个候选字段中读取非空字符串。
 */
function resolveStringField(record: Record<string, unknown> | null, fieldNames: string[]): string | null {
  if (!record) {
    return null
  }
  for (const fieldName of fieldNames) {
    const value = record[fieldName]
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

onMounted(() => {
  window.addEventListener('agent:apply-suggested-content', handleGlobalAgentApplySuggestedContent)
  window.addEventListener('agent:page-updated', handleGlobalAgentPageUpdated)
  window.addEventListener('agent:project-pages-updated', handleGlobalAgentProjectPagesUpdated)
  window.addEventListener('agent:component-updated', handleGlobalAgentComponentUpdated)
  window.addEventListener('agent:asset-updated', handleGlobalAgentAssetUpdated)
})

onUnmounted(() => {
  window.removeEventListener('agent:apply-suggested-content', handleGlobalAgentApplySuggestedContent)
  window.removeEventListener('agent:page-updated', handleGlobalAgentPageUpdated)
  window.removeEventListener('agent:project-pages-updated', handleGlobalAgentProjectPagesUpdated)
  window.removeEventListener('agent:component-updated', handleGlobalAgentComponentUpdated)
  window.removeEventListener('agent:asset-updated', handleGlobalAgentAssetUpdated)
})

/**
 * 根据当前状态发起保存，请求进行中时会合并后续保存需求。
 */
async function requestSave(
  reason: EditorSaveReason,
  explicitValue?: string,
  options: SaveRequestOptions = {},
): Promise<boolean> {
  const currentPage = pageDetails.value
  if (!currentPage) return false

  const targetValue = explicitValue ?? editorCode.value
  const targetFileType = fileType.value
  const latestSavedValue = pageQuery.data.value?.page_content ?? currentPage.page_content
  const latestSavedFileType = pageQuery.data.value?.file_type ?? currentPage.file_type
  const shouldRefreshPreview = options.refreshPreview ?? false

  if (!hasPendingChanges.value && targetValue === latestSavedValue && targetFileType === latestSavedFileType) {
    saveStatus.value = 'saved'
    editorExposeRef.value?.markClean(targetValue)
    if (shouldRefreshPreview) {
      return await syncRuntimePreview(currentPage, {
        showSuccessMessage: options.showPreviewSuccessMessage ?? reason === 'manual',
      })
    }
    if (reason === 'manual' && options.showNoopMessage) {
      Message.info('暂无需要保存的更改。')
    }
    return true
  }

  if (isSaveActionPending.value) {
    pendingSaveRequest.value = { reason, options }
    return false
  }

  return await executeSave(reason, targetValue, targetFileType, options)
}

/**
 * 执行一次真正的保存流程，并在成功后同步查询缓存。
 */
async function executeSave(
  reason: EditorSaveReason,
  submittedValue: string,
  submittedFileType: PageFileType,
  options: SaveRequestOptions,
): Promise<boolean> {
  saveStatus.value = 'saving'
  let success = false

  try {
    const savedPage = await saveMutation.mutateAsync({ pageCode: submittedValue, fileType: submittedFileType })
    queryClient.setQueryData(['page', pageId.value], savedPage)
    await queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] })
    await queryClient.invalidateQueries({ queryKey: ['page-versions', pageId.value] })
    await queryClient.invalidateQueries({ queryKey: ['page-component-index', pageId.value] })

    if (editorCode.value === submittedValue && fileType.value === submittedFileType) {
      editorExposeRef.value?.markClean(savedPage.page_content)
      saveStatus.value = 'saved'
      if (reason === 'manual' && !options.refreshPreview) {
        Message.success('页面源码与文件类型已保存。')
      }
    } else {
      saveStatus.value = 'idle'
    }

    if (options.refreshPreview) {
      success = await syncRuntimePreview(savedPage, {
        showSuccessMessage: options.showPreviewSuccessMessage ?? reason === 'manual',
      })
    } else {
      success = true
    }
  } catch (error) {
    saveStatus.value = 'error'
    Message.error(getErrorMessage(error, '页面代码保存失败。'))
  } finally {
    if (pendingSaveRequest.value) {
      const nextRequest = pendingSaveRequest.value
      pendingSaveRequest.value = null
      await requestSave(nextRequest.reason, editorCode.value, nextRequest.options)
    }
  }

  return success
}

/**
 * 重新生成当前页面截图；若存在未保存修改，会先完成源码保存，再触发后端截图流程。
 */
async function handleSaveScreenshot() {
  if (!pageDetails.value || isScreenshotPending.value || isSaveActionPending.value) return

  if (hasPendingChanges.value) {
    const saved = await requestSave('manual', editorCode.value, {
      refreshPreview: true,
      showNoopMessage: false,
      showPreviewSuccessMessage: false,
    })
    if (!saved) {
      return
    }
  }

  try {
    const updatedPage = await screenshotMutation.mutateAsync({})
    queryClient.setQueryData(['page', pageId.value], updatedPage)
    await queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] })
    Message.success('页面截图已重新生成。')
  } catch (error) {
    Message.error(getErrorMessage(error, '重新截图失败。'))
  }
}

/**
 * 复制当前缓冲区代码，避免只复制服务端旧内容。
 */
function copyCode() {
  if (!editorCode.value) return
  navigator.clipboard.writeText(editorCode.value)
  Message.success('详情代码已复制到剪贴板。')
}

/**
 * 统一把服务端返回的新页面状态同步到编辑器和查询缓存。
 */
function syncPageIntoEditor(page: { page_content: string; file_type: PageFileType }) {
  editorCode.value = page.page_content
  fileType.value = page.file_type
  editorExposeRef.value?.markClean(page.page_content)
  isEditorDirty.value = false
  saveStatus.value = 'saved'
}

/**
 * 读取指定版本的完整源码内容，并缓存在页面内存中复用。
 */
async function ensureVersionContent(versionNo: number): Promise<PageVersionContent> {
  const cached = versionContentMap.value[versionNo]
  if (cached) {
    return cached
  }

  const versionContent = await previewVersionMutation.mutateAsync(versionNo)
  versionContentMap.value = {
    ...versionContentMap.value,
    [versionNo]: versionContent,
  }
  return versionContent
}

/**
 * 读取指定版本的临时预览链接，并缓存在页面内存中复用。
 */
async function ensureVersionPreviewLink(versionNo: number): Promise<PreviewArtifactResponse> {
  const cached = versionPreviewLinkMap.value[versionNo]
  if (cached) {
    return cached
  }

  const previewLink = await createPageVersionPreviewArtifact(pageId.value, versionNo)
  versionPreviewLinkMap.value = {
    ...versionPreviewLinkMap.value,
    [versionNo]: previewLink,
  }
  return previewLink
}

/**
 * 打开创建快照弹窗，允许填写更易识别的快照名称。
 */
function openSnapshotDialog(versionNo: number) {
  snapshotDialogVersionNo.value = versionNo
  snapshotDraftName.value = pageVersions.value.find(item => item.version_no === versionNo)?.snapshot_name ?? ''
  isSnapshotDialogOpen.value = true
}

/**
 * 关闭版本历史右侧展示容器。
 */
function closeHistoryPanel() {
  historyPanel.value = null
}

/**
 * 提交快照创建请求；当前版本若存在未保存修改，会先执行保存。
 */
async function submitSnapshotDialog() {
  if (!pageDetails.value || !snapshotDialogVersionNo.value) return

  const versionNo = snapshotDialogVersionNo.value
  if (versionNo === pageDetails.value.current_version_no && hasPendingChanges.value) {
    const saved = await requestSave('manual', undefined, {
      refreshPreview: false,
      showNoopMessage: false,
    })
    if (!saved) return
  }

  pendingSnapshotVersionNo.value = versionNo
  try {
    const createdSnapshot = await snapshotMutation.mutateAsync({
      versionNo,
      snapshotName: snapshotDraftName.value.trim() || null,
    })
    await queryClient.invalidateQueries({ queryKey: ['page-versions', pageId.value] })
    isSnapshotDialogOpen.value = false
    snapshotDialogVersionNo.value = null
    snapshotDraftName.value = ''
    Message.success(`已创建快照版本 ${createdSnapshot.version_label}。`)
  } catch (error) {
    Message.error(getErrorMessage(error, '创建重点快照失败。'))
  } finally {
    pendingSnapshotVersionNo.value = null
  }
}

/**
 * 展开或收起指定版本的累积 diff，并按需缓存版本内容。
 */
async function toggleVersionDiff(versionNo: number) {
  if (historyPanel.value?.mode === 'diff' && historyPanel.value.versionNo === versionNo) {
    closeHistoryPanel()
    return
  }

  previewVersionNo.value = versionNo
  try {
    await ensureVersionContent(versionNo)
    historyPanel.value = { mode: 'diff', versionNo }
  } catch (error) {
    Message.error(getErrorMessage(error, '读取版本源码失败。'))
  } finally {
    previewVersionNo.value = null
  }
}

/**
 * 展开或收起指定历史版本的内联运行时预览。
 */
async function toggleVersionPreview(versionNo: number) {
  if (historyPanel.value?.mode === 'preview' && historyPanel.value.versionNo === versionNo) {
    closeHistoryPanel()
    return
  }

  previewingRuntimeVersionNo.value = versionNo
  try {
    await ensureVersionPreviewLink(versionNo)
    historyPanel.value = { mode: 'preview', versionNo }
  } catch (error) {
    Message.error(getErrorMessage(error, '生成历史版本预览失败。'))
  } finally {
    previewingRuntimeVersionNo.value = null
  }
}

/**
 * 将历史版本恢复为最新版本，并同步重置本地编辑器缓冲区。
 */
async function handleRestoreVersion(versionNo: number) {
  if (!pageDetails.value) return

  const targetVersion = pageVersions.value.find(item => item.version_no === versionNo)
  const displayLabel = targetVersion?.version_label ?? `#${versionNo}`

  const confirmed = await createConfirm(
    hasPendingChanges.value
      ? `恢复到 ${displayLabel} 会覆盖当前未保存修改，是否继续？`
      : `确认恢复到 ${displayLabel} 吗？系统会基于该版本生成新的最新版本。`,
    '恢复历史版本',
  )
  if (!confirmed) return

  restoringVersionNo.value = versionNo
  try {
    const restoredPage = await restoreMutation.mutateAsync({
      versionNo,
      changeNote: `恢复到 ${displayLabel}`,
    })
    queryClient.setQueryData(['page', pageId.value], restoredPage)
    await queryClient.invalidateQueries({ queryKey: ['page-versions', pageId.value] })
    await queryClient.invalidateQueries({ queryKey: ['pages-by-project', projectId.value] })
    await queryClient.invalidateQueries({ queryKey: ['page-component-index', pageId.value] })
    syncPageIntoEditor(restoredPage)
    previewUrl.value = ''
    previewFilePath.value = ''
    previewViewport.value = { ...DEFAULT_PREVIEW_VIEWPORT }
    Message.success(`已恢复到 ${displayLabel}，并生成新的最新版本。`)
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复页面版本失败。'))
  } finally {
    restoringVersionNo.value = null
  }
}

/**
 * 推送草稿生成整体预览，设定当前页为入口路由。
 */
async function syncRuntimePreview(
  page: Pick<PageItem, 'id' | 'code' | 'file_type'>,
  options: { showSuccessMessage?: boolean } = {},
): Promise<boolean> {
  isPreviewPending.value = true
  try {
    const entryRoute = `src/views/${page.code}.${page.file_type}`
    const previewLink = await createProjectPreviewArtifact(projectId.value, entryRoute)

    applyPreviewLink(previewLink)
    if (options.showSuccessMessage) {
      Message.success('已成功推送草稿信息并加载运行时预览。')
    }
    return true
  } catch (error) {
    Message.error(getErrorMessage(error, '生成草稿预览失败。'))
    return false
  } finally {
    isPreviewPending.value = false
  }
}
</script>

<style scoped>
.page-detail-title-actions :deep(.btn) {
  min-height: 1.75rem;
  border-radius: 0.5rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
}

.page-detail-title-actions :deep(.btn > span:last-child) {
  gap: 0.375rem;
}

.page-detail-identity-action {
  display: inline-flex;
  height: 1.625rem;
  width: 1.625rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  border: 1px solid rgb(226 232 240);
  background: rgb(248 250 252);
  color: rgb(100 116 139);
  transition: all 0.2s ease;
}

.page-detail-identity-action:hover {
  border-color: rgb(199 210 254);
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}

.page-detail-identity-action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
