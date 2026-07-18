<!-- 文件功能：展示选中 Vue 节点的文本、组件参数与受限 Tailwind 属性，并生成本地可视化编辑草稿。 -->
<template>
  <aside class="flex min-h-0 flex-col border-l border-slate-200 bg-white">
    <header class="border-b border-slate-200 px-4 py-3">
      <h3 class="text-sm font-bold text-slate-800">属性</h3>
      <p v-if="props.node" class="mt-1 truncate text-xs text-slate-500">
        {{ props.node.kind === 'root' ? 'Page' : props.node.tag }}
      </p>
    </header>

    <div v-if="props.node" class="min-h-0 flex-1 overflow-auto p-4">
      <section v-if="props.node.loop_context" class="mb-4 rounded-lg border border-sky-100 bg-sky-50 p-3 text-xs text-sky-800">
        <p class="font-semibold">循环容器</p>
        <p class="mt-1 break-all">{{ props.node.loop_context.source_expression }}</p>
        <p v-if="!props.node.loop_context.editable" class="mt-2 text-amber-700">
          {{ readonlyReasonLabel(props.node.loop_context.readonly_reason) }}
        </p>
      </section>

      <section v-if="props.node.bindings.length" class="space-y-2">
        <button
          v-for="binding in props.node.bindings"
          :key="binding.binding_id"
          type="button"
          class="flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs transition"
          :class="selectedBinding?.binding_id === binding.binding_id
            ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
            : 'border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50'"
          @click="emit('select-binding', binding.binding_id)"
        >
          <span class="truncate font-semibold">{{ bindingLabel(binding) }}</span>
          <span class="shrink-0 rounded bg-white/80 px-1.5 py-0.5 text-[10px] uppercase text-slate-500">
            {{ binding.kind }}
          </span>
        </button>
      </section>

      <p v-else class="rounded-lg border border-dashed border-slate-200 px-3 py-6 text-center text-xs text-slate-400">
        此容器没有可展示属性。
      </p>

      <section v-if="selectedBinding" class="mt-5 border-t border-slate-200 pt-4">
        <template v-if="scriptSource">
          <label class="block text-xs font-semibold text-slate-700" for="visual-edit-instance">循环实例</label>
          <select
            id="visual-edit-instance"
            v-model.number="selectedLocationIndex"
            class="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400"
          >
            <option v-for="location in scriptSource.locations" :key="location.index" :value="location.index">
              {{ instanceLabel(location) }}
            </option>
          </select>
          <p class="mt-1 text-[11px] text-slate-500">
            修改 {{ scriptSource.collection_name }} 中对应项的 {{ scriptSource.member }}。
          </p>
        </template>

        <p
          v-else-if="props.loopNodeId"
          class="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          此属性来自模板字面量，保存后会修改所有循环实例。
        </p>

        <div v-if="selectedBinding.kind === 'class'" class="mt-4">
          <template v-if="tailwindEditable">
            <div v-for="group in props.catalog?.groups ?? []" :key="group.key" class="mb-3">
              <label class="block text-xs font-semibold text-slate-700" :for="`tailwind-${group.key}`">
                {{ group.label }}
              </label>
              <select
                :id="`tailwind-${group.key}`"
                class="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400"
                :value="selectedClassForGroup(group.key)"
                @change="handleTailwindGroupChange(group.key, ($event.target as HTMLSelectElement).value)"
              >
                <option value="">清除该组</option>
                <option
                  v-for="option in group.options"
                  :key="option.class_name"
                  :value="option.class_name"
                  :title="option.class_name"
                >
                  {{ option.label }}
                </option>
              </select>
            </div>
          </template>
          <p v-else class="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
            {{ classReadonlyMessage }}
          </p>

          <div v-if="unknownClassTokens.length" class="mt-3">
            <p class="mb-2 text-[11px] font-semibold text-slate-500">保留的复杂 / 未识别类（只读）</p>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="token in unknownClassTokens"
                :key="token"
                class="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 font-mono text-[10px] text-amber-800"
              >
                {{ token }}
              </span>
            </div>
          </div>
        </div>

        <div v-else class="mt-4">
          <label class="mb-1.5 block text-xs font-semibold text-slate-700">
            {{ bindingLabel(selectedBinding) }}
          </label>
          <p v-if="selectedPropField?.description" class="mb-2 text-[11px] leading-4 text-slate-500">
            {{ selectedPropField.description }}
          </p>
          <template v-if="valueEditable">
            <select
              v-if="effectiveControlType === 'select'"
              class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400"
              :value="selectedOptionIndex"
              @change="handleSelectChange"
            >
              <option v-if="selectedOptionIndex < 0" value="-1" disabled>请选择有限选项</option>
              <option v-for="(option, index) in selectedPropField?.options ?? []" :key="index" :value="index">
                {{ option.label }}
              </option>
            </select>
            <label v-else-if="effectiveControlType === 'boolean'" class="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                class="h-4 w-4 rounded border-slate-300 text-indigo-600"
                :checked="Boolean(effectiveValue)"
                @change="handleBooleanChange"
              />
              {{ Boolean(effectiveValue) ? '开启' : '关闭' }}
            </label>
            <input
              v-else-if="effectiveControlType === 'number'"
              type="number"
              class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
              :value="String(effectiveValue ?? '')"
              :placeholder="selectedPropField?.placeholder ?? undefined"
              @input="handleNumberInput"
            />
            <textarea
              v-else-if="effectiveControlType === 'textarea'"
              rows="5"
              class="w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
              :value="String(effectiveValue ?? '')"
              :placeholder="selectedPropField?.placeholder ?? undefined"
              @input="handleStringInput"
            />
            <input
              v-else
              type="text"
              class="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-400"
              :value="String(effectiveValue ?? '')"
              :placeholder="selectedPropField?.placeholder ?? undefined"
              @input="handleStringInput"
            />
          </template>
          <p v-else class="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
            {{ valueReadonlyMessage }}
          </p>
        </div>

        <p v-if="currentOperation" class="mt-3 text-[11px] font-semibold text-indigo-600">
          此属性有待保存修改，画布暂不更新。
        </p>
      </section>
    </div>

    <div v-else class="flex min-h-0 flex-1 items-center justify-center px-5 text-center text-xs text-slate-400">
      从左侧图层或画布中选择一个容器。
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type {
  PageVisualEditBinding,
  PageVisualEditComponentPropField,
  PageVisualEditComponentSchema,
  PageVisualEditInstancePathSegment,
  PageVisualEditNode,
  PageVisualEditOperation,
  PageVisualEditScriptArrayBindingSource,
  PageVisualEditScriptMemberLocation,
  PageVisualEditTailwindCatalog,
  PageVisualEditTailwindTokenChange,
  PageVisualEditTarget,
  PageVisualEditValue,
} from '@/types/page-visual-edit'
import {
  resolvePageVisualEditComponentPropField,
  resolvePageVisualEditComponentSchema,
} from '@/utils/page-visual-edit'

