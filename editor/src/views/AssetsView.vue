<!-- 文件功能：提供工作空间级资源库页面，承载资源筛选、视觉预览、详情编辑、比例重算、引用检查与归档恢复删除。 -->
<template>
  <div data-testid="assets-view" class="flex h-full min-h-0 flex-col gap-2">
    <PageHeader class="shrink-0" :icon="Image" :title="workspaceTitle" description="集中管理工作空间资源，支持筛选、批量维护与引用检查。">
      <template #actions>
        <UiButton variant="secondary" :disabled="!workspaceId || uploading" @click="openUploadForm">
          <Upload class="h-3.5 w-3.5" />
          {{ uploading ? '上传中' : '上传资源' }}
        </UiButton>
        <UiButton variant="secondary" :disabled="!workspaceId || packageImporting" @click="triggerPackageImport">
          <Upload class="h-3.5 w-3.5" />
          {{ packageImporting ? '导入中' : '导入资源包' }}
        </UiButton>
        <UiButton :disabled="!workspaceId" @click="openCreateForm">
          <FilePlus2 class="h-3.5 w-3.5" />
          新建内容资源
        </UiButton>
      </template>
    </PageHeader>

    <div class="grid min-h-0 flex-1 grid-cols-[240px_minmax(0,1fr)] gap-2 overflow-hidden">
      <AssetFilterSidebar
        v-model:active-view="activeView"
        v-model:asset-type-filter="assetTypeFilter"
        v-model:search-keyword="searchKeyword"
        v-model:sort-value="sortValue"
        v-model:active-tag-filter="activeTagFilter"
        :available-tag-options="availableTagOptions"
        @submit-search="refreshAssets"
      />

      <ToolPanel class="min-h-0 min-w-0">
        <template #header>
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="min-w-0">
              <h2 class="text-title-sm font-semibold text-[rgb(var(--ui-text))]">资源预览</h2>
              <p class="mt-0.5 text-xs text-[rgb(var(--ui-text-muted))]">选择资源后可执行批量操作。</p>
            </div>
            <div class="flex min-w-0 flex-wrap items-center gap-2">
              <UiButton
                variant="secondary"
                size="sm"
                :disabled="!selectionMode && assets.length === 0"
                :title="selectionMode ? '退出批量操作选择模式' : '进入选择模式后勾选要批量处理的资源'"
                @click="toggleSelectionMode"
              >
                <ListChecks class="h-3.5 w-3.5" />
                {{ selectionMode ? '退出选择' : '批量操作' }}
              </UiButton>
              <UiIconButton label="刷新资源" size="sm" @click="refreshAssets"><RefreshCw /></UiIconButton>
            </div>
          </div>
        </template>

        <SelectionToolbar
          v-if="selectionMode"
          class="mb-3 shrink-0"
          :count="selectedCount"
          label="资源批量操作"
          @clear="clearBatchSelection"
        >
          <UiButton
            variant="ghost"
            size="sm"
            :disabled="assets.length === 0"
            @click="toggleCurrentPageSelection()"
          >
            {{ allCurrentPageSelected ? '取消全选' : '全选' }}
          </UiButton>
          <UiButton
            v-if="activeView === 'active'"
            variant="secondary"
            size="sm"
            :disabled="!hasBackfillableBatchSelection || batchOperating || backfillRunning"
            :title="hasBackfillableBatchSelection ? '重新计算选中资源比例' : '选中资源中没有可计算比例的资源'"
            @click="openSelectedBackfillDialog"
          >
            <Ruler class="h-3.5 w-3.5" />
            {{ backfillRunning ? '计算中' : '重算比例' }}
          </UiButton>
          <UiButton
            variant="ghost"
            size="sm"
            :disabled="!hasBatchSelection || batchOperating"
            @click="exportSelectedAssets"
          >
            <Download class="h-3.5 w-3.5" />
            {{ batchExporting ? '导出中' : '导出' }}
          </UiButton>
          <UiButton
            v-if="activeView === 'active'"
            variant="ghost"
            size="sm"
            :disabled="!hasBatchSelection || batchOperating"
            @click="archiveSelectedAssets"
          >
            <Archive class="h-3.5 w-3.5" />
            归档
          </UiButton>
          <UiButton
            v-if="activeView === 'archived'"
            variant="ghost"
            size="sm"
            :disabled="!hasBatchSelection || batchOperating"
            @click="restoreSelectedAssets"
          >
            <RotateCcw class="h-3.5 w-3.5" />
            恢复
          </UiButton>
          <UiButton
            v-if="activeView !== 'active'"
            variant="danger"
            size="sm"
            :disabled="!hasBatchSelection || batchOperating"
            @click="deleteSelectedAssets"
          >
            <Trash2 class="h-3.5 w-3.5" />
            删除
          </UiButton>
          <UiButton variant="ghost" size="xs" class="ml-auto" @click="exitSelectionMode">
            退出
          </UiButton>
        </SelectionToolbar>

        <DataState
          :state="assetDataState"
          :title="assetDataState === 'empty' ? emptyAssetText : undefined"
          :description="assetDataState === 'empty' ? '调整筛选条件，或上传第一项资源。' : undefined"
          @retry="refreshAssets"
        >
          <div class="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3">
            <article
              v-for="asset in assets"
              :key="asset.id"
              class="group cursor-pointer overflow-hidden rounded-lg border bg-surface transition-all hover:-translate-y-0.5 hover:border-accent-border hover:shadow-md"
              :class="resolveAssetCardClass(asset)"
              @click="handleAssetCardClick(asset)"
            >
              <div class="relative aspect-[16/10] bg-canvas">
                <label
                  v-if="selectionMode"
                  class="absolute left-2 top-2 z-10 inline-flex h-7 w-7 items-center justify-center rounded-md border border-surface/80 bg-surface/95 shadow-sm"
                  @click.stop
                >
                  <UiCheckbox
                    :model-value="isAssetSelected(asset.id)"
                    :aria-label="`选择资源 ${asset.name}`"
                    @update:model-value="toggleAssetSelection(asset.id)"
                  />
                </label>
                <img
                  v-if="isImage(asset.original_name) && asset.url"
                  :src="asset.url"
                  class="h-full w-full object-contain"
                  :class="asset.asset_type === 'icon' ? 'p-8' : 'p-2.5'"
                  loading="lazy"
                />
                <PenTool v-else-if="asset.asset_type === 'drawio'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-warning" />
                <Workflow v-else-if="asset.asset_type === 'mermaid'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-cyan-500" />
                <BarChart3 v-else-if="asset.asset_type === 'chart'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-success" />
                <Sigma v-else-if="asset.asset_type === 'formula'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-ai" />
                <Video v-else-if="asset.asset_type === 'video'" class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-danger" />
                <FileText v-else class="absolute left-1/2 top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 text-text-disabled" />

                <div class="absolute inset-0 flex items-center justify-center gap-2 bg-overlay/0 opacity-0 transition-all group-hover:bg-overlay/20 group-hover:opacity-100">
                  <UiIconButton
                    label="打开详情"
                    size="sm"
                    variant="secondary"
                    class="rounded-full shadow-sm"
                    @click.stop="openAssetDetail(asset)"
                  >
                    <ZoomIn class="h-3.5 w-3.5" />
                  </UiIconButton>
                  <UiIconButton
                    label="复制资源 name"
                    size="sm"
                    variant="secondary"
                    class="rounded-full shadow-sm"
                    @click.stop="copyAssetName(asset)"
                  >
                    <Copy class="h-3.5 w-3.5" />
                  </UiIconButton>
                </div>
              </div>
              <div class="space-y-1.5 p-2.5">
                <div class="flex items-center justify-between gap-2">
                  <h3 class="truncate text-[13px] font-bold text-text">{{ asset.name }}</h3>
                  <span class="shrink-0 rounded bg-surface-muted px-1.5 py-0.5 text-[10px] font-black uppercase text-text-muted">{{ asset.asset_type }}</span>
                </div>
                <div class="flex items-center justify-between gap-2 text-[10px] font-bold text-text-disabled">
                  <span class="truncate font-mono">{{ asset.original_name }}</span>
                  <span class="shrink-0">{{ resolveAssetStatusBadgeText(asset) }}</span>
                </div>
              </div>
            </article>
          </div>
        </DataState>

        <template #footer>
          <PaginationControl
            :page="page"
            :page-size="pageSize"
            :total="total"
            :page-size-options="[12, 24, 48, 96]"
            @update:page="handlePageChange"
            @update:page-size="handlePageSizeChange"
          />
        </template>
      </ToolPanel>

    </div>

    <input
      ref="replaceFileInput"
      type="file"
      class="hidden"
      :accept="detail.activeReplaceAccept.value"
      @change="handleReplaceFileChange"
    />
    <input
      ref="uploadFileInput"
      type="file"
      class="hidden"
      :accept="activeUploadAccept"
      multiple
      @change="handleUploadFileChange"
    />
    <input ref="packageFileInput" type="file" class="hidden" accept=".zip,application/zip" @change="handlePackageFileChange" />

    <UiDialog
      :open="uploadMode"
      title="上传资源"
      description="选择资源类型后上传文件；同名资源会询问是否覆盖。"
      size="compact"
      body-preset="auto"
      :z-index="205"
      @update:open="value => { if (!value) closeUploadForm() }"
    >
      <div class="space-y-4">
        <div>
          <label class="mb-1 block text-xs font-bold text-text-muted">资源类型</label>
          <UiSelect v-model="uploadForm.asset_type" :options="assetTypeOptions" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-bold text-text-muted">标签，逗号分隔</label>
          <UiInput v-model="uploadTagsText" placeholder="可留空" />
        </div>
      </div>

      <template #footer>
        <UiButton variant="ghost" :disabled="uploading" @click="closeUploadForm">取消</UiButton>
        <UiButton :disabled="uploading" @click="triggerUploadSelect">
          <Upload class="h-3.5 w-3.5" />
          {{ uploading ? '上传中...' : '选择文件上传' }}
        </UiButton>
      </template>
    </UiDialog>

    <UiDialog
      :open="createMode"
      title="新建内容资源"
      description="支持 SVG 图片、SVG 图标、Draw.io、Mermaid、Chart 和 Formula。"
      size="wide"
      body-preset="editor"
      :z-index="210"
      @update:open="value => { if (!value) closeCreateForm() }"
    >
      <div class="flex h-full min-h-0 flex-col gap-2">
        <div class="grid gap-3 lg:grid-cols-[160px_minmax(0,1fr)_minmax(0,1fr)]">
          <UiSelect v-model="createForm.asset_type" :options="creatableTypes" />
          <UiInput v-model.trim="createForm.name" placeholder="资源 name，如 brand_icon" />
          <UiInput v-model.trim="createForm.original_name" placeholder="展示文件名，如 brand_icon.svg" />
        </div>
        <UiInput
          v-model="createForm.content"
          type="textarea"
          textarea-mode="fill"
          class="min-w-0 flex-1 font-mono text-xs leading-5"
          placeholder="输入 SVG 图片 / SVG 图标 / Draw.io XML / Mermaid / Chart JSON/YAML / Formula 内容"
        />
      </div>

      <template #footer>
        <p class="mr-auto text-xs text-text-muted">SVG 会拒绝脚本、事件属性、foreignObject 与远程引用。</p>
        <UiButton variant="ghost" size="sm" @click="closeCreateForm">取消</UiButton>
        <UiButton :disabled="saving" @click="createAsset">创建资源</UiButton>
      </template>
    </UiDialog>

    <UiDialog
      :open="backfillDialogVisible"
      title="重新计算选中资源比例"
      description="通过静态解析或 Runtime 渲染测量选中资源，计算可供 AI 布局参考的近似比例。"
      size="wide"
      body-preset="auto"
      :z-index="215"
      @update:open="value => { if (!value) closeBackfillDialog() }"
    >
      <div class="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
        <section class="space-y-4 rounded-xl border border-border bg-canvas p-4">
          <div>
            <h3 class="mb-2 text-xs font-black uppercase tracking-widest text-text-disabled">资源类型</h3>
            <label class="mb-2 flex items-center gap-2 text-sm font-bold text-text-emphasis">
              <UiCheckbox v-model="backfillForm.image" />
              Image
            </label>
            <label class="mb-2 flex items-center gap-2 text-sm font-bold text-text-emphasis">
              <UiCheckbox v-model="backfillForm.video" />
              Video
            </label>
            <label class="mb-2 flex items-center gap-2 text-sm font-bold text-text-emphasis">
              <UiCheckbox v-model="backfillForm.drawio" />
              Draw.io
            </label>
            <label class="mb-2 flex items-center gap-2 text-sm font-bold text-text-emphasis">
              <UiCheckbox v-model="backfillForm.formula" />
              Formula
            </label>
            <label class="flex items-center gap-2 text-sm font-bold text-text-emphasis">
              <UiCheckbox v-model="backfillForm.mermaid" />
              Mermaid
            </label>
          </div>
          <div>
            <h3 class="mb-2 text-xs font-black uppercase tracking-widest text-text-disabled">范围</h3>
            <p class="rounded-lg bg-surface p-3 text-xs leading-5 text-text-muted">
              仅处理当前已勾选的 Image、Video、Draw.io、Formula、Mermaid 资源，其他类型会自动忽略。
            </p>
          </div>
          <div>
            <h3 class="mb-2 text-xs font-black uppercase tracking-widest text-text-disabled">模式</h3>
            <UiRadioGroup
              v-model="backfillForm.mode"
              aria-label="比例回填模式"
              :options="backfillModeOptions"
            />
          </div>
          <p class="rounded-lg bg-surface p-3 text-xs leading-5 text-text-muted">默认不会覆盖人工或内容助手维护的比例。预览模式只计算候选结果，不写入资源。</p>
        </section>

        <section class="min-h-[320px] rounded-xl border border-border bg-surface p-4">
          <div v-if="!backfillResult" class="flex h-full min-h-[260px] items-center justify-center text-center text-sm font-semibold text-text-disabled">
            运行后会在这里显示可更新、已跳过和失败资源。
          </div>
          <div v-else class="space-y-4">
            <div class="grid grid-cols-4 gap-2">
              <div class="rounded-lg bg-surface-selected p-3"><p class="text-[10px] font-black uppercase text-accent-border">可更新</p><p class="mt-1 text-lg font-black text-accent-hover">{{ backfillResult.succeeded_count }}</p></div>
              <div class="rounded-lg bg-canvas p-3"><p class="text-[10px] font-black uppercase text-text-disabled">已跳过</p><p class="mt-1 text-lg font-black text-text-emphasis">{{ backfillResult.skipped_count }}</p></div>
              <div class="rounded-lg bg-danger-muted p-3"><p class="text-[10px] font-black uppercase text-danger">失败</p><p class="mt-1 text-lg font-black text-danger-strong">{{ backfillResult.failed_count }}</p></div>
              <div class="rounded-lg bg-success-muted p-3"><p class="text-[10px] font-black uppercase text-success">总数</p><p class="mt-1 text-lg font-black text-success-strong">{{ backfillResult.requested_count }}</p></div>
            </div>
            <div class="max-h-[360px] overflow-y-auto rounded-lg border border-border-muted">
              <table class="w-full text-left text-xs">
                <thead class="sticky top-0 bg-canvas text-text-muted">
                  <tr>
                    <th class="px-3 py-2 font-black">资源</th>
                    <th class="px-3 py-2 font-black">类型</th>
                    <th class="px-3 py-2 font-black">当前</th>
                    <th class="px-3 py-2 font-black">计算后</th>
                    <th class="px-3 py-2 font-black">状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="job in backfillResult.jobs" :key="job.id" class="border-t border-border-muted">
                    <td class="max-w-[180px] truncate px-3 py-2 font-bold text-text-emphasis">{{ job.asset_name || `#${job.asset_id}` }}</td>
                    <td class="px-3 py-2 font-mono text-text-muted">{{ job.asset_type }}</td>
                    <td class="px-3 py-2 text-text-muted">{{ job.current_approx_aspect_ratio || '-' }}</td>
                    <td class="px-3 py-2 font-bold text-text-emphasis">{{ job.next_approx_aspect_ratio || '-' }}</td>
                    <td class="px-3 py-2" :title="job.error_message || ''">
                      <span class="font-bold text-text-secondary">{{ formatBackfillJobStatus(job.status) }}</span>
                      <p v-if="job.error_message" class="mt-1 max-w-[220px] truncate text-[11px] text-text-disabled">{{ job.error_message }}</p>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>

      <template #footer>
        <UiButton variant="ghost" :disabled="backfillRunning" @click="closeBackfillDialog">关闭</UiButton>
        <UiButton
          v-if="canApplyBackfillPreview"
          variant="ghost"
          :disabled="backfillRunning"
          @click="applyBackfillPreview"
        >
          应用可更新项
        </UiButton>
        <UiButton :disabled="backfillRunning || !hasBackfillTypeSelection" @click="runBackfillFromDialog">
          <Ruler class="h-3.5 w-3.5" />
          {{ backfillRunning ? '计算中...' : backfillForm.mode === 'apply' ? '开始写回' : '开始预览' }}
        </UiButton>
      </template>
    </UiDialog>

    <AssetDetailDialog
      :workspace-id="workspaceId"
      :detail="detail"
      :backfill-running="backfillRunning"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import {
  Archive,
  BarChart3,
  Copy,
  Download,
  FilePlus2,
  FileText,
  Image,
  ListChecks,
  PenTool,
  RefreshCw,
  RotateCcw,
  Ruler,
  Sigma,
  Trash2,
  Upload,
  Video,
  Workflow,
  ZoomIn,
} from '@lucide/vue'

