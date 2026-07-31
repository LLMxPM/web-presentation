<!-- 文件功能：提供工作空间级样式库管理页面，维护可复制到项目的展示配置与 Markdown 样式规范。 -->
<template>
  <div data-testid="workspace-styles-view" class="flex h-full min-h-0 flex-col gap-2">
    <input
      ref="importFileInputRef"
      class="hidden"
      type="file"
      accept=".zip,application/zip"
      @change="handleImportFileSelected"
    >
    <PageHeader
      class="shrink-0"
      :icon="Palette"
      :title="workspaceTitle"
      description="集中维护可复用的项目展示配置、主题引用和内容助手样式规范；编辑样式不会影响已配置项目。"
    >
      <template #meta>
        <span class="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-black text-text-muted">
          共 {{ styleTotal }} 个样式
        </span>
      </template>
      <template #actions>
        <UiButton
          variant="secondary"
          :disabled="!workspaceId || importValidatePending || importPackagePending"
          @click="openImportFilePicker"
        >
          <Upload class="h-3.5 w-3.5" />
          导入样式
        </UiButton>
        <UiButton
          variant="secondary"
          :disabled="!workspaceId || (!selectionMode && styles.length === 0)"
          :title="selectionMode ? '退出导出选择模式' : '进入选择模式后勾选要导出的样式'"
          @click="toggleSelectionMode"
        >
          <Download class="h-3.5 w-3.5" />
          {{ selectionMode ? '退出选择' : '导出样式' }}
        </UiButton>
        <UiButton variant="secondary" :disabled="loading" @click="loadStyles">
          <RefreshCw class="h-3.5 w-3.5" />
          刷新
        </UiButton>
        <UiButton :disabled="!workspaceId" @click="openCreateStyle">
          <Plus class="h-3.5 w-3.5" />
          新建样式
        </UiButton>
      </template>
    </PageHeader>

    <div class="min-h-0 flex-1 overflow-hidden">
      <ToolPanel class="h-full min-h-0">
        <template #toolbar>
          <div class="space-y-1.5 px-1 py-0.5">
            <SimpleSearchBar
              v-model="keyword"
              placeholder="搜索样式名称、key"
              aria-label="搜索样式名称、key"
              @submit="handleSearchSubmit"
            />
            <SelectionToolbar
              v-if="selectionMode"
              :count="selectedStyleIds.length"
              label="样式导出批量操作"
              @clear="clearStyleSelection"
            >
              <UiButton size="sm" variant="ghost" :disabled="styles.length === 0" @click="selectAllVisibleStyles">
                全选本页
              </UiButton>
              <UiButton
                size="sm"
                variant="primary"
                :disabled="selectedStyleIds.length === 0"
                :loading="exportPackagePending"
                @click="handleExportSelectedStyles"
              >
                <Download class="h-3.5 w-3.5" />
                导出所选
              </UiButton>
              <UiButton size="xs" variant="ghost" class="ml-auto" @click="exitSelectionMode">
                退出选择
              </UiButton>
            </SelectionToolbar>
          </div>
        </template>

        <DataState :state="styleDataState" :title="styleDataState === 'empty' ? (keyword ? '未找到相关样式' : '暂无样式') : undefined">
          <div class="grid gap-3 2xl:grid-cols-2">
            <article
              v-for="style in styles"
              :key="style.id"
              :data-style-id="style.id"
              class="group cursor-pointer rounded-xl border p-4 transition-all hover:shadow-md"
              :class="resolveStyleCardClass(style)"
              @click="handleStyleCardClick(style)"
            >
              <div class="flex items-start justify-between gap-2.5">
                <div class="flex min-w-0 items-start gap-2.5">
                  <label
                    v-if="selectionMode"
                    class="mt-1 flex h-5 w-5 shrink-0 items-center justify-center"
                    @click.stop
                  >
                    <UiCheckbox
                      :aria-label="`选择导出 ${style.name}`"
                      :model-value="isStyleSelected(style)"
                      @update:model-value="toggleStyleSelection(style)"
                    />
                  </label>
                  <div class="min-w-0">
                    <div class="flex min-w-0 items-center gap-2">
                      <h3 class="truncate text-base font-black text-text-strong">{{ style.name }}</h3>
                      <span
                        v-if="style.theme_key"
                        class="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-bold text-text-muted"
                      >
                        主题 {{ style.theme_key }}
                      </span>
                    </div>
                    <p class="mt-0.5 truncate font-mono text-xs text-text-disabled">{{ style.key }}</p>
                  </div>
                </div>
                <div class="flex shrink-0 items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                  <UiIconButton
                    label="编辑"
                    size="sm"
                    variant="ghost"
                    @click.stop="openEditStyle(style)"
                  >
                    <Pencil class="h-3.5 w-3.5" />
                  </UiIconButton>
                  <UiIconButton
                    label="管理建议组件"
                    size="sm"
                    variant="ghost"
                    @click.stop="openEditStyle(style, 'components')"
                  >
                    <Component class="h-3.5 w-3.5" />
                  </UiIconButton>
                  <UiIconButton
                    label="复制"
                    size="sm"
                    variant="ghost"
                    @click.stop="copyStyle(style)"
                  >
                    <Copy class="h-3.5 w-3.5" />
                  </UiIconButton>
                  <UiIconButton
                    label="删除"
                    size="sm"
                    variant="danger"
                    @click.stop="deleteStyle(style)"
                  >
                    <Trash2 class="h-3.5 w-3.5" />
                  </UiIconButton>
                </div>
              </div>

              <p class="mt-2 line-clamp-1 text-sm leading-5 text-text-muted">{{ style.description || '未填写样式说明。' }}</p>

              <div class="mt-3 flex min-w-0 items-center justify-between gap-3">
                <p class="truncate text-xs font-semibold text-text-muted" :title="formatStyleMeta(style)">{{ formatStyleMeta(style) }}</p>
                <span
                  class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold"
                  :class="hasStyleSpec(style) ? 'bg-success-muted text-success-strong ring-1 ring-success-border' : 'bg-surface-muted text-text-disabled'"
                >
                  {{ hasStyleSpec(style) ? '已维护规范' : '未维护规范' }}
                </span>
              </div>
            </article>
          </div>
        </DataState>

        <template #footer>
          <PaginationControl
            :page="stylePage"
            :page-size="stylePageSize"
            :total="styleTotal"
            :page-size-options="[10, 20, 50, 100]"
            @update:page="stylePage = $event"
            @update:page-size="handleStylePageSizeChange"
          />
        </template>
      </ToolPanel>
    </div>

    <WorkspaceStyleEditorDialog
      v-model="editorVisible"
      :workspace-id="workspaceId"
      :style="editingStyle ?? null"
      :default-theme-key="workspaceDetails?.default_theme_key"
      :initial-tab="editorInitialTab"
      :loading="saving"
      @save="saveStyle"
    />

    <WorkspaceStyleDetailDialog
      v-model="styleDetailVisible"
      :workspace-id="workspaceId"
      :style-item="selectedStyle ?? null"
      :default-theme-key="workspaceDetails?.default_theme_key"
      @edit="openEditStyle"
    />

    <ExportPackageAssetsDialog
      v-model="exportDialogVisible"
      title="确认导出样式"
      description="动态资源来自样式建议组件中的组件源码；手动资源会随样式包一起导出。"
      :workspace-id="workspaceId"
      :automatic-assets="exportValidation?.automatic_assets ?? []"
      :manual-assets="exportValidation?.manual_assets ?? []"
      :manual-asset-names="exportManualAssetNames"
      :asset-options="exportAssetOptions"
      :asset-keyword="exportAssetKeyword"
      :asset-options-loading="exportAssetOptionsLoading"
      :export-pending="exportPackagePending"
      :warnings="exportValidation?.warnings ?? []"
      :missing-static-asset-names="exportValidation?.missing_static_asset_names ?? []"
      :missing-manual-asset-names="exportValidation?.missing_manual_asset_names ?? []"
      :dynamic-resource-components="exportValidation?.dynamic_resource_components ?? []"
      @update:asset-keyword="exportAssetKeyword = $event"
      @load-assets="loadExportAssetOptions"
      @toggle-asset="toggleExportManualAsset"
      @remove-asset="removeExportManualAsset"
      @confirm="handleConfirmExportPackage"
    />

    <UiDialog :open="importDialogVisible" title="导入样式" size="standard" @update:open="importDialogVisible = $event">
      <div class="space-y-4">
        <div class="rounded-xl border border-border bg-canvas px-4 py-3">
          <p class="text-sm font-bold text-text-emphasis">{{ importFile?.name || '未选择文件' }}</p>
          <p v-if="importValidation" class="mt-1 text-xs text-text-muted">
            样式 {{ importValidation.styles.length }} 个，组件 {{ importValidation.components.length }} 个，主题 {{ importValidation.themes.length }} 个，资源 {{ importValidation.assets.length }} 个，字体 {{ importValidation.fonts.length }} 个
          </p>
          <p v-else-if="importValidatePending" class="mt-1 text-xs text-text-muted">正在预检样式离线包...</p>
        </div>

        <div v-if="importValidation?.errors.length" class="rounded-xl border border-danger-border bg-danger-muted px-4 py-3">
          <p class="mb-2 text-sm font-bold text-danger-strong">预检未通过，请修改或删除相应资源后重试</p>
          <ul class="space-y-1 text-xs leading-5 text-danger-strong">
            <li v-for="error in importValidation.errors" :key="error">{{ error }}</li>
          </ul>
        </div>

        <div v-if="importValidation?.warnings.length" class="rounded-xl border border-warning-border bg-warning-muted px-4 py-3">
          <p class="mb-2 text-sm font-bold text-warning-strong">包内提示</p>
          <ul class="space-y-1 text-xs leading-5 text-warning-strong">
            <li v-for="warning in importValidation.warnings" :key="warning">{{ warning }}</li>
          </ul>
        </div>

        <div v-if="importValidation" class="space-y-3">
          <section class="rounded-xl border border-border bg-surface p-4">
            <h4 class="text-sm font-bold text-text-emphasis">样式</h4>
            <div class="mt-2 max-h-40 space-y-2 overflow-y-auto">
              <div v-for="style in importValidation.styles" :key="style.key" class="flex items-center justify-between gap-3 text-xs">
                <span class="font-semibold text-text-emphasis">{{ style.name }}</span>
                <span class="flex shrink-0 items-center gap-2">
                  <span class="font-mono text-text-disabled">{{ style.key }}</span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[11px] font-bold ring-1"
                    :class="resolveImportActionBadgeClass(style.action)"
                  >
                    {{ resolveImportActionText(style.action) }}
                  </span>
                  <UiButton
                    type="button"
                    variant="ghost"
                    size="xs"
                    @click="openImportStyleSpec(style)"
                  >
                    查看规范
                  </UiButton>
                </span>
              </div>
            </div>
          </section>

          <section class="grid gap-3 lg:grid-cols-2">
            <div class="rounded-xl border border-border bg-surface p-4">
              <h4 class="text-sm font-bold text-text-emphasis">组件</h4>
              <div class="mt-2 max-h-40 overflow-y-auto rounded-lg border border-border-muted text-xs text-text-muted">
                <p v-if="importValidation.components.length === 0" class="px-3 py-2">无组件</p>
                <div
                  v-for="component in importValidation.components"
                  :key="`${component.source_component_code}-${component.source_version_no}`"
                  class="border-b border-border-muted px-3 py-2.5 last:border-b-0 even:bg-canvas/60"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div class="min-w-0 flex items-baseline gap-2">
                      <span class="truncate font-semibold text-text-emphasis">{{ component.name }}</span>
                      <span class="shrink-0 font-mono text-[11px] text-text-disabled">{{ component.import_name }}</span>
                    </div>
                    <span
                      class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1"
                      :class="resolveImportActionBadgeClass(component.action)"
                      :title="component.match_reason || resolveImportActionText(component.action)"
                    >
                      {{ resolveImportActionText(component.action) }}
                    </span>
                  </div>
                  <div class="mt-1 flex min-w-0 items-center gap-2 text-[11px] text-text-disabled">
                    <span class="font-mono">fp: {{ formatFingerprint(component.component_fingerprint) }}</span>
                    <span v-if="component.matched_component_code" class="truncate">
                      匹配 {{ component.matched_component_code }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <div class="rounded-xl border border-border bg-surface p-4">
              <h4 class="text-sm font-bold text-text-emphasis">主题</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-text-muted">
                <p v-if="importValidation.themes.length === 0">无主题</p>
                <div v-for="theme in importValidation.themes" :key="theme.key" class="flex items-center justify-between gap-2">
                  <span class="truncate">{{ theme.name }}</span>
                  <span
                    class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1"
                    :class="resolveImportActionBadgeClass(theme.action)"
                  >
                    {{ resolveImportActionText(theme.action) }}
                  </span>
                </div>
              </div>
            </div>
            <div class="rounded-xl border border-border bg-surface p-4">
              <h4 class="text-sm font-bold text-text-emphasis">资源</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-text-muted">
                <p v-if="importValidation.assets.length === 0">无资源</p>
                <div v-for="asset in importValidation.assets" :key="asset.name" class="flex items-center justify-between gap-2">
                  <span class="flex min-w-0 items-center gap-1.5">
                    <span class="truncate">{{ asset.name }}</span>
                    <span class="shrink-0 rounded bg-surface-muted px-1.5 py-0.5 text-[10px] font-bold text-text-muted">
                      {{ resolveAssetTypeLabel(asset.asset_type) }}
                    </span>
                  </span>
                  <span class="flex shrink-0 items-center gap-1.5">
                    <span
                      class="rounded-full px-2 py-0.5 text-[11px] font-bold ring-1"
                      :class="resolveImportActionBadgeClass(asset.action)"
                    >
                      {{ resolveImportActionText(asset.action) }}
                    </span>
                  </span>
                </div>
              </div>
            </div>
            <div class="rounded-xl border border-border bg-surface p-4">
              <h4 class="text-sm font-bold text-text-emphasis">字体</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-text-muted">
                <p v-if="importValidation.fonts.length === 0">无字体</p>
                <div v-for="font in importValidation.fonts" :key="font.asset_name" class="flex items-center justify-between gap-2">
                  <span class="truncate">{{ font.asset_name }}</span>
                  <span
                    class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1"
                    :class="resolveImportActionBadgeClass(font.action)"
                  >
                    {{ resolveImportActionText(font.action) }}
                  </span>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>

      <template #footer>
        <UiButton variant="ghost" @click="closeImportDialog">取消</UiButton>
        <UiButton
          variant="primary"
          :disabled="!importValidation?.valid || !importFile"
          :loading="importPackagePending"
          @click="handleConfirmImportPackage"
        >
          确认导入
        </UiButton>
      </template>
    </UiDialog>

    <UiDialog
      :open="importStyleSpecDialogVisible"
      :title="selectedImportStyleSpec ? `${selectedImportStyleSpec.name} · 最终导入规范` : '最终导入规范'"
      size="standard"
      @update:open="importStyleSpecDialogVisible = $event"
    >
      <div class="space-y-3">
        <div class="flex items-center justify-between gap-3 rounded-xl border border-border bg-canvas px-4 py-3 text-xs">
          <span class="min-w-0 truncate font-semibold text-text-emphasis">{{ selectedImportStyleSpec?.key }}</span>
          <span
            v-if="selectedImportStyleSpec"
            class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1"
            :class="resolveImportActionBadgeClass(selectedImportStyleSpec.action)"
          >
            {{ resolveImportActionText(selectedImportStyleSpec.action) }}
          </span>
        </div>
        <section v-if="selectedImportStyleSpec" class="rounded-xl border border-border bg-surface p-4">
          <h4 class="text-sm font-black text-text-strong">展示配置</h4>
          <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div
              v-for="item in importStyleSpecDetailItems"
              :key="item.label"
              class="rounded-lg border border-border-muted bg-canvas px-3 py-2"
            >
              <p class="text-[11px] font-bold text-text-disabled">{{ item.label }}</p>
              <p class="mt-1 text-sm font-black text-text">{{ item.value }}</p>
            </div>
          </div>
        </section>
        <pre class="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-xl border border-border bg-surface p-4 text-sm leading-6 text-text-emphasis">{{ selectedImportStyleSpec?.style_spec_markdown || '无样式规范' }}</pre>
      </div>
    </UiDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Component, Copy, Download, Palette, Pencil, Plus, RefreshCw, Trash2, Upload } from '@lucide/vue'

