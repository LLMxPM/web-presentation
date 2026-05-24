<!-- 文件功能：提供仅面向图标资源的统一选择器，支持按名称/标签/类型搜索、预览，并按名称或资源 ID 输出选择结果。 -->
<template>
  <div class="space-y-2">
    <div
      class="flex items-center rounded-xl"
      :class="[triggerContainerClass, disabled ? 'cursor-not-allowed bg-slate-50 text-slate-400' : 'hover:border-slate-300']"
    >
      <button
        type="button"
        class="flex min-w-0 items-center text-left"
        :class="triggerButtonClass"
        :disabled="disabled"
        @click="openPicker"
      >
        <div
          class="flex shrink-0 items-center justify-center overflow-hidden border"
          :class="[previewBoxClass, previewBoxToneClass]"
        >
          <img
            v-if="selectedAsset?.url"
            :src="selectedAsset.url"
            :alt="selectedAsset.name"
            class="object-contain"
            :class="previewImageClass"
          >
          <ImageIcon v-else class="h-4 w-4 text-slate-300" />
        </div>
        <div v-if="showAssetSummary" class="min-w-0 flex-1">
          <div v-if="selectedAsset" class="truncate text-sm font-medium text-slate-700">
            {{ selectedAsset.name }}
          </div>
          <div v-else class="truncate text-sm text-slate-400">
            {{ placeholder }}
          </div>
          <div v-if="showAssetMeta && selectedAsset" class="truncate text-[11px] text-slate-400">
            {{ buildAssetMeta(selectedAsset) }}
          </div>
        </div>
      </button>

      <button
        v-if="showClearButton"
        type="button"
        class="shrink-0 text-slate-400 transition hover:text-slate-600"
        :class="clearButtonClass"
        title="清空图标"
        @click="clearSelection"
      >
        <X class="h-4 w-4" />
      </button>
      <button
        v-if="showActionButton"
        type="button"
        class="shrink-0 whitespace-nowrap text-xs font-semibold text-slate-600 transition hover:text-indigo-600"
        :class="actionButtonClass"
        :disabled="disabled"
        @click="openPicker"
      >
        选择
      </button>
    </div>

    <p v-if="hint" class="text-[11px] leading-5 text-slate-500">
      {{ hint }}
    </p>
  </div>

  <BaseDialog v-model="dialogVisible" :title="title" width="1080px">
    <div class="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside class="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
        <div class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">图标预览</div>
        <div class="mt-3 flex min-h-[220px] items-center justify-center rounded-2xl border border-slate-200 bg-white">
          <img
            v-if="pendingAsset?.url"
            :src="pendingAsset.url"
            :alt="pendingAsset.name"
            class="h-24 w-24 object-contain"
          >
          <div v-else class="flex flex-col items-center gap-2 text-slate-400">
            <ImageIcon class="h-8 w-8" />
            <span class="text-sm">未选择图标</span>
          </div>
        </div>

        <div class="mt-4 space-y-2">
          <div class="text-lg font-bold text-slate-900">
            {{ pendingAsset?.name || '请选择图标' }}
          </div>
          <div v-if="pendingAsset" class="space-y-2 text-xs text-slate-500">
            <div>原文件名：{{ pendingAsset.original_name }}</div>
            <div>类型：{{ getIconStyleLabel(pendingAsset.analysis_metadata) }} / {{ getRenderModeLabel(pendingAsset.analysis_metadata) }}</div>
            <div>能力：{{ getIconCapabilitySummary(pendingAsset.analysis_metadata) }}</div>
            <div v-if="pendingAsset.tags.length > 0" class="flex flex-wrap gap-1.5">
              <span
                v-for="tag in pendingAsset.tags"
                :key="`${pendingAsset.id}-${tag}`"
                class="rounded-full bg-indigo-50 px-2 py-1 text-[11px] font-semibold text-indigo-700"
              >
                {{ tag }}
              </span>
            </div>
            <div v-else class="text-slate-400">当前图标没有标签。</div>
          </div>
        </div>
      </aside>

      <section class="min-w-0 space-y-4">
        <div class="flex flex-wrap items-center gap-3">
          <label class="flex min-w-0 flex-1 items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-3">
            <Search class="h-4 w-4 shrink-0 text-slate-400" />
            <input
              v-model="searchKeyword"
              type="text"
              class="h-11 min-w-0 flex-1 bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
              placeholder="按名称、标签、类型搜索图标"
            >
          </label>
          <div class="rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500">
            共 {{ iconAssets.length }} 个图标
          </div>
        </div>

        <div v-if="loading" class="flex min-h-[360px] items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-400">
          正在加载图标资源...
        </div>
        <div v-else-if="filteredAssets.length === 0" class="flex min-h-[360px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50 text-center">
          <ImageIcon class="h-8 w-8 text-slate-300" />
          <div class="mt-3 text-sm font-semibold text-slate-500">没有匹配的图标</div>
          <div class="mt-1 text-xs text-slate-400">可尝试搜索图标名、标签或描边/填充等类型关键字。</div>
        </div>
        <div v-else class="grid max-h-[520px] grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3 overflow-y-auto pr-1">
          <button
            v-for="asset in filteredAssets"
            :key="asset.id"
            type="button"
            class="rounded-2xl border p-3 text-left transition"
            :class="pendingSelectedId === asset.id
              ? 'border-indigo-400 bg-indigo-50 shadow-sm'
              : 'border-slate-200 bg-white hover:border-indigo-200 hover:bg-slate-50'"
            @click="selectPendingAsset(asset)"
          >
            <div class="flex h-24 items-center justify-center rounded-xl border border-slate-100 bg-slate-50">
              <img :src="asset.url || ''" :alt="asset.name" class="h-12 w-12 object-contain">
            </div>
            <div class="mt-3 truncate text-sm font-semibold text-slate-800">{{ asset.name }}</div>
            <div class="mt-1 line-clamp-2 text-[11px] leading-5 text-slate-500">
              {{ buildAssetMeta(asset) }}
            </div>
            <div class="mt-2 flex flex-wrap gap-1.5">
              <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                {{ getIconStyleLabel(asset.analysis_metadata) }}
              </span>
              <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                {{ getRenderModeLabel(asset.analysis_metadata) }}
              </span>
              <span
                v-for="tag in asset.tags.slice(0, 2)"
                :key="`${asset.id}-${tag}`"
                class="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700"
              >
                {{ tag }}
              </span>
            </div>
          </button>
        </div>
      </section>
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="dialogVisible = false">取消</BaseButton>
      <BaseButton variant="ghost" :disabled="!pendingAsset" @click="clearSelectionAndClose">清空</BaseButton>
      <BaseButton variant="primary" :disabled="!pendingAsset" @click="confirmSelection">确认选择</BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Image as ImageIcon, Search, X } from '@lucide/vue'

