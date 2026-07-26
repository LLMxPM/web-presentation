<!-- 文件功能：为 Runtime Kit AssetImage.v1 提供低门槛图片内容、位置与外层图片框样式检查器。 -->
<template>
  <div class="space-y-3">
    <InspectorSection title="图片内容" :collapsible="false">
      <article
        v-for="field in primaryFields"
        :key="field.name"
        class="rounded-lg border p-3 transition"
        :class="fieldCardClass(field)"
        @click="selectField(field)"
        @focusin="selectField(field)"
      >
        <div class="mb-2 flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p :id="fieldLabelId(field)" class="text-xs font-semibold text-text-emphasis">
              {{ fieldLabel(field) }}
            </p>
            <p class="mt-1 text-[11px] leading-4 text-text-muted">
              {{ fieldDescription(field) }}
            </p>
          </div>
          <UiButton
            v-if="canRestoreField(field)"
            type="button"
            variant="ghost"
            size="xs"
            class="shrink-0"
            @click.stop="restoreField(field)"
          >
            恢复原值
          </UiButton>
        </div>

        <p
          v-if="field.templateLiteralWarning"
          class="mb-3 rounded-lg bg-warning-muted px-3 py-2 text-xs text-warning-strong"
        >
          此项来自模板字面量，保存后会修改所有循环实例。
        </p>

        <div
          v-if="field.name === 'name' && canEditResource(field)"
          role="group"
          :aria-labelledby="fieldLabelId(field)"
        >
          <AssetPicker
            :model-value="stringFieldValue(field)"
            :workspace-id="props.workspaceId"
            asset-type="image"
            value-mode="name"
            title="选择图片资源"
            :placeholder="stringFieldValue(field) || '请选择图片资源'"
            hint="只会写入工作空间图片的资源名。"
            :clearable="false"
            size="compact"
            @update:model-value="value => handleResourceChange(field, value)"
          />
        </div>
        <UiInput
          v-else-if="field.name === 'alt' && field.editable"
          :input-id="fieldControlId(field)"
          :aria-labelledby="fieldLabelId(field)"
          :model-value="stringFieldValue(field)"
          placeholder="简要描述图片内容"
          @update:model-value="value => setFieldValue(field, value)"
        />
        <UiSelect
          v-else-if="field.name === 'fit' && field.editable"
          :id="fieldControlId(field)"
          :aria-labelledby="fieldLabelId(field)"
          :model-value="stringFieldValue(field)"
          :options="fitOptions"
          placeholder="选择框内填充方式"
          @update:model-value="value => setFieldValue(field, String(value ?? ''))"
        />
        <p v-else class="rounded-lg bg-canvas px-3 py-2 text-xs leading-5 text-text-secondary">
          {{ fieldReadonlyMessage(field) }}
        </p>

        <p v-if="field.pending" class="mt-3 text-[11px] font-semibold text-accent">
          {{ pendingFieldSummary(field) }}
        </p>
      </article>
    </InspectorSection>

    <InspectorSection title="图片位置" :collapsible="false">
      <article
        class="rounded-lg border p-3 transition"
        :class="fieldCardClass(positionField)"
        @click="selectField(positionField)"
        @focusin="selectField(positionField)"
      >
        <div class="mb-3 flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p :id="fieldLabelId(positionField)" class="text-xs font-semibold text-text-emphasis">框内图片位置</p>
            <p class="mt-1 text-[11px] leading-4 text-text-muted">
              选择图片在外层图片框中的对齐位置。
            </p>
          </div>
          <UiButton
            v-if="canRestoreField(positionField)"
            type="button"
            variant="ghost"
            size="xs"
            class="shrink-0"
            @click.stop="restoreField(positionField)"
          >
            恢复原值
          </UiButton>
        </div>

        <p
          v-if="positionField.templateLiteralWarning"
          class="mb-3 rounded-lg bg-warning-muted px-3 py-2 text-xs text-warning-strong"
        >
          此项来自模板字面量，保存后会修改所有循环实例。
        </p>

        <div
          v-if="positionField.editable"
          :aria-labelledby="fieldLabelId(positionField)"
          class="grid grid-cols-3 gap-1.5 rounded-lg border border-border bg-canvas p-2"
          role="radiogroup"
          @keydown="handlePositionKeydown"
        >
          <UiButton
            v-for="(option, index) in positionOptions"
            :key="option.value"
            :ref="element => setPositionButtonRef(element, index)"
            type="button"
            variant="secondary"
            size="sm"
            role="radio"
            :aria-label="option.label"
            :aria-checked="stringFieldValue(positionField) === option.value"
            :tabindex="positionButtonTabindex(option.value, index)"
            class="h-10 px-0 text-text-disabled hover:border-accent-border hover:text-accent"
            :class="stringFieldValue(positionField) === option.value
              ? 'border-accent-border bg-surface-selected text-accent-hover shadow-sm'
              : 'border-border'"
            @click="setFieldValue(positionField, option.value)"
          >
            <span class="h-2.5 w-2.5 rounded-full bg-current" aria-hidden="true" />
          </UiButton>
        </div>
        <p v-else class="rounded-lg bg-canvas px-3 py-2 text-xs leading-5 text-text-secondary">
          {{ fieldReadonlyMessage(positionField) }}
        </p>

        <details
          v-if="customPositionValue"
          class="mt-3 rounded-lg border border-border bg-canvas px-3 py-2 text-xs text-text-secondary"
        >
          <summary class="cursor-pointer font-semibold">自定义位置（高级）</summary>
          <p class="mt-2 leading-5">
            当前保留源码中的自定义值：
            <code class="rounded bg-surface px-1.5 py-0.5 font-mono text-[11px]">{{ customPositionValue }}</code>
          </p>
          <p class="mt-1 text-text-muted">选择上方九宫格后才会替换此值。</p>
        </details>

        <p v-if="positionField.pending" class="mt-3 text-[11px] font-semibold text-accent">
          {{ pendingFieldSummary(positionField) }}
        </p>
      </article>
    </InspectorSection>

    <InspectorSection title="图片框样式">
      <p class="mb-3 text-xs leading-5 text-text-muted">
        这里只调整外层图片框的宽高、内边距、背景、边框和圆角；图片缩放与位置请使用上方控件。
      </p>
      <PageVisualEditTailwindStyleEditor
        v-if="props.style"
        :binding-id="props.style.bindingId"
        :editable="props.style.editable"
        :groups="props.style.groups"
        :pending="props.style.pending"
        :readonly-message="props.style.readonlyMessage"
        :template-literal-warning="props.style.templateLiteralWarning"
        :unknown-tokens="props.style.unknownTokens"
        :common-group-keys="assetImageStyleGroupKeys"
        :allowed-group-keys="assetImageStyleGroupKeys"
        @change="payload => emit('set-tailwind', { bindingId: props.style!.bindingId, ...payload })"
        @select="emit('select', props.style.bindingId)"
      />
      <p v-else class="rounded-lg bg-canvas px-3 py-2 text-xs leading-5 text-text-secondary">
        页面源码没有为该图片声明静态 class。请使用 AI 或高级源码补充图片框样式。
      </p>
    </InspectorSection>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'