import { getWorkspace } from '@/api/catalog'
import { listWorkspaceAssets } from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import {
  copyWorkspaceStyle,
  createWorkspaceStyle,
  deleteWorkspaceStyle,
  exportWorkspaceStylePackage,
  importWorkspaceStylePackage,
  listWorkspaceStyles,
  updateWorkspaceStyleSuggestedComponents,
  updateWorkspaceStyle,
  validateWorkspaceStylePackageExport,
  validateWorkspaceStylePackageImport,
  type WorkspaceStylePayload,
} from '@/api/styles'
import DataState from '@/components/patterns/DataState.vue'
import PageHeader from '@/components/patterns/PageHeader.vue'
import SelectionToolbar from '@/components/patterns/SelectionToolbar.vue'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import ToolPanel from '@/components/patterns/ToolPanel.vue'
import { UiButton, UiCheckbox, UiDialog, UiIconButton } from '@/components/ui'
import PaginationControl from '@/components/ui/PaginationControl.vue'
import ExportPackageAssetsDialog from '@/components/project/ExportPackageAssetsDialog.vue'
import WorkspaceStyleDetailDialog from '@/components/project/WorkspaceStyleDetailDialog.vue'
import WorkspaceStyleEditorDialog from '@/components/project/WorkspaceStyleEditorDialog.vue'
import type {
  AssetResponse,
  ProjectMenuMode,
  WorkspaceStyleExportValidationResult,
  WorkspaceItem,
  WorkspaceStyleImportValidationResult,
  WorkspaceStyleItem,
  WorkspaceStylePackageStyleSummary,
} from '@/types/api'
import { createConfirm, Message } from '@/utils/message'

