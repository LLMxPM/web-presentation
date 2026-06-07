<!-- 文件功能：项目建议引用内容资源弹窗，支持选择一组项目级 AI 参考素材。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    title="项目建议资源"
    size="wide"
    body-preset="dense"
    @update:model-value="handleVisibleChange"
  >
    <div v-if="projectId && workspaceId" class="grid h-full min-h-0 grid-rows-[minmax(220px,0.95fr)_minmax(0,1.05fr)] gap-4 overflow-hidden lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)] lg:grid-rows-1">
      <section class="flex h-full min-h-0 flex-col rounded-lg border border-indigo-100 bg-indigo-50/40 p-3">
        <div class="flex shrink-0 items-center justify-between gap-2">
          <div class="flex min-w-0 items-center gap-2">
            <Image class="h-4 w-4 shrink-0 text-indigo-600" />
            <h4 class="truncate text-sm font-bold text-indigo-700">已选资源</h4>
          </div>
          <span class="rounded-full bg-white px-2 py-0.5 text-xs font-semibold text-indigo-600">
            {{ selectedAssetIds.length }}
          </span>
        </div>

        <div v-if="loading" class="flex min-h-0 flex-1 items-center justify-center text-sm font-semibold text-slate-400">
          <RefreshCw class="mr-2 h-4 w-4 animate-spin" />
          正在加载
        </div>
        <div v-else-if="selectedAssetSummaries.length" class="asset-column-scroll mt-3 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          <article
            v-for="asset in selectedAssetSummaries"
            :key="asset.id"
            class="flex w-full min-w-0 items-center justify-between gap-2 rounded-md border border-indigo-200 bg-white px-3 py-2 text-left transition hover:border-indigo-300"
          >
            <span class="min-w-0 text-left">
              <span class="block truncate text-xs font-bold text-slate-800">{{ asset.name }}</span>
              <span class="mt-0.5 block truncate text-[11px] text-slate-400">{{ asset.original_name }}</span>
            </span>
            <span class="inline-flex shrink-0 items-center gap-1">
              <span class="rounded-full bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-600">
                {{ resolveAssetTypeLabel(asset.asset_type) }}
              </span>
              <button
                type="button"
                class="rounded-md p-1 text-indigo-500 transition hover:bg-indigo-50 hover:text-indigo-700"
                :aria-label="`预览资源 ${asset.name}`"
                :title="`预览 ${asset.name}`"
                @click="openAssetPreview(asset)"
              >
                <ZoomIn class="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                class="rounded-md p-1 text-indigo-500 transition hover:bg-indigo-50 hover:text-indigo-700"
                :aria-label="`移除资源 ${asset.name}`"
                :title="`移除 ${asset.name}`"
                @click="removeAsset(asset.id)"
              >
                <X class="h-3.5 w-3.5" />
              </button>
            </span>
          </article>
        </div>
        <p v-else class="mt-3 flex min-h-0 flex-1 items-center justify-center text-xs text-slate-400">未选择资源</p>
      </section>

      <section class="flex h-full min-h-0 flex-col rounded-lg border border-slate-200 bg-white p-3">
        <div class="grid shrink-0 grid-cols-[minmax(0,1fr)_auto_auto_auto] gap-2">
          <BaseInput
            :model-value="assetKeyword"
            placeholder="按资源 name 搜索"
            @update:model-value="assetKeyword = String($event)"
            @keyup.enter="loadAvailableAssets"
          />
          <BaseButton
            variant="secondary"
            :loading="assetOptionsLoading"
            custom-class="h-11 min-w-[80px] whitespace-nowrap"
            @click="loadAvailableAssets"
          >
            <template #icon>
              <Search class="h-4 w-4" />
            </template>
            搜索
          </BaseButton>
          <BaseButton
            variant="ghost"
            size="sm"
            :loading="assetOptionsLoading"
            custom-class="h-11 min-w-[64px] whitespace-nowrap"
            @click="loadAvailableAssets"
          >
            <template #icon>
              <RefreshCw class="h-4 w-4" />
            </template>
            刷新
          </BaseButton>
          <BaseButton
            variant="secondary"
            size="sm"
            :loading="uploading"
            :disabled="!projectId || !workspaceId || loading || saving"
            custom-class="h-11 min-w-[108px] whitespace-nowrap"
            :title="uploadButtonTitle"
            @click="triggerUpload"
          >
            <template #icon>
              <Upload class="h-4 w-4" />
            </template>
            {{ uploadButtonText }}
          </BaseButton>
          <input
            :ref="setUploadFileInput"
            type="file"
            class="hidden"
            multiple
            :accept="uploadAccept"
            @change="handleUploadFileChange"
          />
        </div>

        <div class="mt-3 flex shrink-0 flex-wrap gap-1.5">
          <button
            v-for="tab in assetTypeTabs"
            :key="tab.key"
            type="button"
            class="inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-semibold transition"
            :class="activeAssetTypeTab === tab.key ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
            @click="activeAssetTypeTab = tab.key"
          >
            <span>{{ tab.label }}</span>
            <span class="rounded-full px-1 text-[10px]" :class="activeAssetTypeTab === tab.key ? 'bg-white/20 text-white' : 'bg-white text-slate-500'">
              {{ tab.count }}
            </span>
          </button>
        </div>

        <div v-if="assetOptionsLoading" class="mt-3 flex min-h-0 flex-1 items-center justify-center text-sm font-semibold text-slate-400">
          <RefreshCw class="mr-2 h-4 w-4 animate-spin" />
          正在加载资源
        </div>
        <div v-else-if="activeTabAssets.length" class="asset-column-scroll mt-3 grid min-h-0 flex-1 content-start gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
          <article
            v-for="asset in activeTabAssets"
            :key="asset.id"
            class="flex min-h-16 min-w-0 items-stretch justify-between gap-1 rounded-md border text-left transition"
            :class="assetOptionClass(asset.id)"
          >
            <button
              type="button"
              class="flex min-w-0 flex-1 items-center justify-between gap-2 px-3 py-2 text-left"
              @click="toggleAsset(asset.id)"
            >
              <span class="min-w-0 text-left">
                <span class="block truncate text-xs font-bold">{{ asset.name }}</span>
                <span class="mt-0.5 block truncate text-[11px] opacity-70">{{ asset.original_name }}</span>
                <span v-if="asset.description" class="mt-0.5 block truncate text-[11px] opacity-70">{{ asset.description }}</span>
              </span>
              <Check v-if="isSelected(asset.id)" class="h-4 w-4 shrink-0" />
              <Plus v-else class="h-4 w-4 shrink-0" />
            </button>
            <button
              type="button"
              class="flex w-9 shrink-0 items-center justify-center rounded-r-md border-l border-current/10 opacity-80 transition hover:bg-white/60 hover:opacity-100"
              :aria-label="`预览资源 ${asset.name}`"
              :title="`预览 ${asset.name}`"
              @click="openAssetPreview(asset)"
            >
              <ZoomIn class="h-4 w-4" />
            </button>
          </article>
        </div>
        <p v-else class="mt-3 flex min-h-0 flex-1 items-center justify-center text-xs text-slate-400">没有匹配的内容资源</p>
      </section>
    </div>

    <div v-else class="py-10 text-center text-sm text-slate-400">
      当前没有可编辑的项目。
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="ghost" :disabled="loading || saving || uploading || !projectId" @click="loadDialogData">恢复当前值</BaseButton>
      <BaseButton variant="primary" :loading="saving" :disabled="!projectId || !workspaceId || uploading" @click="saveSelection">
        保存资源
      </BaseButton>
    </template>
  </BaseDialog>

  <BaseDialog
    :model-value="!!previewAsset"
    :title="previewDialogTitle"
    size="wide"
    body-preset="split"
    :z-index="1110"
    @update:model-value="handlePreviewVisibleChange"
  >
    <AssetPreviewFrame class="h-full" :workspace-id="workspaceId" :asset="previewAsset" />
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Image, Plus, RefreshCw, Search, Upload, X, ZoomIn } from '@lucide/vue'

