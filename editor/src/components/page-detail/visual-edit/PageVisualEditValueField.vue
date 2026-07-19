<!-- 文件功能：渲染可视化编辑属性面板中的单个内容或组件参数字段，并把用户输入转换为字段级事件。 -->
<template>
  <article
    class="rounded-lg border p-3 transition"
    :class="props.selected ? 'border-indigo-200 bg-indigo-50/50' : 'border-slate-200 bg-white hover:border-slate-300'"
    @click="emit('select')"
    @focusin="emit('select')"
  >
    <div v-if="props.kind !== 'rich_text'" class="mb-2">
      <div class="flex items-center justify-between gap-3">
        <label class="min-w-0 text-xs font-semibold text-slate-700" :for="props.controlId">
          {{ props.label }}
          <span v-if="props.required" class="text-rose-500">*</span>
        </label>
        <code v-if="props.propName" class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
          {{ props.propName }}
        </code>
      </div>
      <p v-if="props.description" class="mt-1 text-[11px] leading-4 text-slate-500">
        {{ props.description }}
      </p>
    </div>
    <p
      v-if="props.templateLiteralWarning"
      class="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800"
    >
      此项来自模板字面量，保存后会修改所有循环实例。
    </p>

    <div v-if="props.kind === 'rich_text'">
      <label class="mb-1.5 block text-xs font-semibold text-slate-700">段落内容</label>
      <PageVisualEditRichTextEditor
        :model-value="String(props.effectiveValue ?? '')"
        :baseline-html="props.baselineRichText"
        :disabled="!props.editable"
        @update:model-value="emit('set-rich-text', $event)"
      />
      <p v-if="!props.editable" class="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
        {{ props.readonlyMessage }}
      </p>
    </div>
    <template v-else-if="props.editable">
      <select
        v-if="props.controlType === 'select'"
        :id="props.controlId"
        class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400"
        :value="props.optionIndex"
        @change="handleSelectChange"
      >
        <option v-if="props.optionIndex < 0" value="-1" disabled>请选择有限选项</option>
        <option v-for="(option, index) in props.options" :key="index" :value="index">
          {{ option.label }}
        </option>
      </select>
      <label v-else-if="props.controlType === 'boolean'" class="flex items-center gap-2 text-sm text-slate-700">
        <input
          :id="props.controlId"
          type="checkbox"
          class="h-4 w-4 rounded border-slate-300 text-indigo-600"
          :checked="Boolean(props.effectiveValue)"
          @change="emit('set-value', ($event.target as HTMLInputElement).checked)"
        />
        {{ Boolean(props.effectiveValue) ? '开启' : '关闭' }}
      </label>
      <input
        v-else-if="props.controlType === 'number'"
        :id="props.controlId"
        type="number"
        class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
        :value="String(props.effectiveValue ?? '')"
        :placeholder="props.placeholder ?? undefined"
        @input="handleNumberInput"
      />
      <textarea
        v-else-if="props.controlType === 'textarea'"
        :id="props.controlId"
        :rows="props.rows"
        class="w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
        :value="String(props.effectiveValue ?? '')"
        :placeholder="props.placeholder ?? undefined"
        @input="emit('set-value', ($event.target as HTMLTextAreaElement).value)"
      />
      <input
        v-else
        :id="props.controlId"
        type="text"
        class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
        :value="String(props.effectiveValue ?? '')"
        :placeholder="props.placeholder ?? undefined"
        @input="emit('set-value', ($event.target as HTMLInputElement).value)"
      />
    </template>
    <p v-else class="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
      {{ props.readonlyMessage }}
    </p>
    <p v-if="props.pending" class="mt-3 text-[11px] font-semibold text-indigo-600">
      此项有待保存修改，画布暂未更新。
    </p>
  </article>
</template>

<script setup lang="ts">
import PageVisualEditRichTextEditor from '@/components/page-detail/visual-edit/PageVisualEditRichTextEditor.vue'
import type {
  PageVisualEditBindingKind,
  PageVisualEditComponentSelectOption,
  PageVisualEditValue,
} from '@/types/page-visual-edit'

const props = withDefaults(defineProps<{
  controlId: string
  controlType: string
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

/** 写入有效数字值，空值或非法数字不生成字段事件。 */
function handleNumberInput(event: Event): void {
  const rawValue = (event.target as HTMLInputElement).value
  if (!rawValue.trim()) return
  const value = Number(rawValue)
  if (Number.isFinite(value)) emit('set-value', value)
}

/** 按有限选项原始值发出字段事件，避免 DOM 字符串化破坏数字或布尔类型。 */
function handleSelectChange(event: Event): void {
  const optionIndex = Number((event.target as HTMLSelectElement).value)
  const option = props.options[optionIndex]
  if (option) emit('set-value', option.value)
}
</script>
