<!-- 文件功能：提供工作空间级主题与字体管理页面，统一维护主题库、主题详情和字体注册。 -->
<template>
  <div data-testid="themes-view" class="flex h-full min-h-0 flex-col gap-2">
    <PageHeader
      class="shrink-0"
      :icon="SwatchBook"
      :title="workspaceTitle"
      description="集中维护工作空间主题、字体注册与字体文件。"
    >
      <template #actions>
        <UiButton variant="secondary" :disabled="loadingThemes || loadingFonts" @click="reloadAll">
          <RefreshCw class="h-3.5 w-3.5" />
          刷新
        </UiButton>
      </template>
    </PageHeader>

    <div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_380px] gap-2 overflow-hidden">
      <section class="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
        <header class="flex shrink-0 items-center justify-between gap-4 border-b border-border-muted px-5 py-4">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h2 class="text-base font-black text-text-strong">主题库</h2>
              <span class="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-black text-text-muted">
                共 {{ themeTotal }} 个主题
              </span>
            </div>
          </div>
          <UiButton size="sm" @click="openCreateTheme">
            <Plus class="h-3.5 w-3.5" />
            新建主题
          </UiButton>
        </header>

        <div class="shrink-0 border-b border-border-muted px-5 py-3">
          <SimpleSearchBar
            v-model="themeKeyword"
            placeholder="搜索主题名称、key"
            aria-label="搜索主题名称、key"
            @submit="loadThemes"
          />
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          <DataState
            :state="themeDataState"
            :title="themeDataState === 'empty' ? (themeKeyword ? '未找到相关主题' : '暂无主题') : undefined"
          >
          <div class="grid gap-3 2xl:grid-cols-2">
            <article
              v-for="theme in themes"
              :key="theme.id"
              class="group cursor-pointer rounded-xl border p-3 transition-all hover:shadow-md"
              :class="isDefaultTheme(theme) ? 'ring-2 ring-accent-muted' : ''"
              :style="getThemeCardStyle(theme)"
              @click="openThemeDetail(theme)"
            >
              <div class="flex items-start justify-between gap-2.5">
                <div class="min-w-0">
                  <div class="flex min-w-0 items-center gap-2">
                    <h3 class="truncate text-base font-black" :style="{ color: theme.palette.text.primary }">{{ theme.name }}</h3>
                    <span
                      v-if="isDefaultTheme(theme)"
                      class="shrink-0 rounded-full border border-accent-muted bg-surface-selected px-2 py-0.5 text-[10px] font-black text-accent"
                    >
                      默认
                    </span>
                  </div>
                  <p class="mt-0.5 truncate font-mono text-xs opacity-70" :style="{ color: theme.palette.text.secondary }">{{ theme.key }}</p>
                </div>

                <div class="flex shrink-0 items-center gap-1 opacity-70 transition-opacity group-hover:opacity-100">
                  <UiIconButton
                    v-if="!isDefaultTheme(theme)"
                    label="设为默认"
                    size="sm"
                    variant="ghost"
                    @click.stop="setDefaultTheme(theme)"
                  >
                    <Pin class="h-3.5 w-3.5" />
                  </UiIconButton>
                  <UiIconButton
                    label="编辑"
                    size="sm"
                    variant="ghost"
                    @click.stop="openEditTheme(theme)"
                  >
                    <Pencil class="h-3.5 w-3.5" />
                  </UiIconButton>
                  <UiIconButton
                    label="复制"
                    size="sm"
                    variant="ghost"
                    @click.stop="copyTheme(theme)"
                  >
                    <Copy class="h-3.5 w-3.5" />
                  </UiIconButton>
                  <UiIconButton
                    label="删除"
                    size="sm"
                    variant="danger"
                    @click.stop="deleteTheme(theme)"
                  >
                    <Trash2 class="h-3.5 w-3.5" />
                  </UiIconButton>
                </div>
              </div>

              <p class="mt-2 line-clamp-1 text-sm leading-5" :style="{ color: theme.palette.text.secondary }">
                {{ theme.description || '未填写主题说明。' }}
              </p>

              <div class="mt-3 grid grid-cols-3 gap-2 text-xs">
                <div class="rounded-lg p-2" :style="getThemeMetaBlockStyle(theme)">
                  <p class="opacity-65" :style="{ color: theme.palette.text.secondary }">标题字体</p>
                  <p class="mt-0.5 truncate font-bold" :style="{ color: theme.palette.text.primary }">
                    {{ getThemeFontLabel(theme, 'heading') }}
                    <span v-if="isThemeFontFallback(theme, 'heading')" class="text-[10px] opacity-60">回退</span>
                  </p>
                </div>
                <div class="rounded-lg p-2" :style="getThemeMetaBlockStyle(theme)">
                  <p class="opacity-65" :style="{ color: theme.palette.text.secondary }">正文字体</p>
                  <p class="mt-0.5 truncate font-bold" :style="{ color: theme.palette.text.primary }">
                    {{ getThemeFontLabel(theme, 'body') }}
                    <span v-if="isThemeFontFallback(theme, 'body')" class="text-[10px] opacity-60">回退</span>
                  </p>
                </div>
                <div class="rounded-lg p-2" :style="getThemeMetaBlockStyle(theme)">
                  <p class="opacity-65" :style="{ color: theme.palette.text.secondary }">代码字体</p>
                  <p class="mt-0.5 truncate font-bold" :style="{ color: theme.palette.text.primary }">
                    {{ getThemeFontLabel(theme, 'code') }}
                    <span v-if="isThemeFontFallback(theme, 'code')" class="text-[10px] opacity-60">回退</span>
                  </p>
                </div>
              </div>

              <div class="mt-3 flex items-center justify-between gap-3">
                <div class="flex min-w-0 flex-1 gap-1.5">
                  <span
                    v-for="(color, index) in getThemeAccentColors(theme)"
                    :key="`${theme.id}-${color}-${index}`"
                    class="h-6 min-w-0 flex-1 rounded-md border shadow-sm"
                    :style="{ backgroundColor: color, borderColor: theme.palette.border.subtle }"
                  ></span>
                </div>
                <span class="inline-flex shrink-0 items-center gap-1 text-xs font-bold opacity-70 transition-opacity group-hover:opacity-100" :style="{ color: theme.palette.link.default }">
                  详情
                  <ChevronRight class="h-3.5 w-3.5" />
                </span>
              </div>
            </article>
          </div>
          </DataState>
        </div>

        <PaginationControl
          :page="themePage"
          :page-size="themePageSize"
          :total="themeTotal"
          :page-size-options="[10, 20, 50, 100]"
          @update:page="themePage = $event"
          @update:page-size="handleThemePageSizeChange"
        />
      </section>

      <aside class="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-sm">
        <header class="shrink-0 border-b border-border-muted px-4 py-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <h2 class="text-base font-black text-text-strong">字体管理</h2>
                <span class="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-black text-text-muted">
                  共 {{ fontFamilyTotal }} 个字体族
                </span>
              </div>
              <p class="mt-1 text-xs text-text-disabled">上传后自动注册并归入字体族，同族多字重会自动匹配。</p>
            </div>
            <div class="flex shrink-0 items-center gap-1">
              <UiButton size="sm" :disabled="!workspaceId || uploadingFontAsset" @click="triggerFontUpload">
                <Upload class="h-3.5 w-3.5" />
                {{ uploadingFontAsset ? '上传中' : '上传字体' }}
              </UiButton>
              <input
                ref="fontFileInput"
                type="file"
                class="hidden"
                :accept="ASSET_UPLOAD_ACCEPT.font"
                multiple
                @change="handleFontFileChange"
              />
              <input
                ref="fontReplaceFileInput"
                type="file"
                class="hidden"
                :accept="ASSET_UPLOAD_ACCEPT.font"
                @change="handleFontReplaceFileChange"
              />
              <input
                ref="fontAddFileInput"
                data-testid="font-add-file-input"
                type="file"
                class="hidden"
                :accept="ASSET_UPLOAD_ACCEPT.font"
                multiple
                @change="handleAddFaceFileChange"
              />
            </div>
          </div>
        </header>

        <div class="shrink-0 border-b border-border-muted bg-canvas/70 px-4 py-3">
          <SimpleSearchBar v-model="fontKeyword" placeholder="搜索字体族名称" />
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto p-4">
          <DataState
            :state="fontDataState"
            :title="fontDataState === 'empty' ? (fontKeyword ? '未找到相关字体族' : '暂无字体，上传字体文件即可使用') : undefined"
          >
            <div class="space-y-4">
              <section v-if="pendingFontAssets.length" class="space-y-2">
                <h3 class="text-xs font-black text-warning-strong">待注册字体文件</h3>
                <article
                  v-for="asset in pendingFontAssets"
                  :key="`pending-${asset.id}`"
                  class="group rounded-xl border border-warning-muted bg-surface p-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div class="min-w-0">
                      <h4 class="truncate text-sm font-bold text-text">{{ asset.original_name }}</h4>
                      <p class="mt-0.5 text-[11px] text-text-disabled">{{ formatFontFileSize(asset.file_size) }}</p>
                    </div>
                    <div class="flex shrink-0 gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                      <UiIconButton label="完成注册" size="sm" variant="ghost" @click="openPendingFontEditor(asset)">
                        <Pencil class="h-3.5 w-3.5" />
                      </UiIconButton>
                      <UiIconButton label="删除字体文件" size="sm" variant="danger" @click="deletePendingFontAsset(asset)">
                        <Trash2 class="h-3.5 w-3.5" />
                      </UiIconButton>
                    </div>
                  </div>
                </article>
              </section>

              <article
                v-for="family in fontFamilies"
                :key="family.id"
                class="group/family rounded-xl border border-border bg-surface p-3 transition-colors hover:border-accent-ring"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0 flex-1">
                    <div v-if="renamingFamilyId === family.id" class="flex items-center gap-1.5">
                      <UiInput
                        v-model="renameFamilyValue"
                        class="h-8"
                        placeholder="字体族名称"
                        @keyup.enter="confirmRenameFamily(family)"
                      />
                      <UiIconButton label="保存" size="sm" variant="ghost" :disabled="savingFamily" @click="confirmRenameFamily(family)">
                        <Check class="h-3.5 w-3.5" />
                      </UiIconButton>
                      <UiIconButton label="取消" size="sm" variant="ghost" @click="cancelRenameFamily">
                        <X class="h-3.5 w-3.5" />
                      </UiIconButton>
                    </div>
                    <div v-else class="flex items-center gap-1.5">
                      <h3 class="truncate text-sm font-black text-text">{{ family.name }}</h3>
                      <span class="shrink-0 rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] font-bold text-text-muted">
                        {{ family.faces.length }} 个文件
                      </span>
                      <UiIconButton
                        label="重命名字体族"
                        size="sm"
                        variant="ghost"
                        class="opacity-0 transition-opacity focus-visible:opacity-100 group-hover/family:opacity-100"
                        @click="startRenameFamily(family)"
                      >
                        <Pencil class="h-3 w-3" />
                      </UiIconButton>
                    </div>
                  </div>
                  <UiIconButton
                    label="添加字体文件"
                    size="sm"
                    variant="ghost"
                    class="shrink-0 opacity-0 transition-opacity focus-visible:opacity-100 group-hover/family:opacity-100"
                    :disabled="uploadingFontAsset"
                    @click="triggerAddFaceToFamily(family)"
                  >
                    <Plus class="h-3.5 w-3.5" />
                  </UiIconButton>
                </div>

                <div class="mt-3 space-y-2">
                  <div
                    v-for="face in family.faces"
                    :key="face.id"
                    class="group/face rounded-lg border border-border-muted bg-canvas/60 p-2.5"
                  >
                    <div class="flex items-center justify-between gap-2">
                      <div class="min-w-0">
                        <p class="truncate font-mono text-[11px] text-text">{{ face.asset_name }}</p>
                        <p class="mt-0.5 text-[11px] font-semibold text-text-muted">
                          {{ face.font_format }} · {{ face.font_weight }} · {{ face.font_style }}
                          <span v-if="face.status !== 'active'" class="text-text-disabled">· 已停用</span>
                        </p>
                      </div>
                      <div class="flex shrink-0 gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover/face:opacity-100">
                        <UiIconButton label="编辑字体" size="sm" variant="ghost" @click="openFaceEditor(face)">
                          <Pencil class="h-3.5 w-3.5" />
                        </UiIconButton>
                        <UiIconButton label="替换字体文件" size="sm" variant="ghost" @click="triggerReplaceFace(face)">
                          <RefreshCw class="h-3.5 w-3.5" />
                        </UiIconButton>
                        <UiIconButton label="删除字体" size="sm" variant="danger" @click="deleteFace(family, face)">
                          <Trash2 class="h-3.5 w-3.5" />
                        </UiIconButton>
                      </div>
                    </div>
                    <div class="mt-2 rounded-md bg-canvas p-2 text-text" :style="getFacePreviewStyle(face)">
                      <div class="text-lg">永字八法 AaBbGg 0123</div>
                    </div>
                  </div>
                </div>
              </article>
            </div>
          </DataState>
        </div>

        <PaginationControl
          compact
          :page="fontFamilyPage"
          :page-size="fontFamilyPageSize"
          :total="fontFamilyTotal"
          :page-size-options="[10, 20, 50, 100]"
          @update:page="fontFamilyPage = $event"
          @update:page-size="handleFontFamilyPageSizeChange"
        />
      </aside>
    </div>

    <ThemeDetailDialog
      v-model="themeDetailVisible"
      :workspace-id="workspaceId"
      :theme-id="detailThemeId"
      :default-theme-key="workspace?.default_theme_key"
      @set-default="setDefaultTheme"
    />

    <ThemeEditorDialog
      v-model="themeEditorVisible"
      :workspace-id="workspaceId"
      :theme="editingTheme"
      :saving="savingTheme"
      @save="saveTheme"
    />

    <FontEditorDialog
      v-model="fontEditorVisible"
      :editing-font="editorFont"
      :asset="editorAsset"
      :preset-family-name="editorPresetFamilyName"
      :saving="savingFont"
      @save="saveFont"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, type CSSProperties } from 'vue'