import { listWorkspaceAssets } from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import type { AssetResponse } from '@/types/api'
import {
  getAnalysisStatusLabel,
  getIconCapabilitySummary,
  getIconStyleLabel,
  getRenderModeLabel,
} from '@/utils/assetAnalysis'
import { Message } from '@/utils/message'
import BaseButton from './BaseButton.vue'
import BaseDialog from './BaseDialog.vue'

type IconPickerValue = string | number | null

const props = withDefaults(defineProps<{
  modelValue: IconPickerValue
  workspaceId?: number | null
  assets?: AssetResponse[] | null
  valueMode?: 'name' | 'id'
  title?: string
  placeholder?: string
  hint?: string
  clearable?: boolean
  disabled?: boolean
  size?: 'default' | 'compact'
}>(), {
  workspaceId: null,
  assets: null,
  valueMode: 'name',
  title: '选择图标',
  placeholder: '请选择图标',
  hint: '',
  clearable: true,
  disabled: false,
  size: 'default',
})

const emit = defineEmits<{
  'update:modelValue': [value: IconPickerValue]
  select: [asset: AssetResponse | null]
}>()

const dialogVisible = ref(false)
const loading = ref(false)
const searchKeyword = ref('')
const loadedAssets = ref<AssetResponse[]>([])
const pendingSelectedId = ref<number | null>(null)

const iconAssets = computed(() => {
  const sourceAssets = props.assets ?? loadedAssets.value
  return sourceAssets.filter(asset => asset.asset_type === 'icon')
})

const selectedAsset = computed(() => findAssetByModelValue(props.modelValue))
const pendingAsset = computed(() => iconAssets.value.find(asset => asset.id === pendingSelectedId.value) ?? null)
const filteredAssets = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) {
    return iconAssets.value
  }
  return iconAssets.value.filter(asset => {
    return buildSearchKeywords(asset).some(item => item.toLowerCase().includes(keyword))
  })
})
const triggerContainerClass = computed(() => (
  props.size === 'compact'
    ? 'h-9 gap-1.5 px-0 py-0'
    : 'min-h-10 border border-slate-200 bg-white px-3 py-2'
))
const previewBoxClass = computed(() => (
  props.size === 'compact'
    ? 'h-9 w-9 rounded-lg'
    : 'h-10 w-10 rounded-xl'
))
const previewBoxToneClass = computed(() => (
  props.size === 'compact'
    ? 'border-slate-200 bg-white'
    : (selectedAsset.value ? 'border-indigo-100 bg-indigo-50/70' : 'border-slate-200 bg-slate-50')
))
const previewImageClass = computed(() => (
  props.size === 'compact'
    ? 'h-4.5 w-4.5'
    : 'h-6 w-6'
))
const actionButtonClass = computed(() => (
  props.size === 'compact'
    ? 'h-9 rounded-lg border border-slate-200 bg-white px-3 py-0 hover:border-indigo-200 hover:bg-indigo-50'
    : 'rounded-lg border border-slate-200 px-2.5 py-1.5 hover:border-indigo-200 hover:bg-indigo-50'
))
const showAssetMeta = computed(() => props.size !== 'compact')
const showAssetSummary = computed(() => props.size !== 'compact')
const showClearButton = computed(() => (
  props.clearable && Boolean(selectedAsset.value) && !props.disabled
))
const showActionButton = computed(() => props.size !== 'compact')
const clearButtonClass = computed(() => (
  props.size === 'compact'
    ? 'flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
    : 'rounded-lg p-1.5 hover:bg-slate-100'
))
const triggerButtonClass = computed(() => (
  props.size === 'compact'
    ? 'shrink-0 justify-start gap-0'
    : 'flex-1 gap-3'
))

