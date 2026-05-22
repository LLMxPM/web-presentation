<!-- 文件功能：渲染组件预览的 props、slots 与 mocks 参数面板，并把实时变更回传给父层。 -->
<template>
  <section :class="compactBody ? 'min-w-0 bg-transparent' : horizontal ? 'min-w-0 bg-transparent' : embedded ? '' : 'bg-white'">
    <div v-if="horizontal && !compactBody" class="flex min-w-0 items-stretch gap-3 overflow-x-auto px-4 py-3">
      <div class="flex min-w-max items-center gap-2">
        <span class="text-xs font-bold text-slate-700">预览参数</span>
        <div v-if="panelTabs.length" class="flex flex-wrap gap-1.5">
          <button
            v-for="tab in panelTabs"
            :key="tab.key"
            type="button"
            class="rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors"
            :class="currentPanel === tab.key
              ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
              : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'"
            @click="currentPanel = tab.key"
          >
            {{ tab.label }}
            <span class="ml-0.5 text-[10px] text-slate-400">{{ tab.count }}</span>
          </button>
        </div>
        <BaseButton
          v-if="schema"
          variant="ghost"
          size="sm"
          custom-class="!h-8 !px-2 !text-xs"
          @click="resetState"
        >
          重置
        </BaseButton>
      </div>

      <div v-if="loading" class="flex min-w-[220px] items-center rounded-xl border border-slate-200 bg-white px-4 text-xs font-semibold text-slate-400">
        正在读取 previewSchema...
      </div>

      <div v-else-if="errorMessage" class="flex min-w-[320px] items-center rounded-xl border border-rose-100 bg-rose-50 px-4 text-xs font-semibold leading-5 text-rose-500">
        组件预览启动失败：{{ errorMessage }}
      </div>

      <div
        v-else-if="!schema"
        class="flex min-w-[260px] items-center rounded-xl border border-dashed border-slate-200 bg-white px-4 text-xs leading-5 text-slate-400"
      >
        当前组件未导出 previewSchema，只能查看静态预览。
      </div>

      <div v-else-if="panelTabs.length === 0" class="flex min-w-[320px] items-center rounded-xl border border-dashed border-slate-200 bg-white px-4 text-xs leading-5 text-slate-400">
        previewSchema 已导出，但暂无可编辑的 props、slots 或 mocks。
      </div>

      <div v-else class="flex min-w-max items-stretch gap-2">
        <section v-if="currentPanel === 'props' && propEntries.length" class="flex min-w-max items-stretch gap-2">
          <h4 class="flex h-9 items-center text-[10px] font-bold uppercase tracking-wide text-slate-400">Props</h4>
          <article
            v-for="[propKey, propField] in propEntries"
            :key="propKey"
            class="rounded-xl border border-slate-100 bg-white px-3 py-2.5"
            :class="resolveHorizontalFieldCardClass(propField.type)"
          >
            <div class="mb-1.5">
              <div class="flex items-center gap-1.5">
                <h5 class="truncate text-xs font-semibold text-slate-800">{{ propField.label || propKey }}</h5>
                <span class="rounded bg-slate-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-400">
                  {{ propField.type }}
                </span>
              </div>
              <p v-if="propField.description" class="mt-0.5 line-clamp-2 text-[11px] leading-5 text-slate-400">
                {{ propField.description }}
              </p>
            </div>

            <div v-if="propField.type === 'boolean'" class="flex h-9 items-center gap-3">
              <input
                :id="`preview-prop-horizontal-${propKey}`"
                :checked="Boolean(localState.props[propKey])"
                type="checkbox"
                class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                @change="updateBooleanProp(propKey, $event)"
              >
              <label :for="`preview-prop-horizontal-${propKey}`" class="text-sm text-slate-700">启用</label>
            </div>

            <select
              v-else-if="propField.type === 'select'"
              class="h-9 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition focus:border-indigo-500"
              :value="getSelectOptionIndex(propField.options, localState.props[propKey])"
              @change="updateSelectProp(propKey, propField.options, $event)"
            >
              <option v-for="(option, optionIndex) in propField.options || []" :key="`${propKey}-${optionIndex}`" :value="optionIndex">
                {{ option.label }}
              </option>
            </select>

            <div v-else-if="propField.type === 'json'" class="space-y-2">
              <MonacoCodeEditor
                :model-value="jsonDrafts[`prop:${propKey}`] || '{}'"
                language="json"
                theme="light"
                :auto-save-delay="0"
                height="116px"
                @update:model-value="updateJsonDraft(`prop:${propKey}`, $event, (value) => updateJsonProp(propKey, value))"
              />
              <p v-if="jsonErrors[`prop:${propKey}`]" class="text-xs text-red-500">
                {{ jsonErrors[`prop:${propKey}`] }}
              </p>
            </div>

            <BaseInput
              v-else
              :model-value="resolveScalarFieldValue(localState.props[propKey])"
              :type="propField.type === 'textarea' ? 'textarea' : propField.type === 'number' ? 'number' : 'text'"
              :rows="propField.type === 'textarea' ? 2 : undefined"
              :placeholder="propField.placeholder || ''"
              @update:model-value="updateScalarProp(propKey, propField.type, $event)"
            />
          </article>
        </section>

        <section v-if="currentPanel === 'slots' && slotEntries.length" class="flex min-w-max items-stretch gap-2">
          <h4 class="flex h-9 items-center text-[10px] font-bold uppercase tracking-wide text-slate-400">Slots</h4>
          <article
            v-for="[slotKey, slotField] in slotEntries"
            :key="slotKey"
            class="w-[420px] rounded-xl border border-slate-100 bg-white px-3 py-2.5"
          >
            <div class="mb-1.5">
              <h5 class="truncate text-xs font-semibold text-slate-800">{{ slotField.label || slotKey }}</h5>
              <p v-if="slotField.description" class="mt-0.5 line-clamp-2 text-[11px] leading-5 text-slate-400">
                {{ slotField.description }}
              </p>
            </div>
            <MonacoCodeEditor
              :model-value="jsonDrafts[`slot:${slotKey}`] || '[]'"
              language="json"
              theme="light"
              :auto-save-delay="0"
              height="116px"
              @update:model-value="updateJsonDraft(`slot:${slotKey}`, $event, (value) => updateSlotValue(slotKey, value))"
            />
            <p v-if="jsonErrors[`slot:${slotKey}`]" class="mt-2 text-xs text-red-500">
              {{ jsonErrors[`slot:${slotKey}`] }}
            </p>
          </article>
        </section>

        <section v-if="currentPanel === 'mocks' && mockEntries.length" class="flex min-w-max items-stretch gap-2">
          <h4 class="flex h-9 items-center text-[10px] font-bold uppercase tracking-wide text-slate-400">Mocks</h4>
          <article
            v-for="[mockKey, mockField] in mockEntries"
            :key="mockKey"
            class="w-[420px] rounded-xl border border-slate-100 bg-white px-3 py-2.5"
          >
            <div class="mb-1.5">
              <h5 class="truncate text-xs font-semibold text-slate-800">{{ mockField.label || mockKey }}</h5>
              <p v-if="mockField.description" class="mt-0.5 line-clamp-2 text-[11px] leading-5 text-slate-400">
                {{ mockField.description }}
              </p>
            </div>
            <MonacoCodeEditor
              :model-value="jsonDrafts[`mock:${mockKey}`] || '{}'"
              language="json"
              theme="light"
              :auto-save-delay="0"
              height="116px"
              @update:model-value="updateJsonDraft(`mock:${mockKey}`, $event, (value) => updateMockValue(mockKey, value))"
            />
            <p v-if="jsonErrors[`mock:${mockKey}`]" class="mt-2 text-xs text-red-500">
              {{ jsonErrors[`mock:${mockKey}`] }}
            </p>
          </article>
        </section>
      </div>
    </div>

    <template v-else>
      <header v-if="!embedded && !compactBody" class="border-b border-slate-100 px-3 py-2">
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <h3 class="text-xs font-bold text-slate-700">预览调参</h3>
          <span v-if="schema && componentMeta" class="text-[10px] font-mono text-slate-400">
            {{ componentMeta.code }}<template v-if="componentMeta.versionNo"> · v{{ componentMeta.versionNo }}</template>
          </span>
        </div>
        <BaseButton
          v-if="schema"
          variant="ghost"
          size="sm"
          custom-class="!px-2 !py-0.5 !text-xs"
          @click="resetState"
        >
          重置
        </BaseButton>
      </div>

      <div v-if="panelTabs.length" class="mt-2 flex flex-wrap gap-1.5">
        <button
          v-for="tab in panelTabs"
          :key="tab.key"
          type="button"
          class="rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors"
          :class="currentPanel === tab.key
            ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'"
          @click="currentPanel = tab.key"
        >
          {{ tab.label }}
          <span class="ml-0.5 text-[10px] text-slate-400">{{ tab.count }}</span>
        </button>
      </div>
      <p class="mt-2 text-[11px] leading-5 text-slate-400">
        {{ headerText }}
      </p>
    </header>

      <div :class="compactBody ? '' : embedded ? 'space-y-3 p-3' : 'px-3 py-2'">
      <div v-if="embedded && schema && !compactBody" class="flex items-start justify-between gap-3">
        <div v-if="panelTabs.length" class="flex min-w-0 flex-1 flex-wrap gap-1.5">
          <button
            v-for="tab in panelTabs"
            :key="tab.key"
            type="button"
            class="rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors"
            :class="currentPanel === tab.key
              ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
              : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'"
            @click="currentPanel = tab.key"
          >
            {{ tab.label }}
            <span class="ml-0.5 text-[10px] text-slate-400">{{ tab.count }}</span>
          </button>
        </div>
        <BaseButton
          variant="ghost"
          size="sm"
          custom-class="!px-2 !py-0.5 !text-xs"
          @click="resetState"
        >
          重置
        </BaseButton>
      </div>

      <div v-if="loading" class="flex min-h-[160px] items-center justify-center text-xs font-semibold text-slate-400">
        正在读取 previewSchema...
      </div>

      <div v-else-if="errorMessage" class="rounded-xl border border-rose-100 bg-rose-50 px-3 py-4 text-xs font-semibold leading-6 text-rose-500">
        组件预览启动失败：{{ errorMessage }}
      </div>

      <div
        v-else-if="!schema"
        class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs leading-6 text-slate-400"
      >
        当前组件未导出 previewSchema，只能查看静态预览。
      </div>

      <div v-else-if="panelTabs.length === 0" class="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs leading-6 text-slate-400">
        previewSchema 已导出，但暂无可编辑的 props、slots 或 mocks。
      </div>

      <div v-else class="space-y-3">
        <section v-if="currentPanel === 'props' && propEntries.length" class="space-y-2">
          <h4 class="text-[10px] font-bold uppercase tracking-wide text-slate-400">Props</h4>
          <div class="space-y-2">
            <article
              v-for="[propKey, propField] in propEntries"
              :key="propKey"
              class="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5"
            >
              <div class="mb-1.5">
                <div class="flex items-center gap-1.5">
                  <h5 class="text-xs font-semibold text-slate-800">{{ propField.label || propKey }}</h5>
                  <span class="rounded bg-white px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-400">
                    {{ propField.type }}
                  </span>
                </div>
                <p v-if="propField.description" class="mt-0.5 text-[11px] leading-5 text-slate-400">
                  {{ propField.description }}
                </p>
              </div>

              <div v-if="propField.type === 'boolean'" class="flex items-center gap-3">
                <input
                  :id="`preview-prop-${propKey}`"
                  :checked="Boolean(localState.props[propKey])"
                  type="checkbox"
                  class="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  @change="updateBooleanProp(propKey, $event)"
                >
                <label :for="`preview-prop-${propKey}`" class="text-sm text-slate-700">启用</label>
              </div>

              <div v-else-if="propField.type === 'select'" class="space-y-2">
                <select
                  class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-indigo-500"
                  :value="getSelectOptionIndex(propField.options, localState.props[propKey])"
                  @change="updateSelectProp(propKey, propField.options, $event)"
                >
                  <option v-for="(option, optionIndex) in propField.options || []" :key="`${propKey}-${optionIndex}`" :value="optionIndex">
                    {{ option.label }}
                  </option>
                </select>
              </div>

              <div v-else-if="propField.type === 'json'" class="space-y-2">
                <MonacoCodeEditor
                  :model-value="jsonDrafts[`prop:${propKey}`] || '{}'"
                  language="json"
                  theme="light"
                  :auto-save-delay="0"
                  height="140px"
                  @update:model-value="updateJsonDraft(`prop:${propKey}`, $event, (value) => updateJsonProp(propKey, value))"
                />
                <p v-if="jsonErrors[`prop:${propKey}`]" class="text-xs text-red-500">
                  {{ jsonErrors[`prop:${propKey}`] }}
                </p>
              </div>

              <BaseInput
                v-else
                :model-value="resolveScalarFieldValue(localState.props[propKey])"
                :type="propField.type === 'textarea' ? 'textarea' : propField.type === 'number' ? 'number' : 'text'"
                :rows="propField.type === 'textarea' ? 4 : undefined"
                :placeholder="propField.placeholder || ''"
                @update:model-value="updateScalarProp(propKey, propField.type, $event)"
              />
            </article>
          </div>
        </section>

        <section v-if="currentPanel === 'slots' && slotEntries.length" class="space-y-2">
          <h4 class="text-[10px] font-bold uppercase tracking-wide text-slate-400">Slots</h4>
          <article
            v-for="[slotKey, slotField] in slotEntries"
            :key="slotKey"
            class="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5"
          >
            <div class="mb-1.5">
              <h5 class="text-xs font-semibold text-slate-800">{{ slotField.label || slotKey }}</h5>
              <p v-if="slotField.description" class="mt-0.5 text-[11px] leading-5 text-slate-400">
                {{ slotField.description }}
              </p>
            </div>
            <MonacoCodeEditor
              :model-value="jsonDrafts[`slot:${slotKey}`] || '[]'"
              language="json"
              theme="light"
              :auto-save-delay="0"
              :height="compactBody ? '180px' : '160px'"
              @update:model-value="updateJsonDraft(`slot:${slotKey}`, $event, (value) => updateSlotValue(slotKey, value))"
            />
            <p v-if="jsonErrors[`slot:${slotKey}`]" class="mt-2 text-xs text-red-500">
              {{ jsonErrors[`slot:${slotKey}`] }}
            </p>
          </article>
        </section>

        <section v-if="currentPanel === 'mocks' && mockEntries.length" class="space-y-2">
          <h4 class="text-[10px] font-bold uppercase tracking-wide text-slate-400">Mocks</h4>
          <article
            v-for="[mockKey, mockField] in mockEntries"
            :key="mockKey"
            class="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5"
          >
            <div class="mb-1.5">
              <h5 class="text-xs font-semibold text-slate-800">{{ mockField.label || mockKey }}</h5>
              <p v-if="mockField.description" class="mt-0.5 text-[11px] leading-5 text-slate-400">
                {{ mockField.description }}
              </p>
            </div>
            <MonacoCodeEditor
              :model-value="jsonDrafts[`mock:${mockKey}`] || '{}'"
              language="json"
              theme="light"
              :auto-save-delay="0"
              :height="compactBody ? '160px' : '140px'"
              @update:model-value="updateJsonDraft(`mock:${mockKey}`, $event, (value) => updateMockValue(mockKey, value))"
            />
            <p v-if="jsonErrors[`mock:${mockKey}`]" class="mt-2 text-xs text-red-500">
              {{ jsonErrors[`mock:${mockKey}`] }}
            </p>
          </article>
        </section>
      </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import MonacoCodeEditor from '@/components/editor/MonacoCodeEditor.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import {
  buildInitialComponentPreviewState,
  cloneComponentPreviewState,
  clonePreviewValue,
  type ComponentPreviewSchema,
  type ComponentPreviewState,
} from '@/types/component-preview'