const route = useRoute()

const workspaceId = computed(() => Number(route.params.workspaceId || 0) || null)
const workspaceDetails = ref<WorkspaceItem | null>(null)
const styles = ref<WorkspaceStyleItem[]>([])
const selectedStyle = ref<WorkspaceStyleItem | null>(null)
const selectedStyleIds = ref<number[]>([])
const selectionMode = ref(false)
const keyword = ref('')
const styleTotal = ref(0)
const stylePage = ref(1)
const stylePageSize = ref(20)
const loading = ref(false)
const highlightStyleId = ref<number | null>(null)
let highlightTimer: number | undefined
let searchDebounceTimer: number | undefined
const styleDataState = computed<'loading' | 'empty' | 'ready'>(() => (
  loading.value ? 'loading' : styles.value.length ? 'ready' : 'empty'
))
const saving = ref(false)
const exportPackagePending = ref(false)
const exportDialogVisible = ref(false)
const exportValidation = ref<WorkspaceStyleExportValidationResult | null>(null)
const exportManualAssetNames = ref<string[]>([])
const exportAssetOptions = ref<AssetResponse[]>([])
const exportAssetKeyword = ref('')
const exportAssetOptionsLoading = ref(false)
const importValidatePending = ref(false)
const importPackagePending = ref(false)
const importDialogVisible = ref(false)
const importFileInputRef = ref<HTMLInputElement | null>(null)
const importFile = ref<File | null>(null)
const importValidation = ref<WorkspaceStyleImportValidationResult | null>(null)
const importStyleSpecDialogVisible = ref(false)
const selectedImportStyleSpec = ref<WorkspaceStylePackageStyleSummary | null>(null)
const editorVisible = ref(false)
const editingStyle = ref<WorkspaceStyleItem | null>(null)
const editorInitialTab = ref<'style' | 'components'>('style')
const styleDetailVisible = ref(false)

