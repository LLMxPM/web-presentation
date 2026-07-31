<!-- 文件功能：提供单个字体文件（face）的注册与编辑弹窗，封装字体族归属、face 声明和实时效果预览。 -->
<template>
  <UiDialog
    :open="modelValue"
    :title="editingFont ? '编辑字体' : '注册字体'"
    :description="asset ? `字体文件：${asset.original_name}` : '字体注册用于主题的标题、正文和代码字体选择。'"
    size="compact"
    body-preset="auto"
    @update:open="closeDialog"
  >
    <div class="space-y-5 rounded-2xl bg-canvas/70 p-0.5">
      <section class="rounded-2xl border border-border bg-surface p-4">
        <div class="mb-4">
          <h4 class="text-sm font-black text-text-strong">字体族名称（font-family）</h4>
          <p class="mt-1 text-xs text-text-disabled">同一字体族下的多个文件按字重、样式自动匹配；修改族名会把该文件移动到目标字体族。</p>
        </div>
        <div>
          <UiInput v-model="form.family_name" :invalid="!form.family_name.trim()" placeholder="例如 Source Han Sans" />
          <p v-if="!form.family_name.trim()" class="mt-1 text-xs font-semibold text-danger">请填写字体族名称。</p>
        </div>
        <div
          class="mt-3 rounded-lg bg-canvas p-3 text-text"
          :style="previewStyle"
        >
          <div class="text-2xl">永字八法 AaBbGg 0123</div>
          <div class="mt-1 text-sm text-text-muted">字体效果预览</div>
        </div>
      </section>

      <section class="rounded-2xl border border-border bg-surface p-4">
        <div class="mb-4 flex items-center gap-1.5">
          <h4 class="text-sm font-black text-text-strong">字体声明</h4>
          <UiPopover v-model:open="declarationTipOpen">
            <template #trigger>
              <button
                type="button"
                aria-label="字体声明说明"
                class="flex size-5 shrink-0 items-center justify-center rounded-full text-text-muted transition-colors hover:bg-surface-muted hover:text-text"
              >
                <Info :size="14" />
              </button>
            </template>
            <div class="max-w-xs space-y-1.5 text-xs text-text-muted">
              <p>字体声明会生成页面中的 @font-face 规则，分两类：</p>
              <p><span class="font-bold text-text">描述文件本身</span>：字体格式、font-weight、font-style 声明的是这个文件“是什么”，需要与文件实际设计相符，不会把字体变成另一种样子。例如把常规体文件声明成 700，页面的粗体文字会匹配到这个文件，实际渲染出来却不够粗。</p>
              <p><span class="font-bold text-text">影响加载效果</span>：font-display 控制字体下载完成前的展示策略，不同选项会产生不同效果：默认 swap 先用备用字体占位、加载完再替换；block 会短暂隐藏文字等待字体。</p>
              <p>同一字体族的常规体、粗体、斜体通常是独立文件，分别上传并声明对应字重和样式后，浏览器会按主题需要的字重自动匹配同族文件。</p>
              <p>可变字体（Variable Font）是单个文件覆盖一段连续字重，开启“可变字体字重范围”后声明其最小、最大字重即可。</p>
            </div>
          </UiPopover>
        </div>
        <div class="grid gap-3 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-bold text-text-muted">字体格式</label>
            <UiSelect v-model="form.font_format" :options="fontFormatOptions" />
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-text-muted">font-style</label>
            <UiSelect v-model="form.font_style" :options="fontStyleOptions" />
          </div>
          <div class="sm:col-span-2">
            <div class="mb-1 flex items-center justify-between gap-2">
              <label class="text-xs font-bold text-text-muted">font-weight</label>
              <label class="flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-text-muted">
                <UiCheckbox :model-value="isVariableWeight" @update:model-value="toggleVariableWeight" />
                可变字体（字重范围）
              </label>
            </div>
            <UiSelect v-if="!isVariableWeight" v-model="form.font_weight" :options="fontWeightOptions" />
            <div v-else class="flex items-center gap-2">
              <UiInput v-model="weightMin" type="number" min="100" max="900" step="100" :invalid="!isWeightRangeValid" placeholder="最小" />
              <span class="text-text-muted">–</span>
              <UiInput v-model="weightMax" type="number" min="100" max="900" step="100" :invalid="!isWeightRangeValid" placeholder="最大" />
            </div>
            <p v-if="isVariableWeight && !isWeightRangeValid" class="mt-1 text-xs font-semibold text-danger">
              请填写有效的字重范围，最小值不大于最大值。
            </p>
          </div>
          <div>
            <label class="mb-1 block text-xs font-bold text-text-muted">font-display</label>
            <UiSelect v-model="form.font_display" :options="fontDisplayOptions" />
          </div>
        </div>
      </section>
    </div>

    <template #footer>
      <UiButton variant="ghost" @click="closeDialog">取消</UiButton>
      <UiButton :loading="saving" :disabled="!canSave" @click="emitSave">
        {{ saving ? '保存中...' : '保存字体' }}
      </UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch, type CSSProperties } from 'vue'
import { Info } from '@lucide/vue'

import { UiButton, UiCheckbox, UiDialog, UiInput, UiPopover, UiSelect } from '@/components/ui'
import type { AssetResponse, WorkspaceFontConfigSummary } from '@/types/api'
import { buildDefaultFontRegistration, FONT_FORMATS } from '@/utils/font-registration'