type ComponentPreviewPanelKey = 'props' | 'slots' | 'mocks'

const props = withDefaults(defineProps<{
  loading: boolean
  errorMessage?: string
  schema: ComponentPreviewSchema | null
  state: ComponentPreviewState
  embedded?: boolean
  horizontal?: boolean
  compactBody?: boolean
  activePanel?: ComponentPreviewPanelKey | null
  componentMeta?: {
    code: string
    versionNo?: number
    displayName: string
    source?: 'workspace_component' | 'runtime_kit'
    runtimeKitComponentName?: string
    runtimeKitManifestVersion?: string
  } | null
}>(), {
  errorMessage: '',
  embedded: false,
  horizontal: false,
  compactBody: false,
  activePanel: null,
  componentMeta: null,
})

const emit = defineEmits<{
  'update:state': [state: ComponentPreviewState]
  'update:activePanel': [panel: ComponentPreviewPanelKey]
}>()

const localState = reactive<ComponentPreviewState>(cloneComponentPreviewState(props.state))
const jsonDrafts = reactive<Record<string, string>>({})
const jsonErrors = reactive<Record<string, string>>({})
const internalPanel = ref<ComponentPreviewPanelKey>('props')
const currentPanel = computed<ComponentPreviewPanelKey>({
  get: () => props.activePanel ?? internalPanel.value,
  set: (nextPanel) => {
    internalPanel.value = nextPanel
    emit('update:activePanel', nextPanel)
  },
})