const props = defineProps<{
  node: PageVisualEditNode | null
  selectedBindingId: string
  selectedInstancePath: PageVisualEditInstancePathSegment[]
  loopNodeId: string
  catalog: PageVisualEditTailwindCatalog | null
  componentSchemas: Record<string, PageVisualEditComponentSchema>
  pendingOperations: PageVisualEditOperation[]
}>()

const emit = defineEmits<{
  'select-binding': [bindingId: string]
  'set-value': [payload: { target: PageVisualEditTarget; value: PageVisualEditValue; baselineValue: PageVisualEditValue | undefined }]
  'set-tailwind': [payload: {
    target: PageVisualEditTarget
    changes: PageVisualEditTailwindTokenChange[]
    baselineChanges: PageVisualEditTailwindTokenChange[]
  }]
}>()

const selectedLocationIndex = ref(0)
const componentSchema = computed(() => resolvePageVisualEditComponentSchema(props.node, props.componentSchemas))
const selectedBinding = computed(() => {
  const bindings = props.node?.bindings ?? []
  return bindings.find(item => item.binding_id === props.selectedBindingId) ?? bindings[0] ?? null
})
const selectedPropField = computed<PageVisualEditComponentPropField | null>(() => {
  const binding = selectedBinding.value
  if (binding?.kind !== 'prop' || !binding.name) return null
  return resolvePageVisualEditComponentPropField(componentSchema.value, binding.name)
})
const scriptSource = computed<PageVisualEditScriptArrayBindingSource | null>(() => (
  selectedBinding.value?.source?.kind === 'script-array-item' ? selectedBinding.value.source : null
))
const selectedLocation = computed(() => (
  scriptSource.value?.locations.find(item => item.index === selectedLocationIndex.value)
  ?? scriptSource.value?.locations[0]
  ?? null
))
const target = computed<PageVisualEditTarget | null>(() => {
  const binding = selectedBinding.value
  if (!binding) return null
  if (!scriptSource.value) {
    return { nodeId: binding.node_id, bindingId: binding.binding_id, instancePath: [] }
  }
  const location = selectedLocation.value
  if (!location || !props.loopNodeId) return null
  if (!isStableInstanceKey(location.key)) return null
  const segment: PageVisualEditInstancePathSegment = {
    loopNodeId: props.loopNodeId,
    key: location.key,
    index: location.index,
  }
  return { nodeId: binding.node_id, bindingId: binding.binding_id, instancePath: [segment] }
})
const currentOperation = computed(() => {
  if (!target.value) return null
  return props.pendingOperations.find(operation => sameTarget(operation, target.value!)) ?? null
})
const baselineValue = computed<PageVisualEditValue | undefined>(() => (
  scriptSource.value ? selectedLocation.value?.value : selectedBinding.value?.value
))
const effectiveValue = computed<PageVisualEditValue | undefined>(() => (
  currentOperation.value?.type === 'set_value' ? currentOperation.value.value : baselineValue.value
))
const selectedLocationEditable = computed(() => (
  !scriptSource.value
  || (selectedLocation.value?.editable === true && isStableInstanceKey(selectedLocation.value.key))
))
const effectiveValueType = computed(() => {
  if (!scriptSource.value) return selectedBinding.value?.value_type ?? 'unknown'
  const value = selectedLocation.value?.value
  if (value === null) return 'null'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return typeof value
  return 'unknown'
})
const effectiveControlType = computed(() => {
  if (selectedPropField.value) return selectedPropField.value.type
  if (selectedBinding.value?.kind === 'text') return 'textarea'
  return effectiveValueType.value
})
const selectedOptionIndex = computed(() => (
  selectedPropField.value?.options?.findIndex(option => Object.is(option.value, effectiveValue.value)) ?? -1
))
const schemaTypeCompatible = computed(() => {
  const field = selectedPropField.value
  if (!field || field.type === 'json') return true
  const actualType = effectiveValueType.value
  if (field.type === 'string' || field.type === 'textarea') return actualType === 'string'
  if (field.type === 'number') return actualType === 'number'
  if (field.type === 'boolean') return actualType === 'boolean'
  if (!field.options?.length) return true
  return actualType !== 'unknown'
    && actualType !== 'null'
    && field.options.every(option => typeof option.value === actualType)
})
const valueEditable = computed(() => (
  Boolean(selectedBinding.value?.editable)
  && selectedLocationEditable.value
  && Boolean(target.value)
  && effectiveValueType.value !== 'unknown'
  && effectiveValueType.value !== 'null'
  && effectiveControlType.value !== 'json'
  && schemaTypeCompatible.value
  && (effectiveControlType.value !== 'select' || Boolean(selectedPropField.value?.options?.length))
))
const tailwindEditable = computed(() => (
  Boolean(selectedBinding.value?.editable)
  && selectedLocationEditable.value
  && Boolean(target.value)
  && typeof baselineValue.value === 'string'
  && Boolean(props.catalog?.groups.length)
))
const baselineClassTokens = computed(() => (
  typeof baselineValue.value === 'string' ? baselineValue.value.split(/\s+/).filter(Boolean) : []
))
const catalogClassNames = computed(() => new Set(
  (props.catalog?.groups ?? []).flatMap(group => group.options.map(option => option.class_name)),
))
const unknownClassTokens = computed(() => (
  baselineClassTokens.value.filter(token => !catalogClassNames.value.has(token))
))
const valueReadonlyMessage = computed(() => {
  if (scriptSource.value && !selectedLocation.value?.editable) {
    return readonlyReasonLabel(selectedLocation.value?.readonly_reason)
  }
  if (scriptSource.value && !isStableInstanceKey(selectedLocation.value?.key)) {
    return '此数组项缺少稳定的字符串或整数 key，不能安全写回。'
  }
  if (selectedPropField.value?.type === 'json') {
    return 'JSON 参数首版仅展示，不支持可视化写回。'
  }
  if (selectedPropField.value && !schemaTypeCompatible.value) {
    return '源码字面量类型与组件 schema 不一致，当前只读。'
  }
  if (selectedPropField.value?.type === 'select' && !selectedPropField.value.options?.length) {
    return '此参数没有可用的有限选项，当前只读。'
  }
  return readonlyReasonLabel(selectedBinding.value?.readonly_reason)
})
const classReadonlyMessage = computed(() => {
  if (typeof baselineValue.value !== 'string') return 'class 源码字面量不是字符串，当前只读。'
  if (!props.catalog?.groups.length) return '当前 Runtime 未提供 Tailwind 可视化目录，class 仅展示不可编辑。'
  return valueReadonlyMessage.value
})