watch(() => props.workspaceId, () => {
  if (props.assets) {
    return
  }
  loadedAssets.value = []
})

watch(selectedAsset, (asset) => {
  if (!dialogVisible.value) {
    pendingSelectedId.value = asset?.id ?? null
  }
})

/**
 * 打开图标选择对话框，并在必要时加载图标资源。
 */
async function openPicker(): Promise<void> {
  if (props.disabled) {
    return
  }
  pendingSelectedId.value = selectedAsset.value?.id ?? null
  dialogVisible.value = true
  searchKeyword.value = ''
  await ensureAssetsLoaded()
}

/**
 * 确保组件持有一份图标资源列表；若父组件已传入则直接复用。
 */
async function ensureAssetsLoaded(): Promise<void> {
  if (props.assets || loadedAssets.value.length > 0 || !props.workspaceId) {
    return
  }

  loading.value = true
  try {
    const response = await listWorkspaceAssets(props.workspaceId, { assetType: 'icon', page: 1, page_size: 100 })
    loadedAssets.value = response.items
  } catch (error) {
    Message.error(getErrorMessage(error, '加载图标资源失败。'))
  } finally {
    loading.value = false
  }
}

/**
 * 记录当前待确认的图标项，用于右侧预览与最终提交。
 * @param asset 当前点选的图标资源
 */
function selectPendingAsset(asset: AssetResponse): void {
  pendingSelectedId.value = asset.id
}

/**
 * 清空已选择的图标，并同步输出空值。
 */
function clearSelection(): void {
  emit('update:modelValue', null)
  emit('select', null)
}

/**
 * 在关闭对话框的同时清空当前图标选择。
 */
function clearSelectionAndClose(): void {
  clearSelection()
  dialogVisible.value = false
}

/**
 * 按配置的输出模式提交当前待确认图标。
 */
function confirmSelection(): void {
  if (!pendingAsset.value) {
    return
  }
  emit('update:modelValue', props.valueMode === 'id' ? pendingAsset.value.id : pendingAsset.value.name)
  emit('select', pendingAsset.value)
  dialogVisible.value = false
}

/**
 * 依据当前 modelValue 解析已选图标，兼容按名称或按资源 ID 输出两种模式。
 * @param modelValue 当前绑定值
 */
function findAssetByModelValue(modelValue: IconPickerValue): AssetResponse | null {
  if (modelValue == null) {
    return null
  }
  if (props.valueMode === 'id') {
    return iconAssets.value.find(asset => asset.id === modelValue) ?? null
  }
  return iconAssets.value.find(asset => asset.name === modelValue) ?? null
}

/**
 * 生成图标卡片与触发器共用的摘要文案。
 * @param asset 图标资源
 */
function buildAssetMeta(asset: AssetResponse): string {
  return `${asset.original_name} · ${getIconStyleLabel(asset.analysis_metadata)} · ${getRenderModeLabel(asset.analysis_metadata)}`
}

/**
 * 生成搜索关键字集合，覆盖名称、标签、类型和分析能力摘要。
 * @param asset 图标资源
 */
function buildSearchKeywords(asset: AssetResponse): string[] {
  return [
    asset.name,
    asset.original_name,
    asset.asset_type,
    asset.analysis_metadata?.icon.style ?? '',
    asset.analysis_metadata?.icon.render_mode ?? '',
    asset.analysis_metadata?.icon.analysis_status ?? '',
    getIconStyleLabel(asset.analysis_metadata),
    getRenderModeLabel(asset.analysis_metadata),
    getAnalysisStatusLabel(asset.analysis_metadata),
    getIconCapabilitySummary(asset.analysis_metadata),
    ...(asset.tags ?? []),
  ]
}
</script>