const propEntries = computed(() => Object.entries(props.schema?.props || {}))
const slotEntries = computed(() => Object.entries(props.schema?.slots || {}))
const mockEntries = computed(() => Object.entries(props.schema?.mocks || {}))
const panelTabs = computed(() => {
  const tabs: Array<{ key: ComponentPreviewPanelKey; label: string; count: number }> = []
  if (propEntries.value.length) {
    tabs.push({ key: 'props', label: 'Props', count: propEntries.value.length })
  }
  if (slotEntries.value.length) {
    tabs.push({ key: 'slots', label: 'Slots', count: slotEntries.value.length })
  }
  if (mockEntries.value.length) {
    tabs.push({ key: 'mocks', label: 'Mocks', count: mockEntries.value.length })
  }
  return tabs
})
const headerText = computed(() => {
  if (props.loading) {
    return '正在从 Runtime 宿主页读取组件 schema。'
  }
  if (props.errorMessage) {
    return `组件预览启动失败：${props.errorMessage}`
  }
  if (!props.schema) {
    return '当前组件没有导出 previewSchema。'
  }
  if (props.componentMeta) {
    return `${props.componentMeta.displayName} · ${props.componentMeta.code} · v${props.componentMeta.versionNo}`
  }
  return '当前已连接组件预览会话。'
})

