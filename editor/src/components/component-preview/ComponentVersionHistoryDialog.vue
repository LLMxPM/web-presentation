<!-- 文件功能：承载组件发布历史弹窗，展示发布版本列表、与当前草稿的源码差异和历史版本预览。 -->
<template>
  <UiDialog
    :open="modelValue"
    title="发布历史"
    size="canvas"
    body-preset="split"
    @update:open="emit('update:modelValue', $event)"
  >
    <div class="h-full overflow-hidden">
      <div v-if="loading && !versions.length" class="px-6 py-10 text-sm text-text-disabled">
        发布历史加载中...
      </div>

      <div
        v-else-if="versions.length"
        class="grid h-full min-h-0 grid-rows-[minmax(220px,0.9fr)_minmax(0,1.1fr)] overflow-hidden xl:grid-cols-[minmax(0,0.9fr)_minmax(420px,1.2fr)] xl:grid-rows-1"
      >
        <div class="h-full overflow-y-auto divide-y divide-border-muted border-r border-border-muted">
          <article v-for="version in versions" :key="version.id" class="px-6 py-4">
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0 space-y-2">
                <div class="flex flex-wrap items-center gap-2">
                  <span
                    v-if="version.is_current"
                    class="rounded-full border border-success-border bg-success-muted px-2 py-0.5 text-[11px] font-semibold text-success"
                  >
                    当前发布
                  </span>
                  <span class="text-sm font-semibold text-text-strong">v{{ version.version_no }}</span>
                  <span class="text-xs text-text-disabled">{{ version.version_label }}</span>
                  <span class="text-xs text-text-disabled">{{ formatDateTime(version.created_at) }}</span>
                </div>
                <p v-if="version.release_name || version.change_note" class="break-all text-sm text-text-muted">
                  {{ version.release_name || version.change_note }}
                  <template v-if="version.release_name && version.change_note">
                    · {{ version.change_note }}
                  </template>
                </p>
              </div>

              <div class="flex shrink-0 flex-wrap justify-end gap-1">
                <UiButton
                  variant="ghost"
                  size="sm"
                  :loading="previewingVersionNo === version.version_no"
                  @click="emit('preview-version', version.version_no)"
                >
                  {{ panel?.mode === 'preview' && panel.versionNo === version.version_no ? '收起' : '预览' }}
                </UiButton>
                <UiButton
                  variant="ghost"
                  size="sm"
                  :loading="loadingContentVersionNo === version.version_no"
                  @click="emit('diff-version', version.version_no)"
                >
                  {{ panel?.mode === 'diff' && panel.versionNo === version.version_no ? '收起' : '差异' }}
                </UiButton>
                <UiButton
                  variant="ghost"
                  size="sm"
                  :loading="restoringVersionNo === version.version_no"
                  @click="emit('restore-version', version.version_no)"
                >
                  恢复到草稿
                </UiButton>
              </div>
            </div>
          </article>
        </div>

        <section class="flex h-full min-h-0 flex-col overflow-hidden bg-canvas/60">
          <div class="border-b border-border-muted px-6 py-4">
            <h3 class="text-base font-semibold text-text-strong">{{ panelTitle }}</h3>
            <p class="mt-1 text-sm text-text-muted">{{ panelSubtitle }}</p>
          </div>

          <div class="min-h-0 flex-1 overflow-hidden p-2">
            <div
              v-if="!panel"
              class="flex h-full items-center justify-center rounded-xl border border-dashed border-border bg-surface/80 px-8 text-center text-sm text-text-muted"
            >
              在左侧选择一个发布版本查看差异或预览
            </div>

            <div v-else-if="panel.mode === 'diff' && activeVersionContent" class="h-full overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
              <MonacoDiffViewer
                :original-value="activeVersionContent.content"
                :modified-value="draftContent"
                language="vue"
                height="100%"
              />
            </div>

            <div v-else-if="panel.mode === 'preview'" class="h-full overflow-hidden rounded-2xl border border-border bg-canvas shadow-sm">
              <RuntimePreviewFrame
                :frame-url="previewFrameUrl"
                :title="`component-release-preview-${activeVersionNo ?? 0}`"
                layout="fill"
                container-class="h-full overflow-hidden rounded-2xl border-0 bg-canvas shadow-none"
                empty-title="发布版本预览准备中"
                empty-description="正在生成所选发布版本的预览，请稍候。"
              />
            </div>
          </div>
        </section>
      </div>

      <div v-else class="px-6 py-10 text-sm text-text-disabled">
        当前组件还没有正式发布版本。
      </div>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import MonacoDiffViewer from '@/components/editor/MonacoDiffViewer.vue'
import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import { UiDialog } from '@/components/ui'
import UiButton from '@/components/ui/button/UiButton.vue'
import type { WorkspaceComponentVersionContent, WorkspaceComponentVersionListItem } from '@/types/api'
import { formatDateTime } from '@/utils/format'

type VersionPanel = { mode: 'diff' | 'preview'; versionNo: number } | null

const props = defineProps<{
  modelValue: boolean
  loading: boolean
  versions: WorkspaceComponentVersionListItem[]
  panel: VersionPanel
  panelTitle: string
  panelSubtitle: string
  draftContent: string
  versionContentMap: Record<number, WorkspaceComponentVersionContent>
  previewFrameUrl: string
  previewingVersionNo: number | null
  loadingContentVersionNo: number | null
  restoringVersionNo: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'preview-version': [versionNo: number]
  'diff-version': [versionNo: number]
  'restore-version': [versionNo: number]
}>()

const activeVersionNo = computed(() => props.panel?.versionNo ?? null)
const activeVersionContent = computed(() => (
  activeVersionNo.value ? props.versionContentMap[activeVersionNo.value] ?? null : null
))
</script>

