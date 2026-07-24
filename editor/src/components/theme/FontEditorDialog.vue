<!-- 文件功能：提供工作空间字体注册的创建与编辑弹窗，封装字体资源、声明参数和状态表单。 -->
<template>
  <UiDialog
    :open="modelValue"
    :title="editingFont ? '编辑字体注册' : '注册字体'"
    description="字体注册用于主题的标题、正文和代码字体选择。"
    size="compact"
    body-preset="auto"
    @update:open="closeDialog"
  >
    <div class="space-y-5 rounded-2xl bg-slate-50/70 p-0.5">
      <section class="rounded-2xl border border-slate-200 bg-white p-4">
        <div class="mb-4">
          <h4 class="text-sm font-black text-slate-900">资源与名称</h4>
          <p class="mt-1 text-xs text-slate-400">注册后会以 font-family 暴露给主题配置。</p>
        </div>
        <div class="space-y-4">
          <div v-if="!editingFont">
            <label class="mb-1 block text-xs font-bold text-slate-500">字体资源</label>
            <UiSelect v-model="form.asset_id" :options="fontAssetOptions" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-slate-500">font-family</label>
            <UiInput
              v-model="form.font_family"
              class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500"
            />
          </div>
        </div>
      </section>

      <section class="rounded-2xl border border-slate-200 bg-white p-4">
        <div class="mb-4">
          <h4 class="text-sm font-black text-slate-900">字体声明</h4>
        </div>
        <div class="grid gap-3 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-bold text-slate-500">字体格式</label>
            <UiSelect v-model="form.font_format" :options="fontFormatOptions" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-slate-500">font-weight</label>
            <UiInput v-model="form.font_weight" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-slate-500">font-style</label>
            <UiSelect v-model="form.font_style" :options="fontStyleOptions" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-slate-500">font-display</label>
            <UiSelect v-model="form.font_display" :options="fontDisplayOptions" />
          </div>
        </div>
      </section>

      <section class="rounded-2xl border border-slate-200 bg-white p-4">
        <label class="mb-2 block text-xs font-bold text-slate-500">状态</label>
        <div class="grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1">
          <UiButton
            type="button"
            variant="ghost"
            size="sm"
            class="rounded-lg py-2 text-xs font-bold transition-all"
            :class="form.status === 'active' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500'"
            @click="form.status = 'active'"
          >
            启用
          </UiButton>
          <UiButton
            type="button"
            variant="ghost"
            size="sm"
            class="rounded-lg py-2 text-xs font-bold transition-all"
            :class="form.status === 'archived' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500'"
            @click="form.status = 'archived'"
          >
            归档
          </UiButton>
        </div>
      </section>
    </div>

    <template #footer>
      <UiButton variant="ghost" @click="closeDialog">取消</UiButton>
      <UiButton :loading="saving" @click="emitSave">
        {{ saving ? '保存中...' : '保存字体' }}
      </UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

import { UiButton, UiDialog, UiInput, UiSelect } from '@/components/ui'
import type { AssetResponse, RecordStatus, WorkspaceFontConfigItem } from '@/types/api'

const props = withDefaults(defineProps<{
  modelValue: boolean
  editingFont: WorkspaceFontConfigItem | null
  fontAssets: AssetResponse[]
  initialAsset?: AssetResponse | null
  saving?: boolean
}>(), {
  initialAsset: null,
  saving: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [payload: {
    asset_id: number
    font_family: string
    font_format: string
    font_weight: string
    font_style: string
    font_display: string
    status: RecordStatus
  }]
}>()

const form = reactive({
  asset_id: 0,
  font_family: '',
  font_format: 'woff2',
  font_weight: '400',
  font_style: 'normal',
  font_display: 'swap',
  status: 'active' as RecordStatus,
})

const fontAssetOptions = computed(() => [
  { value: 0, label: '请选择字体资源' },
  ...props.fontAssets.map(asset => ({ value: asset.id, label: `${asset.name} / ${asset.original_name}` })),
])
const fontFormatOptions = ['woff2', 'woff', 'ttf', 'otf'].map(value => ({ value, label: value }))
const fontStyleOptions = ['normal', 'italic'].map(value => ({ value, label: value }))
const fontDisplayOptions = ['swap', 'auto', 'block', 'fallback', 'optional'].map(value => ({ value, label: value }))

watch(
  () => [props.modelValue, props.editingFont, props.initialAsset, props.fontAssets] as const,
  ([visible]) => {
    if (!visible) return
    syncForm()
  },
  { immediate: true },
)

/**
 * 根据编辑项或初始字体资源同步弹窗表单。
 */
function syncForm(): void {
  if (props.editingFont) {
    Object.assign(form, {
      asset_id: props.editingFont.asset_id,
      font_family: props.editingFont.font_family,
      font_format: props.editingFont.font_format,
      font_weight: props.editingFont.font_weight,
      font_style: props.editingFont.font_style,
      font_display: props.editingFont.font_display,
      status: props.editingFont.status,
    })
    return
  }

  const asset = props.initialAsset ?? props.fontAssets[0] ?? null
  Object.assign(form, {
    asset_id: asset?.id ?? 0,
    font_family: asset ? inferFontFamily(asset.original_name) : '',
    font_format: asset ? inferFontFormat(asset.original_name) : 'woff2',
    font_weight: '400',
    font_style: 'normal',
    font_display: 'swap',
    status: 'active' as RecordStatus,
  })
}

/**
 * 关闭字体编辑弹窗。
 */
function closeDialog(): void {
  emit('update:modelValue', false)
}

/**
 * 向父级提交当前字体表单，具体持久化由页面统一处理。
 */
function emitSave(): void {
  emit('save', { ...form })
}

/**
 * 根据文件名推断字体格式。
 * @param name 字体资源原文件名
 */
function inferFontFormat(name: string): string {
  const lowerName = name.toLowerCase()
  if (lowerName.endsWith('.woff2')) return 'woff2'
  if (lowerName.endsWith('.woff')) return 'woff'
  if (lowerName.endsWith('.ttf')) return 'ttf'
  if (lowerName.endsWith('.otf')) return 'otf'
  return 'woff2'
}

/**
 * 根据字体文件名推断默认 font-family。
 * @param name 字体资源原文件名
 */
function inferFontFamily(name: string): string {
  return name.replace(/\.(woff2|woff|ttf|otf)$/i, '')
}
</script>