const workspaceTitle = computed(() => workspaceDetails.value?.name ? `${workspaceDetails.value.name} · 样式库` : '样式库')
const importStyleSpecDetailItems = computed(() => {
  const style = selectedImportStyleSpec.value
  if (!style) {
    return []
  }
  return [
    { label: '画布尺寸', value: `${style.page_width} x ${style.page_height}` },
    { label: '画布比例', value: formatAspectRatio(style.page_width, style.page_height) },
    { label: '基础字号', value: style.base_font_size },
    { label: '图标描边宽度', value: String(style.icon_default_stroke_width) },
    { label: '导航按钮位置', value: formatMenuMode(style.menu_mode) },
    { label: '导出按钮', value: style.show_pdf_export_button ? '显示' : '隐藏' },
  ]
})

type WorkspaceStyleEditorSavePayload = WorkspaceStylePayload & { suggested_component_ids?: number[] }

onMounted(() => {
  void loadWorkspace()
  void loadStyles()
})

onBeforeUnmount(() => {
  window.clearTimeout(searchDebounceTimer)
  window.clearTimeout(highlightTimer)
})

watch(
  workspaceId,
  () => {
    selectedStyle.value = null
    stylePage.value = 1
    exitSelectionMode()
    void loadWorkspace()
    void loadStyles()
  },
)