import {
  createAssetRenderHintBackfillJobs,
  createWorkspaceAssetContent,
  importWorkspaceAssetPackage,
  listWorkspaceAssets,
  uploadWorkspaceAsset,
  waitForAssetRenderHintBackfillJobGroup,
} from '@/api/assets'
import { getWorkspace } from '@/api/catalog'
import { getErrorCode, getErrorMessage } from '@/api/http'
import DataState from '@/components/patterns/DataState.vue'
import PageHeader from '@/components/patterns/PageHeader.vue'
import SelectionToolbar from '@/components/patterns/SelectionToolbar.vue'
import ToolPanel from '@/components/patterns/ToolPanel.vue'
import { ASSET_UPLOAD_ACCEPT } from '@/components/project/asset-manager'
import type { AgentMutationRefreshEvent } from '@/components/agent/agent-mutation-refresh'
import { UiButton, UiCheckbox, UiDialog, UiIconButton, UiInput, UiRadioGroup, UiSelect } from '@/components/ui'
import PaginationControl from '@/components/ui/PaginationControl.vue'
import type { AssetRenderHintBackfillJobGroup, AssetRenderHintBackfillMode, AssetResponse, AssetType } from '@/types/api'
import { createConfirm, Message } from '@/utils/message'
import AssetDetailDialog from '@/views/assets/AssetDetailDialog.vue'
import AssetFilterSidebar from '@/views/assets/AssetFilterSidebar.vue'
import { useAssetBatchSelection } from '@/views/assets/useAssetBatchSelection'
import { useAssetDetail } from '@/views/assets/useAssetDetail'
import { useAssetListFilters } from '@/views/assets/useAssetListFilters'
import {
  ASSET_TYPE_OPTIONS,
  CREATABLE_ASSET_TYPES,
  isBackfillableAssetType,
  type BackfillableAssetType,
} from '@/views/asset-view-options'

