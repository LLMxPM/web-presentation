<!-- 文件功能：提供轻量资源侧边栏，用于快速浏览、预览、上传与跳转完整资源库。 -->
<template>
  <LibrarySidebarPanel
    :model-value="modelValue"
    title="资源库"
    show-search
    v-model:search-value="searchKeyword"
    search-placeholder="搜索资源名称、文件名、描述或标签..."
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #icon>
      <Image class="h-5 w-5 text-indigo-600" />
    </template>

    <template #actions>
      <button
        v-if="workspaceId"
        type="button"
        class="flex items-center gap-1 rounded-lg p-1.5 text-xs font-bold text-indigo-600 transition-colors hover:bg-indigo-50"
        title="打开完整资源库页面"
        @click="openAssetLibraryPage()"
      >
        <ArrowUpRight class="h-4 w-4" />
        <span class="hidden lg:inline">资源管理</span>
      </button>
      <button
        v-if="canCreateTextAsset"
        type="button"
        class="flex items-center gap-1 rounded-lg p-1.5 text-xs font-bold text-emerald-600 transition-colors hover:bg-emerald-50 disabled:opacity-50"
        title="文本创建资源"
        :disabled="uploading"
        @click="openTextCreateModal"
      >
        <FilePlus2 class="h-4 w-4" />
        <span class="hidden lg:inline">新建</span>
      </button>
      <button
        type="button"
        class="flex items-center gap-1 rounded-lg p-1.5 text-xs font-bold text-indigo-600 transition-colors hover:bg-indigo-50 disabled:opacity-50"
        title="上传资源"
        :disabled="uploading"
        @click="triggerUpload"
      >
        <Upload class="h-4 w-4" />
        <span class="hidden lg:inline">{{ uploading ? '上传中' : '上传' }}</span>
      </button>
      <input
        ref="fileInput"
        type="file"
        class="hidden"
        :accept="activeUploadAccept"
        multiple
        @change="handleFileChange"
      />
    </template>

    <div class="flex shrink-0 flex-col border-b border-slate-100 bg-slate-50/80">
      <div class="space-y-2 px-4 py-3">
        <LibrarySegmentedControl
          :model-value="activeGroupKey"
          :options="assetGroupOptions"
          :columns="assetGroupOptions.length"
          @update:model-value="selectAssetGroup"
        />
        <div v-if="hasMultipleCurrentAssetTypes" class="rounded-xl border border-slate-200/70 bg-white p-1 shadow-sm">
          <LibrarySegmentedControl
            :model-value="activeType"
            :options="currentAssetTypes"
            :columns="currentAssetTypes.length"
            @update:model-value="handleSelectAssetType"
          />
        </div>
      </div>
      <div class="border-t border-slate-100 px-4 py-2">
        <LibraryChipFilter v-model="activeTagFilter" :options="availableTagOptions" />
      </div>
    </div>

    <div v-if="loading" class="flex flex-1 flex-col items-center justify-center gap-3 p-6">
      <div class="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent"></div>
      <span class="text-sm font-bold text-slate-400">正在加载资源...</span>
    </div>

    <div v-else class="asset-list-scroll min-h-0 flex-1 overflow-y-auto p-3">
      <div
        v-if="assets.length === 0"
        class="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-100 bg-slate-50 px-4 py-12 text-center"
      >
        <FolderArchive class="mb-3 h-10 w-10 text-slate-300" />
        <p class="text-sm font-semibold text-slate-500">{{ emptyAssetText }}</p>
      </div>

      <div v-else class="space-y-2">
        <article
          v-for="asset in assets"
          :key="asset.id"
          class="group flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-white p-2.5 transition-all hover:border-indigo-200 hover:bg-indigo-50/20"
          @click="openPreview(asset)"
        >
          <div class="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-slate-100 bg-slate-50">
            <img
              v-if="isImage(asset.original_name) && asset.url"
              :src="asset.url"
              class="h-full w-full object-contain"
              :class="asset.asset_type === 'icon' ? 'p-2.5' : 'p-1.5'"
              loading="lazy"
            />
            <div
              v-else-if="asset.asset_type === 'font'"
              class="flex h-full w-full items-center justify-center text-sm font-bold text-slate-700"
              :style="{ fontFamily: `'preview-font-${asset.id}'` }"
            >
              Aa
            </div>
            <PenTool v-else-if="asset.asset_type === 'drawio'" class="h-5 w-5 text-orange-400" />
            <Workflow v-else-if="asset.asset_type === 'mermaid'" class="h-5 w-5 text-cyan-500" />
            <BarChart3 v-else-if="asset.asset_type === 'chart'" class="h-5 w-5 text-emerald-500" />
            <Sigma v-else-if="asset.asset_type === 'formula'" class="h-5 w-5 text-violet-500" />
            <Video v-else-if="asset.asset_type === 'video'" class="h-5 w-5 text-rose-500" />
            <FileText v-else class="h-5 w-5 text-slate-400" />
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex min-w-0 items-center gap-2">
              <h3 class="truncate text-xs font-bold text-slate-800">{{ asset.name }}</h3>
              <span
                v-if="asset.delete_block_reason"
                class="shrink-0 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-600"
                title="该资源存在引用"
              >
                已引用
              </span>
            </div>
            <p class="mt-1 truncate font-mono text-[10px] text-slate-400">{{ asset.original_name }}</p>
            <div class="mt-1 flex min-w-0 items-center gap-1 text-[10px] font-semibold text-slate-400">
              <span class="shrink-0">{{ formatBytes(asset.file_size) }}</span>
              <span v-if="asset.tags.length" class="truncate">/ {{ asset.tags.join(' / ') }}</span>
            </div>
          </div>

          <div class="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              type="button"
              class="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-white hover:text-indigo-600"
              title="预览资源"
              @click.stop="openPreview(asset)"
            >
              <ZoomIn class="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              class="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-white hover:text-indigo-600"
              title="复制资源 name"
              @click.stop="copyAssetName(asset)"
            >
              <Copy class="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              class="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-white hover:text-indigo-600"
              title="在完整资源库中管理"
              @click.stop="openAssetLibraryPage(asset)"
            >
              <ArrowUpRight class="h-3.5 w-3.5" />
            </button>
          </div>
        </article>
      </div>
    </div>

    <PaginationControl
      v-if="!loading"
      :page="page"
      :page-size="pageSize"
      :total="total"
      compact
      @update:page="handlePageChange"
      @update:page-size="handlePageSizeChange"
    />
  </LibrarySidebarPanel>

  <BaseDialog
    :model-value="textCreating"
    :title="`新建${activeTypeLabel}资源`"
    size="compact"
    body-preset="auto"
    :z-index="210"
    @update:model-value="value => { if (!value) closeTextCreateModal() }"
  >
    <div class="space-y-4">
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label class="mb-1 block text-xs font-bold text-slate-500">资源 name</label>
          <input v-model="textCreateForm.name" type="text" class="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500 focus:bg-white" />
        </div>
        <div>
          <label class="mb-1 block text-xs font-bold text-slate-500">文件名</label>
          <input v-model="textCreateForm.file_name" type="text" class="h-9 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500 focus:bg-white" />
        </div>
      </div>
      <div>
        <label class="mb-1 block text-xs font-bold text-slate-500">文本内容</label>
        <textarea v-model="textCreateForm.content" rows="12" class="w-full resize-y rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs leading-5 outline-none focus:border-indigo-500 focus:bg-white"></textarea>
      </div>
    </div>

    <template #footer>
      <button type="button" class="rounded-xl bg-slate-100 px-4 py-2 text-sm font-bold text-slate-600 transition-all hover:bg-slate-200" @click="closeTextCreateModal">取消</button>
      <button type="button" class="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white shadow-sm transition-all hover:bg-indigo-700 disabled:opacity-50" :disabled="uploading" @click="saveTextAsset">
        {{ uploading ? '创建中...' : '创建资源' }}
      </button>
    </template>
  </BaseDialog>

  <BaseDialog
    :model-value="!!runtimePreviewAsset"
    :title="runtimePreviewAsset?.name || '资源预览'"
    :description="runtimePreviewAsset?.original_name || ''"
    size="workbench"
    body-preset="immersive"
    overlay-class="bg-slate-900/90 backdrop-blur-md"
    :z-index="300"
    @update:model-value="handleRuntimePreviewVisibleChange"
  >
    <div v-if="runtimePreviewAsset" class="h-full min-h-0 bg-slate-50 p-4">
      <AssetPreviewFrame
        :key="`${runtimePreviewAsset.id}:${runtimePreviewAsset.file_hash}`"
        class="h-full"
        :workspace-id="workspaceId"
        :asset="runtimePreviewAsset"
      />
    </div>
  </BaseDialog>

  <BaseDialog
    :model-value="!!previewAsset"
    size="workbench"
    body-preset="immersive"
    :show-header="false"
    :show-close-button="false"
    :panel-style="{
      background: 'transparent',
    }"
    panel-class="!pointer-events-none !border-0 !bg-transparent !shadow-none"
    overlay-class="bg-slate-900/90 backdrop-blur-md"
    :z-index="300"
    @update:model-value="handleQuickPreviewDialogVisibleChange"
  >
    <div v-if="previewAsset" class="pointer-events-none relative flex h-full min-h-0 items-center justify-center p-4 sm:p-6">
      <img
        v-if="previewAsset.asset_type !== 'font' && isImage(previewAsset.original_name)"
        :src="previewAsset.url!"
        class="pointer-events-auto relative max-h-full max-w-full rounded-lg object-contain shadow-2xl drop-shadow-2xl"
      />
      <div
        v-else
        class="pointer-events-auto relative flex w-full max-w-4xl flex-col items-center justify-center gap-6 rounded-2xl bg-white p-6 shadow-2xl sm:p-10"
      >
        <div class="space-y-5 text-center" :style="previewAsset.asset_type === 'font' ? { fontFamily: `'preview-font-${previewAsset.id}'` } : undefined">
          <div class="text-5xl text-slate-800">Aa Bb Cc Dd Ee Ff</div>
          <div class="text-5xl text-slate-800">0123456789</div>
          <div class="pt-2 text-6xl text-slate-800">字体效果预览测试</div>
          <div class="pt-2 text-4xl text-slate-800 opacity-80">The quick brown fox jumps over the lazy dog.</div>
        </div>
      </div>
      <div class="pointer-events-auto absolute right-3 top-3 flex gap-3 sm:right-6 sm:top-6">
        <a v-if="previewAsset.url" :href="previewAsset.url + '?download=1'" download class="rounded-full bg-white/10 p-2.5 text-white backdrop-blur transition-all hover:bg-white/20">
          <Download class="h-5 w-5" />
        </a>
        <BaseCloseButton tone="inverse" label="关闭资源预览" @click="previewAsset = null" />
      </div>
      <div class="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-slate-800/60 px-4 py-2 text-xs tracking-widest text-white backdrop-blur sm:bottom-6">
        {{ previewAsset.original_name }}
      </div>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowUpRight,
  BarChart3,
  Copy,
  Download,
  FilePlus2,
  FileText,
  FolderArchive,
  Image,
  PenTool,
  Sigma,
  Upload,
  Video,
  Workflow,
  ZoomIn,
} from '@lucide/vue'