import { useRoute } from 'vue-router'
import {
  Check,
  ChevronRight,
  Copy,
  Pencil,
  Pin,
  Plus,
  RefreshCw,
  SwatchBook,
  Trash2,
  Upload,
  X,
} from '@lucide/vue'

import {
  createWorkspaceFont,
  deleteWorkspaceFontAsset,
  deleteWorkspaceFont,
  listWorkspaceAssets,
  listWorkspaceFontFamilies,
  renameWorkspaceFontFamily,
  replaceWorkspaceAssetFile,
  updateWorkspaceFont,
  uploadWorkspaceAsset,
} from '@/api/assets'
import { getWorkspace, updateWorkspace } from '@/api/catalog'
import { getErrorCode, getErrorMessage } from '@/api/http'
import { copyWorkspaceTheme, createWorkspaceTheme, deleteWorkspaceTheme, listWorkspaceThemes, updateWorkspaceTheme } from '@/api/themes'
import type { WorkspaceThemePayload } from '@/api/themes'
import DataState from '@/components/patterns/DataState.vue'
import PageHeader from '@/components/patterns/PageHeader.vue'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import { ASSET_UPLOAD_ACCEPT, getAcceptedAssetExtensionText, isAcceptedAssetFile } from '@/components/project/asset-manager'
import FontEditorDialog from '@/components/theme/FontEditorDialog.vue'
import ThemeDetailDialog from '@/components/theme/ThemeDetailDialog.vue'
import ThemeEditorDialog from '@/components/theme/ThemeEditorDialog.vue'
import { UiButton, UiIconButton, UiInput } from '@/components/ui'
import PaginationControl from '@/components/ui/PaginationControl.vue'
import type { AssetResponse, WorkspaceFontConfigItem, WorkspaceFontConfigSummary, WorkspaceFontFamilyItem, WorkspaceItem, WorkspaceThemeItem } from '@/types/api'
import { buildDefaultFontRegistration, inferFontFormat } from '@/utils/font-registration'
import { createConfirm, Message } from '@/utils/message'

