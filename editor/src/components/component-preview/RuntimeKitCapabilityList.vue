<!-- 文件功能：展示 Runtime Kit 内建能力目录，负责筛选、复制 import，并把预览或说明意图交给外层。 -->
<template>
  <section class="flex min-h-0 flex-col">
    <div class="shrink-0 border-b border-slate-100 bg-white px-4 py-2">
      <LibrarySegmentedControl
        :model-value="selectedKind"
        :options="kindOptions"
        :columns="4"
        @update:model-value="handleSelectKind"
      />
      <div class="mt-2">
        <LibraryChipFilter v-model="selectedCategory" :options="categoryOptions" />
      </div>
      <div class="mt-2">
        <LibraryChipFilter v-model="selectedVersion" :options="versionOptions" all-label="最新版本" />
      </div>
    </div>

    <div v-if="loading" class="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-6">
      <div class="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent"></div>
      <span class="text-sm font-bold text-slate-400">正在加载内建能力...</span>
    </div>

    <div v-else class="min-h-0 flex-1 overflow-y-auto p-4 pb-24">
      <div
        v-if="filteredItems.length === 0"
        class="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-100 bg-slate-50 px-4 py-12 text-center"
      >
        <PackageOpen class="mb-3 h-10 w-10 text-slate-300" />
        <p class="text-sm font-semibold text-slate-500">暂无匹配的内建能力</p>
      </div>

      <div v-else class="space-y-3">
        <article
          v-for="item in filteredItems"
          :key="`${item.kind}:${item.name}`"
          class="group cursor-pointer rounded-xl border bg-white p-4 transition-all hover:border-indigo-300 hover:shadow-sm"
          :class="selectedName === item.name ? 'border-indigo-400 ring-1 ring-indigo-200' : 'border-slate-200'"
          @click="openCapability(item)"
        >
          <div class="mb-2 flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <div class="mb-1 flex flex-wrap items-center gap-2">
                <h3 class="truncate text-sm font-bold text-slate-800 group-hover:text-indigo-600">
                  {{ item.display_name }}
                </h3>
                <span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-black uppercase text-slate-500">
                  {{ item.category }}
                </span>
                <span class="rounded bg-slate-50 px-1.5 py-0.5 text-[10px] font-black uppercase text-slate-500">
                  {{ item.kind }}
                </span>
                <span class="rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-black uppercase text-emerald-600">
                  v{{ item.version_no }}
                </span>
                <span
                  v-if="!item.previewable"
                  class="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-black uppercase text-amber-600"
                >
                  doc-only
                </span>
              </div>
              <div class="inline-flex max-w-full rounded border border-slate-100 bg-slate-50 px-1.5 py-0.5">
                <span class="truncate font-mono text-[10px] font-bold text-slate-400">{{ item.import_path }}</span>
              </div>
            </div>
            <div class="mt-0.5 flex shrink-0 items-center gap-1">
              <button
                v-if="item.kind === 'component'"
                type="button"
                class="rounded-lg p-1 text-slate-400 opacity-0 transition-colors hover:bg-indigo-50 hover:text-indigo-600 group-hover:opacity-100"
                title="复制 import 语句"
                @click.stop="copyRuntimeKitComponentImportStatement(item)"
              >
                <Copy class="h-3.5 w-3.5" />
              </button>
              <Eye v-if="item.previewable" class="h-4 w-4 text-slate-300 group-hover:text-indigo-500" />
              <FileText v-else class="h-4 w-4 text-slate-300 group-hover:text-indigo-500" />
            </div>
          </div>
          <p class="mb-3 line-clamp-2 text-[11px] leading-relaxed text-slate-500">
            {{ item.summary || item.description }}
          </p>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="tag in item.tags"
              :key="`${item.name}-${tag}`"
              class="rounded-full bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-400"
            >
              {{ tag }}
            </span>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Copy, Eye, FileText, PackageOpen } from '@lucide/vue'

import { getErrorMessage } from '@/api/http'
import { listRuntimeKitComponents } from '@/api/runtime-kit'
import LibraryChipFilter from '@/components/project/LibraryChipFilter.vue'
import LibrarySegmentedControl from '@/components/project/LibrarySegmentedControl.vue'
import type { RuntimeKitCapabilityKind, RuntimeKitComponentCapabilityItem } from '@/types/api'
import { buildRuntimeKitComponentImportUsage } from '@/utils/component-import'
import { Message } from '@/utils/message'

const props = withDefaults(defineProps<{
  keyword: string
  selectedName?: string | null
}>(), {
  selectedName: null,
})

