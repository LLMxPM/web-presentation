<!-- 文件功能：提供工作空间主题的创建与编辑弹窗，支持资源选择和实时预览。 -->
<template>
  <UiDialog :open="dialogVisible" :title="theme ? '编辑主题' : '新建主题'" size="canvas" @update:open="dialogVisible = $event">
    <div class="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_500px] 2xl:grid-cols-[minmax(0,1fr)_560px]">
      <div class="min-w-0 space-y-4">
        <section class="rounded-2xl border border-border bg-surface p-5 shadow-sm">
          <div class="mb-4">
            <h3 class="text-sm font-black text-text-strong">基础信息</h3>
            <p class="mt-1 text-xs text-text-disabled">主题 key 用于 Runtime 配置引用，保存时会自动归一化为小写。</p>
          </div>
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            <UiFormField
              label="主题 key"
              required
              description="仅支持小写字母、数字、连字符和下划线"
            >
              <template #default="field">
                <UiInput
                  v-model="form.key"
                  required
                  placeholder="例如 lightblue"
                  :input-id="field.inputId"
                  :described-by="field.describedBy"
                />
              </template>
            </UiFormField>
            <UiFormField label="主题名称" required>
              <template #default="field">
                <UiInput
                  v-model="form.name"
                  required
                  placeholder="请输入主题名称"
                  :input-id="field.inputId"
                  :described-by="field.describedBy"
                />
              </template>
            </UiFormField>
          </div>

          <UiFormField class="mt-4" label="主题描述">
            <template #default="field">
              <UiInput
                v-model="form.description"
                placeholder="概括主题的视觉特征和适用场景"
                :input-id="field.inputId"
                :described-by="field.describedBy"
              />
            </template>
          </UiFormField>
        </section>

        <section class="rounded-2xl border border-border bg-surface p-5 shadow-sm">
          <div class="mb-5">
            <h3 class="text-sm font-black text-text-strong">品牌资源与字体绑定</h3>
          </div>

          <div class="space-y-5">
            <div>
              <h4 class="text-xs font-black text-text-emphasis">品牌资源</h4>
              <div class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
                <div class="space-y-1.5">
                  <span class="text-xs font-bold text-text-muted">主题 Logo</span>
                  <AssetPicker
                    :model-value="form.logo_asset_id"
                    :workspace-id="workspaceId"
                    asset-type="image"
                    :selected-asset="selectedLogoAsset"
                    value-mode="id"
                    title="选择主题 Logo"
                    placeholder="不设置"
                    @update:model-value="updateNullableNumberField('logo_asset_id', $event)"
                    @select="selectedLogoAsset = $event"
                  />
                </div>
                <div class="space-y-1.5">
                  <span class="text-xs font-bold text-text-muted">反色 Logo</span>
                  <AssetPicker
                    :model-value="form.invert_logo_asset_id"
                    :workspace-id="workspaceId"
                    asset-type="image"
                    :selected-asset="selectedInvertLogoAsset"
                    value-mode="id"
                    title="选择反色 Logo"
                    placeholder="不设置"
                    @update:model-value="updateNullableNumberField('invert_logo_asset_id', $event)"
                    @select="selectedInvertLogoAsset = $event"
                  />
                </div>
                <div class="space-y-1.5">
                  <span class="text-xs font-bold text-text-muted">项目图标</span>
                  <AssetPicker
                    :model-value="form.project_icon_asset_id"
                    :workspace-id="workspaceId"
                    asset-type="icon"
                    :selected-asset="selectedProjectIconAsset"
                    value-mode="id"
                    placeholder="不设置"
                    @update:model-value="updateNullableNumberField('project_icon_asset_id', $event)"
                    @select="selectedProjectIconAsset = $event"
                  />
                </div>
              </div>
            </div>

            <div class="border-t border-border-muted pt-4">
              <h4 class="text-xs font-black text-text-emphasis">字体绑定</h4>
              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                <label class="space-y-1.5">
                  <span class="text-xs font-bold text-text-muted">标题字体</span>
                  <UiCombobox
                    :model-value="form.heading_font_family_id"
                    :options="fontOptions"
                    clearable
                    placeholder="浏览器默认"
                    search-placeholder="搜索字体族名称"
                    @update:model-value="updateNullableNumberField('heading_font_family_id', $event)"
                  />
                </label>
                <label class="space-y-1.5">
                  <span class="text-xs font-bold text-text-muted">正文字体</span>
                  <UiCombobox
                    :model-value="form.body_font_family_id"
                    :options="fontOptions"
                    clearable
                    placeholder="浏览器默认"
                    search-placeholder="搜索字体族名称"
                    @update:model-value="updateNullableNumberField('body_font_family_id', $event)"
                  />
                </label>
                <label class="space-y-1.5">
                  <span class="text-xs font-bold text-text-muted">代码字体</span>
                  <UiCombobox
                    :model-value="form.code_font_family_id"
                    :options="fontOptions"
                    clearable
                    placeholder="浏览器默认"
                    search-placeholder="搜索字体族名称"
                    @update:model-value="updateNullableNumberField('code_font_family_id', $event)"
                  />
                </label>
              </div>
            </div>

          </div>
        </section>

        <section class="rounded-2xl border border-border bg-surface p-5 shadow-sm">
          <div class="mb-4">
            <h3 class="text-sm font-black text-text-strong">颜色系统</h3>
          </div>

          <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div v-for="group in colorGroups" :key="group.key" class="rounded-xl border border-border-muted bg-canvas p-3">
              <div class="mb-2 flex items-center justify-between gap-2">
                <h4 class="text-xs font-black text-text-emphasis">{{ group.label }}</h4>
                <span class="text-[10px] font-bold text-text-disabled">{{ group.fields.length }} tokens</span>
              </div>
              <p class="mb-2 text-[11px] leading-5 text-text-disabled">{{ group.description }}</p>
              <div class="grid grid-cols-1 gap-2">
                <label
                  v-for="field in group.fields"
                  :key="field.key"
                  class="grid grid-cols-[4.5rem_2.25rem_minmax(0,1fr)] items-center gap-2 rounded-lg border border-border bg-surface px-2 py-1.5"
                >
                  <span class="truncate text-[11px] font-bold text-text-muted">{{ field.label }}</span>
                  <input
                    :value="normalizeColor(field.getter())"
                    type="color"
                    class="h-7 w-8 cursor-pointer rounded border border-border bg-surface p-0.5"
                    @input="field.setter(($event.target as HTMLInputElement).value)"
                  >
                  <UiInput
                    :value="field.getter()"
                    class="h-7 min-w-0 rounded-md border border-border px-2 font-mono text-xs outline-none focus:border-border-focus"
                    @input="field.setter(($event.target as HTMLInputElement).value)"
                  />
                </label>
              </div>
            </div>

            <div class="rounded-xl border border-border-muted bg-canvas p-3 lg:col-span-2">
              <div class="mb-2 flex items-center justify-between gap-2">
                <h4 class="text-xs font-black text-text-emphasis">强调色组</h4>
                <span class="text-[10px] font-bold text-text-disabled">{{ form.palette.accent.length }} tokens</span>
              </div>
              <div class="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
                <label
                  v-for="(_, index) in form.palette.accent"
                  :key="`accent-${index}`"
                  class="grid grid-cols-[3rem_2.25rem_minmax(0,1fr)] items-center gap-2 rounded-lg border border-border bg-surface px-2 py-1.5"
                >
                  <span class="truncate text-[11px] font-bold text-text-muted">色 {{ index + 1 }}</span>
                  <input
                    :value="normalizeColor(form.palette.accent[index])"
                    type="color"
                    class="h-7 w-8 cursor-pointer rounded border border-border bg-surface p-0.5"
                    @input="form.palette.accent[index] = ($event.target as HTMLInputElement).value"
                  >
                  <UiInput
                    v-model="form.palette.accent[index]"
                    class="h-7 min-w-0 rounded-md border border-border px-2 font-mono text-xs outline-none focus:border-border-focus"
                  />
                </label>
              </div>
            </div>
          </div>
        </section>
      </div>

      <aside class="sticky top-0 min-w-0 space-y-4 rounded-2xl border border-border bg-canvas p-5 shadow-sm">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-black text-text-strong">实时预览</h3>
            <p class="mt-1 text-xs text-text-disabled">更宽的预览区便于检查文字、Logo、图标和反色区域。</p>
          </div>
          <span class="rounded-full bg-surface px-2.5 py-1 text-[11px] font-bold text-text-muted shadow-sm">保存前预览</span>
        </div>
        <ThemePreviewCard
          class="rounded-xl shadow-none"
          :key-name="form.key"
          :name="form.name"
          :description="form.description"
          :palette="form.palette"
          :logo-url="selectedLogoAsset?.url"
          :invert-logo-url="selectedInvertLogoAsset?.url"
          :project-icon-url="selectedProjectIconAsset?.url"
          :project-icon-name="selectedProjectIconAsset?.name || form.project_icon_name"
          :project-icon-analysis="selectedProjectIconAsset?.analysis_metadata || null"
          :heading-font-label="selectedHeadingFont?.name || DEFAULT_HEADING_FONT_FAMILY"
          :body-font-label="selectedBodyFont?.name || DEFAULT_BODY_FONT_FAMILY"
          :code-font-label="selectedCodeFont?.name || DEFAULT_CODE_FONT_FAMILY"
          :heading-font-family="selectedHeadingFont"
          :body-font-family="selectedBodyFont"
          :code-font-family="selectedCodeFont"
        />
      </aside>
    </div>

    <template #footer>
      <UiButton variant="ghost" @click="dialogVisible = false">取消</UiButton>
      <UiButton variant="primary" :loading="saving" @click="handleSave">保存主题</UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { listWorkspaceFontFamilies } from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import AssetPicker from '@/components/ui/AssetPicker.vue'
