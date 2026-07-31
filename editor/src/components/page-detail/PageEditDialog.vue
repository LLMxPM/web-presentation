<!-- 文件功能：统一承载页面源码编辑与可视化编辑，并转发保存、切换和安全关闭请求。 -->
<template>
  <UiDialog
    :open="props.modelValue"
    size="workbench"
    body-preset="immersive"
    :show-header="false"
    :show-close-button="false"
    panel-class="bg-surface shadow-xl"
    @update:open="handleVisibleChange"
  >
    <div class="flex h-full min-h-0 flex-col bg-[rgb(var(--ui-canvas))]">
      <CommandBar class="shrink-0 rounded-none border-x-0 border-t-0 px-4 py-3" label="页面编辑操作">
        <template #leading>
        <div class="flex min-w-0 items-center gap-3">
          <div class="min-w-0 max-w-[24rem]">
            <h2 class="truncate text-sm font-bold text-text-strong" :title="dialogTitle">{{ dialogTitle }}</h2>
          </div>

          <div class="flex shrink-0 items-center rounded-lg border border-border bg-canvas p-0.5">
            
            <UiButton
              v-if="props.visualEnabled"
              variant="ghost"
              size="sm"
              :class="props.mode === 'visual' ? 'bg-[rgb(var(--ui-surface))] text-[rgb(var(--ui-accent))] shadow-sm' : ''"
              :disabled="props.busy"
              @click="requestModeChange('visual')"
            >
              <SlidersHorizontal class="h-4 w-4" />
              可视化编辑
            </UiButton>
            <UiButton
              variant="ghost"
              size="sm"
              :class="props.mode === 'source' ? 'bg-[rgb(var(--ui-surface))] text-[rgb(var(--ui-accent))] shadow-sm' : ''"
              :disabled="props.busy"
              @click="requestModeChange('source')"
            >
              <Code2 class="h-4 w-4" />
              源码编辑
            </UiButton>
          </div>

          <template v-if="props.mode === 'visual'">
            <span
              v-if="visualState.pendingCount"
              class="rounded-full bg-accent-muted px-2 py-0.5 text-[11px] font-bold text-accent-hover"
            >
              {{ visualState.pendingCount }} 项待保存
            </span>
            <span v-if="visualState.stale" class="rounded-full bg-warning-muted px-2 py-0.5 text-[11px] font-bold text-warning-strong">
              已过期
            </span>
          </template>
        </div>
        </template>

        <template #actions>
        <div class="flex shrink-0 items-center justify-end gap-2">
          <template v-if="props.mode === 'source'">
            <UiButton variant="ghost" size="sm" @click="emit('copy-code')">
              <Copy class="h-3.5 w-3.5" />
              复制代码
            </UiButton>
            <label class="flex items-center gap-1.5 text-xs font-semibold text-text-muted">
              自动保存
              <UiSelect
                aria-label="自动保存"
                :model-value="props.autoSaveDelay"
                :options="props.autoSaveOptions"
                trigger-class="w-28 text-xs font-semibold"
                @update:model-value="handleAutoSaveChange"
              />
            </label>
            <UiButton
              variant="primary"
              size="sm"
              :disabled="props.busy"
              :loading="props.busy"
              @click="requestSourceSave"
            >
              <Save class="h-3.5 w-3.5" />
              保存
            </UiButton>
          </template>

          <template v-else>
            <UiButton
              variant="ghost"
              size="sm"
              :disabled="props.busy || !visualState.hasPendingChanges"
              @click="visualEditPanelRef?.discardChanges()"
            >
              <Undo2 class="h-3.5 w-3.5" />
              撤销全部修改
            </UiButton>
            <UiButton variant="ghost" size="sm" :disabled="props.busy" @click="visualEditPanelRef?.reanalyze()">
              <RefreshCw class="h-3.5 w-3.5" />
              重新载入页面
            </UiButton>
            <span class="text-xs text-[rgb(var(--ui-text-muted))]">保存后刷新画布</span>
            <UiButton
              variant="primary"
              size="sm"
              :loading="visualState.saving"
              :disabled="props.busy || !visualState.hasPendingChanges || visualState.stale || visualState.hasValidationErrors"
              @click="visualEditPanelRef?.saveChanges()"
            >
              <Save class="h-3.5 w-3.5" />
              保存
            </UiButton>
          </template>

          <div class="mx-0.5 h-5 w-px bg-border"></div>
          <UiButton variant="ghost" size="sm" @click="emit('open-history')">
            <History class="h-3.5 w-3.5" />
            版本
          </UiButton>
          <UiButton variant="ghost" size="sm" @click="emit('open-usage')">
            <Layers class="h-3.5 w-3.5" />
            资源
          </UiButton>
          <UiIconButton label="关闭页面编辑" @click="emit('request-close')"><X class="h-4 w-4" /></UiIconButton>
        </div>
        </template>
      </CommandBar>

      <div class="min-h-0 flex-1 overflow-hidden p-3">
        <PageDetailWorkbenchPanel
          v-if="props.mode === 'source'"
          :model-value="props.sourceValue"
          :auto-save-delay="props.autoSaveDelay"
          :editor-language="props.editorLanguage"
          editor-height="100%"
          @update:model-value="emit('update:sourceValue', $event)"
          @save="emit('source-save', $event)"
          @ready="emit('source-ready', $event)"
          @dirty-change="emit('source-dirty-change', $event)"
        />

        <PageVisualEditPanel
          v-else
          ref="visualEditPanelRef"
          :key="props.pageId"
          :page-id="props.pageId"
          :base-version-no="props.baseVersionNo"
          :page-title="props.pageTitle"
          :workspace-id="props.workspaceId"
          :show-header="false"
          @dirty-change="emit('visual-dirty-change', $event)"
          @busy-change="emit('visual-busy-change', $event)"
          @state-change="visualState = $event"
          @saved="emit('visual-saved', $event)"
        />
      </div>
    </div>
  </UiDialog>

