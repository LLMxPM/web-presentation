<!-- 文件功能：提供工作空间主题的选择器与预览面板，供项目配置和组件预览配置复用。 -->
<template>
  <div :class="compact ? 'space-y-1.5' : 'space-y-3'">
    <div v-if="!compact || label || hint || loading" class="flex items-center justify-between gap-3">
      <div>
        <p
          v-if="label"
          :class="compact ? 'text-[11px] font-semibold text-text-muted' : 'ml-1 text-sm font-semibold text-text-emphasis'"
        >
          {{ label }}
        </p>
        <p v-if="hint" class="mt-1 text-[11px] leading-5 text-text-disabled">{{ hint }}</p>
      </div>
      <span v-if="loading" class="text-[11px] text-text-disabled">正在加载主题...</span>
    </div>

    <UiCombobox
      :model-value="modelValue"
      :options="themeOptions"
      :disabled="loading || !workspaceId"
      :placeholder="workspaceId ? '请选择主题' : '缺少工作空间上下文'"
      search-placeholder="搜索主题名称、key"
      :clearable="clearable"
      @update:model-value="handleThemeChange"
    />

    <div v-if="showPreview && selectedTheme">
      <ThemePreviewCard
        :key-name="selectedTheme.key"
        :name="selectedTheme.name"
        :description="selectedTheme.description"
        :palette="selectedTheme.palette"
        :logo-url="selectedTheme.logo_asset?.url"
        :invert-logo-url="selectedTheme.invert_logo_asset?.url"
        :project-icon-url="selectedTheme.project_icon_asset?.url"
        :project-icon-name="selectedTheme.project_icon_name"
        :project-icon-analysis="selectedTheme.project_icon_asset?.analysis_metadata || null"
        :heading-font-label="selectedTheme.heading_font_family?.name || selectedTheme.heading_font_label || 'sans-serif'"
        :body-font-label="selectedTheme.body_font_family?.name || selectedTheme.body_font_label || 'sans-serif'"
        :code-font-label="selectedTheme.code_font_family?.name || selectedTheme.code_font_label || 'monospace'"
        :heading-font-family="fontFamilyById.get(selectedTheme.heading_font_family_id || -1) || null"
        :body-font-family="fontFamilyById.get(selectedTheme.body_font_family_id || -1) || null"
        :code-font-family="fontFamilyById.get(selectedTheme.code_font_family_id || -1) || null"
      />
    </div>
    <div
      v-else-if="showPreview"
      class="rounded-2xl border border-dashed border-border bg-canvas px-4 py-6 text-center text-sm text-text-disabled"
    >
      当前未选择主题。
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { listWorkspaceFontFamilies } from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import { listWorkspaceThemes } from '@/api/themes'
import { UiCombobox } from '@/components/ui'
import type { SelectModelValue, SelectOption } from '@/components/ui/select'
import type { WorkspaceFontFamilyItem, WorkspaceThemeItem } from '@/types/api'
import { Message } from '@/utils/message'
import ThemePreviewCard from './ThemePreviewCard.vue'

const props = withDefaults(defineProps<{
  workspaceId: number | null
  modelValue: string | null
  preferredKey?: string | null
  label?: string
  hint?: string
  showPreview?: boolean
  compact?: boolean
  clearable?: boolean
  autoSelect?: boolean
}>(), {
  preferredKey: null,
  label: '主题',
  hint: '',
  showPreview: true,
  compact: false,
  clearable: false,
  autoSelect: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
}>()

const loading = ref(false)
const themes = ref<WorkspaceThemeItem[]>([])
const fontFamilies = ref<WorkspaceFontFamilyItem[]>([])
const fontFamilyById = computed(() => new Map(fontFamilies.value.map(family => [family.id, family])))
const themeOptions = computed<SelectOption[]>(() => themes.value.map(theme => ({
  label: theme.name,
  value: theme.key,
  description: props.compact ? undefined : theme.key,
  keywords: [theme.name, theme.key, theme.description ?? ''],
})))

const selectedTheme = computed(() => {
  if (!props.modelValue) {
    return null
  }
  return themes.value.find(item => item.key === props.modelValue) || null
})

watch(
  () => [props.workspaceId, props.showPreview] as const,
  async ([workspaceId, showPreview]) => {
    if (!workspaceId) {
      themes.value = []
      fontFamilies.value = []
      return
    }
    loading.value = true
    try {
      const [response, familyResponse] = await Promise.all([
        listWorkspaceThemes(workspaceId),
        showPreview
          ? listWorkspaceFontFamilies(workspaceId, { page: 1, page_size: 100 })
            .catch(() => ({ items: [] as WorkspaceFontFamilyItem[] }))
          : Promise.resolve({ items: [] as WorkspaceFontFamilyItem[] }),
      ])
      themes.value = response.items
      fontFamilies.value = familyResponse.items
      if (props.autoSelect && !props.modelValue && response.items.length > 0) {
        const preferredTheme = props.preferredKey
          ? response.items.find(item => item.key === props.preferredKey)
          : null
        emit('update:modelValue', preferredTheme?.key || response.items[0].key)
      }
    } catch (error) {
      Message.error(getErrorMessage(error, '加载主题列表失败。'))
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

/**
 * 统一处理主题选择组件的单选输出，确保外层始终持有 string|null。
 * @param value 选择组件返回的值
 */
function handleThemeChange(value: SelectModelValue) {
  emit('update:modelValue', typeof value === 'string' ? value : null)
}
</script>