import { UiButton, UiCombobox, UiDialog, UiFormField, UiInput } from '@/components/ui'
import type { SelectModelValue, SelectOption } from '@/components/ui/select'
import type { AssetResponse, ThemeAssetSummary, ThemePalette, WorkspaceFontFamilyItem, WorkspaceThemeItem } from '@/types/api'
import { Message } from '@/utils/message'
import ThemePreviewCard from './ThemePreviewCard.vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  workspaceId: number | null
  theme: WorkspaceThemeItem | null
  saving?: boolean
}>(), {
  saving: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [value: {
    key: string
    name: string
    description: string | null
    logo_asset_id: number | null
    invert_logo_asset_id: number | null
    project_icon_asset_id: number | null
    heading_font_family_id: number | null
    body_font_family_id: number | null
    code_font_family_id: number | null
    palette: ThemePalette
  }]
}>()

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const fontFamilies = ref<WorkspaceFontFamilyItem[]>([])
const selectedLogoAsset = ref<AssetResponse | ThemeAssetSummary | null>(null)
const selectedInvertLogoAsset = ref<AssetResponse | ThemeAssetSummary | null>(null)
const selectedProjectIconAsset = ref<AssetResponse | ThemeAssetSummary | null>(null)
const DEFAULT_HEADING_FONT_FAMILY = 'system-ui'
const DEFAULT_BODY_FONT_FAMILY = 'system-ui'
const DEFAULT_CODE_FONT_FAMILY = 'monospace'
const DEFAULT_THEME_PALETTE: ThemePalette = {
  text: { primary: '#0D286A', secondary: '#1D5297', invert: '#ffffff' },
  background: { default: '#ffffff', invert: '#0D286A' },
  border: { default: '#e5e7eb', subtle: '#d1d5db' },
  link: { default: '#3b82f6', hover: '#2563eb', visited: '#7c3aed' },
  accent: ['#0D286A', '#260E6D', '#9E8403', '#9E6B03', '#A110AB', '#C5003C'],
}
const form = reactive({
  key: 'lightblue',
  name: '白底蓝色',
  description: '白底蓝色主题，简约经典',
  logo_asset_id: null as number | null,
  invert_logo_asset_id: null as number | null,
  project_icon_asset_id: null as number | null,
  project_icon_name: 'slider',
  heading_font_family_id: null as number | null,
  body_font_family_id: null as number | null,
  code_font_family_id: null as number | null,
  palette: JSON.parse(JSON.stringify(DEFAULT_THEME_PALETTE)) as ThemePalette,
})