const route = useRoute()
const loading = ref(false)
const assetsLoadError = ref(false)
const saving = ref(false)
const uploading = ref(false)
const packageImporting = ref(false)
const backfillRunning = ref(false)
const createMode = ref(false)
const uploadMode = ref(false)
const backfillDialogVisible = ref(false)
const assets = ref<AssetResponse[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(24)
const workspaceId = computed(() => Number.parseInt(route.params.workspaceId as string, 10))

function resetPage(): void {
  page.value = 1
}

const {
  activeView,
  assetTypeFilter,
  activeTag,
  searchKeyword,
  sortValue,
  activeTagFilter,
  availableTagOptions,
  emptyAssetText,
  buildListQueryParams,
  loadTags: loadTagsRaw,
} = useAssetListFilters({ onFilterResetPage: resetPage })

const detail = useAssetDetail({
  workspaceId,
  activeView,
  page,
  assets,
  backfillRunning,
  onRefresh: () => refreshAssets(),
  onRefreshWithPageFallback: () => refreshAssetsWithPageFallback(),
  onRefreshTags: () => loadTags(),
})

const {
  detailAsset,
  selectedAsset,
  openAssetDetail,
  syncDetailAssetAfterBackfill,
  resolveAssetStatusBadgeText,
  handleReplaceFileChange,
} = detail

const replaceFileInput = ref<HTMLInputElement | null>(null)
watch(replaceFileInput, (el) => {
  detail.replaceFileInput.value = el
}, { immediate: true })

const {
  selectionMode,
  batchOperating,
  batchExporting,
  selectedCount,
  hasBatchSelection,
  allCurrentPageSelected,
  selectedBackfillableAssets,
  hasBackfillableBatchSelection,
  isAssetSelected,
  toggleAssetSelection,
  toggleCurrentPageSelection,
  clearBatchSelection,
  toggleSelectionMode,
  exitSelectionMode,
  pruneBatchSelection,
  archiveSelectedAssets,
  restoreSelectedAssets,
  deleteSelectedAssets,
  exportSelectedAssets,
} = useAssetBatchSelection({
  workspaceId,
  activeView,
  assets,
  onAfterBatch: async (assetIds) => {
    detail.closeDetailIfSelected(assetIds)
    await refreshAssetsWithPageFallback()
  },
})

const uploadFileInput = ref<HTMLInputElement | null>(null)
const packageFileInput = ref<HTMLInputElement | null>(null)
const openedQueryAssetId = ref<number | null>(null)

const assetTypeOptions = ASSET_TYPE_OPTIONS
const creatableTypes = CREATABLE_ASSET_TYPES
const createForm = reactive({
  asset_type: 'icon' as AssetType,
  name: '',
  original_name: 'new_icon.svg',
  content: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3l8 18H4L12 3z"/></svg>',
})
const uploadForm = reactive({
  asset_type: 'image' as AssetType,
})
const uploadTagsText = ref('')
const backfillForm = reactive({
  image: true,
  video: true,
  drawio: true,
  formula: true,
  mermaid: true,
  mode: 'preview' as AssetRenderHintBackfillMode,
})
const backfillModeOptions = [
  { label: '预览结果', value: 'preview' },
  { label: '直接写回', value: 'apply' },
]
const backfillResult = ref<AssetRenderHintBackfillJobGroup | null>(null)

const workspaceQuery = useQuery(
  computed(() => ({
    queryKey: ['workspace', workspaceId.value],
    queryFn: () => getWorkspace(workspaceId.value),
    enabled: Number.isFinite(workspaceId.value),
  })),
)
const workspaceTitle = computed(() => {
  const workspaceName = workspaceQuery.data.value?.name
  return workspaceName ? `${workspaceName} · 资源库` : '资源库'
})
const activeUploadAccept = computed(() => ASSET_UPLOAD_ACCEPT[uploadForm.asset_type])
const hasBackfillTypeSelection = computed(() => (
  backfillForm.image
  || backfillForm.video
  || backfillForm.drawio
  || backfillForm.formula
  || backfillForm.mermaid
))
const selectedBackfillAssetTypes = computed<BackfillableAssetType[]>(() => {
  const types: BackfillableAssetType[] = []
  if (backfillForm.image) types.push('image')
  if (backfillForm.video) types.push('video')
  if (backfillForm.drawio) types.push('drawio')
  if (backfillForm.formula) types.push('formula')
  if (backfillForm.mermaid) types.push('mermaid')
  return types
})
const assetDataState = computed<'loading' | 'empty' | 'error' | 'ready'>(() => {
  if (loading.value) return 'loading'
  if (assetsLoadError.value) return 'error'
  return assets.value.length > 0 ? 'ready' : 'empty'
})
const backfillPreviewUpdatableAssetIds = computed(() => (
  backfillResult.value?.jobs
    .filter(job => job.status === 'succeeded' && Boolean(job.next_render_metadata))
    .map(job => job.asset_id) || []
))
const canApplyBackfillPreview = computed(() => (
  backfillForm.mode === 'preview'
  && backfillPreviewUpdatableAssetIds.value.length > 0
  && Boolean(backfillResult.value)
))


watch(
  [workspaceId, activeView, assetTypeFilter, activeTag, searchKeyword, sortValue, page, pageSize],
  () => {
    void refreshAssets()
  },
  { immediate: true },
)

watch([activeView, assetTypeFilter, activeTag, searchKeyword, sortValue, page, pageSize], () => {
  clearBatchSelection()
})

watch([workspaceId, activeView, assetTypeFilter], ([id]) => {
  if (Number.isFinite(id)) {
    void loadTags()
  }
}, { immediate: true })

watch(
  () => createForm.asset_type,
  (type) => {
    const next = defaultCreateTemplate(type)
    createForm.original_name = next.originalName
    createForm.content = next.content
  },
)



async function refreshAssets(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  loading.value = true
  assetsLoadError.value = false
  try {
    const response = await listWorkspaceAssets(workspaceId.value, {
      ...buildListQueryParams(),
      page: page.value,
      page_size: pageSize.value,
    })
    assets.value = response.items
    total.value = response.total
    pruneBatchSelection()
    syncSelectionAfterListLoad()
    openQueryAssetIfNeeded()
  } catch (error) {
    assetsLoadError.value = true
    Message.error(getErrorMessage(error, '读取资源列表失败'))
  } finally {
    loading.value = false
  }
}

async function loadTags(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  await loadTagsRaw(workspaceId.value)
}

function syncSelectionAfterListLoad(): void {
  if (!selectedAsset.value) {
    selectedAsset.value = assets.value[0] ?? null
    detail.referenceSummary.value = null
    return
  }
  const latest = assets.value.find(asset => asset.id === selectedAsset.value?.id) ?? null
  selectedAsset.value = latest ?? assets.value[0] ?? null
  if (detailAsset.value) {
    detailAsset.value = assets.value.find(asset => asset.id === detailAsset.value?.id) ?? detailAsset.value
  }
}

/**
 * 卡片点击：选择模式下切换勾选，否则打开资源详情。
 * @param asset 当前资源
 */
function handleAssetCardClick(asset: AssetResponse): void {
  if (selectionMode.value) {
    toggleAssetSelection(asset.id)
    return
  }
  void openAssetDetail(asset)
}



function handleGlobalAgentAssetUpdated(event: Event): void {
  const payload = (event as CustomEvent<AgentMutationRefreshEvent>).detail
  if (!payload) {
    return
  }
  if (payload.workspaceId !== null && payload.workspaceId !== undefined && Number(payload.workspaceId) !== workspaceId.value) {
    return
  }
  const updatedAssetId = Number(payload.assetId)
  void refreshAssets()
  void loadTags()
  if (Number.isFinite(updatedAssetId) && detail.detailAsset.value?.id === updatedAssetId) {
    if (detail.detailTab.value === 'content') {
      void detail.loadContent()
    }
    if (detail.detailTab.value === 'references') {
      void detail.loadReferences()
    }
  }
}

function openQueryAssetIfNeeded(): void {
  const assetId = Number(route.query.assetId)
  if (!Number.isFinite(assetId) || openedQueryAssetId.value === assetId) return
  const matched = assets.value.find(asset => asset.id === assetId)
  if (!matched) return
  openedQueryAssetId.value = assetId
  void openAssetDetail(matched)
}

function openUploadForm(): void {
  uploadForm.asset_type = assetTypeFilter.value || 'image'
  uploadTagsText.value = activeTag.value || ''
  uploadMode.value = true
}

function closeUploadForm(): void {
  if (uploading.value) return
  uploadMode.value = false
}

function triggerUploadSelect(): void {
  uploadFileInput.value?.click()
}

async function handleUploadFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  if (!Number.isFinite(workspaceId.value) || files.length === 0) {
    target.value = ''
    return
  }

  uploading.value = true
  let successCount = 0
  let firstUploaded: AssetResponse | null = null
  let firstError = ''
  const tags = uploadTagsText.value.split(/[,，]/).map(item => item.trim()).filter(Boolean)
  try {
    for (const file of files) {
      try {
        const uploaded = await uploadAssetWithOverwriteConfirm(file, tags)
        if (uploaded) {
          successCount += 1
          firstUploaded ||= uploaded
        }
      } catch (error) {
        firstError ||= getErrorMessage(error, '上传资源失败')
      }
    }
    if (successCount > 0) {
      Message.success(files.length === 1 ? '上传成功' : `已上传 ${successCount} 个资源`)
      uploadMode.value = false
      activeView.value = 'active'
      assetTypeFilter.value = uploadForm.asset_type
      page.value = 1
      await Promise.all([refreshAssets(), loadTags()])
      if (firstUploaded) {
        await openAssetDetail(firstUploaded)
      }
    }
    if (firstError) {
      Message.error(successCount > 0 ? `部分资源上传失败：${firstError}` : firstError)
    }
  } finally {
    uploading.value = false
    target.value = ''
  }
}