watch(() => props.state, (nextState) => {
  const clonedState = cloneComponentPreviewState(nextState)
  localState.props = clonedState.props
  localState.slots = clonedState.slots
  localState.mocks = clonedState.mocks
  localState.activePresetKey = clonedState.activePresetKey
  syncJsonDrafts()
}, { deep: true, immediate: true })

watch(() => props.schema, () => {
  syncJsonDrafts()
  ensureCurrentPanel()
}, { immediate: true })

/**
 * 确保当前选中的标签页仍然可用，避免 schema 变化后落在空面板上。
 */
function ensureCurrentPanel() {
  if (panelTabs.value.some(item => item.key === currentPanel.value)) {
    return
  }
  currentPanel.value = panelTabs.value[0]?.key || 'props'
}

/**
 * 同步 JSON 字段的编辑草稿，避免 props.state 变化后编辑器文本不同步。
 */
function syncJsonDrafts() {
  for (const [propKey, propField] of propEntries.value) {
    if (propField.type === 'json') {
      jsonDrafts[`prop:${propKey}`] = serializeJson(localState.props[propKey] ?? null)
      jsonErrors[`prop:${propKey}`] = ''
    }
  }
  for (const [slotKey] of slotEntries.value) {
    jsonDrafts[`slot:${slotKey}`] = serializeJson(localState.slots[slotKey] ?? [])
    jsonErrors[`slot:${slotKey}`] = ''
  }
  for (const [mockKey] of mockEntries.value) {
    jsonDrafts[`mock:${mockKey}`] = serializeJson(localState.mocks[mockKey] ?? null)
    jsonErrors[`mock:${mockKey}`] = ''
  }
}