watch(stylePage, () => {
  void loadStyles()
})

watch(keyword, () => {
  window.clearTimeout(searchDebounceTimer)
  searchDebounceTimer = window.setTimeout(() => {
    handleSearchSubmit()
  }, 300)
})

/**
 * 加载工作空间详情，用于标题和默认主题。
 */
async function loadWorkspace(): Promise<void> {
  if (!workspaceId.value) {
    workspaceDetails.value = null
    return
  }
  try {
    workspaceDetails.value = await getWorkspace(workspaceId.value)
  } catch (error) {
    Message.error(getErrorMessage(error, '加载工作空间失败。'))
  }
}

/**
 * 加载当前页样式列表；保留跨页/跨搜索的导出勾选。
 */
async function loadStyles(): Promise<void> {
  if (!workspaceId.value) {
    styles.value = []
    return
  }
  loading.value = true
  try {
    const response = await listWorkspaceStyles(workspaceId.value, {
      page: stylePage.value,
      page_size: stylePageSize.value,
      keyword: keyword.value.trim() || undefined,
    })
    styles.value = response.items
    styleTotal.value = response.total
  } catch (error) {
    Message.error(getErrorMessage(error, '加载样式列表失败。'))
  } finally {
    loading.value = false
  }
}

/**
 * 搜索提交时回到第一页并立即刷新列表。
 */
function handleSearchSubmit(): void {
  window.clearTimeout(searchDebounceTimer)
  if (stylePage.value !== 1) {
    stylePage.value = 1
    return
  }
  void loadStyles()
}

/**
 * 切换页容量并回到第一页。
 * @param size 新页容量
 */
function handleStylePageSizeChange(size: number): void {
  stylePageSize.value = size
  if (stylePage.value !== 1) {
    stylePage.value = 1
    return
  }
  void loadStyles()
}