const props = withDefaults(defineProps<{
  modelValue: boolean
  editingFont: WorkspaceFontConfigSummary | null
  asset?: AssetResponse | null
  presetFamilyName?: string | null
  saving?: boolean
}>(), {
  asset: null,
  presetFamilyName: null,
  saving: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [payload: {
    family_name: string
    font_format: string
    font_weight: string
    font_style: string
    font_display: string
  }]
}>()

const form = reactive({
  family_name: '',
  font_format: 'woff2',
  font_weight: '400',
  font_style: 'normal',
  font_display: 'swap',
})

/** 可变字体开关及字重范围输入，开启后 font-weight 以 "最小 最大" 形式提交。 */
const isVariableWeight = ref(false)
const weightMin = ref('100')
const weightMax = ref('900')

/** 字体声明说明浮层的开关状态。 */
const declarationTipOpen = ref(false)

const fontFormatOptions = FONT_FORMATS.map(value => ({ value, label: value }))
const standardFontWeights = ['100', '200', '300', '400', '500', '600', '700', '800', '900']
const fontWeightOptions = computed(() => {
  const weights = standardFontWeights.includes(form.font_weight) || !form.font_weight
    ? standardFontWeights
    : [form.font_weight, ...standardFontWeights]
  return weights.map(value => ({ value, label: value === '400' ? '400（常规）' : value === '700' ? '700（加粗）' : value }))
})
const fontStyleOptions = ['normal', 'italic'].map(value => ({ value, label: value }))
const fontDisplayOptions = ['swap', 'auto', 'block', 'fallback', 'optional'].map(value => ({ value, label: value }))

/** 校验可变字体字重范围：两端均为正整数且最小值不大于最大值。 */
const isWeightRangeValid = computed(() => {
  const min = Number(weightMin.value)
  const max = Number(weightMax.value)
  if (!Number.isInteger(min) || !Number.isInteger(max)) return false
  if (min <= 0 || max <= 0) return false
  return min <= max
})

/** 提交按钮可用性：需填写族名，且可变字体时范围合法。 */
const canSave = computed(() => Boolean(form.family_name.trim()) && (!isVariableWeight.value || isWeightRangeValid.value))

/** 弹窗内预览使用的临时 font-family，避免与页面级预览样式冲突。 */
const previewFamily = computed(() => (props.asset ? `font-editor-preview-${props.asset.id}` : ''))

/** 预览字重：可变字体使用范围下限，否则使用单值字重。 */
const previewWeight = computed(() => (isVariableWeight.value ? weightMin.value : form.font_weight))

const previewStyle = computed<CSSProperties>(() => ({
  fontFamily: previewFamily.value ? `'${previewFamily.value}'` : undefined,
  fontWeight: previewWeight.value || undefined,
  fontStyle: form.font_style || undefined,
}))

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return
    syncForm()
    syncPreviewFontFace()
  },
  { immediate: true },
)

/**
 * 打开弹窗时根据编辑项或字体文件推断值初始化表单，避免打开后被外部刷新覆盖。
 * 注册新 face 且指定了预置字体族名时，族名优先使用预置值而非文件名推断。
 */
function syncForm(): void {
  if (props.editingFont) {
    Object.assign(form, {
      family_name: props.editingFont.font_family,
      font_format: props.editingFont.font_format,
      font_weight: props.editingFont.font_weight,
      font_style: props.editingFont.font_style,
      font_display: props.editingFont.font_display,
    })
    applyWeightToRangeState(props.editingFont.font_weight)
    return
  }
  const defaults = buildDefaultFontRegistration(props.asset?.original_name ?? '')
  Object.assign(form, defaults)
  if (props.presetFamilyName?.trim()) {
    form.family_name = props.presetFamilyName.trim()
  }
  applyWeightToRangeState(defaults.font_weight)
}

/**
 * 依据字重值初始化可变字体开关与范围输入。
 * @param weight 单值或 "最小 最大" 形式的字重声明
 */
function applyWeightToRangeState(weight: string): void {
  const parts = String(weight || '').trim().split(/\s+/)
  if (parts.length === 2) {
    isVariableWeight.value = true
    weightMin.value = parts[0]
    weightMax.value = parts[1]
    form.font_weight = '400'
    return
  }
  isVariableWeight.value = false
  weightMin.value = '100'
  weightMax.value = '900'
}

/**
 * 切换可变字体开关；开启时用当前单值预填范围下限，关闭时回落到单值字重。
 * @param value 复选框最新状态
 */
function toggleVariableWeight(value: boolean | 'indeterminate'): void {
  const enabled = value === true
  isVariableWeight.value = enabled
  if (enabled) {
    const current = Number(form.font_weight)
    if (Number.isInteger(current) && current > 0) {
      weightMin.value = String(current)
    }
  }
}

/**
 * 为当前字体文件注入弹窗预览专用的 @font-face 声明。
 */
function syncPreviewFontFace(): void {
  const asset = props.asset
  let styleTag = document.getElementById('font-editor-preview')
  if (!styleTag) {
    styleTag = document.createElement('style')
    styleTag.id = 'font-editor-preview'
    document.head.appendChild(styleTag)
  }
  styleTag.textContent = asset?.url
    ? `@font-face { font-family: '${previewFamily.value}'; src: url('${encodeURI(asset.url)}'); font-display: swap; }`
    : ''
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
  if (!canSave.value) return
  const fontWeight = isVariableWeight.value
    ? `${Number(weightMin.value)} ${Number(weightMax.value)}`
    : form.font_weight
  emit('save', {
    family_name: form.family_name.trim(),
    font_format: form.font_format,
    font_weight: fontWeight,
    font_style: form.font_style,
    font_display: form.font_display,
  })
}
</script>
