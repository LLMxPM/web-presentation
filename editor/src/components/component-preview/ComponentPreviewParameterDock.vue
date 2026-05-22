<!-- 文件功能：提供组件预览参数薄栏、Preset radio 切换与顶部浮层抽屉。 -->
<template>
  <section class="relative border-t border-slate-100 bg-slate-50/70">
    <div class="flex h-11 items-center gap-3 overflow-hidden px-4">
      <span class="shrink-0 text-xs font-bold text-slate-700">预览参数</span>

      <div
        v-if="presetOptions.length"
        class="overflow-x-auto whitespace-nowrap"
        :class="simplified ? 'min-w-0 flex-1 basis-[220px]' : 'min-w-[220px] max-w-[360px]'"
        role="radiogroup"
        aria-label="预览参数预设"
      >
        <div class="inline-flex items-center gap-1.5">
          <label
            v-if="!simplified"
            class="inline-flex cursor-pointer items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors"
            :class="resolvePresetRadioClass(!activePresetKey)"
          >
            <input
              class="sr-only"
              type="radio"
              :name="presetRadioName"
              :checked="!activePresetKey"
              @change="selectCustomPreset"
            >
            自定义
          </label>

          <label
            v-for="preset in presetOptions"
            :key="preset.key"
            class="inline-flex cursor-pointer items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors"
            :class="resolvePresetRadioClass(activePresetKey === preset.key)"
          >
            <input
              class="sr-only"
              type="radio"
              :name="presetRadioName"
              :checked="activePresetKey === preset.key"
              @change="selectPreset(preset)"
            >
            {{ preset.label }}
          </label>
        </div>
      </div>

      <div v-if="!simplified && panelTabs.length" class="flex shrink-0 items-center gap-1.5">
        <button
          v-for="tab in panelTabs"
          :key="tab.key"
          type="button"
          class="rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors"
          :class="activePanel === tab.key
            ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
            : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'"
          @click="selectPanelTab(tab.key)"
        >
          {{ tab.label }}
          <span class="ml-0.5 text-[10px] text-slate-400">{{ tab.count }}</span>
        </button>
      </div>

      <p
        class="min-w-0 flex-1 truncate text-xs"
        :class="errorMessage ? 'font-semibold text-rose-500' : 'text-slate-400'"
      >
        {{ statusText }}
      </p>

      <BaseButton
        v-if="schema && !simplified"
        variant="ghost"
        size="sm"
        custom-class="!h-8 !px-2 !text-xs"
        @click="resetState"
      >
        重置
      </BaseButton>

      <button
        v-if="!simplified"
        type="button"
        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-white hover:text-slate-700 disabled:cursor-not-allowed disabled:text-slate-300 disabled:hover:bg-transparent"
        :disabled="!canOpenDrawer"
        :aria-expanded="drawerOpen"
        title="展开预览参数"
        @click="toggleDrawer"
      >
        <component :is="drawerOpen ? ChevronUp : ChevronDown" class="h-4 w-4" />
      </button>
    </div>

    <div
      v-if="drawerOpen && canOpenDrawer"
      class="absolute left-0 right-0 top-full z-20 border-t border-slate-200 bg-white shadow-xl shadow-slate-900/10"
    >
      <div class="max-h-[min(360px,42vh)] overflow-y-auto p-4">
        <ComponentPreviewPanel
          v-model:active-panel="activePanel"
          compact-body
          embedded
          :loading="loading"
          :error-message="errorMessage"
          :schema="schema"
          :state="state"
          :component-meta="componentMeta"
          @update:state="emitState"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, ChevronUp } from 'lucide-vue-next'

import ComponentPreviewPanel from '@/components/component-preview/ComponentPreviewPanel.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import {
  buildInitialComponentPreviewState,
  cloneComponentPreviewState,
  clonePreviewValue,
  type ComponentPreviewPreset,
  type ComponentPreviewSchema,
  type ComponentPreviewState,
} from '@/types/component-preview'

type ComponentPreviewPanelKey = 'props' | 'slots' | 'mocks'

const props = defineProps<{
  loading: boolean
  errorMessage?: string
  schema: ComponentPreviewSchema | null
  state: ComponentPreviewState
  componentMeta?: {
    code: string
    versionNo?: number
    displayName: string
    source?: 'workspace_component' | 'runtime_kit'
    runtimeKitComponentName?: string
    runtimeKitManifestVersion?: string
  } | null
  simplified?: boolean
}>()

const emit = defineEmits<{
  'update:state': [state: ComponentPreviewState]
}>()

const presetRadioName = `component-preview-preset-${Math.random().toString(36).slice(2)}`
const drawerOpen = ref(false)
const activePanel = ref<ComponentPreviewPanelKey>('props')