import {
  createWorkspaceAssetContent,
  listWorkspaceAssetTags,
  listWorkspaceAssets,
  uploadWorkspaceAsset,
} from '@/api/assets'
import { getErrorCode, getErrorMessage } from '@/api/http'
import type { AssetResponse, AssetType } from '@/types/api'
import { Message, createConfirm } from '@/utils/message'
import { buildWorkspaceAssetsPath } from '@/utils/workspace-routes'
import { ASSET_GROUPS, ASSET_UPLOAD_ACCEPT, TEXT_CREATABLE_ASSET_TYPES, getTextAssetDefaults } from './asset-manager'
import AssetPreviewFrame from '@/components/project/AssetPreviewFrame.vue'
import LibraryChipFilter from '@/components/project/LibraryChipFilter.vue'
import LibrarySegmentedControl from '@/components/project/LibrarySegmentedControl.vue'
import LibrarySidebarPanel from '@/components/project/LibrarySidebarPanel.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
import PaginationControl from '@/components/ui/PaginationControl.vue'

const props = defineProps<{
  modelValue: boolean
  workspaceId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const router = useRouter()

interface AgentAssetMutationDetail {
  workspaceId?: number | null
  assetId?: number | null
}
const assetGroups = ASSET_GROUPS

const activeGroupKey = ref(assetGroups[0]?.key || 'foundation')
const activeType = ref<AssetType>('icon')
const activeTag = ref<string | null>(null)
const loading = ref(false)
const uploading = ref(false)
const assets = ref<AssetResponse[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 24
const searchKeyword = ref('')
const availableTags = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const previewAsset = ref<AssetResponse | null>(null)
const runtimePreviewAsset = ref<AssetResponse | null>(null)
const textCreating = ref(false)
const textCreateForm = ref({ name: '', file_name: '', content: '' })

watch(assets, (newAssets) => {
  if (activeType.value !== 'font') return
  let styleTag = document.getElementById('dynamic-font-preview')
  if (!styleTag) {
    styleTag = document.createElement('style')
    styleTag.id = 'dynamic-font-preview'
    document.head.appendChild(styleTag)
  }
  styleTag.innerHTML = newAssets
    .filter(asset => asset.url)
    .map(asset => `@font-face { font-family: 'preview-font-${asset.id}'; src: url('${asset.url}'); font-display: swap; }`)
    .join('\n')
})

watch(
  () => [props.modelValue, props.workspaceId, activeType.value, activeTag.value, searchKeyword.value, page.value] as const,
  async ([visible, workspaceId]) => {
    if (visible && workspaceId) {
      await fetchAssets(workspaceId)
    }
  },
  { immediate: true },
)

watch(
  () => [props.modelValue, props.workspaceId, activeType.value] as const,
  async ([visible, workspaceId]) => {
    if (visible && workspaceId) {
      await fetchTags(workspaceId)
    }
  },
  { immediate: true },
)

const assetGroupOptions = computed(() => assetGroups.map(group => ({ label: group.label, value: group.key })))
const currentAssetGroup = computed(() => assetGroups.find(group => group.key === activeGroupKey.value) || assetGroups[0])
const currentAssetTypes = computed(() => currentAssetGroup.value?.types || [])
const hasMultipleCurrentAssetTypes = computed(() => currentAssetTypes.value.length > 1)
const activeUploadAccept = computed(() => ASSET_UPLOAD_ACCEPT[activeType.value])
const canCreateTextAsset = computed(() => TEXT_CREATABLE_ASSET_TYPES.includes(activeType.value))
const availableTagOptions = computed(() => availableTags.value.map(tag => ({ label: tag, value: tag })))
const activeTagFilter = computed({
  get: () => activeTag.value || '',
  set: value => {
    activeTag.value = value || null
    page.value = 1
  },
})
const activeTypeLabel = computed(() => {
  for (const group of assetGroups) {
    const matchedType = group.types.find(item => item.value === activeType.value)
    if (matchedType) return matchedType.label
  }
  return ''
})
const emptyAssetText = computed(() => {
  if (searchKeyword.value.trim()) return '未找到相关资源'
  if (activeTag.value) return '当前标签下暂无资源'
  return '暂无资源'
})

watch(searchKeyword, () => {
  page.value = 1
})

/**
 * 切换资源一级分组，并自动选中该分组首个类型。
 * @param groupKey 资源分组标识
 */
function selectAssetGroup(groupKey: string): void {
  const nextGroup = assetGroups.find(group => group.key === groupKey)
  if (!nextGroup || nextGroup.key === activeGroupKey.value) return
  activeGroupKey.value = nextGroup.key
  activeType.value = nextGroup.types[0]?.value || activeType.value
  page.value = 1
}

/**
 * 处理资源类型选择。
 * @param value 分段控件返回的资源类型字符串
 */
function handleSelectAssetType(value: string): void {
  activeType.value = value as AssetType
  page.value = 1
}

/**
 * 后端分页读取当前侧边栏资源。
 * @param workspaceId 工作空间 ID
 */
async function fetchAssets(workspaceId: number): Promise<void> {
  loading.value = true
  try {
    const response = await listWorkspaceAssets(workspaceId, {
      assetType: activeType.value,
      page: page.value,
      page_size: pageSize,
      keyword: searchKeyword.value.trim() || undefined,
      tag: activeTag.value || undefined,
    })
    assets.value = response.items
    total.value = response.total
  } catch (err) {
    Message.error(getErrorMessage(err, '加载资源列表失败'))
  } finally {
    loading.value = false
  }
}

/**
 * 读取工作空间资源标签，用于侧边栏标签筛选。
 * @param workspaceId 工作空间 ID
 */
async function fetchTags(workspaceId: number): Promise<void> {
  try {
    const tags = await listWorkspaceAssetTags(workspaceId, { assetType: activeType.value })
    availableTags.value = tags
    if (activeTag.value && !tags.includes(activeTag.value)) {
      activeTag.value = null
      page.value = 1
    }
  } catch {
    availableTags.value = []
    activeTag.value = null
  }
}

/**
 * 智能体写入资源后刷新当前打开的侧边栏列表和标签。
 */
function handleGlobalAgentAssetUpdated(event: Event): void {
  const detail = (event as CustomEvent<AgentAssetMutationDetail>).detail
  if (!props.modelValue || !props.workspaceId) {
    return
  }
  if (detail?.workspaceId && detail.workspaceId !== props.workspaceId) {
    return
  }
  void Promise.all([
    fetchAssets(props.workspaceId),
    fetchTags(props.workspaceId),
  ])
}

function triggerUpload(): void {
  if (!props.workspaceId) return
  fileInput.value?.click()
}

async function handleFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0 || !props.workspaceId) return

  const files = Array.from(target.files)
  uploading.value = true
  let successCount = 0
  let firstError = ''
  try {
    const currentTags = activeTag.value ? [activeTag.value] : []
    for (const file of files) {
      try {
        const uploaded = await uploadAssetWithOverwriteConfirm(file, currentTags)
        if (uploaded) successCount += 1
      } catch (err) {
        firstError ||= getErrorMessage(err, '上传资源失败')
      }
    }
    if (successCount > 0) {
      Message.success(files.length === 1 ? '上传成功' : `已上传 ${successCount} 个资源`)
      await fetchTags(props.workspaceId)
    }
    if (firstError) {
      Message.error(successCount > 0 ? `部分资源上传失败：${firstError}` : firstError)
    }
    await fetchAssets(props.workspaceId)
  } finally {
    uploading.value = false
    target.value = ''
  }
}

