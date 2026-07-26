<!-- 文件功能：提供按资源类型配置的统一资源选择器，支持服务端搜索、分页、预览与选择确认。 -->
<template>
  <div class="space-y-2">
    <div
      class="flex items-center rounded-xl"
      :class="[triggerContainerClass, disabled ? 'cursor-not-allowed bg-canvas text-text-disabled' : 'hover:border-border-strong']"
    >
      <button
        type="button"
        class="flex min-w-0 items-center text-left"
        :class="triggerButtonClass"
        :disabled="disabled"
        :aria-label="size === 'compact' ? resolvedTitle : undefined"
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
          <ImageIcon v-else class="h-4 w-4 text-text-faint" />
        </div>
        <div v-if="showAssetSummary" class="min-w-0 flex-1">
          <div v-if="selectedAsset" class="truncate text-sm font-medium text-text-emphasis" :title="selectedAsset.name">
            {{ selectedAsset.name }}
          </div>
          <div v-else class="truncate text-sm text-text-disabled">
            {{ resolvedPlaceholder }}
          </div>
          <div v-if="showAssetMeta && selectedAsset" class="truncate text-[11px] text-text-disabled">
            {{ buildAssetMeta(selectedAsset) }}
          </div>
        </div>
      </button>

      <button
        v-if="showClearButton"
        type="button"
        class="shrink-0 text-text-disabled transition hover:text-text-secondary"
        :class="clearButtonClass"
        :title="`清空${resourceLabel}`"
        @click="clearSelection"
      >
        <X class="h-4 w-4" />
      </button>
      <button
        v-if="showActionButton"
        type="button"
        class="shrink-0 whitespace-nowrap text-xs font-semibold text-text-secondary transition hover:text-accent"
        :class="actionButtonClass"
        :disabled="disabled"
        @click="openPicker"
      >
        选择
      </button>
    </div>

    <p v-if="hint" class="text-[11px] leading-5 text-text-muted">
      {{ hint }}
    </p>
  </div>

  <UiDialog
    :open="dialogVisible"
    :title="resolvedTitle"
    size="wide"
    body-preset="dense"
    @update:open="dialogVisible = $event"
  >
    <div class="grid h-full min-h-0 gap-4 overflow-y-auto lg:grid-cols-[300px_minmax(0,1fr)] lg:overflow-hidden">
      <aside class="min-w-0 overflow-hidden rounded-2xl border border-border bg-canvas/70 p-4">
        <div class="flex min-w-0 items-center justify-between gap-2">
          <div class="shrink-0 text-xs font-semibold uppercase tracking-[0.2em] text-text-disabled">{{ resourceLabel }}预览</div>
          <AssetPreviewBackgroundControl
            v-model="previewBackground"
            class="w-[148px] shrink-0"
          />
        </div>
        <AssetPreviewSurface
          :background="previewBackground"
          class="mt-3 flex min-h-[220px] items-center justify-center rounded-2xl border border-border transition-colors"
        >
          <img
            v-if="pendingAsset?.url"
            :src="pendingAsset.url"
            :alt="pendingAsset.name"
            class="h-24 w-24 object-contain"
          >
          <div v-else class="flex flex-col items-center gap-2 text-text-disabled">
            <ImageIcon class="h-8 w-8" />
            <span class="text-sm">未选择{{ resourceLabel }}</span>
          </div>
        </AssetPreviewSurface>

        <div class="mt-4 min-w-0 space-y-2 overflow-hidden">
          <div class="truncate text-lg font-bold text-text-strong" :title="pendingAsset?.name">
            {{ pendingAsset?.name || `请选择${resourceLabel}` }}
          </div>
          <div v-if="pendingAsset" class="min-w-0 space-y-2 text-xs text-text-muted">
            <div class="flex min-w-0 items-center gap-1">
              <span class="shrink-0">原文件名：</span>
              <span class="min-w-0 truncate" :title="pendingAsset.original_name">{{ pendingAsset.original_name }}</span>
            </div>
            <template v-if="assetType === 'icon'">
              <div>类型：{{ getIconStyleLabel(pendingAsset.analysis_metadata) }} / {{ getRenderModeLabel(pendingAsset.analysis_metadata) }}</div>
              <div>能力：{{ getIconCapabilitySummary(pendingAsset.analysis_metadata) }}</div>
            </template>
            <div v-else>资源类型：{{ resourceLabel }}</div>
            <div v-if="getAssetTags(pendingAsset).length > 0" class="flex max-h-24 flex-wrap gap-1.5 overflow-hidden">
              <span
                v-for="tag in getAssetTags(pendingAsset)"
                :key="`${pendingAsset.id}-${tag}`"
                class="rounded-full bg-surface-selected px-2 py-1 text-[11px] font-semibold text-accent-hover"
              >
                {{ tag }}
              </span>
            </div>
            <div v-else class="text-text-disabled">当前资源没有标签。</div>
          </div>
        </div>
      </aside>

      <section class="flex min-h-0 min-w-0 flex-col gap-4">
        <div class="flex shrink-0 flex-wrap items-center gap-3">
          <label class="flex min-w-0 flex-1 items-center gap-2 rounded-2xl border border-border bg-canvas px-3">
            <Search class="h-4 w-4 shrink-0 text-text-disabled" />
            <input
              v-model="searchKeyword"
              type="text"
              class="h-11 min-w-0 flex-1 bg-transparent text-sm text-text-emphasis outline-none placeholder:text-text-disabled"
              :placeholder="`按名称、文件名或标签搜索${resourceLabel}`"
            >
          </label>
          <div class="rounded-full border border-border bg-canvas px-3 py-2 text-xs font-semibold text-text-muted">
            共 {{ total }} 个{{ resourceLabel }}
          </div>
        </div>

        <div v-if="loading" class="flex min-h-[360px] flex-1 items-center justify-center rounded-2xl border border-dashed border-border bg-canvas text-sm text-text-disabled">
          正在加载{{ resourceLabel }}资源...
        </div>
        <div v-else-if="assets.length === 0" class="flex min-h-[360px] flex-1 flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-canvas text-center">
          <ImageIcon class="h-8 w-8 text-text-faint" />
          <div class="mt-3 text-sm font-semibold text-text-muted">没有匹配的{{ resourceLabel }}</div>
          <div class="mt-1 text-xs text-text-disabled">可尝试搜索资源名称、原文件名或标签。</div>
        </div>
        <div v-else class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border-muted">
          <div class="grid min-h-0 flex-1 grid-cols-[repeat(auto-fill,minmax(160px,1fr))] content-start gap-3 overflow-y-auto p-1">
            <button
              v-for="asset in assets"
              :key="asset.id"
              type="button"
              class="rounded-2xl border p-3 text-left transition"
              :class="pendingSelectedId === asset.id
                ? 'border-accent-border bg-surface-selected shadow-sm'
                : 'border-border bg-surface hover:border-accent-ring hover:bg-surface-hover'"
              @click="selectPendingAsset(asset)"
            >
              <div class="flex h-24 items-center justify-center rounded-xl border border-border-muted bg-canvas">
                <img :src="asset.url || ''" :alt="asset.name" :class="assetType === 'icon' ? 'h-12 w-12 object-contain' : 'h-full w-full object-contain'">
              </div>
              <div class="mt-3 truncate text-sm font-semibold text-text">{{ asset.name }}</div>
              <div class="mt-1 line-clamp-2 text-[11px] leading-5 text-text-muted">
                {{ buildAssetMeta(asset) }}
              </div>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <template v-if="assetType === 'icon'">
                  <span class="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-semibold text-text-secondary">
                    {{ getIconStyleLabel(asset.analysis_metadata) }}
                  </span>
                  <span class="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-semibold text-text-secondary">
                    {{ getRenderModeLabel(asset.analysis_metadata) }}
                  </span>
                </template>
                <span
                  v-for="tag in getAssetTags(asset).slice(0, 2)"
                  :key="`${asset.id}-${tag}`"
                  class="rounded-full bg-surface-selected px-2 py-0.5 text-[10px] font-semibold text-accent-hover"
                >
                  {{ tag }}
                </span>
              </div>
            </button>
          </div>
          <PaginationControl
            compact
            :page="page"
            :page-size="pageSize"
            :total="total"
            @update:page="page = $event"
          />
        </div>
      </section>
    </div>

    <template #footer>
      <UiButton variant="ghost" @click="dialogVisible = false">取消</UiButton>
      <UiButton variant="ghost" :disabled="!pendingAsset" @click="clearSelectionAndClose">清空</UiButton>
      <UiButton variant="primary" :disabled="!pendingAsset" @click="confirmSelection">确认选择</UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Image as ImageIcon, Search, X } from '@lucide/vue'

