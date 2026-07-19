<!-- 文件功能：提供按语义标签切分、锁定静态 class 结构的受控富文本编辑器。 -->
<template>
  <div class="overflow-hidden rounded-lg border border-slate-200 bg-white">
    <div v-if="!props.disabled" class="flex items-center gap-1 border-b border-slate-200 bg-slate-50 px-2 py-1.5">
      <button
        type="button"
        class="rounded px-2 py-1 text-xs font-bold text-slate-600 hover:bg-white hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
        :disabled="!canWrapSelection('strong')"
        aria-label="加粗所选文本"
        @mousedown.prevent="applySemanticTag('strong')"
      >
        B
      </button>
      <button
        type="button"
        class="rounded px-2 py-1 text-xs italic text-slate-600 hover:bg-white hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
        :disabled="!canWrapSelection('em')"
        aria-label="斜体所选文本"
        @mousedown.prevent="applySemanticTag('em')"
      >
        I
      </button>
      <span class="ml-auto text-[10px] text-slate-400">选中文字添加语义 · Enter 换行</span>
    </div>

    <div class="min-h-28 p-3">
      <PageVisualEditRichTextNodeEditor
        :nodes="nodes"
        :disabled="props.disabled"
        @remove-lock="removeLock"
        @selection-change="selection = $event"
        @text-change="updateText"
        @unwrap-node="unwrapNode"
      />
    </div>

    <p v-if="invalidStructure" class="border-t border-amber-100 bg-amber-50 px-3 py-1.5 text-[11px] text-amber-800">
      当前草稿修改了锁定样式结构，已恢复为基准内容。
    </p>
    <p v-if="tooLong" class="border-t border-rose-100 bg-rose-50 px-3 py-1.5 text-[11px] text-rose-700">
      内容超过 20000 字符限制，本次输入未加入草稿。
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import PageVisualEditRichTextNodeEditor from '@/components/page-detail/visual-edit/PageVisualEditRichTextNodeEditor.vue'
import {
  isPageVisualEditRichTextLockedStructurePruning,
  normalizePageVisualEditRichText,
  parsePageVisualEditRichText,
  removePageVisualEditRichTextLock,
  serializePageVisualEditRichText,
  unwrapPageVisualEditRichTextNode,
  updatePageVisualEditRichText,
  wrapPageVisualEditRichTextSelection,
  type PageVisualEditRichTextNode,
} from '@/utils/page-visual-edit-rich-text'

const MAX_RICH_TEXT_LENGTH = 20_000

interface PageVisualEditRichTextSelection {
  nodeId: string
  start: number
  end: number
  semanticTags: Array<'strong' | 'em'>
}

const props = withDefaults(defineProps<{
  modelValue: string
  baselineHtml?: string | null
  disabled?: boolean
}>(), {
  baselineHtml: null,
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const nodes = ref<PageVisualEditRichTextNode[]>(parsePageVisualEditRichText(props.modelValue))
const selection = ref<PageVisualEditRichTextSelection | null>(null)
const tooLong = ref(false)
const invalidStructure = ref(false)

watch(
  () => [props.modelValue, props.baselineHtml] as const,
  ([value]) => syncEditorValue(value),
  { flush: 'post', immediate: true },
)

/** 将外部草稿同步为结构化节点，并拒绝超出基准锁定标签骨架的内容。 */
function syncEditorValue(value: string): void {
  const baseline = props.baselineHtml ?? value
  const safeBaseline = normalizePageVisualEditRichText(baseline)
  const safeValue = normalizePageVisualEditRichText(value)
  invalidStructure.value = !isPageVisualEditRichTextLockedStructurePruning(safeBaseline, safeValue)
  const acceptedValue = invalidStructure.value ? safeBaseline : safeValue
  if (serializePageVisualEditRichText(nodes.value) !== acceptedValue) {
    nodes.value = parsePageVisualEditRichText(acceptedValue)
    selection.value = null
  }
  tooLong.value = false
}

/** 修改文本节点并尝试生成规范化草稿。 */
function updateText(payload: { nodeId: string; text: string }): void {
  if (props.disabled || !updatePageVisualEditRichText(nodes.value, payload.nodeId, payload.text)) return
  emitCurrentValue()
}

/** 移除锁定标签外壳，保留内部文本与子标签。 */
function removeLock(nodeId: string): void {
  if (props.disabled || !removePageVisualEditRichTextLock(nodes.value, nodeId)) return
  selection.value = null
  emitCurrentValue()
}

/** 取消 classless strong/em 标签并提升其子节点。 */
function unwrapNode(nodeId: string): void {
  if (props.disabled || !unwrapPageVisualEditRichTextNode(nodes.value, nodeId)) return
  selection.value = null
  emitCurrentValue()
}

/** 判断当前非空选区能否增加指定语义标签。 */
function canWrapSelection(tag: 'strong' | 'em'): boolean {
  return Boolean(
    !props.disabled
    && selection.value
    && selection.value.start < selection.value.end
    && !selection.value.semanticTags.includes(tag),
  )
}

/** 把当前单文本框选区包装成 classless strong/em。 */
function applySemanticTag(tag: 'strong' | 'em'): void {
  const currentSelection = selection.value
  if (!currentSelection || !canWrapSelection(tag)) return
  const changed = wrapPageVisualEditRichTextSelection(
    nodes.value,
    currentSelection.nodeId,
    currentSelection.start,
    currentSelection.end,
    tag,
  )
  if (!changed) return
  selection.value = null
  emitCurrentValue()
}

/** 序列化本地树；合法长度内才向草稿层发出变更。 */
function emitCurrentValue(): void {
  const normalized = serializePageVisualEditRichText(nodes.value)
  tooLong.value = normalized.length > MAX_RICH_TEXT_LENGTH
  invalidStructure.value = false
  if (!tooLong.value) emit('update:modelValue', normalized)
}
</script>
