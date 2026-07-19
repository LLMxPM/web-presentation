<!-- 文件功能：编辑 Manifest 中一个整块 JSON source，并在生成结构化操作前完成本地格式与规模校验。 -->
<template>
  <section class="rounded-lg border border-slate-200 bg-white p-3">
    <div class="mb-2">
      <div class="flex items-center justify-between gap-3">
        <p class="min-w-0 flex-1 text-xs font-bold text-slate-700">{{ props.label }}</p>
        <div class="flex shrink-0 gap-1 whitespace-nowrap">
          <button type="button" class="whitespace-nowrap rounded px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-100" @click="formatDraft">格式化</button>
          <button type="button" class="whitespace-nowrap rounded px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-100" @click="restoreBaseline">恢复</button>
        </div>
      </div>
      <p v-if="props.componentProp" class="mt-1 text-[11px] text-amber-700">仅校验 JSON 格式，组件可能有额外运行约束。</p>
    </div>
    <MonacoCodeEditor
      :model-value="draft"
      language="json"
      theme="light"
      :auto-save-delay="0"
      height="180px"
      @update:model-value="updateDraft"
    />
    <p v-if="errorMessage" class="mt-2 text-xs text-rose-600">{{ errorMessage }}</p>
    <p v-else-if="props.pendingValue !== undefined" class="mt-2 text-[11px] font-semibold text-indigo-600">此 JSON 有待保存修改，画布暂未更新。</p>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import MonacoCodeEditor from '@/components/editor/MonacoCodeEditor.vue'
import type { PageVisualEditJsonSource, PageVisualEditJsonValue } from '@/types/page-visual-edit'

const MAX_JSON_BYTES = 200_000
const MAX_JSON_DEPTH = 32
const MAX_JSON_NODES = 10_000

const props = defineProps<{
  source: PageVisualEditJsonSource
  label: string
  componentProp: boolean
  pendingValue?: PageVisualEditJsonValue
}>()

const emit = defineEmits<{
  'set-json': [payload: { sourceId: string; value: PageVisualEditJsonValue; baselineValue: PageVisualEditJsonValue }]
  'validation-change': [payload: { sourceId: string; invalid: boolean }]
}>()

const draft = ref('')
const errorMessage = ref('')

watch(
  () => [props.source.source_id, props.pendingValue, props.source.value] as const,
  () => {
    draft.value = serialize(props.pendingValue === undefined ? props.source.value : props.pendingValue)
    setError('')
  },
  { immediate: true, deep: true },
)

/** 更新 Monaco 草稿；只有完整合法 JSON 才生成结构化操作。 */
function updateDraft(value: string): void {
  draft.value = value
  try {
    if (new TextEncoder().encode(value).byteLength > MAX_JSON_BYTES) throw new Error('JSON 值超过 200000 字节上限。')
    const parsed = JSON.parse(value) as PageVisualEditJsonValue
    validateJsonShape(parsed)
    if (props.source.kind !== 'template-expression') {
      const sourceArray = Array.isArray(props.source.value)
      if (parsed === null || typeof parsed !== 'object' || sourceArray !== Array.isArray(parsed)) {
        throw new Error('顶层数据必须保持原有数组或对象根类型。')
      }
    }
    setError('')
    emit('set-json', { sourceId: props.source.source_id, value: parsed, baselineValue: props.source.value })
  } catch (error) {
    setError(error instanceof Error ? error.message : 'JSON 格式不合法。')
  }
}

/** 将合法草稿格式化为两空格 JSON。 */
function formatDraft(): void {
  try {
    draft.value = serialize(JSON.parse(draft.value) as PageVisualEditJsonValue)
    updateDraft(draft.value)
  } catch (error) {
    setError(error instanceof Error ? error.message : 'JSON 格式不合法。')
  }
}

/** 恢复 artifact 对应的规范源码基准值。 */
function restoreBaseline(): void {
  draft.value = serialize(props.source.value)
  updateDraft(draft.value)
}

/** 校验深度、节点数和有限数值，与服务端限制保持一致。 */
function validateJsonShape(value: PageVisualEditJsonValue): void {
  let nodes = 0
  const walk = (item: PageVisualEditJsonValue, depth: number): void => {
    nodes += 1
    if (depth > MAX_JSON_DEPTH) throw new Error('JSON 嵌套深度超过 32。')
    if (nodes > MAX_JSON_NODES) throw new Error('JSON 节点数量超过 10000。')
    if (typeof item === 'number' && !Number.isFinite(item)) throw new Error('JSON 数字必须是有限值。')
    if (Array.isArray(item)) item.forEach(child => walk(child, depth + 1))
    else if (item && typeof item === 'object') Object.values(item).forEach(child => walk(child, depth + 1))
  }
  walk(value, 1)
}

/** 更新错误并让父面板统一禁用整批保存。 */
function setError(message: string): void {
  errorMessage.value = message
  emit('validation-change', { sourceId: props.source.source_id, invalid: Boolean(message) })
}

function serialize(value: PageVisualEditJsonValue): string {
  return JSON.stringify(value, null, 2)
}
</script>