import type { AssetResponse, AssetType, ThemeAssetSummary } from '@/types/api'
import {
  getIconCapabilitySummary,
  getIconStyleLabel,
  getRenderModeLabel,
} from '@/utils/assetAnalysis'
import { useAssetPickerSearch } from './asset-picker-search'
import AssetPreviewBackgroundControl from './AssetPreviewBackgroundControl.vue'
import AssetPreviewSurface from './AssetPreviewSurface.vue'
import type { AssetPreviewBackground } from './asset-preview-background'
import UiButton from './button/UiButton.vue'
import UiDialog from './dialog/UiDialog.vue'
import PaginationControl from './PaginationControl.vue'

type AssetPickerValue = string | number | null
type AssetPickerAsset = AssetResponse | ThemeAssetSummary

const props = withDefaults(defineProps<{
  modelValue: AssetPickerValue
  workspaceId: number | null
  assetType: AssetType
  selectedAsset?: AssetPickerAsset | null
  valueMode?: 'name' | 'id'
  title?: string
  placeholder?: string
  hint?: string
  clearable?: boolean
  disabled?: boolean
  size?: 'default' | 'compact'
}>(), {
  selectedAsset: null,
  valueMode: 'name',
  title: '',
  placeholder: '',
  hint: '',
  clearable: true,
  disabled: false,
  size: 'default',
})