</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Code2, Copy, History, Layers, RefreshCw, Save, SlidersHorizontal, Undo2, X } from '@lucide/vue'

import PageDetailWorkbenchPanel from '@/components/page-detail/PageDetailWorkbenchPanel.vue'
import PageVisualEditPanel from '@/components/page-detail/visual-edit/PageVisualEditPanel.vue'
import CommandBar from '@/components/patterns/CommandBar.vue'
import { UiButton, UiDialog, UiIconButton, UiSelect } from '@/components/ui'
import type { EditorLanguage, EditorSaveReason, MonacoEditorReadyPayload } from '@/types/monaco'
import type { PageEditMode } from '@/types/page-edit'
import type { PageVisualEditApplyResponse, PageVisualEditPanelState } from '@/types/page-visual-edit'

interface AutoSaveOption {
  label: string
  value: number
}

interface PageVisualEditPanelExpose {
  discardChanges: () => void
  reanalyze: () => Promise<void>
  markStale: () => void
  saveChanges: () => Promise<void>
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  mode: PageEditMode
  visualEnabled: boolean
  busy: boolean
  pageId: number
  baseVersionNo: number
  pageTitle: string
  sourceValue: string
  editorLanguage: EditorLanguage
  autoSaveDelay: number
  autoSaveOptions: AutoSaveOption[]
  workspaceId?: number | null
}>(), {
  workspaceId: null,
})

const emit = defineEmits<{
  'update:sourceValue': [value: string]
  'update:autoSaveDelay': [value: number]
  'request-mode-change': [mode: PageEditMode]
  'request-close': []
  'open-history': []
  'open-usage': []
  'source-save': [payload: { reason: EditorSaveReason; value: string }]
  'source-ready': [payload: MonacoEditorReadyPayload]
  'source-dirty-change': [dirty: boolean]
  'copy-code': []
  'visual-dirty-change': [dirty: boolean]
  'visual-busy-change': [busy: boolean]
  'visual-saved': [response: PageVisualEditApplyResponse]
}>()

const visualEditPanelRef = ref<PageVisualEditPanelExpose | null>(null)
const dialogTitle = computed(() => `编辑页面 · ${props.pageTitle}`)
const visualState = ref<PageVisualEditPanelState>({
  pendingCount: 0,
  hasPendingChanges: false,
  stale: false,
  saving: false,
  hasValidationErrors: false,
})

/** 将 UiDialog 的任意关闭入口转为父层可拦截的安全关闭请求。 */
function handleVisibleChange(visible: boolean): void {
  if (!visible) emit('request-close')
}

/** 请求切换编辑方式，实际保存和草稿确认由页面详情统一编排。 */
function requestModeChange(mode: PageEditMode): void {
  if (mode !== props.mode) emit('request-mode-change', mode)
}

/** 将弹窗工具栏的手动保存统一为 Monaco 保存事件结构。 */
function requestSourceSave(): void {
  emit('source-save', { reason: 'manual', value: props.sourceValue })
}

/** 将选择器值转换为毫秒数后同步给页面详情。 */
function handleAutoSaveChange(value: string | number | boolean | (string | number | boolean)[] | null): void {
  if (value === null || Array.isArray(value)) return
  emit('update:autoSaveDelay', Number(value))
}

defineExpose({
  discardChanges: () => visualEditPanelRef.value?.discardChanges(),
  reanalyze: async () => await visualEditPanelRef.value?.reanalyze(),
  markStale: () => visualEditPanelRef.value?.markStale(),
  saveChanges: async () => await visualEditPanelRef.value?.saveChanges(),
})
</script>
