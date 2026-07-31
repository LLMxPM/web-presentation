<!-- 文件功能：渲染可视化编辑属性面板中的单个内容或组件参数字段，并把用户输入转换为字段级事件。 -->
<template>
  <article
    class="rounded-lg border p-3 transition"
    :class="props.selected ? 'border-accent-ring bg-surface-selected/50' : 'border-border bg-surface hover:border-border-strong'"
    @click="emit('select')"
    @focusin="emit('select')"
  >
    <div v-if="props.kind !== 'rich_text'" class="mb-2">
      <div class="flex items-center justify-between gap-3">
        <label class="min-w-0 text-xs font-semibold text-text-emphasis" :for="props.controlId">
          {{ props.label }}
          <span v-if="props.required" class="text-danger">*</span>
        </label>
        <UiButton
          v-if="canRestore"
          type="button"
          variant="ghost"
          size="xs"
          class="shrink-0"
          :aria-label="`恢复${props.label}原值`"
          @click.stop="restoreBaseline"
        >
          恢复原值
        </UiButton>
      </div>
      <p v-if="props.description" class="mt-1 text-[11px] leading-4 text-text-muted">
        {{ props.description }}
      </p>
    </div>
    <p
      v-if="props.templateLiteralWarning"
      class="mb-3 rounded-lg bg-warning-muted px-3 py-2 text-xs text-warning-strong"
    >
      此项来自模板字面量，保存后会修改所有循环实例。
    </p>

    <div v-if="props.kind === 'rich_text'">
      <div class="mb-1.5 flex items-center justify-between gap-2">
        <label class="block text-xs font-semibold text-text-emphasis">段落内容</label>
        <UiButton
          v-if="canRestore"
          type="button"
          variant="ghost"
          size="xs"
          :aria-label="`恢复${props.label}原值`"
          @click.stop="restoreBaseline"
        >
          恢复原值
        </UiButton>
      </div>
      <PageVisualEditRichTextEditor
        :model-value="String(props.effectiveValue ?? '')"
        :baseline-html="props.baselineRichText"
        :disabled="!props.editable"
        @update:model-value="emit('set-rich-text', $event)"
      />
      <p v-if="!props.editable" class="mt-2 rounded-lg bg-canvas px-3 py-2 text-xs text-text-secondary">
        {{ props.readonlyMessage }}
      </p>
    </div>
    <template v-else-if="props.editable">
      <UiSelect
        v-if="props.controlType === 'select'"
        :id="props.controlId"
        :aria-label="props.label"
        :model-value="props.optionIndex"
        :options="selectOptions"
        placeholder="请选择有限选项"
        @update:model-value="handleSelectValueChange"
      />
      <label v-else-if="props.controlType === 'boolean'" class="flex items-center gap-2 text-sm text-text-emphasis">
        <UiCheckbox
          :model-value="Boolean(props.effectiveValue)"
          @update:model-value="emit('set-value', $event === true)"
        />
        {{ Boolean(props.effectiveValue) ? '开启' : '关闭' }}
      </label>
      <UiInput
        v-else-if="props.controlType === 'number'"
        :input-id="props.controlId"
        type="number"
        :model-value="String(props.effectiveValue ?? '')"
        :placeholder="props.placeholder ?? undefined"
        @update:model-value="handleNumberInput"
      />
      <UiInput
        v-else-if="props.controlType === 'textarea'"
        type="textarea"
        :input-id="props.controlId"
        :rows="props.rows"
        :model-value="String(props.effectiveValue ?? '')"
        :placeholder="props.placeholder ?? undefined"
        @update:model-value="emit('set-value', $event)"
      />
      <UiInput
        v-else
        :input-id="props.controlId"
        :model-value="String(props.effectiveValue ?? '')"
        :placeholder="props.placeholder ?? undefined"
        @update:model-value="emit('set-value', $event)"
      />
    </template>
    <p v-else class="rounded-lg bg-canvas px-3 py-2 text-xs text-text-secondary">
      {{ props.readonlyMessage }}
    </p>
    <p v-if="props.pending" class="mt-3 text-[11px] font-semibold text-accent">
      {{ props.label }}：{{ displayValue(baselineDisplayValue) }}
      <span aria-hidden="true">→</span>
      {{ displayValue(props.effectiveValue) }}
    </p>
    <details
      v-if="props.propName"
      class="mt-3 rounded-ui-md border border-border bg-surface-muted px-2.5 py-2 text-[11px] text-text-muted"
    >
      <summary class="cursor-pointer font-medium outline-none focus-visible:ring-2 focus-visible:ring-border-focus">
        技术详情
      </summary>
      <p class="mt-1.5">
        源码属性：<code class="font-mono">{{ props.propName }}</code>
      </p>
    </details>
  </article>