const route = useRoute()
const workspaceId = computed(() => Number.parseInt(route.params.workspaceId as string, 10))

const workspace = ref<WorkspaceItem | null>(null)
const themes = ref<WorkspaceThemeItem[]>([])
const fontFamilies = ref<WorkspaceFontFamilyItem[]>([])
const pendingFontAssets = ref<AssetResponse[]>([])
const themeTotal = ref(0)
const fontFamilyTotal = ref(0)
const themePage = ref(1)
const themePageSize = ref(10)
const fontFamilyPage = ref(1)
const fontFamilyPageSize = ref(10)
const themeKeyword = ref('')
const themeDataState = computed<'loading' | 'empty' | 'ready'>(() => (
  loadingThemes.value ? 'loading' : themes.value.length ? 'ready' : 'empty'
))
const fontKeyword = ref('')
const fontDataState = computed<'loading' | 'empty' | 'ready'>(() => (
  loadingFonts.value ? 'loading' : (fontFamilies.value.length || pendingFontAssets.value.length) ? 'ready' : 'empty'
))
const loadingThemes = ref(false)
const loadingFonts = ref(false)
const uploadingFontAsset = ref(false)
const savingTheme = ref(false)
const savingFont = ref(false)
const savingFamily = ref(false)
const renamingFamilyId = ref<number | null>(null)
const renameFamilyValue = ref('')
const replacingFontTarget = ref<WorkspaceFontConfigItem | null>(null)
const themeDetailVisible = ref(false)
const detailThemeId = ref<number | null>(null)
const themeEditorVisible = ref(false)
const fontEditorVisible = ref(false)
const editingTheme = ref<WorkspaceThemeItem | null>(null)
const editorAsset = ref<AssetResponse | null>(null)
const editorFont = ref<WorkspaceFontConfigSummary | null>(null)
const editorPresetFamilyName = ref<string | null>(null)
const fontFileInput = ref<HTMLInputElement | null>(null)
const fontReplaceFileInput = ref<HTMLInputElement | null>(null)
const fontAddFileInput = ref<HTMLInputElement | null>(null)
const addFaceFamilyTarget = ref<WorkspaceFontFamilyItem | null>(null)