const paletteFields = [
  { key: 'text.primary', label: '主文字', getter: () => form.palette.text.primary, setter: (value: string) => { form.palette.text.primary = value } },
  { key: 'text.secondary', label: '副文字', getter: () => form.palette.text.secondary, setter: (value: string) => { form.palette.text.secondary = value } },
  { key: 'text.invert', label: '反色文字', getter: () => form.palette.text.invert, setter: (value: string) => { form.palette.text.invert = value } },
  { key: 'background.default', label: '主背景', getter: () => form.palette.background.default, setter: (value: string) => { form.palette.background.default = value } },
  { key: 'background.invert', label: '反色背景', getter: () => form.palette.background.invert, setter: (value: string) => { form.palette.background.invert = value } },
  { key: 'border.default', label: '主边框', getter: () => form.palette.border.default, setter: (value: string) => { form.palette.border.default = value } },
  { key: 'border.subtle', label: '弱边框', getter: () => form.palette.border.subtle, setter: (value: string) => { form.palette.border.subtle = value } },
  { key: 'link.default', label: '链接色', getter: () => form.palette.link.default, setter: (value: string) => { form.palette.link.default = value } },
  { key: 'link.hover', label: '悬停链接', getter: () => form.palette.link.hover, setter: (value: string) => { form.palette.link.hover = value } },
  { key: 'link.visited', label: '访问后链接', getter: () => form.palette.link.visited, setter: (value: string) => { form.palette.link.visited = value } },
]
const colorGroups = [
  {
    key: 'surface',
    label: '背景与边框',
    description: '统一观察页面底色、反色区块和边框层次，避免颜色关系割裂。',
    fields: paletteFields.filter(
      field => field.key.startsWith('background.') || field.key.startsWith('border.'),
    ),
  },
  {
    key: 'content',
    label: '文字与链接',
    description: '控制正文层级、反色文字和链接不同交互状态。',
    fields: paletteFields.filter(
      field => field.key.startsWith('text.') || field.key.startsWith('link.'),
    ),
  },
]