const emit = defineEmits<{
  'update:modelValue': [value: AssetPickerValue]
  select: [asset: AssetPickerAsset | null]
}>()

const dialogVisible = ref(false)
const previewBackground = ref<AssetPreviewBackground>('checker')
const pendingSelectedId = ref<number | null>(null)
const selectedAssetCache = ref<AssetPickerAsset | null>(props.selectedAsset)

const resourceLabel = computed(() => props.assetType === 'icon' ? '图标' : props.assetType === 'image' ? '图片' : '资源')
const resolvedTitle = computed(() => props.title || `选择${resourceLabel.value}`)
const resolvedPlaceholder = computed(() => props.placeholder || `请选择${resourceLabel.value}`)
const {
  assets,
  loading,
  page,
  pageSize,
  resetSearchAndFetch,
  searchKeyword,
  total,
} = useAssetPickerSearch({
  dialogVisible,
  workspaceId: () => props.workspaceId,
  assetType: () => props.assetType,
  resourceLabel: () => resourceLabel.value,
})
const selectedAsset = computed(() => findAssetByModelValue(props.modelValue))
const pendingAsset = computed(() => (
  assets.value.find(asset => asset.id === pendingSelectedId.value)
  ?? (selectedAssetCache.value?.id === pendingSelectedId.value ? selectedAssetCache.value : null)
))
const triggerContainerClass = computed(() => (
  props.size === 'compact'
    ? 'h-9 gap-1.5 px-0 py-0'
    : 'min-h-10 border border-border bg-surface px-3 py-2'
))
const previewBoxClass = computed(() => (
  props.size === 'compact'
    ? 'h-9 w-9 rounded-lg'
    : 'h-10 w-10 rounded-xl'
))
const previewBoxToneClass = computed(() => (
  props.size === 'compact'
    ? 'border-border bg-surface'
    : (selectedAsset.value ? 'border-accent-muted bg-surface-selected/70' : 'border-border bg-canvas')
))
const previewImageClass = computed(() => (
  props.size === 'compact'
    ? 'h-4.5 w-4.5'
    : 'h-6 w-6'
))
const actionButtonClass = computed(() => (
  props.size === 'compact'
    ? 'h-9 rounded-lg border border-border bg-surface px-3 py-0 hover:border-accent-ring hover:bg-surface-selected'
    : 'rounded-lg border border-border px-2.5 py-1.5 hover:border-accent-ring hover:bg-surface-selected'
))
const showAssetMeta = computed(() => props.size !== 'compact')
const showAssetSummary = computed(() => props.size !== 'compact')
const showClearButton = computed(() => (
  props.clearable && Boolean(selectedAsset.value) && !props.disabled
))
const showActionButton = computed(() => props.size !== 'compact')
const clearButtonClass = computed(() => (
  props.size === 'compact'
    ? 'flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-surface hover:border-border-strong hover:bg-surface-hover'
    : 'rounded-lg p-1.5 hover:bg-surface-muted'
))
const triggerButtonClass = computed(() => (
  props.size === 'compact'
    ? 'shrink-0 justify-start gap-0'
    : 'flex-1 gap-3'
))