interface FontEditorSavePayload {
  family_name: string
  font_format: string
  font_weight: string
  font_style: string
  font_display: string
}

const workspaceTitle = computed(() => {
  const workspaceName = workspace.value?.name
  return workspaceName ? `${workspaceName} · 主题与字体` : '主题与字体'
})

watch(workspaceId, () => {
  void reloadAll()
}, { immediate: true })

watch([themePage, themePageSize, themeKeyword], () => {
  void loadThemes()
})

watch([fontFamilyPage, fontFamilyPageSize, fontKeyword], () => {
  void loadFonts()
})

watch(themeKeyword, () => {
  themePage.value = 1
})

watch(fontKeyword, () => {
  fontFamilyPage.value = 1
})

watch([fontFamilies, pendingFontAssets], () => {
  let styleTag = document.getElementById('theme-font-preview')
  if (!styleTag) {
    styleTag = document.createElement('style')
    styleTag.id = 'theme-font-preview'
    document.head.appendChild(styleTag)
  }
  const faceRules = fontFamilies.value
    .flatMap(family => family.faces)
    .filter(face => face.asset_url)
    .map(face => `@font-face { font-family: 'theme-font-preview-${face.asset_id}'; src: url('${encodeURI(face.asset_url as string)}'); font-weight: ${face.font_weight}; font-style: ${face.font_style}; font-display: swap; }`)
  styleTag.textContent = faceRules.join('\n')
}, { deep: true })