const selectedHeadingFont = computed(() => fontFamilies.value.find(item => item.id === form.heading_font_family_id) || null)
const selectedBodyFont = computed(() => fontFamilies.value.find(item => item.id === form.body_font_family_id) || null)
const selectedCodeFont = computed(() => fontFamilies.value.find(item => item.id === form.code_font_family_id) || null)
const fontOptions = computed<SelectOption[]>(() => fontFamilies.value.map(family => ({
  label: family.name,
  value: family.id,
  description: describeFontFamily(family),
  keywords: [family.name, ...family.faces.map(face => face.asset_name)],
})))

/** 汇总字体族内可用 face 的字重，作为下拉项的辅助说明。 */
function describeFontFamily(family: WorkspaceFontFamilyItem): string {
  const activeFaces = family.faces.filter(face => face.status === 'active')
  if (activeFaces.length === 0) {
    return '暂无可用字体文件'
  }
  const weights = Array.from(new Set(activeFaces.map(face => face.font_weight))).join(' / ')
  return `${activeFaces.length} 个字体文件（${weights}）`
}

watch(
  () => [props.modelValue, props.theme] as const,
  async ([visible, theme]) => {
    if (!visible) {
      return
    }
    await loadOptions()
    syncForm(theme)
  },
  { immediate: true },
)