async function uploadAssetWithOverwriteConfirm(file: File, tags: string[]): Promise<AssetResponse | null> {
  try {
    return await uploadWorkspaceAsset(workspaceId.value, file, uploadForm.asset_type, tags)
  } catch (error) {
    if (getErrorCode(error) !== 'ASSET_NAME_CONFLICT') {
      throw error
    }
    const conflictMessage = getErrorMessage(error, `文件 "${file.name}" 已存在，请确认是否覆盖。`)
    const confirmed = await createConfirm(
      `${conflictMessage} 覆盖后现有页面、路由、主题和预览引用会指向新文件，确认覆盖吗？`,
      '覆盖同名资源',
    )
    if (!confirmed) return null
    return await uploadWorkspaceAsset(workspaceId.value, file, uploadForm.asset_type, tags, undefined, undefined, true)
  }
}

function openCreateForm(): void {
  createMode.value = true
}

function closeCreateForm(): void {
  createMode.value = false
}

async function createAsset(): Promise<void> {
  if (!Number.isFinite(workspaceId.value) || !createForm.name.trim() || !createForm.original_name.trim() || !createForm.content.trim()) {
    Message.warning('请填写资源 name、展示文件名和内容')
    return
  }
  saving.value = true
  try {
    const created = await createWorkspaceAssetContent(workspaceId.value, {
      asset_type: createForm.asset_type,
      name: createForm.name.trim(),
      original_name: createForm.original_name.trim(),
      content: createForm.content,
      tags: [],
    })
    Message.success('资源已创建')
    createMode.value = false
    activeView.value = 'active'
    page.value = 1
    await Promise.all([refreshAssets(), loadTags()])
    await openAssetDetail(created)
  } catch (error) {
    Message.error(getErrorMessage(error, '创建资源失败'))
  } finally {
    saving.value = false
  }
}

