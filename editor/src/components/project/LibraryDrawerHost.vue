<!-- 文件功能：提供弹窗层素材/组件侧栏抽屉宿主，承载抽屉渲染、右下触发胶囊与全局快捷键入口。 -->
<template>
  <UiDialog
    :open="isOpen"
    title="素材 / 组件"
    size="standard"
    body-preset="immersive"
    :show-header="false"
    :show-close-button="false"
    :z-index="'var(--ui-z-drawer)'"
    bare-overlay
    :panel-style="drawerPanelStyle"
    @update:open="handleOpenChange"
  >
    <div class="flex h-full min-h-0 w-full flex-col overflow-hidden bg-surface">
      <div class="flex shrink-0 items-center justify-between gap-2 border-b border-border-muted px-4 py-2.5">
        <div class="flex min-w-0 items-center gap-2">
          <Library class="h-5 w-5 text-accent" />
          <h2 class="truncate text-base font-bold text-text">素材 / 组件</h2>
        </div>
        <UiIconButton type="button" label="关闭侧栏" @click="closeLibraryDrawer()">
          <X class="h-4 w-4" />
        </UiIconButton>
      </div>
      <div class="shrink-0 border-b border-canvas bg-canvas/50 px-3 py-2">
        <LibrarySegmentedControl
          :model-value="resolvedPanel"
          :options="panelOptions"
          :columns="2"
          @update:model-value="handlePanelChange"
        />
      </div>
      <div class="min-h-0 flex-1 overflow-hidden">
        <AssetManagerPanel
          v-if="activePanel === 'assets'"
          v-model="assetPanelVisible"
          :workspace-id="workspaceId"
          :layer-index="previewLayerIndex"
          hide-navigation
          hide-panel-header
        />
        <ComponentManagerPanel
          v-else-if="activePanel === 'components'"
          v-model="componentPanelVisible"
          read-only
          :workspace-id="workspaceId"
          :layer-index="previewLayerIndex"
          hide-navigation
          hide-panel-header
        />
      </div>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, type CSSProperties, watch } from 'vue'
import { Library, X } from '@lucide/vue'

import { useLibraryDrawerState } from '@/composables/library-drawer-state'
import AssetManagerPanel from '@/components/project/AssetManagerPanel.vue'
import ComponentManagerPanel from '@/components/project/ComponentManagerPanel.vue'
import LibrarySegmentedControl, { type LibrarySegmentedOption } from '@/components/project/LibrarySegmentedControl.vue'
import { UiDialog, UiIconButton } from '@/components/ui'

const props = defineProps<{
  workspaceId: number | null
}>()

const { activePanel, openLibraryDrawer, closeLibraryDrawer } = useLibraryDrawerState()

/** 抽屉宿主层级；抽屉内嵌预览弹窗需高于此值。 */
const previewLayerIndex = 1300
const panelOptions: LibrarySegmentedOption[] = [
  { label: '素材', value: 'assets' },
  { label: '组件', value: 'components' },
]

/** 右侧全高抽屉定位，覆盖 UiDialog 的居中布局。 */
const drawerPanelStyle: CSSProperties = {
  left: 'auto',
  right: '0',
  top: '0',
  bottom: '0',
  width: 'min(400px, 100dvw)',
  height: '100dvh',
  maxHeight: '100dvh',
  transform: 'none',
  borderRadius: '0',
}

const isOpen = computed(() => activePanel.value !== null)
const resolvedPanel = computed(() => activePanel.value ?? 'assets')

const assetPanelVisible = computed({
  get: () => activePanel.value === 'assets',
  set: (value: boolean) => {
    if (!value && activePanel.value === 'assets') {
      closeLibraryDrawer()
    }
  },
})
const componentPanelVisible = computed({
  get: () => activePanel.value === 'components',
  set: (value: boolean) => {
    if (!value && activePanel.value === 'components') {
      closeLibraryDrawer()
    }
  },
})

/**
 * 离开工作空间时关闭模块级抽屉状态，避免常驻布局在无工作空间路由上残留弹层。
 */
watch(
  () => props.workspaceId,
  (workspaceId) => {
    if (workspaceId === null) {
      closeLibraryDrawer()
    }
  },
  { immediate: true },
)

/**
 * 处理抽屉内的素材/组件页签切换。
 * @param value 分段控件返回的页签值
 */
function handlePanelChange(value: string): void {
  if (value === 'assets' || value === 'components') {
    openLibraryDrawer(value)
  }
}

/**
 * 同步 UiDialog 受控开关，关闭时清空全局抽屉状态。
 * @param open 目标打开状态
 */
function handleOpenChange(open: boolean): void {
  if (!open) {
    closeLibraryDrawer()
  }
}

/**
 * 全局快捷键开合抽屉。在工作空间上下文内始终吞掉该组合键，避免触发浏览器默认行为。
 * @param event 键盘事件
 */
function handleGlobalKeydown(event: KeyboardEvent): void {
  if (!(event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'k')) {
    return
  }
  if (props.workspaceId === null) {
    return
  }
  event.preventDefault()
  if (activePanel.value === null) {
    openLibraryDrawer('assets')
    return
  }
  closeLibraryDrawer()
}

onMounted(() => {
  window.addEventListener('keydown', handleGlobalKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  closeLibraryDrawer()
})
</script>
