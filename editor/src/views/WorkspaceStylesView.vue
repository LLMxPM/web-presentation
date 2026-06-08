<!-- 文件功能：提供工作空间级样式库管理页面，维护可复制到项目的展示配置与 Markdown 样式规范。 -->
<template>
  <div data-testid="workspace-styles-view" class="flex h-full min-h-0 flex-col gap-4">
    <input
      ref="importFileInputRef"
      class="hidden"
      type="file"
      accept=".zip,application/zip"
      @change="handleImportFileSelected"
    >
    <PageTitleBar
      class="shrink-0"
      :title="workspaceTitle"
      description="集中维护可复用的项目展示配置、主题引用和内容助手样式规范。"
    >
      <template #actions>
        <BaseButton
          variant="ghost"
          :disabled="!workspaceId || importValidatePending || importPackagePending"
          @click="openImportFilePicker"
        >
          <Upload class="h-3.5 w-3.5" />
          导入样式
        </BaseButton>
        <BaseButton
          variant="ghost"
          :disabled="!workspaceId || selectedStyleIds.length === 0 || exportPackagePending"
          :loading="exportPackagePending"
          @click="handleExportSelectedStyles"
        >
          <Download class="h-3.5 w-3.5" />
          导出样式
        </BaseButton>
        <BaseButton variant="ghost" :disabled="loading" @click="loadStyles">
          <RefreshCw class="h-3.5 w-3.5" />
          刷新
        </BaseButton>
        <BaseButton :disabled="!workspaceId" @click="openCreateStyle">
          <Plus class="h-3.5 w-3.5" />
          新建样式
        </BaseButton>
      </template>
    </PageTitleBar>

    <div class="min-h-0 flex-1 overflow-hidden">
      <section class="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <header class="flex shrink-0 items-center justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h2 class="text-base font-black text-slate-900">样式库</h2>
              <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-black text-slate-500">
                共 {{ styleTotal }} 个样式
              </span>
              <span
                v-if="selectedStyleIds.length"
                class="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-black text-indigo-600"
              >
                已选 {{ selectedStyleIds.length }} 个
              </span>
            </div>
            <p class="mt-1 text-xs text-slate-400">可编辑、复制、导出或查看样式详情；编辑样式不会影响已配置项目。</p>
          </div>
        </header>

        <div class="shrink-0 border-b border-slate-100 bg-slate-50/70 px-5 py-3">
          <label class="flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-500 focus-within:border-indigo-400">
            <Search class="h-4 w-4 text-slate-400" />
            <input
              v-model="keyword"
              class="min-w-0 flex-1 bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
              placeholder="搜索样式名称、key"
              @keydown.enter="loadStyles"
            >
          </label>
        </div>

        <div v-if="loading" class="flex flex-1 items-center justify-center text-sm font-semibold text-slate-400">
          正在加载样式...
        </div>
        <div v-else class="min-h-0 flex-1 overflow-y-auto p-5">
          <div
            v-if="styles.length === 0"
            class="flex min-h-[160px] flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-100 bg-slate-50 text-center"
          >
            <Palette class="mb-3 h-10 w-10 text-slate-300" />
            <p class="text-sm font-semibold text-slate-500">{{ keyword ? '未找到相关样式' : '暂无样式' }}</p>
          </div>

          <div v-else class="grid gap-4">
            <article
              v-for="style in styles"
              :key="style.id"
              class="group rounded-lg border border-slate-200 p-5 transition-all hover:border-indigo-200 hover:shadow-md"
            >
              <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(380px,520px)]">
                <div class="min-w-0">
                  <div class="flex items-start justify-between gap-3">
                    <div class="flex min-w-0 items-start gap-3">
                      <label
                        class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border border-slate-300 bg-white"
                        title="选择导出样式"
                        @click.stop
                      >
                        <input
                          class="h-3.5 w-3.5 accent-indigo-600"
                          type="checkbox"
                          :aria-label="`选择导出 ${style.name}`"
                          :checked="isStyleSelected(style)"
                          @change="toggleStyleSelection(style)"
                        >
                      </label>
                      <div class="min-w-0">
                        <h3 class="truncate text-base font-black text-slate-900">{{ style.name }}</h3>
                        <p class="mt-0.5 truncate font-mono text-xs text-slate-400">{{ style.key }}</p>
                      </div>
                    </div>
                  </div>
                  <p class="mt-3 line-clamp-2 text-sm leading-5 text-slate-500">{{ style.description || '未填写样式说明。' }}</p>
                  <p v-if="style.style_spec_markdown" class="mt-3 line-clamp-2 text-xs leading-5 text-slate-400">
                    {{ style.style_spec_markdown }}
                  </p>
                </div>

                <div class="flex flex-col gap-3">
                  <div class="flex justify-end gap-1 opacity-80 transition-opacity group-hover:opacity-100">
                    <button
                      type="button"
                      class="style-icon-button"
                      title="详情"
                      :aria-label="`查看 ${style.name} 详情`"
                      @click.stop="openStyleDetailDialog(style)"
                    >
                      <Info class="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      class="style-icon-button"
                      title="建议组件"
                      :aria-label="`管理 ${style.name} 建议组件`"
                      @click.stop="openSuggestedComponentsDialog(style)"
                    >
                      <Layers class="h-4 w-4" />
                    </button>
                    <button type="button" class="style-icon-button" title="编辑" @click.stop="openEditStyle(style)">
                      <Pencil class="h-4 w-4" />
                    </button>
                    <button type="button" class="style-icon-button" title="复制" @click.stop="copyStyle(style)">
                      <Copy class="h-4 w-4" />
                    </button>
                    <button type="button" class="style-icon-button-danger" title="删除" @click.stop="deleteStyle(style)">
                      <Trash2 class="h-4 w-4" />
                    </button>
                  </div>
                  <div class="grid grid-cols-2 gap-2 text-xs font-semibold text-slate-500 sm:grid-cols-4 xl:grid-cols-2">
                    <span class="rounded-lg bg-slate-50 px-2.5 py-2">{{ style.page_width }} x {{ style.page_height }}</span>
                    <span class="rounded-lg bg-slate-50 px-2.5 py-2">字号 {{ style.base_font_size }}</span>
                    <span class="rounded-lg bg-slate-50 px-2.5 py-2">描边 {{ style.icon_default_stroke_width }}</span>
                    <span class="rounded-lg bg-slate-50 px-2.5 py-2">{{ formatMenuMode(style.menu_mode) }}</span>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>
    </div>

    <WorkspaceStyleEditorDialog
      v-model="editorVisible"
      :workspace-id="workspaceId"
      :style="editingStyle ?? null"
      :default-theme-key="workspaceDetails?.default_theme_key"
      :loading="saving"
      @save="saveStyle"
    />

    <WorkspaceStyleDetailDialog
      v-model="styleDetailVisible"
      :workspace-id="workspaceId"
      :style="selectedStyle ?? null"
      :default-theme-key="workspaceDetails?.default_theme_key"
      @edit="openEditStyle"
    />

    <WorkspaceStyleSuggestedComponentsDialog
      v-model="suggestedComponentsDialogVisible"
      :workspace-id="workspaceId"
      :style="suggestedComponentsStyle ?? null"
      @saved="handleSuggestedComponentsSaved"
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

    <BaseDialog v-model="importDialogVisible" title="导入样式" size="standard">
      <div class="space-y-4">
        <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p class="text-sm font-bold text-slate-700">{{ importFile?.name || '未选择文件' }}</p>
          <p v-if="importValidation" class="mt-1 text-xs text-slate-500">
            样式 {{ importValidation.styles.length }} 个，组件 {{ importValidation.components.length }} 个，主题 {{ importValidation.themes.length }} 个，资源 {{ importValidation.assets.length }} 个，字体 {{ importValidation.fonts.length }} 个
          </p>
          <p v-else-if="importValidatePending" class="mt-1 text-xs text-slate-500">正在预检样式离线包...</p>
        </div>

        <div v-if="importValidation?.errors.length" class="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3">
          <p class="mb-2 text-sm font-bold text-rose-700">预检未通过，请修改或删除相应资源后重试</p>
          <ul class="space-y-1 text-xs leading-5 text-rose-700">
            <li v-for="error in importValidation.errors" :key="error">{{ error }}</li>
          </ul>
        </div>

        <div v-if="importValidation?.warnings.length" class="rounded-xl border border-amber-100 bg-amber-50 px-4 py-3">
          <p class="mb-2 text-sm font-bold text-amber-800">包内提示</p>
          <ul class="space-y-1 text-xs leading-5 text-amber-800">
            <li v-for="warning in importValidation.warnings" :key="warning">{{ warning }}</li>
          </ul>
        </div>

        <div v-if="importValidation" class="space-y-3">
          <section class="rounded-xl border border-slate-200 bg-white p-4">
            <h4 class="text-sm font-bold text-slate-700">样式</h4>
            <div class="mt-2 max-h-40 space-y-2 overflow-y-auto">
              <div v-for="style in importValidation.styles" :key="style.key" class="flex items-center justify-between gap-3 text-xs">
                <span class="font-semibold text-slate-700">{{ style.name }}</span>
                <span class="flex shrink-0 items-center gap-2">
                  <span class="font-mono text-slate-400">{{ style.key }}</span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[11px] font-bold ring-1"
                    :class="resolveImportActionBadgeClass(style.action)"
                  >
                    {{ resolveImportActionText(style.action) }}
                  </span>
                  <button
                    type="button"
                    class="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] font-semibold text-slate-500 hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-600"
                    @click="openImportStyleSpec(style)"
                  >
                    查看规范
                  </button>
                </span>
              </div>
            </div>
          </section>

          <section class="grid gap-3 lg:grid-cols-2">
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">组件</h4>
              <div class="mt-2 max-h-40 overflow-y-auto rounded-lg border border-slate-100 text-xs text-slate-500">
                <p v-if="importValidation.components.length === 0" class="px-3 py-2">无组件</p>
                <div
                  v-for="component in importValidation.components"
                  :key="`${component.source_component_code}-${component.source_version_no}`"
                  class="border-b border-slate-100 px-3 py-2.5 last:border-b-0 even:bg-slate-50/60"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div class="min-w-0 flex items-baseline gap-2">
                      <span class="truncate font-semibold text-slate-700">{{ component.name }}</span>
                      <span class="shrink-0 font-mono text-[11px] text-slate-400">{{ component.import_name }}</span>
                    </div>
                    <span
                      class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1"
                      :class="resolveImportActionBadgeClass(component.action)"
                      :title="component.match_reason || resolveImportActionText(component.action)"
                    >
                      {{ resolveImportActionText(component.action) }}
                    </span>
                  </div>
                  <div class="mt-1 flex min-w-0 items-center gap-2 text-[11px] text-slate-400">
                    <span class="font-mono">fp: {{ formatFingerprint(component.component_fingerprint) }}</span>
                    <span v-if="component.matched_component_code" class="truncate">
                      匹配 {{ component.matched_component_code }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">主题</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-slate-500">
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
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">资源</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-slate-500">
                <p v-if="importValidation.assets.length === 0">无资源</p>
                <div v-for="asset in importValidation.assets" :key="asset.name" class="flex items-center justify-between gap-2">
                  <span class="flex min-w-0 items-center gap-1.5">
                    <span class="truncate">{{ asset.name }}</span>
                    <span class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500">
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
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">字体</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-slate-500">
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
        <BaseButton variant="ghost" @click="closeImportDialog">取消</BaseButton>
        <BaseButton
          variant="primary"
          :disabled="!importValidation?.valid || !importFile"
          :loading="importPackagePending"
          @click="handleConfirmImportPackage"
        >
          确认导入
        </BaseButton>
      </template>
    </BaseDialog>

    <BaseDialog
      v-model="importStyleSpecDialogVisible"
      :title="selectedImportStyleSpec ? `${selectedImportStyleSpec.name} · 最终导入规范` : '最终导入规范'"
      size="standard"
    >
      <div class="space-y-3">
        <div class="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs">
          <span class="min-w-0 truncate font-semibold text-slate-700">{{ selectedImportStyleSpec?.key }}</span>
          <span
            v-if="selectedImportStyleSpec"
            class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1"
            :class="resolveImportActionBadgeClass(selectedImportStyleSpec.action)"
          >
            {{ resolveImportActionText(selectedImportStyleSpec.action) }}
          </span>
        </div>
        <section v-if="selectedImportStyleSpec" class="rounded-xl border border-slate-200 bg-white p-4">
          <h4 class="text-sm font-black text-slate-900">展示配置</h4>
          <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div
              v-for="item in importStyleSpecDetailItems"
              :key="item.label"
              class="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
            >
              <p class="text-[11px] font-bold text-slate-400">{{ item.label }}</p>
              <p class="mt-1 text-sm font-black text-slate-800">{{ item.value }}</p>
            </div>
          </div>
        </section>
        <pre class="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-700">{{ selectedImportStyleSpec?.style_spec_markdown || '无样式规范' }}</pre>
      </div>
    </BaseDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Copy, Download, Info, Layers, Palette, Pencil, Plus, RefreshCw, Search, Trash2, Upload } from '@lucide/vue'

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
import PageTitleBar from '@/components/layout/PageTitleBar.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import ExportPackageAssetsDialog from '@/components/project/ExportPackageAssetsDialog.vue'
import WorkspaceStyleDetailDialog from '@/components/project/WorkspaceStyleDetailDialog.vue'
import WorkspaceStyleEditorDialog from '@/components/project/WorkspaceStyleEditorDialog.vue'
import WorkspaceStyleSuggestedComponentsDialog from '@/components/project/WorkspaceStyleSuggestedComponentsDialog.vue'
import type {
  AssetResponse,
  ProjectMenuMode,
  SuggestedComponentItem,
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
const keyword = ref('')
const styleTotal = ref(0)
const loading = ref(false)
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
const styleDetailVisible = ref(false)
const suggestedComponentsDialogVisible = ref(false)
const suggestedComponentsStyle = ref<WorkspaceStyleItem | null>(null)

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

watch(
  workspaceId,
  () => {
    selectedStyle.value = null
    void loadWorkspace()
    void loadStyles()
  },
)

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
 * 加载样式列表。
 */
async function loadStyles(): Promise<void> {
  if (!workspaceId.value) {
    styles.value = []
    return
  }
  loading.value = true
  try {
    const response = await listWorkspaceStyles(workspaceId.value, {
      page: 1,
      page_size: 100,
      keyword: keyword.value.trim() || undefined,
    })
    styles.value = response.items
    styleTotal.value = response.total
    syncSelectedStyleIds()
  } catch (error) {
    Message.error(getErrorMessage(error, '加载样式列表失败。'))
  } finally {
    loading.value = false
  }
}

/**
 * 打开新建样式弹窗。
 */
function openCreateStyle(): void {
  editingStyle.value = null
  editorVisible.value = true
}

/**
 * 打开编辑样式弹窗。
 */
function openEditStyle(style: WorkspaceStyleItem): void {
  editingStyle.value = style
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
 * 打开样式建议组件管理弹窗。
 * @param style 当前样式
 */
function openSuggestedComponentsDialog(style: WorkspaceStyleItem): void {
  suggestedComponentsStyle.value = style
  suggestedComponentsDialogVisible.value = true
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
 * 列表刷新后移除已经不可见的导出选择。
 */
function syncSelectedStyleIds(): void {
  const visibleStyleIds = new Set(styles.value.map(style => style.id))
  selectedStyleIds.value = selectedStyleIds.value.filter(id => visibleStyleIds.has(id))
}

/**
 * 下载当前勾选样式的离线包。
 */
async function handleExportSelectedStyles(): Promise<void> {
  if (!workspaceId.value || selectedStyleIds.value.length === 0) {
    return
  }
  exportPackagePending.value = true
  try {
    exportManualAssetNames.value = []
    const validation = await validateWorkspaceStylePackageExport(workspaceId.value, {
      style_ids: selectedStyleIds.value,
      manual_asset_names: [],
    })
    exportValidation.value = validation
    if (!shouldConfirmExport(validation)) {
      await downloadSelectedStylePackage([])
      Message.success('样式离线包已生成。')
      return
    }
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
 * 判断样式导出预检结果是否需要用户确认。
 * @param validation 导出预检结果
 */
function shouldConfirmExport(validation: WorkspaceStyleExportValidationResult): boolean {
  return (
    validation.warnings.length > 0
    || validation.dynamic_resource_components.length > 0
    || validation.missing_static_asset_names.length > 0
    || validation.missing_manual_asset_names.length > 0
  )
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
 * 在确认弹窗中继续导出样式离线包。
 */
async function handleConfirmExportPackage(): Promise<void> {
  if (!workspaceId.value || selectedStyleIds.value.length === 0) {
    return
  }
  exportPackagePending.value = true
  try {
    await downloadSelectedStylePackage(exportManualAssetNames.value)
    exportDialogVisible.value = false
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
  if (action === 'overwrite') return 'bg-amber-50 text-amber-700 ring-amber-200'
  if (action === 'reuse') return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  if (action === 'conflict') return 'bg-rose-50 text-rose-700 ring-rose-200'
  return 'bg-sky-50 text-sky-700 ring-sky-200'
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
 * 创建或更新样式。
 */
async function saveStyle(payload: WorkspaceStyleEditorSavePayload): Promise<void> {
  if (!workspaceId.value) {
    return
  }
  const { suggested_component_ids: suggestedComponentIds, ...stylePayload } = payload
  saving.value = true
  try {
    const savedStyle = editingStyle.value
      ? await updateWorkspaceStyle(workspaceId.value, editingStyle.value.id, stylePayload)
      : await createWorkspaceStyle(workspaceId.value, stylePayload)
    if (suggestedComponentIds) {
      await updateWorkspaceStyleSuggestedComponents(workspaceId.value, savedStyle.id, suggestedComponentIds)
    }
    editorVisible.value = false
    editingStyle.value = null
    await loadStyles()
    Message.success('样式已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存样式失败。'))
  } finally {
    saving.value = false
  }
}

/**
 * 复制样式。
 */
async function copyStyle(style: WorkspaceStyleItem): Promise<void> {
  if (!workspaceId.value) {
    return
  }
  try {
    await copyWorkspaceStyle(workspaceId.value, style.id)
    await loadStyles()
    Message.success('样式已复制。')
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
    await loadStyles()
    Message.success('样式已删除。')
  } catch (error) {
    Message.error(getErrorMessage(error, '删除样式失败。'))
  }
}

/**
 * 建议组件保存后保留当前列表，仅关闭弹窗并给出轻量提示。
 * @param _items 后端返回的建议组件摘要
 */
function handleSuggestedComponentsSaved(_items: SuggestedComponentItem[]): void {
  suggestedComponentsStyle.value = null
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

<style scoped>
.style-icon-button,
.style-icon-button-danger {
  display: inline-flex;
  height: 2rem;
  width: 2rem;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  color: rgb(100 116 139);
  transition: all 0.18s ease;
}

.style-icon-button:hover {
  background: rgb(238 242 255);
  color: rgb(79 70 229);
}

.style-icon-button-danger:hover {
  background: rgb(255 241 242);
  color: rgb(225 29 72);
}
</style>

