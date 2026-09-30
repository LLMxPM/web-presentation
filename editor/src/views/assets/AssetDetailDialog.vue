<!-- 文件功能：资源详情弹窗，承载预览、基础信息、内容编辑、引用检查与单资源操作。 -->
<template>
  <UiDialog
    :open="!!detail.detailAsset.value"
    size="workbench"
    body-preset="immersive"
    :show-header="false"
    overlay-class="bg-overlay/70 backdrop-blur-sm"
    :z-index="220"
    @update:open="handleOpenChange"
  >
    <div v-if="detail.detailAsset.value" class="grid h-full min-h-0 grid-rows-[minmax(280px,0.95fr)_minmax(0,1.05fr)] overflow-hidden xl:grid-cols-[minmax(0,1.35fr)_460px] xl:grid-rows-1">
      <section class="flex min-h-0 flex-col bg-canvas">
        <header class="flex shrink-0 items-center justify-between border-b border-border bg-surface px-5 py-4">
          <div class="min-w-0">
            <h2 class="truncate text-base font-bold text-text">{{ detail.detailAsset.value.name }}</h2>
            <p class="mt-1 truncate font-mono text-xs text-text-disabled">{{ detail.detailAsset.value.original_name }}</p>
          </div>
          <BaseCloseButton label="关闭资源详情" @click="detail.closeAssetDetail()" />
        </header>
        <div class="min-h-0 flex-1 p-5">
          <AssetPreviewFrame
            :key="`${detail.detailAsset.value.id}:${detail.detailAsset.value.file_hash}`"
            class="h-full"
            :workspace-id="workspaceId"
            :asset="detail.detailAsset.value"
          />
        </div>
      </section>

      <aside class="flex min-h-0 flex-col border-t border-border bg-surface xl:border-l xl:border-t-0">
        <div class="shrink-0 border-b border-border-muted bg-surface">
          <div class="px-5 pb-3 pt-4">
            <div class="grid grid-cols-3 rounded-xl bg-surface-muted p-1">
              <UiButton
                v-for="tab in detailTabs"
                :key="tab.value"
                type="button"
                variant="ghost"
                size="sm"
                class="h-8 rounded-lg px-3 text-xs font-bold transition-colors"
                :class="detail.detailTab.value === tab.value ? 'bg-surface text-accent shadow-sm' : 'text-text-muted hover:text-text'"
                @click="detail.detailTab.value = tab.value"
              >
                {{ tab.label }}
              </UiButton>
            </div>
          </div>
          <div class="flex items-center justify-between gap-3 border-t border-border-muted bg-canvas/80 px-5 py-3">
            <span class="shrink-0 text-xs font-black uppercase tracking-widest text-text-disabled">资源操作</span>
            <div class="flex min-w-0 flex-wrap justify-end gap-2">
              <UiButton type="button" variant="secondary" size="sm" title="替换文件" @click="detail.triggerReplace(detail.detailAsset.value)">
                <Replace class="h-3.5 w-3.5" />
                替换
              </UiButton>
              <UiButton
                v-if="detail.detailAsset.value.status === 'active'"
                type="button"
                variant="secondary"
                size="sm"
                title="归档资源"
                @click="detail.archiveDetailAsset()"
              >
                <Archive class="h-3.5 w-3.5" />
                归档
              </UiButton>
              <UiButton
                v-if="detail.detailAsset.value.status === 'archived' && !detail.detailAsset.value.history_kind"
                type="button"
                variant="secondary"
                size="sm"
                title="恢复资源"
                @click="detail.restoreDetailAsset()"
              >
                <RotateCcw class="h-3.5 w-3.5" />
                恢复
              </UiButton>
              <UiButton
                v-if="detail.detailAsset.value.status === 'archived'"
                type="button"
                variant="danger"
                size="sm"
                title="删除资源"
                @click="detail.deleteDetailAsset()"
              >
                <Trash2 class="h-3.5 w-3.5" />
                删除
              </UiButton>
            </div>
          </div>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          <div v-if="detail.detailTab.value === 'basic'" class="space-y-4">
            <section class="rounded-xl border border-border bg-canvas p-4">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h3 class="truncate text-sm font-bold text-text">资源摘要</h3>
                  <p class="mt-1 truncate font-mono text-xs text-text-disabled">{{ detail.detailAsset.value.file_hash }}</p>
                </div>
                <span class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-black" :class="detail.detailAsset.value.status === 'active' ? 'bg-success-muted text-success-strong' : 'bg-border text-text-secondary'">
                  {{ detail.resolveAssetStatusBadgeText(detail.detailAsset.value) }}
                </span>
              </div>
              <dl class="mt-4 grid grid-cols-2 gap-3 text-xs">
                <div><dt class="text-text-muted">类型</dt><dd class="mt-1 font-bold text-text">{{ detail.detailAsset.value.asset_type }}</dd></div>
                <div><dt class="text-text-muted">大小</dt><dd class="mt-1 font-bold text-text">{{ formatBytes(detail.detailAsset.value.file_size) }}</dd></div>
                <div><dt class="text-text-muted">Content-Type</dt><dd class="mt-1 truncate font-mono text-text-emphasis">{{ detail.detailAsset.value.content_type || '-' }}</dd></div>
                <div><dt class="text-text-muted">引用数</dt><dd class="mt-1 font-bold text-text">{{ detail.referenceCountText.value }}</dd></div>
                <div><dt class="text-text-muted">近似比例</dt><dd class="mt-1 font-bold text-text">{{ detail.formatAssetAspectRatio(detail.detailAsset.value) }}</dd></div>
                <div><dt class="text-text-muted">比例来源</dt><dd class="mt-1 font-bold text-text">{{ detail.formatAspectRatioSource(detail.detailAsset.value.aspect_ratio_source) }}</dd></div>
              </dl>
              <UiButton
                v-if="detail.canRecalculateDetailAspectRatio.value"
                class="mt-4"
                variant="ghost"
                size="sm"
                :disabled="backfillRunning"
                @click="detail.recalculateDetailAssetAspectRatio()"
              >
                <RefreshCw class="h-3.5 w-3.5" />
                重新计算比例
              </UiButton>
            </section>
            <div>
              <label class="mb-1 block text-xs font-bold text-text-muted">资源 name</label>
              <UiInput v-model="detail.editForm.name" />
            </div>
            <div>
              <label class="mb-1 block text-xs font-bold text-text-muted">展示文件名</label>
              <UiInput v-model="detail.editForm.original_name" />
            </div>
            <div>
              <label class="mb-1 block text-xs font-bold text-text-muted">描述</label>
              <UiInput v-model="detail.editForm.description" type="textarea" :rows="4" />
            </div>
            <div>
              <label class="mb-1 block text-xs font-bold text-text-muted">标签，逗号分隔</label>
              <UiInput v-model="detail.editTagsText.value" />
            </div>
            <div v-if="detail.canEditAssetAspectRatio(detail.detailAsset.value)">
              <label class="mb-1 block text-xs font-bold text-text-muted">近似比例</label>
              <UiInput v-model="detail.editForm.approx_aspect_ratio" placeholder="16:9" />
            </div>
          </div>

          <div v-else-if="detail.detailTab.value === 'content'" class="flex h-full min-h-0 flex-col">
            <div v-if="!detail.detailAsset.value.content_editable" class="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border bg-canvas p-6 text-center">
              <div>
                <FileText class="mx-auto mb-3 h-10 w-10 text-text-faint" />
                <p class="text-sm font-bold text-text-secondary">该资源不支持文本内容编辑</p>
                <p class="mt-2 text-xs leading-6 text-text-disabled">位图图标和位图图片只能复制、归档、删除或维护元数据。</p>
              </div>
            </div>
            <template v-else>
              <UiInput v-model="detail.contentDraft.value" type="textarea" textarea-mode="fill" class="font-mono text-xs leading-5" />
              <p class="mt-3 text-xs text-text-muted">写入内容会自动保留写入前副本。</p>
            </template>
          </div>

          <div v-else-if="detail.detailTab.value === 'references'" class="space-y-4">
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-bold text-text-emphasis">引用明细</h3>
              <UiButton type="button" variant="ghost" size="xs" @click="detail.loadReferences()">刷新</UiButton>
            </div>
            <div v-if="detail.referencesLoading.value" class="text-sm text-text-muted">正在检查引用...</div>
            <div v-else-if="!detail.referenceSummary.value?.has_references" class="rounded-xl bg-success-muted p-4 text-sm font-bold text-success-strong">未发现引用阻断。</div>
            <div v-else class="space-y-3">
              <div class="rounded-xl bg-danger-muted p-4 text-xs leading-6 text-danger-strong">
                页面 {{ detail.referenceSummary.value.page_count }}，组件 {{ detail.referenceSummary.value.component_count }}，组件版本 {{ detail.referenceSummary.value.component_version_count }}，主题 {{ detail.referenceSummary.value.theme_count }}，字体 {{ detail.referenceSummary.value.font_count }}。
              </div>
              <section v-for="group in detail.referenceGroups.value" :key="group.kind" class="rounded-xl border border-border bg-surface p-4">
                <div class="mb-3 flex items-center justify-between">
                  <h4 class="text-sm font-bold text-text-emphasis">{{ group.label }}</h4>
                  <span class="rounded-full bg-surface-muted px-2 py-0.5 text-xs font-bold text-text-muted">{{ group.items.length }}</span>
                </div>
                <div class="space-y-2">
                  <UiButton
                    v-for="item in group.items"
                    :key="`${item.kind}-${item.id}-${item.version_no || ''}`"
                    type="button"
                    class="flex w-full items-center justify-between rounded-lg bg-canvas px-3 py-2 text-left text-xs transition-colors hover:bg-surface-selected"
                    @click="detail.goToReference(item)"
                  >
                    <span class="min-w-0 truncate font-semibold text-text-emphasis">{{ detail.formatReferenceName(item) }}</span>
                    <ArrowUpRight v-if="detail.canOpenReference(item)" class="h-3.5 w-3.5 shrink-0 text-text-disabled" />
                  </UiButton>
                </div>
              </section>
            </div>
          </div>
        </div>

        <footer class="flex shrink-0 items-center justify-end gap-2 border-t border-border-muted bg-canvas px-5 py-4">
          <UiButton variant="ghost" size="sm" @click="detail.closeAssetDetail()">关闭</UiButton>
          <UiButton v-if="detail.detailTab.value === 'basic'" size="sm" :disabled="detail.saving.value" @click="detail.saveAssetMetadata()">保存信息</UiButton>
          <UiButton v-if="detail.detailTab.value === 'content' && detail.detailAsset.value.content_editable" size="sm" :disabled="detail.saving.value || !detail.canSaveContent.value" @click="detail.saveContent()">
            <Save class="h-3.5 w-3.5" />
            写入内容
          </UiButton>
        </footer>
      </aside>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { Archive, ArrowUpRight, FileText, RefreshCw, Replace, RotateCcw, Save, Trash2 } from '@lucide/vue'

import AssetPreviewFrame from '@/components/project/AssetPreviewFrame.vue'
import { UiButton, UiDialog, UiInput } from '@/components/ui'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
import { DETAIL_TABS } from '@/views/asset-view-options'
import type { AssetDetailController } from '@/views/assets/useAssetDetail'

const props = defineProps<{
  workspaceId: number
  detail: AssetDetailController
  backfillRunning: boolean
}>()

const detailTabs = DETAIL_TABS

function handleOpenChange(value: boolean): void {
  props.detail.handleDetailDialogVisibleChange(value)
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
</script>