</template>

<script setup lang="ts">
import PageVisualEditRichTextEditor from '@/components/page-detail/visual-edit/PageVisualEditRichTextEditor.vue'
import { UiButton, UiCheckbox, UiInput, UiSelect } from '@/components/ui'
import type { SelectModelValue, SelectOption } from '@/components/ui/select'
import { computed } from 'vue'
import type {
  PageVisualEditBindingKind,
  PageVisualEditComponentSelectOption,
  PageVisualEditValue,
} from '@/types/page-visual-edit'

const props = withDefaults(defineProps<{
  controlId: string
  controlType: string
  baselineValue?: PageVisualEditValue
  baselineRichText?: string | null
  description?: string | null
  editable: boolean
  effectiveValue: PageVisualEditValue | undefined
  kind: PageVisualEditBindingKind
  label: string
  optionIndex: number
  options: PageVisualEditComponentSelectOption[]
  pending: boolean
  placeholder?: string | null
  propName?: string | null
  readonlyMessage: string
  required: boolean
  rows?: number
  selected: boolean
  templateLiteralWarning: boolean
}>(), {
  description: null,
  baselineRichText: null,
  placeholder: null,
  propName: null,
  rows: 4,
})

const emit = defineEmits<{
  select: []
  'set-rich-text': [html: string]
  'set-value': [value: PageVisualEditValue]
}>()

const selectOptions = computed<SelectOption[]>(() => props.options.map((option, index) => ({
  label: option.label,
  value: index,
})))
const canRestore = computed(() => (
  props.pending
  && (props.kind === 'rich_text'
    ? props.baselineRichText !== null
    : props.baselineValue !== undefined)
))
const baselineDisplayValue = computed<PageVisualEditValue | undefined>(() => (
  props.kind === 'rich_text' ? props.baselineRichText ?? '' : props.baselineValue
))

/** 写入有效数字值，空值或非法数字不生成字段事件。 */
function handleNumberInput(rawValue: string): void {
  if (!rawValue.trim()) return
  const value = Number(rawValue)
  if (Number.isFinite(value)) emit('set-value', value)
}

/** 按有限选项原始值发出字段事件，避免 DOM 字符串化破坏数字或布尔类型。 */
function handleSelectValueChange(value: SelectModelValue): void {
  const optionIndex = Number(value)
  const option = props.options[optionIndex]
  if (option) emit('set-value', option.value)
}

/** 把当前字段恢复到 artifact 原值，让草稿层移除对应操作。 */
function restoreBaseline(): void {
  if (!canRestore.value) return
  if (props.kind === 'rich_text') {
    emit('set-rich-text', props.baselineRichText ?? '')
    return
  }
  if (props.baselineValue !== undefined) emit('set-value', props.baselineValue)
}

/** 将字段值转换为简短业务摘要，避免待保存区暴露源码表达式。 */
function displayValue(value: PageVisualEditValue | undefined): string {
  const matchedOption = props.options.find(option => Object.is(option.value, value))
  if (matchedOption) return matchedOption.label
  if (typeof value === 'boolean') return value ? '开启' : '关闭'
  if (value === null || value === undefined || value === '') return '空'
  const normalized = String(value)
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  const characters = Array.from(normalized)
  return characters.length > 24 ? `${characters.slice(0, 24).join('')}…` : normalized
}
</script>
