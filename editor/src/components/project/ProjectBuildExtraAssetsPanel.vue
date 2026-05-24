<!-- 文件功能：项目构建弹窗的额外资源选择区域，支持搜索资源、选择资源和保存草稿。 -->
<template>
  <section class="flex min-h-0 flex-col rounded-lg border border-slate-200 bg-white p-3">
    <div class="flex shrink-0 items-center justify-between gap-3">
      <div class="flex items-center gap-2">
        <Package class="h-4 w-4 text-indigo-500" />
        <h4 class="text-base font-semibold text-slate-900">构建资源</h4>
        <span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">
          额外 {{ extraAssetNames.length }}
        </span>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <BaseButton
          v-if="canSaveExtraAssets"
          variant="ghost"
          size="sm"
          custom-class="whitespace-nowrap"
          @click="emit('restore')"
        >
          <template #icon>
            <RotateCcw class="h-4 w-4" />
          </template>
          还原
        </BaseButton>
        <BaseButton
          variant="secondary"
          size="sm"
          :loading="extraAssetsSaving"
          :disabled="!canSaveExtraAssets"
          custom-class="whitespace-nowrap"
          @click="emit('saveExtraAssets')"
        >
          保存额外资源
        </BaseButton>
      </div>
    </div>

    <div class="mt-3 grid shrink-0 grid-cols-[minmax(0,1fr)_auto_auto] gap-2">
      <BaseInput
        :model-value="assetKeyword"
        class="min-w-0 flex-1"
        placeholder="按资源 name 搜索"
        @update:model-value="emit('update:assetKeyword', String($event))"
        @keyup.enter="emit('loadAssets')"
      />
      <BaseButton
        variant="secondary"
        :loading="assetOptionsLoading"
        :disabled="!workspaceId"
        custom-class="h-11 min-w-[80px] whitespace-nowrap"
        @click="emit('loadAssets')"
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
        :disabled="!workspaceId"
        custom-class="h-11 min-w-[64px] whitespace-nowrap"
        @click="emit('loadAssets')"
      >
        <template #icon>
          <RefreshCw class="h-4 w-4" />
        </template>
        刷新
      </BaseButton>
    </div>

    <div class="mt-3 grid min-h-0 flex-1 gap-2 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,0.9fr)_minmax(0,1.55fr)]">
      <div class="flex min-h-0 min-w-0 flex-col rounded-lg border border-slate-200 bg-slate-50/80 p-2.5">
        <div class="flex shrink-0 items-center justify-between gap-2 text-[11px] font-semibold text-slate-500">
          <span>自动包含</span>
          <span class="rounded-full bg-white px-1.5 py-0.5 text-[10px]">{{ automaticIncludedAssets.length }}</span>
        </div>
        <div v-if="automaticIncludedAssets.length" class="resource-column-scroll mt-2 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          <button
            v-for="asset in automaticIncludedAssets"
            :key="asset.name"
            type="button"
            class="flex w-full min-w-0 cursor-not-allowed items-center justify-between gap-1 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-left text-xs font-semibold text-slate-500"
            :title="`${asset.name} 已由当前构建自动包含`"
            disabled
          >
            <span class="min-w-0 truncate">{{ asset.name }}</span>
            <span class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
              {{ asset.typeLabel }}
            </span>
          </button>
        </div>
        <p v-else class="mt-2 flex min-h-0 flex-1 items-center justify-center text-xs text-slate-400">暂无自动资源</p>
      </div>

      <div class="flex min-h-0 min-w-0 flex-col rounded-lg border border-indigo-100 bg-indigo-50/40 p-2.5">
        <div class="flex shrink-0 items-center justify-between gap-2 text-[11px] font-semibold text-indigo-600">
          <span>额外资源</span>
          <span class="rounded-full bg-white px-1.5 py-0.5 text-[10px]">{{ extraIncludedAssets.length }}</span>
        </div>
        <div v-if="extraIncludedAssets.length" class="resource-column-scroll mt-2 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          <button
            v-for="asset in extraIncludedAssets"
            :key="asset.name"
            type="button"
            class="flex w-full min-w-0 items-center justify-between gap-1 rounded-md border border-indigo-200 bg-white px-2 py-1.5 text-left text-xs font-semibold text-indigo-700"
            :title="`移除 ${asset.name}`"
            @click="emit('removeAsset', asset.name)"
          >
            <span class="min-w-0 truncate">{{ asset.name }}</span>
            <span class="inline-flex shrink-0 items-center gap-1">
              <span class="rounded-full bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-500">
                {{ asset.typeLabel }}
              </span>
              <X class="h-3 w-3" />
            </span>
          </button>
        </div>
        <p v-else class="mt-2 flex min-h-0 flex-1 items-center justify-center text-xs text-slate-400">未选择额外资源</p>
      </div>

      <div class="flex min-h-0 min-w-0 flex-col rounded-lg border border-slate-200 bg-white p-2.5">
        <div class="flex shrink-0 items-center justify-between gap-2 text-[11px] font-semibold text-slate-500">
          <span>待选资源</span>
          <span class="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px]">{{ activeTabAssets.length }}</span>
        </div>
        <div v-if="assetOptionsLoading" class="mt-2 flex min-h-0 flex-1 items-center justify-center text-sm font-semibold text-slate-400">
          <RefreshCw class="mr-2 h-4 w-4 animate-spin" />
          正在加载资源
        </div>
        <div v-else-if="assetTypeTabs.length" class="mt-2 flex min-h-0 flex-1 flex-col">
          <div class="grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-1">
            <button
              type="button"
              class="flex h-7 w-6 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="向左查看更多资源类型"
              title="向左查看更多类型"
              @click="scrollAssetTypeTabs(-1)"
            >
              <ChevronLeft class="h-3.5 w-3.5" />
            </button>
            <div
              ref="assetTypeTabScroller"
              class="asset-type-tab-scroll flex min-w-0 flex-nowrap items-center gap-1 overflow-x-auto overflow-y-hidden rounded-md border border-slate-200 bg-slate-50 p-0.5"
              @wheel="handleAssetTypeTabWheel"
            >
              <button
                v-for="tab in assetTypeTabs"
                :key="tab.key"
                type="button"
                class="inline-flex h-6 shrink-0 items-center justify-center gap-1 rounded px-1.5 text-[10px] font-semibold leading-none transition"
                :class="isActiveTab(tab.key) ? 'bg-indigo-600 text-white shadow-sm' : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-100 hover:text-slate-800'"
                :title="`${tab.label} ${tab.count}`"
                @click="activeAssetTypeTab = tab.key"
              >
                <span>{{ tab.label }}</span>
                <span
                  class="shrink-0 rounded-full px-1 text-[9px] leading-4"
                  :class="isActiveTab(tab.key) ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'"
                >
                  {{ tab.count }}
                </span>
              </button>
            </div>
            <button
              type="button"
              class="flex h-7 w-6 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="向右查看更多资源类型"
              title="向右查看更多类型"
              @click="scrollAssetTypeTabs(1)"
            >
              <ChevronRight class="h-3.5 w-3.5" />
            </button>
          </div>
          <div class="resource-column-scroll mt-2 grid min-h-0 flex-1 gap-1.5 overflow-y-auto pr-1 sm:grid-cols-2">
            <button
              v-for="asset in activeTabAssets"
              :key="asset.id"
              type="button"
              class="flex min-w-0 items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-left text-xs font-semibold transition disabled:cursor-not-allowed"
              :class="assetOptionClass(asset.name)"
              :disabled="isAutomatic(asset.name)"
              @click="emit('toggleAsset', asset.name)"
            >
              <span class="truncate">{{ asset.name }}</span>
              <span v-if="isAutomatic(asset.name)" class="shrink-0 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                自动
              </span>
              <Check v-else-if="isSelected(asset.name)" class="h-3.5 w-3.5 shrink-0" />
              <Plus v-else class="h-3.5 w-3.5 shrink-0" />
            </button>
          </div>
        </div>
        <p v-else class="mt-2 flex min-h-0 flex-1 items-center justify-center text-xs text-slate-400">
          {{ workspaceId ? '没有匹配的资源' : '暂无工作空间资源' }}
        </p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, ChevronLeft, ChevronRight, Package, Plus, RefreshCw, RotateCcw, Search, X } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import type { AssetResponse, AssetType } from '@/types/api'