async function loadOptions() {
  if (!props.workspaceId) {
    return
  }

  try {
    const familyResponse = await listWorkspaceFontFamilies(props.workspaceId, { page: 1, page_size: 100 })
    fontFamilies.value = familyResponse.items
  } catch (error) {
    Message.error(getErrorMessage(error, '加载主题编辑依赖失败。'))
  }
}

function syncForm(theme: WorkspaceThemeItem | null) {
  form.key = theme?.key || 'lightblue'
  form.name = theme?.name || '白底蓝色'
  form.description = theme?.description || '白底蓝色主题，简约经典'
  form.logo_asset_id = theme?.logo_asset_id || null
  form.invert_logo_asset_id = theme?.invert_logo_asset_id || null
  form.project_icon_asset_id = theme?.project_icon_asset_id || null
  selectedLogoAsset.value = theme?.logo_asset || null
  selectedInvertLogoAsset.value = theme?.invert_logo_asset || null
  selectedProjectIconAsset.value = theme?.project_icon_asset || null
  form.project_icon_name = theme?.project_icon_name || 'slider'
  form.heading_font_family_id = theme?.heading_font_family_id || null
  form.body_font_family_id = theme?.body_font_family_id || null
  form.code_font_family_id = theme?.code_font_family_id || null
  form.palette = JSON.parse(JSON.stringify(theme?.palette || DEFAULT_THEME_PALETTE)) as ThemePalette
}

/**
 * 将 select 的字符串值归一化为可选数字，避免 DOM 字符串污染表单状态。
 * @param field 需要更新的字段
 * @param value 通用下拉组件回传的最新值
 */
function updateNullableNumberField(
  field: 'logo_asset_id' | 'invert_logo_asset_id' | 'project_icon_asset_id' | 'heading_font_family_id' | 'body_font_family_id' | 'code_font_family_id',
  value: SelectModelValue,
) {
  if (Array.isArray(value) || value == null || value === '') {
    form[field] = null
    return
  }
  form[field] = typeof value === 'number' ? value : Number(value)
}

/**
 * 将任意颜色文本规范为 color input 可接受的 6 位 HEX，失败时回退到黑色。
 * @param value 用户当前输入的颜色文本
 */
function normalizeColor(value: string): string {
  const normalized = value.trim().replace('#', '')
  if (/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return `#${normalized}`
  }
  if (/^[0-9a-fA-F]{3}$/.test(normalized)) {
    return `#${normalized.split('').map(char => `${char}${char}`).join('')}`
  }
  return '#000000'
}

function handleSave() {
  const normalizedKey = form.key.trim().toLowerCase()
  if (!normalizedKey || !form.name.trim()) {
    Message.error('请填写主题 key 和名称。')
    return
  }
  if (!/^[a-z0-9_-]+$/.test(normalizedKey)) {
    Message.error('主题 key 仅支持小写字母、数字、连字符和下划线。')
    return
  }
  form.key = normalizedKey

  emit('save', {
    key: normalizedKey,
    name: form.name.trim(),
    description: form.description?.trim() || null,
    logo_asset_id: form.logo_asset_id,
    invert_logo_asset_id: form.invert_logo_asset_id,
    project_icon_asset_id: form.project_icon_asset_id,
    heading_font_family_id: form.heading_font_family_id,
    body_font_family_id: form.body_font_family_id,
    code_font_family_id: form.code_font_family_id,
    palette: JSON.parse(JSON.stringify(form.palette)) as ThemePalette,
  })
}
</script>