/**
 * 发出最新组件预览状态给父层，并确保对象已深拷贝。
 */
function emitState() {
  emit('update:state', cloneComponentPreviewState(localState))
}

/**
 * 将标量 props 字段写回本地状态。
 * @param propKey props 键名
 * @param fieldType 字段类型
 * @param value 原始输入值
 */
function updateScalarProp(propKey: string, fieldType: string, value: string | number) {
  if (fieldType === 'number') {
    const normalizedValue = String(value).trim()
    localState.props[propKey] = normalizedValue === '' ? undefined : Number(normalizedValue)
  } else {
    localState.props[propKey] = value
  }
  localState.activePresetKey = null
  emitState()
}

/**
 * 更新布尔 props。
 * @param propKey props 键名
 * @param event change 事件
 */
function updateBooleanProp(propKey: string, event: Event) {
  localState.props[propKey] = (event.target as HTMLInputElement).checked
  localState.activePresetKey = null
  emitState()
}

/**
 * 更新 select 类型 props。
 * @param propKey props 键名
 * @param options 选项集合
 * @param event select change 事件
 */
function updateSelectProp(propKey: string, options: Array<{ label: string; value: string | number | boolean }> | undefined, event: Event) {
  const optionIndex = Number((event.target as HTMLSelectElement).value)
  localState.props[propKey] = options?.[optionIndex]?.value
  localState.activePresetKey = null
  emitState()
}

