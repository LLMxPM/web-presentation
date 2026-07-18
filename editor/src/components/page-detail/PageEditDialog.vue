<!-- 文件功能：统一承载页面源码编辑与可视化编辑，并转发保存、切换和安全关闭请求。 -->
<template>
  <BaseDialog
    :model-value="props.modelValue"
    size="workbench"
    body-preset="immersive"
    :show-header="false"
    :show-close-button="false"
    panel-class="bg-white shadow-xl"
    @update:model-value="handleVisibleChange"
  >
    <div class="flex h-full min-h-0 flex-col bg-slate-100">
      <header class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3">
        <div class="flex min-w-0 flex-wrap items-center gap-3">
          <div class="min-w-0 max-w-[24rem]">
            <h2 class="truncate text-sm font-bold text-slate-900" :title="dialogTitle">{{ dialogTitle }}</h2>
          </div>

          <div class="flex shrink-0 items-center rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            
            <button
              v-if="props.visualEnabled"
              type="button"
              class="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-semibold transition"
              :class="props.mode === 'visual' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
              :disabled="props.busy"
              @click="requestModeChange('visual')"
            >
              <SlidersHorizontal class="h-4 w-4" />
              可视化编辑
            </button>
            <button
              type="button"
              class="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-semibold transition"
              :class="props.mode === 'source' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
              :disabled="props.busy"
              @click="requestModeChange('source')"
            >
              <Code2 class="h-4 w-4" />
              源码编辑
            </button>
          </div>

          <template v-if="props.mode === 'visual'">
            <span
              v-if="visualState.pendingCount"
              class="rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-bold text-indigo-700"
            >
              {{ visualState.pendingCount }} 项待保存
            </span>
            <span v-if="visualState.stale" class="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold text-amber-800">
              已过期
            </span>
          </template>
        </div>

        <div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <template v-if="props.mode === 'source'">
            <BaseButton variant="ghost" size="sm" @click="emit('copy-code')">
              <Copy class="h-3.5 w-3.5" />
              复制代码
            </BaseButton>
            <div class="flex items-center rounded-lg bg-slate-100 p-0.5">
              <button
                type="button"
                title="明亮模式"
                class="flex h-7 w-7 items-center justify-center rounded-md transition"
                :class="props.editorTheme === 'light' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-400 hover:text-slate-700'"
                @click="emit('update:editorTheme', 'light')"
              >
                <Sun class="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                title="暗黑模式"
                class="flex h-7 w-7 items-center justify-center rounded-md transition"
                :class="props.editorTheme === 'dark' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-400 hover:text-slate-700'"
                @click="emit('update:editorTheme', 'dark')"
              >
                <Moon class="h-3.5 w-3.5" />
              </button>
            </div>
            <label class="flex items-center gap-1.5 text-xs font-semibold text-slate-500">
              自动保存
              <select
                aria-label="自动保存"
                class="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs font-semibold text-slate-700 outline-none focus:border-indigo-300"
                :value="props.autoSaveDelay"
                @change="handleAutoSaveChange"
              >
                <option v-for="option in props.autoSaveOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <BaseButton
              variant="primary"
              size="sm"
              :disabled="props.busy"
              :loading="props.busy"
              @click="requestSourceSave"
            >
              <Save class="h-3.5 w-3.5" />
              保存
            </BaseButton>
          </template>

          <template v-else>
            <BaseButton
              variant="ghost"
              size="sm"
              :disabled="props.busy || !visualState.hasPendingChanges"
              @click="visualEditPanelRef?.discardChanges()"
            >
              <Undo2 class="h-3.5 w-3.5" />
              放弃修改
            </BaseButton>
            <BaseButton variant="ghost" size="sm" :disabled="props.busy" @click="visualEditPanelRef?.reanalyze()">
              <RefreshCw class="h-3.5 w-3.5" />
              重新分析
            </BaseButton>
            <BaseButton
              variant="primary"
              size="sm"
              :loading="visualState.saving"
              :disabled="props.busy || !visualState.hasPendingChanges || visualState.stale"
              @click="visualEditPanelRef?.saveChanges()"
            >
              <Save class="h-3.5 w-3.5" />
              保存并刷新
            </BaseButton>
          </template>

          <div class="mx-0.5 h-5 w-px bg-slate-200"></div>
          <BaseButton variant="ghost" size="sm" @click="emit('open-history')">
            <History class="h-3.5 w-3.5" />
            版本
          </BaseButton>
          <BaseButton variant="ghost" size="sm" @click="emit('open-usage')">
            <Layers class="h-3.5 w-3.5" />
            资源
          </BaseButton>
          <BaseCloseButton label="关闭页面编辑" @click="emit('request-close')" />
        </div>
      </header>

      <div class="min-h-0 flex-1 overflow-hidden p-3">
        <PageDetailWorkbenchPanel
          v-if="props.mode === 'source'"
          :model-value="props.sourceValue"
          :editor-theme="props.editorTheme"
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
          :show-header="false"
          @dirty-change="emit('visual-dirty-change', $event)"
          @busy-change="emit('visual-busy-change', $event)"
          @state-change="visualState = $event"
          @saved="emit('visual-saved', $event)"
        />
      </div>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Code2, Copy, History, Layers, Moon, RefreshCw, Save, SlidersHorizontal, Sun, Undo2 } from '@lucide/vue'

import PageDetailWorkbenchPanel from '@/components/page-detail/PageDetailWorkbenchPanel.vue'
import PageVisualEditPanel from '@/components/page-detail/visual-edit/PageVisualEditPanel.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { EditorLanguage, EditorSaveReason, EditorThemeMode, MonacoEditorReadyPayload } from '@/types/monaco'
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

const props = defineProps<{
  modelValue: boolean
  mode: PageEditMode
  visualEnabled: boolean
  busy: boolean
  pageId: number
  baseVersionNo: number
  pageTitle: string
  sourceValue: string
  editorLanguage: EditorLanguage
  editorTheme: EditorThemeMode
  autoSaveDelay: number
  autoSaveOptions: AutoSaveOption[]
}>()

const emit = defineEmits<{
  'update:sourceValue': [value: string]
  'update:editorTheme': [value: EditorThemeMode]
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
})

/** 将 BaseDialog 的任意关闭入口转为父层可拦截的安全关闭请求。 */
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

/** 将原生选择框值转换为毫秒数后同步给页面详情。 */
function handleAutoSaveChange(event: Event): void {
  emit('update:autoSaveDelay', Number((event.target as HTMLSelectElement).value))
}

defineExpose({
  discardChanges: () => visualEditPanelRef.value?.discardChanges(),
  reanalyze: async () => await visualEditPanelRef.value?.reanalyze(),
  markStale: () => visualEditPanelRef.value?.markStale(),
  saveChanges: async () => await visualEditPanelRef.value?.saveChanges(),
})
</script>