const props = defineProps<{
  workspaceId?: number | null
  assetKeyword: string
  automaticAssetNames: string[]
  extraAssetNames: string[]
  assetOptions: AssetResponse[]
  assetOptionsLoading: boolean
  extraAssetsSaving?: boolean
  canSaveExtraAssets: boolean
}>()

const emit = defineEmits<{
  'update:assetKeyword': [value: string]
  loadAssets: []
  toggleAsset: [assetName: string]
  removeAsset: [assetName: string]
  restore: []
  saveExtraAssets: []
}>()

const assetTypeOrder: AssetType[] = ['image', 'icon', 'font', 'video', 'drawio', 'mermaid', 'chart', 'formula']
const assetTypeLabels: Record<AssetType, string> = {
  image: '图片',
  icon: '图标',
  font: '字体',
  video: '视频',
  drawio: 'Draw.io',
  mermaid: 'Mermaid',
  chart: '图表',
  formula: '公式',
}

type AssetTypeTabKey = 'all' | AssetType

const activeAssetTypeTab = ref<AssetTypeTabKey>('all')
const assetTypeTabScroller = ref<HTMLElement | null>(null)
const automaticAssetNameSet = computed(() => new Set(props.automaticAssetNames))
const assetTypeLabelByName = computed(() => {
  const result = new Map<string, string>()
  for (const asset of props.assetOptions) {
    result.set(asset.name, assetTypeLabels[asset.asset_type])
  }
  return result
})
const automaticIncludedAssets = computed(() => props.automaticAssetNames.map(name => ({
  name,
  typeLabel: assetTypeLabelByName.value.get(name) ?? '资源',
})))
const extraIncludedAssets = computed(() => props.extraAssetNames
  .filter(name => !automaticAssetNameSet.value.has(name))
  .map(name => ({
    name,
    typeLabel: assetTypeLabelByName.value.get(name) ?? '资源',
  })))