async function reloadAll(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  try {
    workspace.value = await getWorkspace(workspaceId.value)
  } catch (error) {
    Message.error(getErrorMessage(error, '加载工作空间失败。'))
  }
  await Promise.all([loadThemes(), loadFonts()])
}

async function loadThemes(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  loadingThemes.value = true
  try {
    const response = await listWorkspaceThemes(workspaceId.value, {
      page: themePage.value,
      page_size: themePageSize.value,
      keyword: themeKeyword.value.trim() || undefined,
    })
    themes.value = response.items
    themeTotal.value = response.total
  } catch (error) {
    Message.error(getErrorMessage(error, '加载主题库失败。'))
  } finally {
    loadingThemes.value = false
  }
}

async function loadFonts(): Promise<void> {
  await Promise.all([loadFontFamilies(), loadPendingFontAssets()])
}

async function loadFontFamilies(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  loadingFonts.value = true
  try {
    const response = await listWorkspaceFontFamilies(workspaceId.value, {
      page: fontFamilyPage.value,
      page_size: fontFamilyPageSize.value,
      keyword: fontKeyword.value.trim() || undefined,
    })
    fontFamilies.value = response.items
    fontFamilyTotal.value = response.total
  } catch (error) {
    fontFamilies.value = []
    fontFamilyTotal.value = 0
    Message.error(getErrorMessage(error, '加载字体族失败。'))
  } finally {
    loadingFonts.value = false
  }
}

async function loadPendingFontAssets(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  try {
    const response = await listWorkspaceAssets(workspaceId.value, {
      assetType: 'font',
      page: 1,
      page_size: 100,
      sort_by: 'updated_at',
      sort_order: 'desc',
    })
    pendingFontAssets.value = response.items.filter(asset => !asset.font_config)
  } catch {
    pendingFontAssets.value = []
  }
}

async function loadFontsWithPageFallback(): Promise<void> {
  const currentPage = fontFamilyPage.value
  await loadFonts()
  if (fontFamilies.value.length === 0 && currentPage > 1) {
    fontFamilyPage.value = currentPage - 1
  }
}

function triggerFontUpload(): void {
  if (!Number.isFinite(workspaceId.value) || uploadingFontAsset.value) return
  fontFileInput.value?.click()
}

async function handleFontFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  await processFontFilesSelection(target, null)
}

/**
 * 处理字体文件选择：上传并自动注册；指定目标字体族时强制归入该族，否则按文件名推断。
 * @param target 触发选择的文件输入框
 * @param targetFamily 目标字体族；为空时走通用上传入口的推断归组
 */
async function processFontFilesSelection(target: HTMLInputElement, targetFamily: WorkspaceFontFamilyItem | null): Promise<void> {
  if (!target.files || target.files.length === 0 || !Number.isFinite(workspaceId.value)) return

  const files = Array.from(target.files)
  const invalidFiles = files.filter(file => !isAcceptedAssetFile(file, 'font'))
  if (invalidFiles.length > 0) {
    Message.error(`字体文件仅支持 ${getAcceptedAssetExtensionText('font')}，已跳过：${invalidFiles.map(file => file.name).join('、')}`)
  }
  const validFiles = files.filter(file => isAcceptedAssetFile(file, 'font'))
  if (validFiles.length === 0) {
    target.value = ''
    return
  }

  uploadingFontAsset.value = true
  let uploadedCount = 0
  let registeredCount = 0
  let firstPendingAsset: AssetResponse | null = null
  const failures: string[] = []

  try {
    for (const file of validFiles) {
      let uploaded: AssetResponse | null = null
      try {
        uploaded = await uploadFontAssetWithOverwriteConfirm(file)
      } catch (error) {
        failures.push(`${file.name}：${getErrorMessage(error, '上传失败。')}`)
        continue
      }
      if (!uploaded) continue
      uploadedCount += 1
      if (uploaded.font_config) {
        // 覆盖了已注册字体：指定目标族且不在该族时，把 face 移动到目标族。
        if (targetFamily && uploaded.font_config.family_id !== targetFamily.id) {
          try {
            await updateWorkspaceFont(workspaceId.value, uploaded.font_config.id, { family_name: targetFamily.name })
            registeredCount += 1
          } catch (error) {
            failures.push(`${file.name}：${getErrorMessage(error, '移入字体族失败。')}`)
          }
        } else {
          registeredCount += 1
        }
        continue
      }
      try {
        const registration = buildDefaultFontRegistration(uploaded.original_name)
        if (targetFamily) {
          registration.family_name = targetFamily.name
        }
        await createWorkspaceFont(workspaceId.value, {
          asset_id: uploaded.id,
          ...registration,
          status: 'active',
        })
        registeredCount += 1
      } catch (error) {
        firstPendingAsset ??= uploaded
        failures.push(`${file.name}：${getErrorMessage(error, '自动注册失败。')}`)
      }
    }

    if (uploadedCount > 0) {
      Message.success(
        targetFamily
          ? `已向字体族 "${targetFamily.name}" 添加 ${registeredCount} 个字体文件。`
          : uploadedCount === 1 && registeredCount === 1
            ? '字体已上传并自动注册，可直接在主题中选用。'
            : `已上传 ${uploadedCount} 个字体，自动注册 ${registeredCount} 个。`,
      )
      if (!targetFamily) {
        fontKeyword.value = ''
        fontFamilyPage.value = 1
      }
      await Promise.all([loadFonts(), loadThemes()])
    }
    if (failures.length > 0) {
      Message.error(failures.join('；'))
    }
    if (firstPendingAsset) {
      openPendingFontEditor(firstPendingAsset, targetFamily?.name ?? null)
    }
  } finally {
    uploadingFontAsset.value = false
    target.value = ''
  }
}