import { listWorkspaceAssets } from '@/api/assets'
import {
  getProjectSuggestedReferenceAssets,
  updateProjectSuggestedReferenceAssets,
} from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import AssetPreviewFrame from '@/components/project/AssetPreviewFrame.vue'
import type { AssetResponse, AssetType, ProjectSuggestedReferenceAssetItem } from '@/types/api'
import { Message } from '@/utils/message'
import {
  PROJECT_SUGGESTED_REFERENCE_ASSET_TYPES,
  type ProjectSuggestedReferenceAssetTabKey,
} from './project-suggested-reference-assets'
import { useProjectSuggestedReferenceAssetUpload } from './project-suggested-reference-upload'

type ReferenceAssetSummary = Pick<ProjectSuggestedReferenceAssetItem, 'id' | 'name' | 'original_name' | 'description' | 'asset_type'>
type PreviewAssetTarget = Pick<ProjectSuggestedReferenceAssetItem, 'id' | 'name'> & { file_hash?: string }

const props = defineProps<{
  modelValue: boolean
  projectId: number | null
  workspaceId: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [items: ProjectSuggestedReferenceAssetItem[]]
}>()

const CONTENT_ASSET_TYPES = PROJECT_SUGGESTED_REFERENCE_ASSET_TYPES
const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  image: '图片',
  icon: '图标',
  font: '字体',
  video: '视频',
  drawio: 'Draw.io',
  mermaid: 'Mermaid',
  chart: '图表',
  formula: '公式',
}