/**
 * 上传前处理同名覆盖确认。
 * @param file 待上传文件
 * @param tags 上传标签
 * @returns 是否完成上传
 */
async function uploadAssetWithOverwriteConfirm(file: File, tags: string[]): Promise<boolean> {
  try {
    await uploadWorkspaceAsset(props.workspaceId!, file, activeType.value, tags)
    return true
  } catch (err) {
    if (getErrorCode(err) !== 'ASSET_NAME_CONFLICT') {
      throw err
    }

    const conflictMessage = getErrorMessage(err, `文件 "${file.name}" 已存在，请确认是否覆盖。`)
    const confirmed = await createConfirm(
      `${conflictMessage} 覆盖后现有页面、路由、主题和预览引用会指向新文件，确认覆盖吗？`,
      '覆盖同名资源',
    )
    if (!confirmed) return false

    await uploadWorkspaceAsset(props.workspaceId!, file, activeType.value, tags, undefined, undefined, true)
    return true
  }
}

function openTextCreateModal(): void {
  if (!canCreateTextAsset.value) return
  const defaults = getTextAssetDefaults(activeType.value)
  textCreateForm.value = {
    name: defaults.fileName.replace(/\.[^.]+$/, ''),
    file_name: defaults.fileName,
    content: defaults.content,
  }
  textCreating.value = true
}