/**
 * 打开新建样式弹窗。
 */
function openCreateStyle(): void {
  editingStyle.value = null
  editorInitialTab.value = 'style'
  editorVisible.value = true
}

/**
 * 打开编辑样式弹窗，可指定初始定位到建议组件页签。
 * @param style 待编辑样式
 * @param tab 初始页签
 */
function openEditStyle(style: WorkspaceStyleItem, tab: 'style' | 'components' = 'style'): void {
  editingStyle.value = style
  editorInitialTab.value = tab
  editorVisible.value = true
}

/**
 * 打开当前样式详情弹窗。
 */
function openStyleDetailDialog(style: WorkspaceStyleItem): void {
  selectedStyle.value = style
  styleDetailVisible.value = true
}

/**
 * 卡片主点击：选择模式下切换勾选，否则打开详情。
 * @param style 被点击样式
 */
function handleStyleCardClick(style: WorkspaceStyleItem): void {
  if (selectionMode.value) {
    toggleStyleSelection(style)
    return
  }
  openStyleDetailDialog(style)
}

/**
 * 切换导出选择模式；退出时清空已勾选样式。
 */
function toggleSelectionMode(): void {
  if (selectionMode.value) {
    exitSelectionMode()
    return
  }
  selectionMode.value = true
}

/**
 * 退出选择模式并清空勾选。
 */
function exitSelectionMode(): void {
  selectionMode.value = false
  selectedStyleIds.value = []
}

/**
 * 清空当前勾选但保持选择模式。
 */
function clearStyleSelection(): void {
  selectedStyleIds.value = []
}

/**
 * 将当前页全部样式并入勾选集合。
 */
function selectAllVisibleStyles(): void {
  const merged = new Set(selectedStyleIds.value)
  for (const style of styles.value) {
    merged.add(style.id)
  }
  selectedStyleIds.value = [...merged]
}

/**
 * 生成样式卡片的选中/高亮边框样式。
 * @param style 当前样式
 */
function resolveStyleCardClass(style: WorkspaceStyleItem): string {
  if (selectionMode.value && isStyleSelected(style)) {
    return 'border-accent-ring bg-surface-selected/40'
  }
  if (highlightStyleId.value === style.id) {
    return 'border-accent-ring ring-2 ring-accent-muted'
  }
  return 'border-border hover:border-accent-ring'
}

/**
 * 判断样式是否已维护非空规范。
 * @param style 当前样式
 */
function hasStyleSpec(style: WorkspaceStyleItem): boolean {
  return Boolean(style.style_spec_markdown?.trim())
}

/**
 * 把展示配置汇总成单行可截断的元信息文本。
 * @param style 当前样式
 */
function formatStyleMeta(style: WorkspaceStyleItem): string {
  return [
    `画布 ${style.page_width}×${style.page_height} (${formatAspectRatio(style.page_width, style.page_height)})`,
    `字号 ${style.base_font_size}`,
    `描边 ${style.icon_default_stroke_width}`,
    formatMenuMode(style.menu_mode),
  ].join(' · ')
}

/**
 * 判断样式是否已被勾选为导出对象。
 */
function isStyleSelected(style: WorkspaceStyleItem): boolean {
  return selectedStyleIds.value.includes(style.id)
}

/**
 * 切换样式导出选择状态。
 */
function toggleStyleSelection(style: WorkspaceStyleItem): void {
  if (isStyleSelected(style)) {
    selectedStyleIds.value = selectedStyleIds.value.filter(id => id !== style.id)
    return
  }
  selectedStyleIds.value = [...selectedStyleIds.value, style.id]
}

/**
 * 预检当前勾选样式并打开导出确认弹窗，统一由用户确认后下载。
 */
async function handleExportSelectedStyles(): Promise<void> {
  if (!workspaceId.value || selectedStyleIds.value.length === 0) {
    return
  }
  exportPackagePending.value = true
  try {
    exportManualAssetNames.value = []
    exportValidation.value = await validateWorkspaceStylePackageExport(workspaceId.value, {
      style_ids: selectedStyleIds.value,
      manual_asset_names: [],
    })
    exportDialogVisible.value = true
    exportAssetKeyword.value = ''
    void loadExportAssetOptions()
  } catch (error) {
    Message.error(`导出样式失败：${getErrorMessage(error, '未知原因')}`)
  } finally {
    exportPackagePending.value = false
  }
}

/**
 * 加载可手动补充到样式离线包的工作空间资源。
 */
