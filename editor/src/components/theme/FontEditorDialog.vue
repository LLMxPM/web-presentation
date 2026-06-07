<!-- 文件功能：提供工作空间字体注册的创建与编辑弹窗，封装字体资源、声明参数和状态表单。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    :title="editingFont ? '编辑字体注册' : '注册字体'"
    description="字体注册用于主题的标题、正文和代码字体选择。"
    size="compact"
    body-preset="auto"
    @update:model-value="closeDialog"
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
            <select
              v-model.number="form.asset_id"
              class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500"
            >
              <option :value="0">请选择字体资源</option>
              <option v-for="asset in fontAssets" :key="asset.id" :value="asset.id">
                {{ asset.name }} / {{ asset.original_name }}
              </option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-slate-500">font-family</label>
            <input
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
            <select v-model="form.font_format" class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500">
              <option value="woff2">woff2</option>
              <option value="woff">woff</option>
              <option value="ttf">ttf</option>
              <option value="otf">otf</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-slate-500">font-weight</label>
            <input v-model="form.font_weight" class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-slate-500">font-style</label>
            <select v-model="form.font_style" class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500">
              <option value="normal">normal</option>
              <option value="italic">italic</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-slate-500">font-display</label>
            <select v-model="form.font_display" class="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-indigo-500">
              <option value="swap">swap</option>
              <option value="auto">auto</option>
              <option value="block">block</option>
              <option value="fallback">fallback</option>
              <option value="optional">optional</option>
            </select>
          </div>
        </div>
      </section>

      <section class="rounded-2xl border border-slate-200 bg-white p-4">
        <label class="mb-2 block text-xs font-bold text-slate-500">状态</label>
        <div class="grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1">
          <button
            type="button"
            class="rounded-lg py-2 text-xs font-bold transition-all"
            :class="form.status === 'active' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500'"
            @click="form.status = 'active'"
          >
            启用
          </button>
          <button
            type="button"
            class="rounded-lg py-2 text-xs font-bold transition-all"
            :class="form.status === 'archived' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500'"
            @click="form.status = 'archived'"
          >
            归档
          </button>
        </div>
      </section>
    </div>

    <template #footer>
      <button class="rounded-xl bg-slate-100 px-4 py-2 text-sm font-bold text-slate-600 transition-all hover:bg-slate-200" @click="closeDialog">取消</button>
      <button class="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white shadow-sm transition-all hover:bg-indigo-700 disabled:opacity-50" :disabled="saving" @click="emitSave">
        {{ saving ? '保存中...' : '保存字体' }}
      </button>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

import BaseDialog from '@/components/ui/BaseDialog.vue'
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