watch(() => props.selectedAsset, (asset) => {
  if (asset) {
    selectedAssetCache.value = asset
  }
}, { immediate: true })

watch(selectedAsset, asset => {
  if (!dialogVisible.value) {
    pendingSelectedId.value = asset?.id ?? null
  }
})

/**
 * 打开资源选择对话框，并按当前类型加载第一页资源。
 */
async function openPicker(): Promise<void> {
  if (props.disabled) {
    return
  }
  pendingSelectedId.value = selectedAsset.value?.id ?? null
  dialogVisible.value = true
  await resetSearchAndFetch()
}

/**
 * 记录当前待确认资源，用于左侧预览与最终提交。
 * @param asset 当前点选的资源
 */
function selectPendingAsset(asset: AssetResponse): void {
  pendingSelectedId.value = asset.id
}

/**
 * 清空已选择的图标，并同步输出空值。
 */
function clearSelection(): void {
  selectedAssetCache.value = null
  pendingSelectedId.value = null
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
  selectedAssetCache.value = pendingAsset.value
  emit('update:modelValue', props.valueMode === 'id' ? pendingAsset.value.id : pendingAsset.value.name)
  emit('select', pendingAsset.value)
  dialogVisible.value = false
}

/**
 * 依据当前 modelValue 解析已选资源，兼容分页结果和父组件提供的初始资源。
 * @param modelValue 当前绑定值
 */
function findAssetByModelValue(modelValue: AssetPickerValue): AssetPickerAsset | null {
  if (modelValue == null) {
    return null
  }
  const candidates = selectedAssetCache.value
    ? [selectedAssetCache.value, ...assets.value]
    : assets.value
  if (props.valueMode === 'id') {
    return candidates.find(asset => asset.id === Number(modelValue)) ?? null
  }
  return candidates.find(asset => asset.name === modelValue) ?? null
}

/**
 * 生成资源卡片与触发器共用的摘要文案，图标额外展示分析能力。
 * @param asset 当前资源
 */
function buildAssetMeta(asset: AssetPickerAsset): string {
  if (asset.asset_type === 'icon') {
    return `${asset.original_name} · ${getIconStyleLabel(asset.analysis_metadata)} · ${getRenderModeLabel(asset.analysis_metadata)}`
  }
  const tags = getAssetTags(asset)
  return tags.length > 0
    ? `${asset.original_name} · ${tags.slice(0, 2).join(' / ')}`
    : asset.original_name
}

/**
 * 从完整资源响应中读取标签；主题摘要未携带标签时返回空数组。
 * @param asset 完整资源或主题资源摘要
 */
function getAssetTags(asset: AssetPickerAsset): string[] {
  return 'tags' in asset ? asset.tags : []
}
</script>