function closeTextCreateModal(): void {
  textCreating.value = false
}

async function saveTextAsset(): Promise<void> {
  if (!props.workspaceId) return
  const fileName = textCreateForm.value.file_name.trim()
  const assetName = textCreateForm.value.name.trim()
  if (!fileName || !assetName) {
    Message.error('资源 name 和文件名不能为空')
    return
  }

  uploading.value = true
  try {
    const currentTags = activeTag.value ? [activeTag.value] : []
    await createWorkspaceAssetContent(props.workspaceId, {
      asset_type: activeType.value,
      name: assetName,
      original_name: fileName,
      content: textCreateForm.value.content,
      tags: currentTags,
    })
    Message.success('资源已创建')
    closeTextCreateModal()
    await Promise.all([fetchAssets(props.workspaceId), fetchTags(props.workspaceId)])
  } catch (err) {
    Message.error(getErrorMessage(err, '创建资源失败'))
  } finally {
    uploading.value = false
  }
}

async function copyAssetName(asset: AssetResponse): Promise<void> {
  try {
    await navigator.clipboard.writeText(asset.name)
    Message.success(`已复制资源 name: ${asset.name}`)
  } catch {
    Message.error('复制资源 name 失败，请检查浏览器剪贴板权限。')
  }
}

function openAssetLibraryPage(asset?: AssetResponse): void {
  if (!props.workspaceId) return
  emit('update:modelValue', false)
  void router.push(buildWorkspaceAssetsPath(props.workspaceId, asset?.id ?? null))
}