function openSelectedBackfillDialog(): void {
  if (!Number.isFinite(workspaceId.value) || activeView.value !== 'active') return
  const selectedAssets = selectedBackfillableAssets.value
  if (selectedAssets.length === 0) {
    Message.info('选中资源中没有可重新计算比例的资源。')
    return
  }
  backfillDialogVisible.value = true
  backfillResult.value = null
  backfillForm.image = selectedAssets.some(asset => asset.asset_type === 'image')
  backfillForm.video = selectedAssets.some(asset => asset.asset_type === 'video')
  backfillForm.drawio = selectedAssets.some(asset => asset.asset_type === 'drawio')
  backfillForm.formula = selectedAssets.some(asset => asset.asset_type === 'formula')
  backfillForm.mermaid = selectedAssets.some(asset => asset.asset_type === 'mermaid')
  backfillForm.mode = 'preview'
}

function closeBackfillDialog(): void {
  if (backfillRunning.value) return
  backfillDialogVisible.value = false
}

async function runBackfillFromDialog(): Promise<void> {
  if (!Number.isFinite(workspaceId.value) || !hasBackfillTypeSelection.value) return
  try {
    const assetIds = resolveSelectedBackfillAssetIds()
    if (assetIds.length === 0) {
      Message.info('选中资源中没有可重新计算比例的资源。')
      return
    }
    const completed = await executeBackfill({
      mode: backfillForm.mode,
      assetIds,
      assetTypes: selectedBackfillAssetTypes.value,
    })
    backfillResult.value = completed
    showBackfillResultMessage(completed, backfillForm.mode)
  } catch (error) {
    Message.error(getErrorMessage(error, '资源比例回填失败。'))
  }
}