import InspectorSection from '@/components/patterns/InspectorSection.vue'
import PageVisualEditTailwindStyleEditor from '@/components/page-detail/visual-edit/PageVisualEditTailwindStyleEditor.vue'
import { ASSET_IMAGE_STYLE_GROUP_KEYS } from '@/components/page-detail/visual-edit/page-visual-edit-component-inspectors'
import AssetPicker from '@/components/ui/AssetPicker.vue'
import { UiButton, UiInput, UiSelect } from '@/components/ui'
import type { PageVisualEditValue } from '@/types/page-visual-edit'

type AssetImageFieldName = 'name' | 'alt' | 'fit' | 'position'

interface AssetImageFieldView {
  name: AssetImageFieldName
  bindingId: string | null
  value: PageVisualEditValue | undefined
  baselineValue: PageVisualEditValue | undefined
  editable: boolean
  pending: boolean
  readonlyMessage: string
  selected: boolean
  templateLiteralWarning: boolean
}

interface AssetImageTailwindGroupView {
  key: string
  label: string
  selectedClass: string
  baselineClass?: string
  options: Array<{ class_name: string; label: string }>
}

interface AssetImageStyleView {
  bindingId: string
  editable: boolean
  groups: AssetImageTailwindGroupView[]
  pending: boolean
  readonlyMessage: string
  templateLiteralWarning: boolean
  unknownTokens: string[]
}