const emit = defineEmits<{
  'runtime-kit-preview-selected': [item: RuntimeKitComponentCapabilityItem]
  'runtime-kit-doc-selected': [item: RuntimeKitComponentCapabilityItem]
}>()

const loading = ref(false)
const items = ref<RuntimeKitComponentCapabilityItem[]>([])
const selectedKind = ref<RuntimeKitCapabilityKind | ''>('')
const selectedCategory = ref('')
const selectedVersion = ref('')

const kindOptions: Array<{ value: RuntimeKitCapabilityKind | ''; label: string }> = [
  { value: '', label: '全部' },
  { value: 'component', label: '组件' },
  { value: 'composable', label: 'Composables' },
  { value: 'util', label: 'Utils' },
]

const categories = computed(() => {
  const sourceItems = selectedKind.value ? items.value.filter(item => item.kind === selectedKind.value) : items.value
  return Array.from(new Set(sourceItems.map(item => item.category))).sort()
})
const categoryOptions = computed(() => categories.value.map(category => ({ label: category, value: category })))
const versionOptions = computed(() => {
  return Array.from(new Set(items.value.map(item => item.version_no)))
    .sort((left, right) => left - right)
    .map(versionNo => ({ label: `v${versionNo}`, value: String(versionNo) }))
})
const filteredItems = computed(() => {
  const keyword = props.keyword.trim().toLowerCase()
  return getVisibleVersionItems(items.value, selectedVersion.value).filter(item => {
    if (selectedKind.value && item.kind !== selectedKind.value) {
      return false
    }
    if (selectedCategory.value && item.category !== selectedCategory.value) {
      return false
    }
    if (!keyword) {
      return true
    }
    return [
      item.name,
      item.import_path,
      item.display_name,
      item.summary,
      item.description,
      ...item.tags,
      ...item.usage,
      item.returns || '',
      ...item.return_example,
      ...item.constraints,
    ].some(value => String(value || '').toLowerCase().includes(keyword))
  })
})

watch(() => selectedKind.value, () => {
  selectedCategory.value = ''
})

/**
 * 接收分段控件值并切换能力类型筛选。
 * @param value 能力类型，空字符串表示全部
 */
function handleSelectKind(value: string): void {
  selectedKind.value = value as RuntimeKitCapabilityKind | ''
}

/**
 * 加载 Runtime Kit manifest 暴露出的能力目录。
 */
async function fetchItems(): Promise<void> {
  loading.value = true
  try {
    const response = await listRuntimeKitComponents({ include_all_versions: true })
    items.value = response.items
  } catch (error) {
    Message.error(getErrorMessage(error, '加载 Runtime Kit 内建能力失败'))
  } finally {
    loading.value = false
  }
}

/**
 * 按版本筛选能力；未选择版本时每个能力只展示最新版本。
 * @param sourceItems Runtime Kit 能力项
 * @param versionValue 当前版本筛选值
 * @returns 可用于列表展示的能力项
 */
function getVisibleVersionItems(
  sourceItems: RuntimeKitComponentCapabilityItem[],
  versionValue: string,
): RuntimeKitComponentCapabilityItem[] {
  const selectedVersionNo = Number(versionValue)
  if (Number.isInteger(selectedVersionNo) && selectedVersionNo > 0) {
    return sourceItems.filter(item => item.version_no === selectedVersionNo)
  }

  const latestByKey = new Map<string, number>()
  sourceItems.forEach((item) => {
    const key = `${item.kind}:${item.base_name}`
    latestByKey.set(key, Math.max(latestByKey.get(key) || 0, item.version_no))
  })
  return sourceItems.filter(item => item.version_no === latestByKey.get(`${item.kind}:${item.base_name}`))
}

/**
 * 打开能力条目，可预览项交给右侧工作台，doc-only 项交给说明弹窗。
 * @param item Runtime Kit 能力条目
 */
function openCapability(item: RuntimeKitComponentCapabilityItem): void {
  if (item.previewable) {
    emit('runtime-kit-preview-selected', item)
    return
  }
  emit('runtime-kit-doc-selected', item)
}

/**
 * 复制 Runtime Kit 组件能力的 import 语句。
 * @param item Runtime Kit 能力条目
 */
async function copyRuntimeKitComponentImportStatement(item: RuntimeKitComponentCapabilityItem): Promise<void> {
  const usage = buildRuntimeKitComponentImportUsage(item)
  if (!usage) {
    Message.error('当前能力不是可默认导入的组件。')
    return
  }

  try {
    await navigator.clipboard.writeText(usage.importStatement)
    Message.success('import 语句已复制到剪贴板。')
  } catch {
    Message.error('复制 import 语句失败，请检查浏览器剪贴板权限。')
  }
}

void fetchItems()
</script>