async function applyBackfillPreview(): Promise<void> {
  const assetIds = backfillPreviewUpdatableAssetIds.value
  if (assetIds.length === 0) return
  try {
    const completed = await executeBackfill({
      mode: 'apply',
      assetIds,
      assetTypes: selectedBackfillAssetTypes.value,
    })
    backfillResult.value = completed
    showBackfillResultMessage(completed, 'apply')
  } catch (error) {
    Message.error(getErrorMessage(error, '应用资源比例回填结果失败。'))
  }
}

async function executeBackfill(options: {
  mode: AssetRenderHintBackfillMode
  assetIds?: number[]
  assetTypes: BackfillableAssetType[]
}): Promise<AssetRenderHintBackfillJobGroup> {
  backfillRunning.value = true
  try {
    let group = await createAssetRenderHintBackfillJobs(workspaceId.value, {
      asset_types: options.assetTypes,
      asset_ids: options.assetIds,
      mode: options.mode,
      overwrite_manual: false,
    })
    backfillResult.value = group
    if (group.requested_count > 0 && isBackfillGroupActive(group.status)) {
      group = await waitForAssetRenderHintBackfillJobGroup(group.job_group_id, {
        onProgress: nextGroup => {
          backfillResult.value = nextGroup
        },
      })
    }
    if (options.mode === 'apply') {
      await refreshAssets()
      syncDetailAssetAfterBackfill()
    }
    return group
  } finally {
    backfillRunning.value = false
  }
}