async function loadExportAssetOptions(): Promise<void> {
  if (!workspaceId.value) {
    exportAssetOptions.value = []
    return
  }
  exportAssetOptionsLoading.value = true
  try {
    const response = await listWorkspaceAssets(workspaceId.value, {
      page: 1,
      page_size: 100,
      keyword: exportAssetKeyword.value.trim() || undefined,
      status: 'active',
    })
    exportAssetOptions.value = response.items
  } catch (error) {
    Message.error(getErrorMessage(error, '加载可选资源失败。'))
  } finally {
    exportAssetOptionsLoading.value = false
  }
}

/**
 * 切换本次样式导出的手动资源。
 * @param assetName 资源名
 */
function toggleExportManualAsset(assetName: string): void {
  if (exportManualAssetNames.value.includes(assetName)) {
    removeExportManualAsset(assetName)
    return
  }
  exportManualAssetNames.value = [...exportManualAssetNames.value, assetName]
}

/**
 * 移除本次样式导出的手动资源。
 * @param assetName 资源名
 */
function removeExportManualAsset(assetName: string): void {
  exportManualAssetNames.value = exportManualAssetNames.value.filter(name => name !== assetName)
}

/**
 * 在确认弹窗中继续导出样式离线包；成功后退出选择模式。
 */
async function handleConfirmExportPackage(): Promise<void> {
  if (!workspaceId.value || selectedStyleIds.value.length === 0) {
    return
  }
  exportPackagePending.value = true
  try {
    await downloadSelectedStylePackage(exportManualAssetNames.value)
    exportDialogVisible.value = false
    exitSelectionMode()
    Message.success('样式离线包已生成。')
  } catch (error) {
    Message.error(`导出样式失败：${getErrorMessage(error, '未知原因')}`)
  } finally {
    exportPackagePending.value = false
  }
}

/**
 * 调用下载接口生成样式离线包。
 * @param manualAssetNames 本次导出手动补充资源名
 */
async function downloadSelectedStylePackage(manualAssetNames: string[]): Promise<void> {
  if (!workspaceId.value) {
    return
  }
  const { blob, filename } = await exportWorkspaceStylePackage(workspaceId.value, {
    style_ids: selectedStyleIds.value,
    manual_asset_names: manualAssetNames,
  })
  downloadBlob(blob, filename)
}

/**
 * 打开本地样式离线包选择器。
 */
function openImportFilePicker(): void {
  importFileInputRef.value?.click()
}

/**
 * 选择 Zip 后立即预检样式离线包。
 */
async function handleImportFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  if (!file || !workspaceId.value) {
    return
  }
  importFile.value = file
  importValidation.value = null
  importDialogVisible.value = true
  importValidatePending.value = true
  try {
    importValidation.value = await validateWorkspaceStylePackageImport(workspaceId.value, file)
  } catch (error) {
    Message.error(getErrorMessage(error, '样式离线包预检失败。'))
    importDialogVisible.value = false
  } finally {
    importValidatePending.value = false
  }
}

/**
 * 确认导入预检通过的样式离线包。
 */
async function handleConfirmImportPackage(): Promise<void> {
  if (!workspaceId.value || !importFile.value || !importValidation.value?.valid) {
    return
  }
  importPackagePending.value = true
  try {
    const result = await importWorkspaceStylePackage(workspaceId.value, importFile.value)
    Message.success(`已导入 ${result.styles.length} 个样式。`)
    closeImportDialog()
    keyword.value = ''
    await loadStyles()
  } catch (error) {
    Message.error(getErrorMessage(error, '导入样式离线包失败。'))
  } finally {
    importPackagePending.value = false
  }
}

/**
 * 打开样式离线包中将最终写入的样式规范预览。
 * @param style 样式导入摘要
 */
function openImportStyleSpec(style: WorkspaceStylePackageStyleSummary): void {
  selectedImportStyleSpec.value = style
  importStyleSpecDialogVisible.value = true
}

/**
 * 关闭导入弹窗并清理临时文件状态。
 */
function closeImportDialog(): void {
  importDialogVisible.value = false
  importFile.value = null
  importValidation.value = null
  importStyleSpecDialogVisible.value = false
  selectedImportStyleSpec.value = null
}

/**
 * 把 Blob 保存为浏览器下载文件。
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/**
 * 展示导入预检中的处理动作。
 */
function resolveImportActionText(action: string): string {
  if (action === 'overwrite') return '覆盖'
  if (action === 'reuse') return '复用'
  if (action === 'conflict') return '冲突'
  return '新增'
}

/**
 * 为样式导入组件列表中的处理动作提供醒目的状态样式。
 */
function resolveImportActionBadgeClass(action: string): string {
  if (action === 'overwrite') return 'bg-warning-muted text-warning-strong ring-warning-border'
  if (action === 'reuse') return 'bg-success-muted text-success-strong ring-success-border'
  if (action === 'conflict') return 'bg-danger-muted text-danger-strong ring-danger-border'
  return 'bg-info-muted text-info-strong ring-info-border'
}

