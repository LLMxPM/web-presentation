<!-- 文件功能：提供工作空间样式选择与应用入口，只把样式字段填充到外层草稿。 -->
<template>
  <div :class="rootClass">
    <div class="flex items-start justify-between gap-3">
      <div>
        <label class="text-sm font-semibold text-slate-700">{{ label }}</label>
        <p v-if="hint" class="mt-1 text-xs text-slate-400">{{ hint }}</p>
      </div>
      <button
        type="button"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 text-xs font-semibold text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
        :disabled="loading || !workspaceId"
        @click="loadStyles"
      >
        <RefreshCw class="h-3.5 w-3.5" />
        刷新
      </button>
    </div>

    <div class="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_92px]">
      <SearchableSelect
        :model-value="selectedStyleId"
        :options="styleOptions"
        :disabled="loading || !workspaceId"
        :placeholder="workspaceId ? '选择工作空间样式' : '缺少工作空间上下文'"
        search-placeholder="搜索样式名称、key"
        clearable
        @update:model-value="handleSelectedStyleChange"
      />
      <button
        type="button"
        class="inline-flex h-10 items-center justify-center rounded-xl bg-slate-900 px-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="!selectedStyle || loading"
        @click="applySelectedStyle"
      >
        应用
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RefreshCw } from '@lucide/vue'

import { getErrorMessage } from '@/api/http'
import { listWorkspaceStyles } from '@/api/styles'
import SearchableSelect from '@/components/ui/SearchableSelect.vue'
import type { SelectModelValue, SelectOption } from '@/components/ui/select'
import type { WorkspaceStyleItem } from '@/types/api'
import { Message } from '@/utils/message'

const props = withDefaults(defineProps<{
  workspaceId: number | null
  label?: string
  hint?: string
  embedded?: boolean
}>(), {
  label: '应用工作空间样式',
  hint: '会填充主题、页面尺寸、菜单模式、PDF 导出按钮和 Markdown 样式规范，保存后才会写入项目。',
  embedded: false,
})

const emit = defineEmits<{
  apply: [style: WorkspaceStyleItem]
}>()

const loading = ref(false)
const styles = ref<WorkspaceStyleItem[]>([])
const selectedStyleId = ref<number | null>(null)
const rootClass = computed(() => (
  props.embedded ? '' : 'rounded-xl border border-slate-200 bg-white p-4'
))

const styleOptions = computed<SelectOption[]>(() => styles.value.map(style => ({
  label: style.name,
  value: style.id,
  description: formatStyleOptionDescription(style),
  keywords: [style.name, style.key, style.description ?? ''],
})))

const selectedStyle = computed(() => styles.value.find(style => style.id === selectedStyleId.value) || null)

watch(
  () => props.workspaceId,
  () => {
    selectedStyleId.value = null
    void loadStyles()
  },
  { immediate: true },
)

/**
 * 加载当前工作空间的样式列表。
 */
async function loadStyles(): Promise<void> {
  if (!props.workspaceId) {
    styles.value = []
    return
  }
  loading.value = true
  try {
    const response = await listWorkspaceStyles(props.workspaceId, { page: 1, page_size: 100 })
    styles.value = response.items
  } catch (error) {
    Message.error(getErrorMessage(error, '加载样式列表失败。'))
  } finally {
    loading.value = false
  }
}

/**
 * 统一处理样式选择器输出。
 * @param value 选择组件返回值
 */
function handleSelectedStyleChange(value: SelectModelValue): void {
  selectedStyleId.value = typeof value === 'number' ? value : null
}

/**
 * 格式化样式选项的辅助说明，显式展示样式是否会覆盖项目主题。
 * @param style 工作空间样式
 */
function formatStyleOptionDescription(style: WorkspaceStyleItem): string {
  const themeLabel = style.theme_key ? `主题 ${style.theme_key}` : '不覆盖主题'
  return `${style.key} · ${themeLabel} · ${style.page_width} x ${style.page_height}`
}

/**
 * 将当前选中样式交给外层填充草稿。
 */
function applySelectedStyle(): void {
  if (selectedStyle.value) {
    emit('apply', selectedStyle.value)
  }
}
</script>