const loading = ref(false)
const saving = ref(false)
const assetOptionsLoading = ref(false)
const assetOptions = ref<AssetResponse[]>([])
const savedAssets = ref<ProjectSuggestedReferenceAssetItem[]>([])
const selectedAssetIds = ref<number[]>([])
const assetKeyword = ref('')
const activeAssetTypeTab = ref<ProjectSuggestedReferenceAssetTabKey>('all')
const previewAsset = ref<PreviewAssetTarget | null>(null)

const {
  uploading,
  uploadFileInput,
  uploadAccept,
  uploadButtonTitle,
  triggerUpload,
  handleUploadFileChange,
} = useProjectSuggestedReferenceAssetUpload({
  getProjectId: () => props.projectId,
  getWorkspaceId: () => props.workspaceId,
  activeAssetTypeTab,
  assetOptions,
  selectedAssetIds,
  savedAssets,
  emitSaved: items => emit('saved', items),
  resolveAssetTypeLabel,
})
const selectedAssetIdSet = computed(() => new Set(selectedAssetIds.value))
const assetOptionSummaryById = computed(() => {
  const result = new Map<number, ReferenceAssetSummary>()
  for (const asset of assetOptions.value) {
    result.set(asset.id, toAssetSummary(asset))
  }
  for (const asset of savedAssets.value) {
    if (!result.has(asset.id)) {
      result.set(asset.id, asset)
    }
  }
  return result
})
const selectedAssetSummaries = computed(() => selectedAssetIds.value
  .map(id => assetOptionSummaryById.value.get(id))
  .filter((asset): asset is ReferenceAssetSummary => !!asset))
const groupedAssetOptions = computed(() => CONTENT_ASSET_TYPES.map(type => ({
  type,
  label: ASSET_TYPE_LABELS[type],
  items: assetOptions.value.filter(asset => asset.asset_type === type),
})))
const assetTypeTabs = computed(() => [
  { key: 'all' as const, label: '全部', count: assetOptions.value.length },
  ...groupedAssetOptions.value.map(group => ({
    key: group.type,
    label: group.label,
    count: group.items.length,
  })),
])
const activeTabAssets = computed(() => {
  if (activeAssetTypeTab.value === 'all') {
    return assetOptions.value
  }
  return assetOptions.value.filter(asset => asset.asset_type === activeAssetTypeTab.value)
})
const uploadButtonText = computed(() => (
  activeAssetTypeTab.value === 'all'
    ? '上传并关联'
    : `上传${resolveAssetTypeLabel(activeAssetTypeTab.value)}`
))
const previewDialogTitle = computed(() => previewAsset.value ? `资源预览：${previewAsset.value.name}` : '资源预览')

watch(
  () => [props.modelValue, props.projectId, props.workspaceId] as const,
  ([visible]) => {
    if (visible) {
      void loadDialogData()
    }
  },
  { immediate: true },
)