const groupedAssetOptions = computed(() => {
  const groups = new Map<AssetType, AssetResponse[]>()
  for (const asset of props.assetOptions) {
    const items = groups.get(asset.asset_type) ?? []
    items.push(asset)
    groups.set(asset.asset_type, items)
  }
  return [...groups.entries()]
    .sort(([left], [right]) => assetTypeOrder.indexOf(left) - assetTypeOrder.indexOf(right))
    .map(([type, items]) => ({
      type,
      label: assetTypeLabels[type],
      items,
    }))
})
const assetTypeTabs = computed(() => [
  {
    key: 'all' as const,
    label: '全部',
    count: props.assetOptions.length,
  },
  ...groupedAssetOptions.value.map(group => ({
    key: group.type,
    label: group.label,
    count: group.items.length,
  })),
])
const activeTabAssets = computed(() => {
  if (activeAssetTypeTab.value === 'all') {
    return props.assetOptions
  }
  return groupedAssetOptions.value.find(group => group.type === activeAssetTypeTab.value)?.items ?? []
})
watch(assetTypeTabs, (tabs) => {
  if (!tabs.some(tab => tab.key === activeAssetTypeTab.value)) {
    activeAssetTypeTab.value = 'all'
  }
})

/**
 * 判断资源是否已被选入额外资源草稿。
 * @param assetName 资源名
 */
function isSelected(assetName: string): boolean {
  return props.extraAssetNames.includes(assetName)
}

/**
 * 判断资源类型 Tab 是否处于选中状态。
 * @param tabKey Tab key
 */
function isActiveTab(tabKey: AssetTypeTabKey): boolean {
  return activeAssetTypeTab.value === tabKey
}

/**
 * 判断资源是否由当前构建自动包含，自动资源只展示不可取消。
 * @param assetName 资源名
 */
function isAutomatic(assetName: string): boolean {
  return automaticAssetNameSet.value.has(assetName)
}

/**
 * 滚动资源类型筛选条，避免窄列中隐藏的类型无法访问。
 * @param direction 滚动方向，-1 向左，1 向右
 */
function scrollAssetTypeTabs(direction: -1 | 1): void {
  const scroller = assetTypeTabScroller.value
  if (!scroller) {
    return
  }
  scroller.scrollBy({
    left: direction * Math.max(120, scroller.clientWidth * 0.75),
    behavior: 'smooth',
  })
}

/**
 * 在类型筛选条上使用滚轮时转为横向滚动。
 * @param event 鼠标滚轮事件
 */
function handleAssetTypeTabWheel(event: WheelEvent): void {
  const scroller = assetTypeTabScroller.value
  if (!scroller || scroller.scrollWidth <= scroller.clientWidth) {
    return
  }
  event.preventDefault()
  scroller.scrollLeft += event.deltaX || event.deltaY
}

/**
 * 生成资源项样式，区分自动包含、额外选中和未选择。
 * @param assetName 资源名
 */
function assetOptionClass(assetName: string): string {
  if (isAutomatic(assetName)) {
    return 'border-slate-200 bg-slate-50 text-slate-500'
  }
  if (isSelected(assetName)) {
    return 'border-indigo-200 bg-indigo-50 text-indigo-700'
  }
  return 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
}
</script>

<style scoped>
.resource-column-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgb(203 213 225) transparent;
}

.resource-column-scroll::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}

.resource-column-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.resource-column-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgb(203 213 225);
}

.asset-type-tab-scroll {
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.asset-type-tab-scroll::-webkit-scrollbar {
  display: none;
}
</style>
