<!-- 文件功能：提供工作空间主题的创建与编辑弹窗，支持资源选择和实时预览。 -->
<template>
  <BaseDialog v-model="dialogVisible" :title="theme ? '编辑主题' : '新建主题'" width="1440px">
    <div class="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_500px] 2xl:grid-cols-[minmax(0,1fr)_560px]">
      <div class="min-w-0 space-y-4">
        <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="mb-4">
            <h3 class="text-sm font-black text-slate-900">基础信息</h3>
            <p class="mt-1 text-xs text-slate-400">主题 key 用于 Runtime 配置引用，保存时会自动归一化为小写。</p>
          </div>
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            <label class="space-y-1.5">
              <span class="text-xs font-bold text-slate-500">主题 key</span>
              <input
                v-model="form.key"
                class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500 focus:bg-white"
              >
            </label>
            <label class="space-y-1.5">
              <span class="text-xs font-bold text-slate-500">主题名称</span>
              <input
                v-model="form.name"
                class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500 focus:bg-white"
              >
            </label>
          </div>

          <label class="mt-4 block space-y-1.5">
            <span class="text-xs font-bold text-slate-500">主题描述</span>
            <input
              v-model="form.description"
              class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500 focus:bg-white"
            >
          </label>
        </section>

        <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="mb-5">
            <h3 class="text-sm font-black text-slate-900">品牌资源与字体绑定</h3>
          </div>

          <div class="space-y-5">
            <div>
              <h4 class="text-xs font-black text-slate-700">品牌资源</h4>
              <div class="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
                <label class="space-y-1.5">
                  <span class="text-xs font-bold text-slate-500">主题 Logo</span>
                  <SearchableSelect
                    :model-value="form.logo_asset_id"
                    :options="logoAssetOptions"
                    clearable
                    placeholder="不设置"
                    search-placeholder="搜索 Logo 资源"
                    @update:model-value="updateNullableNumberField('logo_asset_id', $event)"
                  />
                </label>
                <label class="space-y-1.5">
                  <span class="text-xs font-bold text-slate-500">反色 Logo</span>
                  <SearchableSelect
                    :model-value="form.invert_logo_asset_id"
                    :options="logoAssetOptions"
                    clearable
                    placeholder="不设置"
                    search-placeholder="搜索反色 Logo 资源"
                    @update:model-value="updateNullableNumberField('invert_logo_asset_id', $event)"
                  />
                </label>
                <label class="space-y-1.5">
                  <span class="text-xs font-bold text-slate-500">项目图标</span>
                  <IconPicker
                    :model-value="form.project_icon_asset_id"
                    :assets="projectIconAssets"
                    value-mode="id"
                    placeholder="不设置"
                    @update:model-value="updateNullableNumberField('project_icon_asset_id', $event)"
                  />
                </label>
              </div>
            </div>

            <div class="border-t border-slate-100 pt-4">
              <h4 class="text-xs font-black text-slate-700">字体绑定</h4>
              <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                <label class="space-y-1.5">
                  <span class="text-xs font-bold text-slate-500">标题字体</span>
                  <SearchableSelect
                    :model-value="form.heading_font_id"
                    :options="fontOptions"
                    clearable
                    placeholder="浏览器默认"
                    search-placeholder="搜索字体名称"
                    @update:model-value="updateNullableNumberField('heading_font_id', $event)"
                  />
                </label>
                <label class="space-y-1.5">
                  <span class="text-xs font-bold text-slate-500">正文字体</span>
                  <SearchableSelect
                    :model-value="form.body_font_id"
                    :options="fontOptions"
                    clearable
                    placeholder="浏览器默认"
                    search-placeholder="搜索字体名称"
                    @update:model-value="updateNullableNumberField('body_font_id', $event)"
                  />
                </label>
                <label class="space-y-1.5">
                  <span class="text-xs font-bold text-slate-500">代码字体</span>
                  <SearchableSelect
                    :model-value="form.code_font_id"
                    :options="fontOptions"
                    clearable
                    placeholder="浏览器默认"
                    search-placeholder="搜索字体名称"
                    @update:model-value="updateNullableNumberField('code_font_id', $event)"
                  />
                </label>
              </div>
            </div>

          </div>
        </section>

        <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="mb-4">
            <h3 class="text-sm font-black text-slate-900">颜色系统</h3>
          </div>

          <div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div v-for="group in colorGroups" :key="group.key" class="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <div class="mb-2 flex items-center justify-between gap-2">
                <h4 class="text-xs font-black text-slate-700">{{ group.label }}</h4>
                <span class="text-[10px] font-bold text-slate-400">{{ group.fields.length }} tokens</span>
              </div>
              <p class="mb-2 text-[11px] leading-5 text-slate-400">{{ group.description }}</p>
              <div class="grid grid-cols-1 gap-2">
                <label
                  v-for="field in group.fields"
                  :key="field.key"
                  class="grid grid-cols-[4.5rem_2.25rem_minmax(0,1fr)] items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1.5"
                >
                  <span class="truncate text-[11px] font-bold text-slate-500">{{ field.label }}</span>
                  <input
                    :value="normalizeColor(field.getter())"
                    type="color"
                    class="h-7 w-8 cursor-pointer rounded border border-slate-200 bg-white p-0.5"
                    @input="field.setter(($event.target as HTMLInputElement).value)"
                  >
                  <input
                    :value="field.getter()"
                    class="h-7 min-w-0 rounded-md border border-slate-200 px-2 font-mono text-xs outline-none focus:border-indigo-500"
                    @input="field.setter(($event.target as HTMLInputElement).value)"
                  >
                </label>
              </div>
            </div>

            <div class="rounded-xl border border-slate-100 bg-slate-50 p-3 lg:col-span-2">
              <div class="mb-2 flex items-center justify-between gap-2">
                <h4 class="text-xs font-black text-slate-700">强调色组</h4>
                <span class="text-[10px] font-bold text-slate-400">{{ form.palette.accent.length }} tokens</span>
              </div>
              <div class="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
                <label
                  v-for="(_, index) in form.palette.accent"
                  :key="`accent-${index}`"
                  class="grid grid-cols-[3rem_2.25rem_minmax(0,1fr)] items-center gap-2 rounded-lg border border-slate-200 bg-white px-2 py-1.5"
                >
                  <span class="truncate text-[11px] font-bold text-slate-500">色 {{ index + 1 }}</span>
                  <input
                    :value="normalizeColor(form.palette.accent[index])"
                    type="color"
                    class="h-7 w-8 cursor-pointer rounded border border-slate-200 bg-white p-0.5"
                    @input="form.palette.accent[index] = ($event.target as HTMLInputElement).value"
                  >
                  <input
                    v-model="form.palette.accent[index]"
                    class="h-7 min-w-0 rounded-md border border-slate-200 px-2 font-mono text-xs outline-none focus:border-indigo-500"
                  >
                </label>
              </div>
            </div>
          </div>
        </section>
      </div>

      <aside class="sticky top-0 min-w-0 space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-5 shadow-sm">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-black text-slate-900">实时预览</h3>
            <p class="mt-1 text-xs text-slate-400">更宽的预览区便于检查文字、Logo、图标和反色区域。</p>
          </div>
          <span class="rounded-full bg-white px-2.5 py-1 text-[11px] font-bold text-slate-500 shadow-sm">保存前预览</span>
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
          :heading-font-label="selectedHeadingFont?.font_family || DEFAULT_HEADING_FONT_FAMILY"
          :body-font-label="selectedBodyFont?.font_family || DEFAULT_BODY_FONT_FAMILY"
          :code-font-label="selectedCodeFont?.font_family || DEFAULT_CODE_FONT_FAMILY"
        />
      </aside>
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="dialogVisible = false">取消</BaseButton>
      <BaseButton variant="primary" :loading="saving" @click="handleSave">保存主题</BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { listWorkspaceAssets, listWorkspaceFonts } from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import IconPicker from '@/components/ui/IconPicker.vue'