watch(assetTypeTabs, (tabs) => {
  if (!tabs.some(tab => tab.key === activeAssetTypeTab.value)) {
    activeAssetTypeTab.value = 'all'
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
 * 并行读取已保存建议资源与可选内容资源。
 */
async function loadDialogData(): Promise<void> {
  if (!props.projectId || !props.workspaceId) {
    return
  }
  loading.value = true
  try {
    await Promise.all([loadSavedAssets(), loadAvailableAssets()])
  } finally {
    loading.value = false
  }
}

/**
 * 读取项目当前已保存的建议引用资源。
 */
async function loadSavedAssets(): Promise<void> {
  if (!props.projectId) {
    return
  }
  try {
    const response = await getProjectSuggestedReferenceAssets(props.projectId)
    savedAssets.value = response.items
    selectedAssetIds.value = response.items.map(asset => asset.id)
  } catch (error) {
    Message.error(getErrorMessage(error, '加载项目建议资源失败。'))
  }
}

/**
 * 读取当前工作空间可选内容资源。
 */
async function loadAvailableAssets(): Promise<void> {
  if (!props.workspaceId) {
    return
  }
  assetOptionsLoading.value = true
  try {
    const response = await listWorkspaceAssets(props.workspaceId, {
      assetRole: 'content',
      page: 1,
      page_size: 100,
      keyword: assetKeyword.value.trim() || undefined,
    })
    assetOptions.value = response.items.filter(asset => CONTENT_ASSET_TYPES.includes(asset.asset_type))
  } catch (error) {
    Message.error(getErrorMessage(error, '加载内容资源失败。'))
  } finally {
    assetOptionsLoading.value = false
  }
}

/**
 * 切换资源选择状态。
 * @param assetId 资源 ID
 */
function toggleAsset(assetId: number): void {
  if (selectedAssetIdSet.value.has(assetId)) {
    removeAsset(assetId)
    return
  }
  selectedAssetIds.value = [...selectedAssetIds.value, assetId]
}

/**
 * 从已选列表移除资源。
 * @param assetId 资源 ID
 */
function removeAsset(assetId: number): void {
  selectedAssetIds.value = selectedAssetIds.value.filter(id => id !== assetId)
}

/**
 * 判断资源是否已选择。
 * @param assetId 资源 ID
 */
function isSelected(assetId: number): boolean {
  return selectedAssetIdSet.value.has(assetId)
}

/**
 * 接收模板中的隐藏文件输入引用，供上传按钮主动触发选择文件。
 * @param element Vue ref 回调传入的 DOM 节点或组件实例
 */
function setUploadFileInput(element: unknown): void {
  uploadFileInput.value = element instanceof HTMLInputElement ? element : null
}

/**
 * 打开资源预览弹窗。
 * @param asset 待预览资源摘要或完整资源
 */
function openAssetPreview(asset: ReferenceAssetSummary | AssetResponse): void {
  previewAsset.value = {
    id: asset.id,
    name: asset.name,
    file_hash: 'file_hash' in asset ? asset.file_hash : undefined,
  }
}

/**
 * 同步资源预览弹窗可见状态。
 * @param value 目标可见状态
 */
function handlePreviewVisibleChange(value: boolean): void {
  if (!value) {
    previewAsset.value = null
  }
}

/**
 * 保存当前建议资源选择。
 */
async function saveSelection(): Promise<void> {
  if (!props.projectId) {
    return
  }
  saving.value = true
  try {
    const response = await updateProjectSuggestedReferenceAssets(props.projectId, selectedAssetIds.value)
    savedAssets.value = response.items
    selectedAssetIds.value = response.items.map(asset => asset.id)
    emit('saved', response.items)
    handleVisibleChange(false)
    Message.success('项目建议资源已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存项目建议资源失败。'))
  } finally {
    saving.value = false
  }
}

/**
 * 转换工作空间资源为弹窗内部摘要。
 * @param asset 工作空间资源
 */
function toAssetSummary(asset: AssetResponse): ReferenceAssetSummary {
  return {
    id: asset.id,
    name: asset.name,
    original_name: asset.original_name,
    description: asset.description,
    asset_type: asset.asset_type,
  }
}

/**
 * 解析资源类型中文标签。
 * @param assetType 资源类型
 */
function resolveAssetTypeLabel(assetType: AssetType): string {
  return ASSET_TYPE_LABELS[assetType] ?? '资源'
}

/**
 * 生成资源按钮样式。
 * @param assetId 资源 ID
 */
function assetOptionClass(assetId: number): string {
  if (isSelected(assetId)) {
    return 'border-indigo-200 bg-indigo-50 text-indigo-700'
  }
  return 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
}
</script>

<style scoped>
.asset-column-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgb(203 213 225) transparent;
}

.asset-column-scroll::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}

.asset-column-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.asset-column-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgb(203 213 225);
}
</style>