watch(
  [scriptSource, () => props.selectedInstancePath],
  ([source, instancePath]) => {
    if (!source?.locations.length) return
    const runtimeSegment = instancePath.find(segment => segment.loopNodeId === props.loopNodeId)
    const matched = source.locations.find(location => (
      runtimeSegment?.key !== undefined
        ? location.key === runtimeSegment.key
        : location.index === runtimeSegment?.index
    ))
    selectedLocationIndex.value = (matched ?? source.locations[0])!.index
  },
  { immediate: true },
)

/** 生成人类可读的绑定名称。 */
function bindingLabel(binding: PageVisualEditBinding): string {
  if (binding.kind === 'text') return '文本内容'
  if (binding.kind === 'class') return 'Tailwind 样式'
  const schemaLabel = binding.kind === 'prop' && binding.name
    ? resolvePageVisualEditComponentPropField(componentSchema.value, binding.name)?.label
    : null
  return schemaLabel || (binding.name ? `组件参数 · ${binding.name}` : '组件参数')
}

/** 展示脚本数组实例的稳定 key，并保留 index 作为辅助定位信息。 */
function instanceLabel(location: PageVisualEditScriptMemberLocation): string {
  return location.key !== null && location.key !== undefined
    ? `key: ${String(location.key)}（第 ${location.index + 1} 项）`
    : `第 ${location.index + 1} 项`
}

