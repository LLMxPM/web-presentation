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
      :style="editingStyle"
      :default-theme-key="workspaceDetails?.default_theme_key"
      :loading="saving"
      @save="saveStyle"
    />

    <WorkspaceStyleDetailDialog
      v-model="styleDetailVisible"
      :style="selectedStyle"
      @edit="openEditStyle"
    />

    <BaseDialog v-model="importDialogVisible" title="导入样式" width="760px">
      <div class="space-y-4">
        <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p class="text-sm font-bold text-slate-700">{{ importFile?.name || '未选择文件' }}</p>
          <p v-if="importValidation" class="mt-1 text-xs text-slate-500">
            样式 {{ importValidation.styles.length }} 个，主题 {{ importValidation.themes.length }} 个，资源 {{ importValidation.assets.length }} 个，字体 {{ importValidation.fonts.length }} 个
          </p>
          <p v-else-if="importValidatePending" class="mt-1 text-xs text-slate-500">正在预检样式离线包...</p>
        </div>

        <div v-if="importValidation?.errors.length" class="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3">
          <p class="mb-2 text-sm font-bold text-rose-700">预检未通过</p>
          <ul class="space-y-1 text-xs leading-5 text-rose-700">
            <li v-for="error in importValidation.errors" :key="error">{{ error }}</li>
          </ul>
        </div>

        <div v-if="importValidation && importValidation.valid" class="space-y-3">
          <section class="rounded-xl border border-slate-200 bg-white p-4">
            <h4 class="text-sm font-bold text-slate-700">样式</h4>
            <div class="mt-2 max-h-40 space-y-2 overflow-y-auto">
              <div v-for="style in importValidation.styles" :key="style.key" class="flex items-center justify-between gap-3 text-xs">
                <span class="font-semibold text-slate-700">{{ style.name }}</span>
                <span class="font-mono text-slate-400">{{ style.key }} · {{ resolveImportActionText(style.action) }}</span>
              </div>
            </div>
          </section>

          <section class="grid gap-3 lg:grid-cols-3">
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">主题</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-slate-500">
                <p v-if="importValidation.themes.length === 0">无主题</p>
                <p v-for="theme in importValidation.themes" :key="theme.key">
                  {{ theme.name }} · {{ resolveImportActionText(theme.action) }}
                </p>
              </div>
            </div>
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">资源</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-slate-500">
                <p v-if="importValidation.assets.length === 0">无资源</p>
                <p v-for="asset in importValidation.assets" :key="asset.name">
                  {{ asset.name }} · {{ resolveImportActionText(asset.action) }}
                </p>
              </div>
            </div>
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">字体</h4>
              <div class="mt-2 max-h-32 space-y-1 overflow-y-auto text-xs text-slate-500">
                <p v-if="importValidation.fonts.length === 0">无字体</p>
                <p v-for="font in importValidation.fonts" :key="font.asset_name">
                  {{ font.asset_name }} · {{ resolveImportActionText(font.action) }}
                </p>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Copy, Download, Info, Palette, Pencil, Plus, RefreshCw, Search, Trash2, Upload } from '@lucide/vue'

import { getWorkspace } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import {
  copyWorkspaceStyle,
  createWorkspaceStyle,
  deleteWorkspaceStyle,
  exportWorkspaceStylePackage,
  importWorkspaceStylePackage,
  listWorkspaceStyles,
  updateWorkspaceStyle,
  validateWorkspaceStylePackageImport,
  type WorkspaceStylePayload,
} from '@/api/styles'
import PageTitleBar from '@/components/layout/PageTitleBar.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import WorkspaceStyleDetailDialog from '@/components/project/WorkspaceStyleDetailDialog.vue'
import WorkspaceStyleEditorDialog from '@/components/project/WorkspaceStyleEditorDialog.vue'
import type { ProjectMenuMode, WorkspaceItem, WorkspaceStyleImportValidationResult, WorkspaceStyleItem } from '@/types/api'
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
const importValidatePending = ref(false)
const importPackagePending = ref(false)
const importDialogVisible = ref(false)
const importFileInputRef = ref<HTMLInputElement | null>(null)
const importFile = ref<File | null>(null)
const importValidation = ref<WorkspaceStyleImportValidationResult | null>(null)
const editorVisible = ref(false)
const editingStyle = ref<WorkspaceStyleItem | null>(null)
const styleDetailVisible = ref(false)

const workspaceTitle = computed(() => workspaceDetails.value?.name ? `${workspaceDetails.value.name} · 样式库` : '样式库')

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
    const { blob, filename } = await exportWorkspaceStylePackage(workspaceId.value, {
      style_ids: selectedStyleIds.value,
    })
    downloadBlob(blob, filename)
    Message.success('样式离线包已生成。')
  } catch (error) {
    Message.error(`导出样式失败：${getErrorMessage(error, '未知原因')}`)
  } finally {
    exportPackagePending.value = false
  }
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
 * 关闭导入弹窗并清理临时文件状态。
 */
function closeImportDialog(): void {
  importDialogVisible.value = false
  importFile.value = null
  importValidation.value = null
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
  return action === 'reuse' ? '复用' : '新增'
}

/**
 * 创建或更新样式。
 */
async function saveStyle(payload: WorkspaceStylePayload): Promise<void> {
  if (!workspaceId.value) {
    return
  }
  saving.value = true
  try {
    if (editingStyle.value) {
      await updateWorkspaceStyle(workspaceId.value, editingStyle.value.id, payload)
    } else {
      await createWorkspaceStyle(workspaceId.value, payload)
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