function resolveSelectedBackfillAssetIds(): number[] {
  return selectedBackfillableAssets.value
    .filter(asset => isBackfillAssetTypeSelected(asset.asset_type))
    .map(asset => asset.id)
}

function isBackfillAssetTypeSelected(assetType: AssetType): boolean {
  return isBackfillableAssetType(assetType) && selectedBackfillAssetTypes.value.includes(assetType)
}



function isBackfillGroupActive(status: AssetRenderHintBackfillJobGroup['status']): boolean {
  return status === 'pending' || status === 'running'
}

function showBackfillResultMessage(group: AssetRenderHintBackfillJobGroup, mode: AssetRenderHintBackfillMode): void {
  if (group.requested_count === 0) {
    Message.info('选中资源中没有需要重新计算比例的资源。')
    return
  }
  const actionText = mode === 'apply' ? '写回' : '计算'
  if (group.failed_count === 0) {
    Message.success(`资源比例${actionText}完成：可更新 ${group.succeeded_count} 个，跳过 ${group.skipped_count} 个。`)
    return
  }
  Message.warning(`资源比例${actionText}部分完成：失败 ${group.failed_count} 个，${group.failures[0]?.detail || '请查看结果列表。'}`)
}

/**
 * 打开资源包文件选择器。
 */