/** 写入字符串值草稿。 */
function handleStringInput(event: Event): void {
  stageValue((event.target as HTMLInputElement | HTMLTextAreaElement).value)
}

/** 写入有效数字值，空值或非法数字不生成草稿。 */
function handleNumberInput(event: Event): void {
  const rawValue = (event.target as HTMLInputElement).value
  if (!rawValue.trim()) return
  const value = Number(rawValue)
  if (Number.isFinite(value)) stageValue(value)
}

/** 写入布尔值草稿。 */
function handleBooleanChange(event: Event): void {
  stageValue((event.target as HTMLInputElement).checked)
}

/** 按有限选项原始值写入 select 参数，避免 DOM 字符串化破坏数字或布尔类型。 */
function handleSelectChange(event: Event): void {
  const optionIndex = Number((event.target as HTMLSelectElement).value)
  const option = selectedPropField.value?.options?.[optionIndex]
  if (option) stageValue(option.value)
}

/** 发出一个带规范源码基准值的值变更。 */
function stageValue(value: PageVisualEditValue): void {
  if (!target.value || !valueEditable.value) return
  emit('set-value', { target: target.value, value, baselineValue: baselineValue.value })
}

/** 按 Tailwind 互斥组写入或清除一个受限 class。 */
function handleTailwindGroupChange(group: string, className: string): void {
  if (!target.value || !tailwindEditable.value) return
  emit('set-tailwind', {
    target: target.value,
    changes: [{ group, className: className || null }],
    baselineChanges: [{ group, className: baselineClassForGroup(group) }],
  })
}

/** 读取指定组当前草稿值；无草稿时回退到 artifact 基准 class。 */
function selectedClassForGroup(group: string): string {
  const pending = currentOperation.value?.type === 'set_tailwind_tokens'
    ? currentOperation.value.changes.find(change => change.group === group)
    : null
  return pending ? pending.className ?? '' : baselineClassForGroup(group) ?? ''
}

/** 从基准 class tokens 中寻找指定目录组的选项。 */
function baselineClassForGroup(groupKey: string): string | null {
  const group = props.catalog?.groups.find(item => item.key === groupKey)
  return group?.options.find(option => baselineClassTokens.value.includes(option.class_name))?.class_name ?? null
}

/** 比较两个草稿目标的节点、绑定和实例路径。 */
function sameTarget(left: PageVisualEditTarget, right: PageVisualEditTarget): boolean {
  return left.nodeId === right.nodeId
    && left.bindingId === right.bindingId
    && JSON.stringify(left.instancePath) === JSON.stringify(right.instancePath)
}

/** 判断数组实例 key 是否可用于跨 Runtime 与源码的稳定定位。 */
function isStableInstanceKey(value: unknown): value is string | number {
  return typeof value === 'string'
    || (typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value))
}

/** 将稳定只读原因转换为属性面板提示。 */
function readonlyReasonLabel(reason: string | null | undefined): string {
  const labels: Record<string, string> = {
    SFC_PARSE_ERROR: '页面源码解析失败，此属性只读。',
    TEMPLATE_UNSUPPORTED: '当前模板结构暂不支持可视化写回。',
    DYNAMIC_EXPRESSION: '动态表达式仅展示，不支持可视化编辑。',
    DYNAMIC_SCRIPT_SOURCE: '动态脚本数据源仅展示，不支持可视化编辑。',
    SCRIPT_SOURCE_NOT_FOUND: '未找到可安全写回的脚本数据源。',
    LOOP_SOURCE_UNSUPPORTED: '当前循环数据源暂不支持写回。',
    NESTED_LOOP_UNSUPPORTED: '首版不支持嵌套循环实例写回。',
    LOOP_MEMBER_UNSUPPORTED: '循环缺少稳定唯一 key，实例属性只读。',
    MEMBER_NOT_FOUND: '数组项中未找到对应成员。',
    MEMBER_VALUE_DYNAMIC: '数组成员是动态值，不能安全写回。',
    ATTRIBUTE_VALUE_MISSING: '属性没有可写回的字面量值。',
  }
  return reason ? labels[reason] ?? `只读：${reason}` : '此属性当前只读。'
}
</script>