/**
 * 更新 JSON 类型 props。
 * @param propKey props 键名
 * @param value 已解析 JSON 值
 */
function updateJsonProp(propKey: string, value: unknown) {
  localState.props[propKey] = value
  localState.activePresetKey = null
  emitState()
}

/**
 * 更新 slot 节点值。
 * @param slotKey slot 名称
 * @param value 已解析 JSON 值
 */
function updateSlotValue(slotKey: string, value: unknown) {
  localState.slots[slotKey] = Array.isArray(value) ? clonePreviewValue(value) : []
  localState.activePresetKey = null
  emitState()
}

/**
 * 更新 mock 值。
 * @param mockKey mock 键名
 * @param value 已解析 JSON 值
 */
function updateMockValue(mockKey: string, value: unknown) {
  localState.mocks[mockKey] = value
  localState.activePresetKey = null
  emitState()
}

/**
 * 处理 JSON 文本编辑，仅在解析成功时才同步到父层。
 * @param draftKey 当前 JSON 草稿键名
 * @param value 原始文本
 * @param onValid 解析成功后的回调
 */
function updateJsonDraft(draftKey: string, value: string, onValid: (value: unknown) => void) {
  jsonDrafts[draftKey] = value
  try {
    const parsedValue = JSON.parse(value)
    jsonErrors[draftKey] = ''
    onValid(parsedValue)
  } catch (error) {
    jsonErrors[draftKey] = error instanceof Error ? error.message : 'JSON 解析失败。'
  }
}

/**
 * 将面板恢复到 schema 默认值。
 */
function resetState() {
  const nextState = buildInitialComponentPreviewState(props.schema)
  localState.props = nextState.props
  localState.slots = nextState.slots
  localState.mocks = nextState.mocks
  localState.activePresetKey = nextState.activePresetKey
  syncJsonDrafts()
  emitState()
}

/**
 * 将任意 JSON 值序列化为更易读的缩进文本。
 * @param value 原始值
 * @returns JSON 字符串
 */
function serializeJson(value: unknown) {
  return JSON.stringify(value ?? null, null, 2)
}

/**
 * 归一化标量输入框展示值。
 * @param value 原始字段值
 * @returns 输入框展示值
 */
function resolveScalarFieldValue(value: unknown) {
  if (value === undefined || value === null) {
    return ''
  }
  return typeof value === 'string' || typeof value === 'number' ? value : String(value)
}

/**
 * 计算横向模式下单个字段卡片宽度，JSON 与多行文本保留更大的编辑空间。
 * @param fieldType previewSchema 字段类型
 * @returns Tailwind 宽度类名
 */
function resolveHorizontalFieldCardClass(fieldType: string) {
  if (fieldType === 'json') {
    return 'w-[360px]'
  }
  if (fieldType === 'textarea') {
    return 'w-[280px]'
  }
  return 'w-[220px]'
}

/**
 * 计算 select 字段当前命中的选项索引。
 * @param options 选项列表
 * @param currentValue 当前字段值
 * @returns 选项索引
 */
function getSelectOptionIndex(options: Array<{ label: string; value: string | number | boolean }> | undefined, currentValue: unknown) {
  const index = (options || []).findIndex(option => option.value === currentValue)
  return index >= 0 ? index : 0
}
</script>