function triggerPackageImport(): void {
  packageFileInput.value?.click()
}

/**
 * 选择资源包后立即上传导入。
 */
async function handlePackageFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0] ?? null
  target.value = ''
  if (!file || !Number.isFinite(workspaceId.value)) return

  packageImporting.value = true
  try {
    const result = await importWorkspaceAssetPackage(workspaceId.value, file)
    if (result.failed_count > 0) {
      const firstFailure = result.failures[0]
      const importedText = result.imported_count > 0 ? `已导入 ${result.imported_count} 个资源，` : ''
      Message.warning(`${importedText}${result.failed_count} 个资源失败：${firstFailure?.detail || '请检查资源包内容'}`)
    } else {
      const updatedText = result.updated_count > 0 ? `，同步 ${result.updated_count} 个同名资源元数据` : ''
      const reusedText = result.reused_count > 0 ? `，复用 ${result.reused_count} 个同名资源` : ''
      Message.success(`已导入 ${result.imported_count} 个资源${updatedText}${reusedText}`)
    }
    activeView.value = 'active'
    page.value = 1
    await Promise.all([refreshAssets(), loadTags()])
  } catch (error) {
    Message.error(getErrorMessage(error, '导入资源包失败'))
  } finally {
    packageImporting.value = false
  }
}

async function copyAssetName(asset: AssetResponse): Promise<void> {
  try {
    await navigator.clipboard.writeText(asset.name)
    Message.success('资源 name 已复制到剪贴板。')
  } catch {
    Message.error('复制资源 name 失败，请检查浏览器剪贴板权限。')
  }
}

function resolveAssetCardClass(asset: AssetResponse): string {
  if (selectionMode.value && isAssetSelected(asset.id)) {
    return 'border-accent-ring bg-surface-selected/40'
  }
  if (selectedAsset.value?.id === asset.id) {
    return 'border-accent-border ring-1 ring-accent-ring'
  }
  return 'border-border'
}

function formatBackfillJobStatus(status: string): string {
  if (status === 'pending') return '等待中'
  if (status === 'running') return '计算中'
  if (status === 'succeeded') return '可更新'
  if (status === 'skipped') return '已跳过'
  if (status === 'failed') return '失败'
  return status || '-'
}

function isImage(name: string): boolean {
  return /\.(jpeg|jpg|png|gif|webp|svg)$/i.test(name)
}

function handlePageChange(nextPage: number): void {
  page.value = nextPage
}

function handlePageSizeChange(nextPageSize: number): void {
  pageSize.value = nextPageSize
  page.value = 1
}

async function refreshAssetsWithPageFallback(): Promise<void> {
  const currentPage = page.value
  await refreshAssets()
  if (assets.value.length === 0 && currentPage > 1) {
    page.value = currentPage - 1
  }
}

function defaultCreateTemplate(type: AssetType): { originalName: string; content: string } {
  if (type === 'image') {
    return {
      originalName: 'image.svg',
      content: [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 540">',
        '  <rect width="960" height="540" fill="#f8fafc"/>',
        '  <circle cx="480" cy="270" r="120" fill="#4f46e5" opacity="0.18"/>',
        '  <path d="M260 340C350 210 430 210 520 340s170 130 260 0" fill="none" stroke="#4f46e5" stroke-width="24" stroke-linecap="round"/>',
        '</svg>',
      ].join('\n'),
    }
  }
  if (type === 'drawio') return { originalName: 'diagram.drawio', content: '<mxfile><diagram name="Page-1"><mxGraphModel /></diagram></mxfile>' }
  if (type === 'mermaid') return { originalName: 'flow.mmd', content: 'flowchart TD\n  A[Start] --> B[Done]' }
  if (type === 'chart') return { originalName: 'chart.json', content: '{\n  "title": "示例图表",\n  "series": []\n}' }
  if (type === 'formula') return { originalName: 'formula.tex', content: 'E = mc^2' }
  return { originalName: 'new_icon.svg', content: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M12 3l8 18H4L12 3z"/></svg>' }
}

onMounted(() => {
  window.addEventListener('agent:asset-updated', handleGlobalAgentAssetUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('agent:asset-updated', handleGlobalAgentAssetUpdated)
})
</script>