import SearchableSelect from '@/components/ui/SearchableSelect.vue'
import type { SelectModelValue, SelectOption } from '@/components/ui/select'
import type { AssetResponse, ThemePalette, WorkspaceFontConfigItem, WorkspaceThemeItem } from '@/types/api'
import { Message } from '@/utils/message'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
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
    heading_font_id: number | null
    body_font_id: number | null
    code_font_id: number | null
    palette: ThemePalette
  }]
}>()

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const logoAssets = ref<AssetResponse[]>([])
const projectIconAssets = ref<AssetResponse[]>([])
const fonts = ref<WorkspaceFontConfigItem[]>([])
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
  heading_font_id: null as number | null,
  body_font_id: null as number | null,
  code_font_id: null as number | null,
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

const selectedLogoAsset = computed(() => logoAssets.value.find(item => item.id === form.logo_asset_id) || null)
const selectedInvertLogoAsset = computed(() => logoAssets.value.find(item => item.id === form.invert_logo_asset_id) || null)
const selectedProjectIconAsset = computed(() => projectIconAssets.value.find(item => item.id === form.project_icon_asset_id) || null)
const selectedHeadingFont = computed(() => fonts.value.find(item => item.id === form.heading_font_id) || null)
const selectedBodyFont = computed(() => fonts.value.find(item => item.id === form.body_font_id) || null)
const selectedCodeFont = computed(() => fonts.value.find(item => item.id === form.code_font_id) || null)
const logoAssetOptions = computed<SelectOption[]>(() => logoAssets.value.map(asset => ({
  label: asset.name,
  value: asset.id,
  description: `${asset.asset_type === 'icon' ? '图标资源' : '图片资源'} / 原文件名：${asset.original_name}`,
  keywords: [asset.name, asset.original_name, asset.asset_type, ...(asset.tags ?? [])],
})))
const fontOptions = computed<SelectOption[]>(() => fonts.value.map(font => ({
  label: font.font_family,
  value: font.id,
  description: `${font.font_weight} / ${font.font_style} / ${font.font_display}`,
  keywords: [font.font_family, font.asset_name, font.font_weight, font.font_style, font.font_display],
})))

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
    const [iconResponse, imageResponse, fontResponse] = await Promise.all([
      listWorkspaceAssets(props.workspaceId, { assetType: 'icon', page: 1, page_size: 100 }),
      listWorkspaceAssets(props.workspaceId, { assetType: 'image', page: 1, page_size: 100 }),
      listWorkspaceFonts(props.workspaceId, { page: 1, page_size: 100 }),
    ])
    projectIconAssets.value = iconResponse.items
    logoAssets.value = [...iconResponse.items, ...imageResponse.items]
    fonts.value = fontResponse.items
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
  form.project_icon_name = theme?.project_icon_name || 'slider'
  form.heading_font_id = theme?.heading_font_id || null
  form.body_font_id = theme?.body_font_id || null
  form.code_font_id = theme?.code_font_id || null
  form.palette = JSON.parse(JSON.stringify(theme?.palette || DEFAULT_THEME_PALETTE)) as ThemePalette
}

/**
 * 将 select 的字符串值归一化为可选数字，避免 DOM 字符串污染表单状态。
 * @param field 需要更新的字段
 * @param value 通用下拉组件回传的最新值
 */
function updateNullableNumberField(
  field: 'logo_asset_id' | 'invert_logo_asset_id' | 'project_icon_asset_id' | 'heading_font_id' | 'body_font_id' | 'code_font_id',
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
    heading_font_id: form.heading_font_id,
    body_font_id: form.body_font_id,
    code_font_id: form.code_font_id,
    palette: JSON.parse(JSON.stringify(form.palette)) as ThemePalette,
  })
}
</script>