const props = defineProps<{
  workspaceId: number | null
  fields: AssetImageFieldView[]
  style: AssetImageStyleView | null
}>()

const emit = defineEmits<{
  select: [bindingId: string]
  'set-value': [payload: { bindingId: string; value: PageVisualEditValue }]
  'set-tailwind': [payload: { bindingId: string; group: string; className: string }]
}>()

const fitOptions = [
  { value: 'contain', label: '完整显示' },
  { value: 'cover', label: '填满并裁切' },
  { value: 'fill', label: '拉伸填满' },
  { value: 'none', label: '原始尺寸' },
]
const positionOptions = [
  { value: 'left top', label: '左上' },
  { value: 'top', label: '上方居中' },
  { value: 'right top', label: '右上' },
  { value: 'left', label: '左侧居中' },
  { value: 'center', label: '居中' },
  { value: 'right', label: '右侧居中' },
  { value: 'left bottom', label: '左下' },
  { value: 'bottom', label: '下方居中' },
  { value: 'right bottom', label: '右下' },
]
const assetImageStyleGroupKeys = [...ASSET_IMAGE_STYLE_GROUP_KEYS]
const positionButtonRefs = ref<Array<HTMLButtonElement | null>>([])

const primaryFields = computed(() => [
  resolveField('name'),
  resolveField('alt'),
  resolveField('fit'),
])
const positionField = computed(() => resolveField('position'))
const customPositionValue = computed(() => {
  const value = stringFieldValue(positionField.value)
  return value && !positionOptions.some(option => option.value === value) ? value : ''
})

/** 补齐缺失 prop 的只读视图，确保界面明确说明当前协议不能自动插入属性。 */
function resolveField(name: AssetImageFieldName): AssetImageFieldView {
  return props.fields.find(field => field.name === name) ?? {
    name,
    bindingId: null,
    value: undefined,
    baselineValue: undefined,
    editable: false,
    pending: false,
    readonlyMessage: `页面源码没有声明静态 ${name} 属性。请使用 AI 或高级源码补充。`,
    selected: false,
    templateLiteralWarning: false,
  }
}

/** 返回面向内容创作者的字段名称。 */
function fieldLabel(field: AssetImageFieldView): string {
  const labels: Record<AssetImageFieldName, string> = {
    name: '图片资源',
    alt: '替代文本',
    fit: '框内填充',
    position: '框内图片位置',
  }
  return labels[field.name]
}

/** 返回字段用途说明，避免暴露源码 prop 术语。 */
function fieldDescription(field: AssetImageFieldView): string {
  const descriptions: Record<AssetImageFieldName, string> = {
    name: '从当前工作空间选择一张图片。',
    alt: '图片无法显示或由读屏软件读取时使用的简短描述。',
    fit: '决定图片如何填入外层图片框。',
    position: '决定图片在外层图片框中的对齐位置。',
  }
  return descriptions[field.name]
}

/** 把待保存字段转换为“原值 → 当前值”的语义摘要。 */
function pendingFieldSummary(field: AssetImageFieldView): string {
  return `${fieldLabel(field)}：${displayFieldValue(field, field.baselineValue)} → ${displayFieldValue(field, field.value)}`
}

/** 使用业务标签展示字段值，避免摘要泄露 fit 等协议枚举。 */
function displayFieldValue(field: AssetImageFieldView, value: PageVisualEditValue | undefined): string {
  if (typeof value !== 'string' || !value.trim()) return '未设置'
  if (field.name === 'fit') {
    return fitOptions.find(option => option.value === value)?.label ?? value
  }
  if (field.name === 'position') {
    return positionOptions.find(option => option.value === value)?.label ?? value
  }
  const normalizedValue = value.trim()
  return normalizedValue.length > 24 ? `${normalizedValue.slice(0, 24)}…` : normalizedValue
}

/** 为专用字段生成稳定且可读的控件关联 id。 */
function fieldControlId(field: AssetImageFieldView): string {
  return `asset-image-${field.name}-${safeDomId(field.bindingId ?? 'missing')}`
}

/** 为字段标题生成 aria-labelledby 目标。 */
function fieldLabelId(field: AssetImageFieldView): string {
  return `${fieldControlId(field)}-label`
}

/** DOM id 只保留安全字符。 */
function safeDomId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-')
}