async function uploadFontAssetWithOverwriteConfirm(file: File): Promise<AssetResponse | null> {
  try {
    return await uploadWorkspaceAsset(workspaceId.value, file, 'font')
  } catch (error) {
    if (getErrorCode(error) !== 'ASSET_NAME_CONFLICT') {
      throw error
    }

    const conflictMessage = getErrorMessage(error, `文件 "${file.name}" 已存在，请确认是否覆盖。`)
    const confirmed = await createConfirm(
      `${conflictMessage} 覆盖后引用该字体的主题和页面会改用新文件，确认覆盖吗？`,
      '覆盖同名字体',
    )
    if (!confirmed) return null

    return await uploadWorkspaceAsset(workspaceId.value, file, 'font', [], undefined, undefined, true)
  }
}

/**
 * 触发向指定字体族添加字体文件的选择器。
 * @param family 目标字体族
 */
function triggerAddFaceToFamily(family: WorkspaceFontFamilyItem): void {
  if (!Number.isFinite(workspaceId.value) || uploadingFontAsset.value) return
  addFaceFamilyTarget.value = family
  fontAddFileInput.value?.click()
}

/** 处理“向字体族添加文件”的选择结果，上传后强制注册到目标族。 */
async function handleAddFaceFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const family = addFaceFamilyTarget.value
  addFaceFamilyTarget.value = null
  if (!family) {
    target.value = ''
    return
  }
  await processFontFilesSelection(target, family)
}

function openCreateTheme(): void {
  editingTheme.value = null
  themeEditorVisible.value = true
}

function openEditTheme(theme: WorkspaceThemeItem): void {
  editingTheme.value = theme
  themeEditorVisible.value = true
}

function openThemeDetail(theme: WorkspaceThemeItem): void {
  detailThemeId.value = theme.id
  themeDetailVisible.value = true
}

async function saveTheme(payload: WorkspaceThemePayload): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  savingTheme.value = true
  try {
    if (editingTheme.value) {
      await updateWorkspaceTheme(workspaceId.value, editingTheme.value.id, payload as never)
      Message.success('主题已更新。')
    } else {
      await createWorkspaceTheme(workspaceId.value, payload as never)
      Message.success('主题已创建。')
    }
    themeEditorVisible.value = false
    await Promise.all([loadThemes(), loadWorkspaceOnly()])
  } catch (error) {
    Message.error(getErrorMessage(error, '保存主题失败。'))
  } finally {
    savingTheme.value = false
  }
}

async function setDefaultTheme(theme: WorkspaceThemeItem): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  try {
    workspace.value = await updateWorkspace(workspaceId.value, { default_theme_key: theme.key })
    Message.success('默认主题已更新。')
  } catch (error) {
    Message.error(getErrorMessage(error, '更新默认主题失败。'))
  }
}

async function copyTheme(theme: WorkspaceThemeItem): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  try {
    await copyWorkspaceTheme(workspaceId.value, theme.id)
    Message.success('主题已复制。')
    await loadThemes()
  } catch (error) {
    Message.error(getErrorMessage(error, '复制主题失败。'))
  }
}

async function deleteTheme(theme: WorkspaceThemeItem): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  const ok = await createConfirm(`确认删除主题 "${theme.name}" 吗？`, '删除主题')
  if (!ok) return
  try {
    await deleteWorkspaceTheme(workspaceId.value, theme.id)
    Message.success('主题已删除。')
    if (detailThemeId.value === theme.id) {
      themeDetailVisible.value = false
      detailThemeId.value = null
    }
    await loadThemesWithPageFallback()
  } catch (error) {
    Message.error(getErrorMessage(error, '删除主题失败。'))
  }
}

