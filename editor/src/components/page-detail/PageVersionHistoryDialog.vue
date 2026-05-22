<!-- 文件功能：承载页面版本历史弹窗，负责展示版本列表、源码差异和历史 Runtime 预览。 -->
<template>
  <BaseDialog :model-value="props.modelValue" title="版本历史" width="1320px"
    @update:model-value="emit('update:modelValue', $event)">
    <div class="-mx-6 -my-5 h-[72vh] max-h-[72vh] overflow-hidden">
      <div v-if="props.loading && !props.versions.length" class="px-6 py-10 text-sm text-slate-400">
        版本历史加载中...
      </div>

      <div v-else-if="props.versions.length"
        class="grid h-full gap-0 overflow-hidden lg:grid-cols-[minmax(0,0.95fr)_minmax(420px,1.25fr)]">
        <div class="h-full overflow-y-auto divide-y divide-slate-100 border-r border-slate-100">
          <article v-for="version in props.versions" :key="version.id" class="px-6 py-4">
            <div class="flex items-start justify-between gap-4 flex-wrap">
              <div class="min-w-0 space-y-2">
                <div class="flex items-center gap-2 flex-wrap">
                  <span v-if="version.is_current"
                    class="px-2 py-0.5 text-[11px] font-semibold rounded-full border border-emerald-200 bg-emerald-50 text-emerald-600">
                    当前
                  </span>
                  <span v-if="version.is_important"
                    class="px-2 py-0.5 text-[11px] font-semibold rounded-full border border-amber-200 bg-amber-50 text-amber-600">
                    快照
                  </span>
                  <span class="text-sm font-semibold text-slate-900">{{ version.version_label }}</span>
                  <span class="text-xs text-slate-400">{{ formatDateTime(version.created_at) }}</span>
                </div>
                <p v-if="version.snapshot_name || version.change_note" class="text-sm text-slate-500 break-all">
                  {{ version.snapshot_name || version.change_note }}
                  <template v-if="version.snapshot_name && version.change_note">
                    · {{ version.change_note }}
                  </template>
                </p>
              </div>

              <div class="flex items-center gap-1 flex-wrap justify-end">
                <BaseButton variant="ghost" size="sm"
                  :loading="props.previewingRuntimeVersionNo === version.version_no"
                  @click="emit('preview-version', version.version_no)">
                  {{ props.historyPanel?.mode === 'preview' && props.historyPanel.versionNo === version.version_no ? '收起' : '预览' }}
                </BaseButton>
                <BaseButton variant="ghost" size="sm"
                  :loading="props.previewVersionPending && props.previewVersionNo === version.version_no"
                  @click="emit('diff-version', version.version_no)">
                  {{ props.historyPanel?.mode === 'diff' && props.historyPanel.versionNo === version.version_no ? '收起' : '差异' }}
                </BaseButton>
                <BaseButton v-if="!version.is_important" variant="ghost" size="sm"
                  :loading="props.snapshotPending && props.pendingSnapshotVersionNo === version.version_no"
                  @click="emit('open-snapshot', version.version_no)">
                  快照
                </BaseButton>
                <BaseButton v-if="!version.is_current" variant="ghost" size="sm"
                  :loading="props.restorePending && props.restoringVersionNo === version.version_no"
                  @click="emit('restore-version', version.version_no)">
                  <RotateCcw class="w-3.5 h-3.5" />
                  恢复
                </BaseButton>
              </div>
            </div>
          </article>
        </div>

        <section class="flex h-full min-h-0 flex-col overflow-hidden bg-slate-50/60">
          <div class="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-4">
            <div class="space-y-1">
              <h3 class="flex items-center gap-2">
                <span class="text-base font-semibold text-slate-900">{{ props.panelTitle }}</span>
                <span class="text-sm text-slate-500">{{ props.panelSubtitle }}</span>
              </h3>
            </div>
          </div>

          <div class="flex-1 min-h-0 overflow-hidden p-2">
            <div v-if="!props.historyPanel"
              class="flex h-full items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white/80 px-8 text-center text-sm text-slate-500">
              在左侧选择一个版本查看差异或预览
            </div>

            <div v-else-if="shouldShowDiff" class="h-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <MonacoDiffViewer
                :original-value="activeVersionContent?.resolved_content ?? ''"
                :modified-value="props.currentContent"
                :language="props.editorLanguage"
                :theme="props.editorTheme"
                height="100%"
              />
            </div>

            <div v-else-if="props.historyPanel?.mode === 'preview'"
              class="h-full overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-sm">
              <RuntimePreviewFrame
                :frame-url="props.historyPanelPreviewFrameUrl"
                :title="`runtime-preview-version-${activeVersionNo ?? 0}`"
                layout="fill"
                container-class="h-full overflow-hidden rounded-2xl border-0 bg-slate-50 shadow-none"
                empty-title="版本预览准备中"
                empty-description="正在生成所选版本的 Runtime 预览，请稍候。"
              />
            </div>
          </div>
        </section>
      </div>

      <div v-else class="px-6 py-10 text-sm text-slate-400">
        当前页面还没有可展示的版本历史。
      </div>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RotateCcw } from 'lucide-vue-next'

import MonacoDiffViewer from '@/components/editor/MonacoDiffViewer.vue'
import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { EditorLanguage, EditorThemeMode } from '@/types/monaco'
import type { PageVersionContent, PageVersionListItem } from '@/types/api'
import { formatDateTime } from '@/utils/format'

type HistoryPanel = { mode: 'diff' | 'preview'; versionNo: number } | null

interface Props {
  modelValue: boolean
  loading: boolean
  versions: PageVersionListItem[]
  historyPanel: HistoryPanel
  panelTitle: string
  panelSubtitle: string
  currentContent: string
  versionContentMap: Record<number, PageVersionContent>
  historyPanelPreviewFrameUrl: string
  editorLanguage: EditorLanguage
  editorTheme: EditorThemeMode
  previewingRuntimeVersionNo: number | null
  previewVersionPending: boolean
  previewVersionNo: number | null
  snapshotPending: boolean
  pendingSnapshotVersionNo: number | null
  restorePending: boolean
  restoringVersionNo: number | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'preview-version': [versionNo: number]
  'diff-version': [versionNo: number]
  'open-snapshot': [versionNo: number]
  'restore-version': [versionNo: number]
}>()

const activeVersionNo = computed(() => props.historyPanel?.versionNo ?? null)
const activeVersionContent = computed(() => (
  activeVersionNo.value ? props.versionContentMap[activeVersionNo.value] ?? null : null
))
const shouldShowDiff = computed(() => (
  props.historyPanel?.mode === 'diff' && Boolean(activeVersionContent.value)
))
</script>