/**
 * 将资源类型转为导入预检中的中文标识；未知类型保留原始值方便排查。
 */
function resolveAssetTypeLabel(assetType: string | null | undefined): string {
  const labels: Record<string, string> = {
    icon: '图标',
    font: '字体',
    image: '图片',
    video: '视频',
    drawio: 'Draw.io',
    mermaid: 'Mermaid',
    chart: '图表',
    formula: '公式',
  }
  return assetType ? labels[assetType] || assetType : '未知'
}

/**
 * 将组件指纹缩短为导入预检中可快速识别的短码。
 */
function formatFingerprint(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : '无指纹'
}

/**
 * 将页面宽高格式化为最简比例。
 */
function formatAspectRatio(width: number, height: number): string {
  const normalizedWidth = Math.max(0, Math.trunc(width))
  const normalizedHeight = Math.max(0, Math.trunc(height))
  if (!normalizedWidth || !normalizedHeight) {
    return '未知'
  }
  const divisor = greatestCommonDivisor(normalizedWidth, normalizedHeight)
  return `${normalizedWidth / divisor}:${normalizedHeight / divisor}`
}

/**
 * 计算两个正整数的最大公约数。
 */
function greatestCommonDivisor(left: number, right: number): number {
  let a = left
  let b = right
  while (b) {
    const next = a % b
    a = b
    b = next
  }
  return a || 1
}

/**
 * 创建或更新样式；样式主体与建议组件分段提交，建议组件失败时保留弹窗与草稿避免重复创建。
 */
async function saveStyle(payload: WorkspaceStyleEditorSavePayload): Promise<void> {
  if (!workspaceId.value) {
    return
  }
  const { suggested_component_ids: suggestedComponentIds, ...stylePayload } = payload
  saving.value = true
  let savedStyle: WorkspaceStyleItem
  try {
    savedStyle = editingStyle.value
      ? await updateWorkspaceStyle(workspaceId.value, editingStyle.value.id, stylePayload)
      : await createWorkspaceStyle(workspaceId.value, stylePayload)
  } catch (error) {
    saving.value = false
    Message.error(getErrorMessage(error, '保存样式失败。'))
    return
  }
  try {
    if (suggestedComponentIds) {
      await updateWorkspaceStyleSuggestedComponents(workspaceId.value, savedStyle.id, suggestedComponentIds)
    }
  } catch (error) {
    // 样式主体已落库：把弹窗切到编辑态，避免用户重试时重复创建样式。
    editingStyle.value = savedStyle
    saving.value = false
    Message.warning(`样式已保存，但建议组件保存失败：${getErrorMessage(error, '未知原因')}`)
    void loadStyles()
    return
  }
  saving.value = false
  editorVisible.value = false
  editingStyle.value = null
  await loadStyles()
  Message.success('样式已保存。')
}

/**
 * 复制样式，并滚动定位与高亮新副本便于用户识别。
 */
async function copyStyle(style: WorkspaceStyleItem): Promise<void> {
  if (!workspaceId.value) {
    return
  }
  try {
    const copied = await copyWorkspaceStyle(workspaceId.value, style.id)
    await loadStyles()
    Message.success('样式已复制。')
    highlightStyleId.value = copied.id
    await nextTick()
    document.querySelector(`[data-style-id="${copied.id}"]`)?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
    window.clearTimeout(highlightTimer)
    highlightTimer = window.setTimeout(() => {
      highlightStyleId.value = null
    }, 3000)
  } catch (error) {
    Message.error(getErrorMessage(error, '复制样式失败。'))
  }
}

/**
 * 删除样式。
 */
async function deleteStyle(style: WorkspaceStyleItem): Promise<void> {
  if (!workspaceId.value) {
    return
  }
  const confirmed = await createConfirm(`确定删除样式「${style.name}」吗？已配置项目不会受到影响。`, '删除样式')
  if (!confirmed) {
    return
  }
  try {
    await deleteWorkspaceStyle(workspaceId.value, style.id)
    selectedStyleIds.value = selectedStyleIds.value.filter(id => id !== style.id)
    await loadStyles()
    Message.success('样式已删除。')
  } catch (error) {
    Message.error(getErrorMessage(error, '删除样式失败。'))
  }
}

/**
 * 格式化菜单模式展示文本。
 */
function formatMenuMode(mode: ProjectMenuMode): string {
  if (mode === 'bottom-preview') return '底部缩略图'
  if (mode === 'text') return '文本菜单'
  return '侧边缩略图'
}
</script>