/** 把字段值收窄为专用图片控件接受的字符串。 */
function stringFieldValue(field: AssetImageFieldView): string {
  return typeof field.value === 'string' ? field.value : ''
}

/** 图片资源选择还依赖有效工作空间；缺失时保持只读。 */
function canEditResource(field: AssetImageFieldView): boolean {
  return field.editable && props.workspaceId !== null
}

/** 生成缺失、动态或缺工作空间时的普通语言说明。 */
function fieldReadonlyMessage(field: AssetImageFieldView): string {
  if (field.name === 'name' && field.editable && props.workspaceId === null) {
    return '当前页面没有可用的工作空间上下文，暂时不能打开图片资源库。'
  }
  return field.readonlyMessage
}

/** 用当前 binding 选择态突出字段，同时保持缺失字段为中性只读卡片。 */
function fieldCardClass(field: AssetImageFieldView): string {
  return field.selected
    ? 'border-accent-ring bg-surface-selected/50'
    : 'border-border bg-surface hover:border-border-strong'
}

/** 点击或聚焦字段时同步选择对应 binding；缺失 prop 不伪造 binding。 */
function selectField(field: AssetImageFieldView): void {
  if (field.bindingId) emit('select', field.bindingId)
}

/** 写入已有、可编辑的静态 prop，缺失或动态 binding 不产生操作。 */
function setFieldValue(field: AssetImageFieldView, value: PageVisualEditValue): void {
  if (!field.bindingId || !field.editable) return
  emit('set-value', { bindingId: field.bindingId, value })
}

/** 资源选择器只接受 name 模式返回的字符串资源名。 */
function handleResourceChange(field: AssetImageFieldView, value: string | number | null): void {
  if (typeof value !== 'string' || !canEditResource(field)) return
  setFieldValue(field, value)
}

/** 只有存在未保存草稿和明确基准值时才提供字段恢复。 */
function canRestoreField(field: AssetImageFieldView): boolean {
  return field.pending && field.bindingId !== null && field.baselineValue !== undefined
}

/** 用规范源码基准值覆盖字段草稿；草稿层会自动移除无变化操作。 */
function restoreField(field: AssetImageFieldView): void {
  if (!canRestoreField(field)) return
  setFieldValue(field, field.baselineValue!)
}

/** 根据当前图片位置维护九宫格单一 Tab 停靠点。 */
function positionButtonTabindex(value: string, index: number): 0 | -1 {
  const currentValue = stringFieldValue(positionField.value)
  const hasKnownValue = positionOptions.some(option => option.value === currentValue)
  return (hasKnownValue ? value === currentValue : index === 0) ? 0 : -1
}

/** 收集九宫格按钮 DOM，供方向键完成二维焦点移动。 */
function setPositionButtonRef(element: Element | ComponentPublicInstance | null, index: number): void {
  if (element instanceof HTMLButtonElement) {
    positionButtonRefs.value[index] = element
    return
  }
  if (!element || element instanceof Element) {
    positionButtonRefs.value[index] = null
    return
  }
  const rootElement = element?.$el
  positionButtonRefs.value[index] = rootElement instanceof HTMLButtonElement ? rootElement : null
}

/** 按九宫格二维结构处理方向键，并立即写入获得焦点的位置。 */
function handlePositionKeydown(event: KeyboardEvent): void {
  const keyDeltas: Record<string, number> = {
    ArrowLeft: -1,
    ArrowRight: 1,
    ArrowUp: -3,
    ArrowDown: 3,
  }
  const delta = keyDeltas[event.key]
  if (delta === undefined) return
  const currentIndex = positionButtonRefs.value.findIndex(element => element === document.activeElement)
  if (currentIndex < 0) return
  const currentRow = Math.floor(currentIndex / 3)
  const currentColumn = currentIndex % 3
  const nextIndex = event.key === 'ArrowLeft' || event.key === 'ArrowRight'
    ? currentRow * 3 + Math.min(2, Math.max(0, currentColumn + delta))
    : Math.min(8, Math.max(0, currentIndex + delta))
  if (nextIndex === currentIndex) return
  event.preventDefault()
  positionButtonRefs.value[nextIndex]?.focus()
  setFieldValue(positionField.value, positionOptions[nextIndex]!.value)
}
</script>
