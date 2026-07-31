<!-- 文件功能：提供组件预览参数薄栏、Preset radio 切换与顶部浮层抽屉。 -->
<template>
  <section ref="dockRootRef" class="relative border-t border-border-muted bg-canvas/70">
    <div class="flex h-10 items-center gap-2.5 overflow-hidden px-3">
      <span class="shrink-0 text-xs font-bold text-text-emphasis">预览参数</span>

      <div
        v-if="presetOptions.length"
        class="component-preview-scrollbar-hidden overflow-x-auto whitespace-nowrap"
        :class="simplified ? 'min-w-0 flex-1 basis-[220px]' : 'min-w-[280px] flex-[1_1_560px]'"
      >
        <UiRadioGroup
          :model-value="activePresetSelection"
          :options="presetRadioOptions"
          orientation="horizontal"
          aria-label="预览参数预设"
          @update:model-value="handlePresetSelection"
        />
      </div>

      <div v-if="!simplified && panelTabs.length" class="flex shrink-0 items-center gap-1.5">
        <UiButton
          v-for="tab in panelTabs"
          :key="tab.key"
          type="button"
          variant="ghost"
          size="xs"
          class="rounded-full border px-2 py-0.5 text-[11px] font-semibold transition-colors"
          :class="activePanel === tab.key
            ? 'border-accent-border bg-surface-selected text-accent-hover'
            : 'border-border bg-surface text-text-secondary hover:border-border-strong hover:text-text-strong'"
          @click="selectPanelTab(tab.key)"
        >
          {{ tab.label }}
          <span class="ml-0.5 text-[10px] text-text-disabled">{{ tab.count }}</span>
        </UiButton>
      </div>

      <p
        v-if="statusText"
        class="min-w-0 truncate text-xs"
        :class="[
          simplified ? 'shrink-0' : 'flex-[0_1_220px]',
          errorMessage ? 'font-semibold text-danger' : 'text-text-disabled',
        ]"
      >
        {{ statusText }}
      </p>

      <UiButton
        v-if="schema && !simplified"
        variant="ghost"
        size="sm"
        custom-class="!h-8 !px-2 !text-xs"
        @click="resetState"
      >
        重置
      </UiButton>

      <UiIconButton
        v-if="!simplified"
        label="展开预览参数"
        size="sm"
        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-text-disabled transition-colors hover:bg-surface hover:text-text-emphasis disabled:cursor-not-allowed disabled:text-text-faint disabled:hover:bg-transparent"
        :disabled="!canOpenDrawer"
        :aria-expanded="drawerOpen"
        title="展开预览参数"
        @click="toggleDrawer"
      >
        <component :is="drawerOpen ? ChevronUp : ChevronDown" class="h-4 w-4" />
      </UiIconButton>
    </div>

    <div
      v-if="drawerOpen && canOpenDrawer"
      class="absolute left-0 right-0 top-full z-20 border-t border-border bg-surface shadow-xl shadow-slate-900/10"
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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ChevronDown, ChevronUp } from '@lucide/vue'

import ComponentPreviewPanel from '@/components/component-preview/ComponentPreviewPanel.vue'
import UiButton from '@/components/ui/button/UiButton.vue'
import UiIconButton from '@/components/ui/button/UiIconButton.vue'
import UiRadioGroup from '@/components/ui/radio/UiRadioGroup.vue'
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

const CUSTOM_PRESET_VALUE = '__custom__'
const dockRootRef = ref<HTMLElement | null>(null)
const drawerOpen = ref(false)
const activePanel = ref<ComponentPreviewPanelKey>('props')

const propCount = computed(() => Object.keys(props.schema?.props || {}).length)
const slotCount = computed(() => Object.keys(props.schema?.slots || {}).length)
const mockCount = computed(() => Object.keys(props.schema?.mocks || {}).length)
const presetOptions = computed(() => props.schema?.presets || [])
const activePresetKey = computed(() => props.state.activePresetKey || '')
const activePresetSelection = computed(() => activePresetKey.value || CUSTOM_PRESET_VALUE)
const presetRadioOptions = computed(() => [
  ...(!props.simplified ? [{ label: '自定义', value: CUSTOM_PRESET_VALUE }] : []),
  ...presetOptions.value.map(preset => ({ label: preset.label, value: preset.key })),
])
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
    return ''
  }
  if (!panelTabs.value.length) {
    return presetOptions.value.length
      ? '当前简化态只允许切换 preview preset。'
      : 'previewSchema 已导出，但暂无可编辑的 props、slots、mocks 或 presets。'
  }
  if (props.simplified) {
    return presetOptions.value.length ? '请选择一个 preview preset' : '当前无可切换的 preview preset'
  }
  return ''
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
 * 选择字段分组 tab；重复点击当前 tab 时收起抽屉，便于快速关闭。
 * @param panel 目标字段分组
 */
function selectPanelTab(panel: ComponentPreviewPanelKey): void {
  if (drawerOpen.value && activePanel.value === panel) {
    drawerOpen.value = false
    return
  }
  activePanel.value = panel
  drawerOpen.value = true
}

/**
 * 点击参数 Dock 之外的区域时关闭抽屉，避免浮层长期遮挡预览画布。
 * @param event 指针事件
 */
function handleDocumentPointerDown(event: PointerEvent): void {
  if (!drawerOpen.value) {
    return
  }
  const rootElement = dockRootRef.value
  if (!rootElement || !(event.target instanceof Node)) {
    return
  }
  if (!rootElement.contains(event.target)) {
    drawerOpen.value = false
  }
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
 * 根据单选组值应用预设或切回自定义状态。
 * @param value 单选组回传的预设 key 或自定义标识
 */
function handlePresetSelection(value: string): void {
  if (value === CUSTOM_PRESET_VALUE) {
    selectCustomPreset()
    return
  }
  const preset = presetOptions.value.find(item => item.key === value)
  if (preset) {
    selectPreset(preset)
  }
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

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
})
</script>

<style scoped>
.component-preview-scrollbar-hidden {
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.component-preview-scrollbar-hidden::-webkit-scrollbar {
  display: none;
}
</style>