async function loadWorkspaceOnly(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  workspace.value = await getWorkspace(workspaceId.value)
}

/**
 * 打开待注册字体文件的补全注册弹窗。
 * @param asset 尚未生成 face 记录的字体资源
 * @param presetFamilyName 预置字体族名；从族内添加入口打开时覆盖文件名推断
 */
function openPendingFontEditor(asset: AssetResponse, presetFamilyName: string | null = null): void {
  editorFont.value = null
  editorAsset.value = asset
  editorPresetFamilyName.value = presetFamilyName
  fontEditorVisible.value = true
}

/**
 * 打开已注册 face 的编辑弹窗，用 face 字段合成弹窗预览所需的最小资源对象。
 * @param face 字体族下的某个 face 记录
 */
function openFaceEditor(face: WorkspaceFontConfigItem): void {
  editorFont.value = face
  editorAsset.value = faceToAsset(face)
  editorPresetFamilyName.value = null
  fontEditorVisible.value = true
}

/**
 * 将 face 记录转换为字体编辑弹窗所需的最小资源对象，仅承载预览与描述字段。
 * @param face 字体族下的某个 face 记录
 */
function faceToAsset(face: WorkspaceFontConfigItem): AssetResponse {
  return {
    id: face.asset_id,
    original_name: face.asset_name,
    url: face.asset_url,
  } as AssetResponse
}

/**
 * 保存字体声明；编辑已有 face 时更新并恢复启用，待注册文件则新建 face。
 */
async function saveFont(payload: FontEditorSavePayload): Promise<void> {
  const face = editorFont.value
  const asset = editorAsset.value
  if (!Number.isFinite(workspaceId.value) || !asset) return
  savingFont.value = true
  try {
    if (face) {
      await updateWorkspaceFont(workspaceId.value, face.id, {
        ...payload,
        status: 'active',
      })
    } else {
      await createWorkspaceFont(workspaceId.value, {
        asset_id: asset.id,
        ...payload,
        status: 'active',
      })
    }
    Message.success('字体已保存。')
    fontEditorVisible.value = false
    editorFont.value = null
    editorAsset.value = null
    editorPresetFamilyName.value = null
    await Promise.all([loadFonts(), loadThemes()])
  } catch (error) {
    Message.error(getErrorMessage(error, '保存字体失败。'))
  } finally {
    savingFont.value = false
  }
}

/**
 * 删除字体族下的某个 face，字体文件一并删除；空族由后端级联清理。
 * @param family face 所属字体族
 * @param face 需要删除的 face 记录
 */
async function deleteFace(family: WorkspaceFontFamilyItem, face: WorkspaceFontConfigItem): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  const ok = await createConfirm(
    `确认删除字体族 "${family.name}" 下的文件 "${face.asset_name}" 吗？字体文件会一并删除，删除后无法恢复。`,
    '删除字体',
  )
  if (!ok) return
  try {
    await deleteWorkspaceFont(workspaceId.value, face.id, { deleteAsset: true })
    Message.success('字体已删除。')
    await Promise.all([loadFontsWithPageFallback(), loadThemes()])
  } catch (error) {
    Message.error(getErrorMessage(error, '删除字体失败。'))
  }
}

/**
 * 删除尚未注册的字体文件。
 * @param asset 待注册字体资源
 */
async function deletePendingFontAsset(asset: AssetResponse): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  const ok = await createConfirm(
    `确认删除字体文件 "${asset.original_name}" 吗？删除后无法恢复。`,
    '删除字体文件',
  )
  if (!ok) return
  try {
    await deleteWorkspaceFontAsset(workspaceId.value, asset.id)
    Message.success('字体文件已删除。')
    await loadFonts()
  } catch (error) {
    Message.error(getErrorMessage(error, '删除字体文件失败。'))
  }
}

/**
 * 进入字体族重命名态，预填当前名称。
 * @param family 目标字体族
 */
function startRenameFamily(family: WorkspaceFontFamilyItem): void {
  renamingFamilyId.value = family.id
  renameFamilyValue.value = family.name
}

/** 退出字体族重命名态。 */
function cancelRenameFamily(): void {
  renamingFamilyId.value = null
  renameFamilyValue.value = ''
}

/**
 * 提交字体族重命名，名称为空或未变化时直接退出。
 * @param family 目标字体族
 */
async function confirmRenameFamily(family: WorkspaceFontFamilyItem): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  const nextName = renameFamilyValue.value.trim()
  if (!nextName || nextName === family.name) {
    cancelRenameFamily()
    return
  }
  savingFamily.value = true
  try {
    await renameWorkspaceFontFamily(workspaceId.value, family.id, nextName)
    Message.success('字体族已重命名。')
    cancelRenameFamily()
    await Promise.all([loadFonts(), loadThemes()])
  } catch (error) {
    Message.error(getErrorMessage(error, '重命名字体族失败。'))
  } finally {
    savingFamily.value = false
  }
}