function openPreview(asset: AssetResponse): void {
  if (shouldUseEditorNativePreview(asset)) {
    previewAsset.value = asset
    return
  }
  runtimePreviewAsset.value = asset
}

function closeRuntimePreview(): void {
  runtimePreviewAsset.value = null
}

/**
 * 同步 Runtime 资源预览弹窗可见状态，关闭时清空预览对象。
 * @param value 弹窗目标可见状态
 */
function handleRuntimePreviewVisibleChange(value: boolean): void {
  if (!value) {
    closeRuntimePreview()
  }
}

/**
 * 同步快速媒体预览弹窗可见状态，关闭时清空当前资源。
 * @param value 弹窗目标可见状态
 */
function handleQuickPreviewDialogVisibleChange(value: boolean): void {
  if (!value) {
    previewAsset.value = null
  }
}

function shouldUseEditorNativePreview(asset: AssetResponse): boolean {
  if (asset.asset_type === 'font') return true
  if (asset.asset_type === 'image' && isImage(asset.original_name)) return true
  if (asset.asset_type === 'icon' && isImage(asset.original_name) && !isSvg(asset.original_name)) return true
  return false
}

function isImage(name: string): boolean {
  return /\.(jpeg|jpg|png|gif|webp|svg)$/i.test(name)
}

function isSvg(name: string): boolean {
  return /\.svg$/i.test(name)
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

function handlePageChange(nextPage: number): void {
  page.value = Math.max(1, nextPage)
}

function handlePageSizeChange(): void {
  page.value = 1
}

onMounted(() => {
  window.addEventListener('agent:asset-updated', handleGlobalAgentAssetUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('agent:asset-updated', handleGlobalAgentAssetUpdated)
})
</script>

<style scoped>
.asset-list-scroll {
  scrollbar-gutter: stable;
}
</style>