const propCount = computed(() => Object.keys(props.schema?.props || {}).length)
const slotCount = computed(() => Object.keys(props.schema?.slots || {}).length)
const mockCount = computed(() => Object.keys(props.schema?.mocks || {}).length)
const presetOptions = computed(() => props.schema?.presets || [])
const activePresetKey = computed(() => props.state.activePresetKey || '')
const panelTabs = computed(() => {
  const tabs: Array<{ key: ComponentPreviewPanelKey; label: string; count: number }> = []
  if (propCount.value) {
    tabs.push({ key: 'props', label: 'Props', count: propCount.value })
  }
  if (slotCount.value) {
    tabs.push({ key: 'slots', label: 'Slots', count: slotCount.value })
  }
  if (mockCount.value) {
    tabs.push({ key: 'mocks', label: 'Mocks', count: mockCount.value })
  }
  return tabs
})
const canOpenDrawer = computed(() => panelTabs.value.length > 0 && !props.loading)
const statusText = computed(() => {
  if (props.loading) {
    return '正在读取 previewSchema...'
  }
  if (props.errorMessage) {
    return `组件预览启动失败：${props.errorMessage}`
  }
  if (!props.schema) {
    return '当前组件未导出 previewSchema，只能查看静态预览。'
  }
  if (activePresetKey.value) {
    const activePreset = presetOptions.value.find(item => item.key === activePresetKey.value)
    return activePreset ? `当前预设：${activePreset.label}` : '当前预设已应用。'
  }
  if (!panelTabs.value.length) {
    return presetOptions.value.length
      ? '当前简化态只允许切换 preview preset。'
      : 'previewSchema 已导出，但暂无可编辑的 props、slots、mocks 或 presets。'
  }
  if (props.simplified) {
    return presetOptions.value.length ? '请选择一个 preview preset。' : '当前无可切换的 preview preset。'
  }
  return props.componentMeta ? `${props.componentMeta.displayName} · ${props.componentMeta.code}` : '当前为自定义参数。'
})

watch(
  () => [props.schema, props.loading],
  () => {
    drawerOpen.value = false
    activePanel.value = resolveFirstAvailablePanel()
  },
  { immediate: true },
)

/**
 * 选择字段分组 tab，并按交互规则强制展开抽屉。
 * @param panel 目标字段分组
 */
function selectPanelTab(panel: ComponentPreviewPanelKey): void {
  activePanel.value = panel
  drawerOpen.value = true
}

/**
 * 切换抽屉展开状态，收起状态下会确保当前分组仍然可用。
 */
function toggleDrawer(): void {
  if (!canOpenDrawer.value) {
    return
  }
  if (drawerOpen.value) {
    drawerOpen.value = false
    return
  }
  if (!panelTabs.value.some(item => item.key === activePanel.value)) {
    activePanel.value = resolveFirstAvailablePanel()
  }
  drawerOpen.value = true
}

/**
 * 应用一个 preset，只覆盖 preset 声明的字段，不改变抽屉状态和当前 tab。
 * @param preset 目标预设
 */
function selectPreset(preset: ComponentPreviewPreset): void {
  const nextState = cloneComponentPreviewState(props.state)
  if (preset.props) {
    nextState.props = {
      ...nextState.props,
      ...clonePreviewValue(preset.props),
    }
  }
  if (preset.slots) {
    nextState.slots = {
      ...nextState.slots,
      ...clonePreviewValue(preset.slots),
    }
  }
  if (preset.mocks) {
    nextState.mocks = {
      ...nextState.mocks,
      ...clonePreviewValue(preset.mocks),
    }
  }
  nextState.activePresetKey = preset.key
  emit('update:state', nextState)
}

/**
 * 切换回自定义参数状态，仅清空 preset 标记，不回滚字段值。
 */
function selectCustomPreset(): void {
  const nextState = cloneComponentPreviewState(props.state)
  nextState.activePresetKey = null
  emit('update:state', nextState)
}

/**
 * 将参数恢复到 schema 默认值。
 */
function resetState(): void {
  emit('update:state', buildInitialComponentPreviewState(props.schema))
}

/**
 * 转发字段编辑器产生的状态变更。
 * @param nextState 字段编辑器回传的完整状态
 */
function emitState(nextState: ComponentPreviewState): void {
  emit('update:state', nextState)
}

/**
 * 按固定优先级解析第一个可用字段分组。
 * @returns 可用字段分组
 */
function resolveFirstAvailablePanel(): ComponentPreviewPanelKey {
  return panelTabs.value[0]?.key || 'props'
}

/**
 * 计算 preset radio pill 样式。
 * @param active 当前 radio 是否选中
 * @returns Tailwind 样式类名
 */
function resolvePresetRadioClass(active: boolean): string {
  return active
    ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
    : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900'
}
</script>