function triggerReplaceFace(face: WorkspaceFontConfigItem): void {
  replacingFontTarget.value = face
  fontReplaceFileInput.value?.click()
}

async function handleFontReplaceFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0] ?? null
  const face = replacingFontTarget.value
  if (!file || !face || !Number.isFinite(workspaceId.value)) {
    target.value = ''
    replacingFontTarget.value = null
    return
  }
  if (!isAcceptedAssetFile(file, 'font')) {
    Message.error(`字体文件仅支持 ${getAcceptedAssetExtensionText('font')}。`)
    target.value = ''
    replacingFontTarget.value = null
    return
  }
  const confirmed = await createConfirm(
    `确认用 "${file.name}" 替换字体文件 "${face.asset_name}" 吗？引用该字体的主题和页面会改用新文件。`,
    '替换字体文件',
  )
  if (!confirmed) {
    target.value = ''
    replacingFontTarget.value = null
    return
  }
  try {
    await replaceWorkspaceAssetFile(workspaceId.value, face.asset_id, file)
    const nextFormat = inferFontFormat(file.name)
    if (face.font_format !== nextFormat) {
      await updateWorkspaceFont(workspaceId.value, face.id, { font_format: nextFormat })
    }
    Message.success('字体文件已替换。')
    await Promise.all([loadFonts(), loadThemes()])
  } catch (error) {
    Message.error(getErrorMessage(error, '替换字体文件失败。'))
  } finally {
    target.value = ''
    replacingFontTarget.value = null
  }
}

async function loadThemesWithPageFallback(): Promise<void> {
  const currentPage = themePage.value
  await loadThemes()
  if (themes.value.length === 0 && currentPage > 1) {
    themePage.value = currentPage - 1
  }
}

function handleThemePageSizeChange(value: number): void {
  themePageSize.value = value
  themePage.value = 1
}

function handleFontFamilyPageSizeChange(value: number): void {
  fontFamilyPageSize.value = value
  fontFamilyPage.value = 1
}

/**
 * 生成 face 预览样式，使用页面级 @font-face 注入的临时 font-family。
 * @param face 字体族下的某个 face 记录
 */
function getFacePreviewStyle(face: WorkspaceFontConfigSummary): CSSProperties {
  return {
    fontFamily: `'theme-font-preview-${face.asset_id}'`,
    fontWeight: face.font_weight || undefined,
    fontStyle: face.font_style || undefined,
  }
}

/**
 * 将字体文件字节数格式化为可读大小。
 * @param size 文件字节数
 */
function formatFontFileSize(size: number): string {
  if (!Number.isFinite(size) || size <= 0) return '未知大小'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function isDefaultTheme(theme: WorkspaceThemeItem): boolean {
  return workspace.value?.default_theme_key === theme.key
}

function getThemeFontLabel(theme: WorkspaceThemeItem, slot: 'heading' | 'body' | 'code'): string {
  const family = slot === 'heading' ? theme.heading_font_family : slot === 'body' ? theme.body_font_family : theme.code_font_family
  const fallback = slot === 'heading' ? theme.heading_font_label : slot === 'body' ? theme.body_font_label : theme.code_font_label
  return family?.name || fallback || '未绑定'
}

function isThemeFontFallback(theme: WorkspaceThemeItem, slot: 'heading' | 'body' | 'code'): boolean {
  const family = slot === 'heading' ? theme.heading_font_family : slot === 'body' ? theme.body_font_family : theme.code_font_family
  return !family
}

function getThemeCardStyle(theme: WorkspaceThemeItem): CSSProperties {
  return {
    backgroundColor: theme.palette.background.default,
    borderColor: isDefaultTheme(theme) ? theme.palette.link.default : theme.palette.border.default,
    color: theme.palette.text.primary,
  }
}

function getThemeMetaBlockStyle(theme: WorkspaceThemeItem): CSSProperties {
  return {
    backgroundColor: withAlpha(theme.palette.background.invert, 0.06),
    border: `1px solid ${withAlpha(theme.palette.border.subtle, 0.8)}`,
  }
}

function getThemeAccentColors(theme: WorkspaceThemeItem): string[] {
  const accents = theme.palette?.accent
  if (!Array.isArray(accents) || accents.length === 0) {
    return ['#e2e8f0', '#cbd5e1', '#94a3b8']
  }
  return accents.slice(0, 6)
}

/**
 * 将 6 位 HEX 转为 rgba，用于生成主题卡片内部的低对比信息块。
 * @param color 主题配置中的颜色值
 * @param alpha 目标透明度
 */
function withAlpha(color: string | undefined, alpha: number): string {
  const fallback = 'rgba(15, 23, 42, 0.06)'
  if (!color) {
    return fallback
  }
  const normalized = color.trim().replace('#', '')
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return fallback
  }
  const red = Number.parseInt(normalized.slice(0, 2), 16)
  const green = Number.parseInt(normalized.slice(2, 4), 16)
  const blue = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
