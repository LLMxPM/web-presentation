<!-- 文件功能：提供工作空间级主题与字体管理页面，统一维护主题库、主题详情和字体注册。 -->
<template>
  <div data-testid="themes-view" class="flex h-full min-h-0 flex-col gap-2">
    <PageTitleBar
      class="shrink-0"
      :title="workspaceTitle"
    >
      <template #actions>
        <BaseButton variant="ghost" :disabled="loadingThemes || loadingFonts || loadingFontAssets" @click="reloadAll">
          <RefreshCw class="h-3.5 w-3.5" />
          刷新
        </BaseButton>
      </template>
    </PageTitleBar>

    <div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_380px] gap-2 overflow-hidden">
      <section class="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <header class="flex shrink-0 items-center justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h2 class="text-base font-black text-slate-900">主题库</h2>
              <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-black text-slate-500">
                共 {{ themeTotal }} 个主题
              </span>
            </div>
            <p class="mt-1 text-xs text-slate-400">点击主题查看详情，常用操作可直接在卡片右侧完成。</p>
          </div>
          <BaseButton size="sm" @click="openCreateTheme">
            <Plus class="h-3.5 w-3.5" />
            新建主题
          </BaseButton>
        </header>

        <div class="shrink-0 border-b border-slate-100 bg-slate-50/70 px-5 py-3">
          <label class="flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-500 focus-within:border-indigo-400">
            <Search class="h-4 w-4 text-slate-400" />
            <input
              v-model="themeKeyword"
              class="min-w-0 flex-1 bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
              placeholder="搜索主题名称、key"
            />
          </label>
        </div>

        <div v-if="loadingThemes" class="flex flex-1 items-center justify-center text-sm font-semibold text-slate-400">
          正在加载主题...
        </div>
        <div v-else class="min-h-0 flex-1 overflow-y-auto p-5">
          <div
            v-if="themes.length === 0"
            class="flex min-h-[140px] flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-100 bg-slate-50 text-center"
          >
            <SwatchBook class="mb-3 h-10 w-10 text-slate-300" />
            <p class="text-sm font-semibold text-slate-500">{{ themeKeyword ? '未找到相关主题' : '暂无主题' }}</p>
          </div>

          <div v-else class="grid gap-3 2xl:grid-cols-2">
            <article
              v-for="theme in themes"
              :key="theme.id"
              class="group cursor-pointer rounded-xl border p-3 transition-all hover:shadow-md"
              :class="isDefaultTheme(theme) ? 'ring-2 ring-indigo-100' : ''"
              :style="getThemeCardStyle(theme)"
              @click="openThemeDetail(theme)"
            >
              <div class="flex items-start justify-between gap-2.5">
                <div class="min-w-0">
                  <div class="flex min-w-0 items-center gap-2">
                    <h3 class="truncate text-base font-black" :style="{ color: theme.palette.text.primary }">{{ theme.name }}</h3>
                    <span
                      v-if="isDefaultTheme(theme)"
                      class="shrink-0 rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[10px] font-black text-indigo-600"
                    >
                      默认
                    </span>
                  </div>
                  <p class="mt-0.5 truncate font-mono text-xs opacity-70" :style="{ color: theme.palette.text.secondary }">{{ theme.key }}</p>
                </div>

                <div class="flex shrink-0 items-center gap-1 opacity-70 transition-opacity group-hover:opacity-100">
                  <button
                    v-if="!isDefaultTheme(theme)"
                    type="button"
                    class="theme-icon-button"
                    title="设为默认"
                    :style="getThemeActionStyle(theme)"
                    @click.stop="setDefaultTheme(theme)"
                  >
                    <Pin class="h-4 w-4" />
                  </button>
                  <button type="button" class="theme-icon-button" title="编辑" :style="getThemeActionStyle(theme)" @click.stop="openEditTheme(theme)">
                    <Pencil class="h-4 w-4" />
                  </button>
                  <button type="button" class="theme-icon-button" title="复制" :style="getThemeActionStyle(theme)" @click.stop="copyTheme(theme)">
                    <Copy class="h-4 w-4" />
                  </button>
                  <button type="button" class="theme-icon-button-danger" title="删除" :style="getThemeActionStyle(theme)" @click.stop="deleteTheme(theme)">
                    <Trash2 class="h-4 w-4" />
                  </button>
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

      <aside class="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <header class="shrink-0 border-b border-slate-100 px-4 py-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <h2 class="text-base font-black text-slate-900">字体管理</h2>
                <span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-black text-slate-500">
                  注册 {{ fontTotal }} / 文件 {{ fontAssetTotal }}
                </span>
              </div>
              <p class="mt-1 text-xs text-slate-400">字体文件在这里上传维护，注册后可绑定到主题。</p>
            </div>
            <div class="flex shrink-0 items-center gap-1">
              <BaseButton size="sm" variant="ghost" :disabled="!workspaceId || uploadingFontAsset" @click="triggerFontUpload">
                <Upload class="h-3.5 w-3.5" />
                {{ uploadingFontAsset ? '上传中' : '上传' }}
              </BaseButton>
              <BaseButton size="sm" @click="openCreateFont">
                <Plus class="h-3.5 w-3.5" />
                注册
              </BaseButton>
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
            </div>
          </div>
        </header>

        <div class="shrink-0 border-b border-slate-100 bg-slate-50/70 px-4 py-3">
          <div class="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
            <button
              type="button"
              class="rounded-lg py-2 text-xs font-black transition-all"
              :class="fontPanelTab === 'registrations' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
              @click="fontPanelTab = 'registrations'"
            >
              字体注册
            </button>
            <button
              type="button"
              class="rounded-lg py-2 text-xs font-black transition-all"
              :class="fontPanelTab === 'files' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
              @click="fontPanelTab = 'files'"
            >
              字体文件
            </button>
          </div>
        </div>

        <div
          v-if="fontPanelTab === 'registrations'"
          class="grid shrink-0 grid-cols-[minmax(0,1fr)_96px] gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-3"
        >
          <label class="flex h-9 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-500 focus-within:border-indigo-400">
            <Search class="h-3.5 w-3.5 text-slate-400" />
            <input
              v-model="fontKeyword"
              class="min-w-0 flex-1 bg-transparent text-xs text-slate-700 outline-none placeholder:text-slate-400"
              placeholder="搜索字体注册"
            />
          </label>
          <select
            v-model="fontStatus"
            class="h-9 rounded-xl border border-slate-200 bg-white px-2 text-xs font-bold text-slate-600 outline-none focus:border-indigo-400"
          >
            <option value="">全部</option>
            <option value="active">启用</option>
            <option value="archived">归档</option>
          </select>
        </div>

        <div
          v-else
          class="grid shrink-0 grid-cols-[minmax(0,1fr)_96px] gap-2 border-b border-slate-100 bg-slate-50/70 px-4 py-3"
        >
          <label class="flex h-9 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-500 focus-within:border-indigo-400">
            <Search class="h-3.5 w-3.5 text-slate-400" />
            <input
              v-model="fontAssetKeyword"
              class="min-w-0 flex-1 bg-transparent text-xs text-slate-700 outline-none placeholder:text-slate-400"
              placeholder="搜索字体文件"
            />
          </label>
          <select
            v-model="fontAssetStatus"
            class="h-9 rounded-xl border border-slate-200 bg-white px-2 text-xs font-bold text-slate-600 outline-none focus:border-indigo-400"
          >
            <option value="">全部</option>
            <option value="active">启用</option>
            <option value="archived">归档</option>
          </select>
        </div>

        <template v-if="fontPanelTab === 'registrations'">
          <div v-if="loadingFonts" class="flex flex-1 items-center justify-center text-sm font-semibold text-slate-400">
            正在加载字体注册...
          </div>
          <div v-else class="min-h-0 flex-1 overflow-y-auto p-4">
            <div
              v-if="fonts.length === 0"
              class="flex min-h-[140px] flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-100 bg-slate-50 text-center"
            >
              <Type class="mb-3 h-10 w-10 text-slate-300" />
              <p class="text-sm font-semibold text-slate-500">{{ fontKeyword ? '未找到相关字体注册' : '暂无字体注册' }}</p>
            </div>

            <div v-else class="space-y-3">
              <article
                v-for="font in fonts"
                :key="font.id"
                class="rounded-xl border border-slate-200 bg-white p-3 transition-colors hover:border-indigo-200"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <h3 class="truncate text-sm font-black text-slate-800">{{ font.font_family }}</h3>
                    <p class="mt-0.5 truncate font-mono text-[11px] text-slate-400">{{ font.asset_name }}</p>
                  </div>
                  <span
                    class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-black"
                    :class="font.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
                  >
                    {{ font.status === 'active' ? '启用' : '归档' }}
                  </span>
                </div>

                <div class="mt-3 rounded-lg bg-slate-50 p-3 text-slate-800" :style="{ fontFamily: `'theme-font-preview-${font.id}'` }">
                  <div class="text-2xl">AaBb 0123</div>
                  <div class="mt-1 text-sm text-slate-500">字体效果预览</div>
                </div>

                <div class="mt-3 flex items-center justify-between gap-3">
                  <span class="truncate text-[11px] font-semibold text-slate-500">
                    {{ font.font_format }} / {{ font.font_weight }} / {{ font.font_style }}
                  </span>
                  <div class="flex gap-1">
                    <button type="button" class="theme-icon-button" title="编辑" @click="openEditFont(font)">
                      <Pencil class="h-4 w-4" />
                    </button>
                    <button type="button" class="theme-icon-button-danger" title="删除注册和字体文件" @click="deleteFont(font)">
                      <Trash2 class="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </article>
            </div>
          </div>

          <PaginationControl
            compact
            :page="fontPage"
            :page-size="fontPageSize"
            :total="fontTotal"
            :page-size-options="[10, 20, 50, 100]"
            @update:page="fontPage = $event"
            @update:page-size="handleFontPageSizeChange"
          />
        </template>

        <template v-else>
          <div v-if="loadingFontAssets" class="flex flex-1 items-center justify-center text-sm font-semibold text-slate-400">
            正在加载字体文件...
          </div>
          <div v-else class="min-h-0 flex-1 overflow-y-auto p-4">
            <div
              v-if="fontAssets.length === 0"
              class="flex min-h-[140px] flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-100 bg-slate-50 text-center"
            >
              <Type class="mb-3 h-10 w-10 text-slate-300" />
              <p class="text-sm font-semibold text-slate-500">{{ fontAssetKeyword ? '未找到相关字体文件' : '暂无字体文件' }}</p>
            </div>

            <div v-else class="space-y-3">
              <article
                v-for="asset in fontAssets"
                :key="asset.id"
                class="rounded-xl border border-slate-200 bg-white p-3 transition-colors hover:border-indigo-200"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <h3 class="truncate text-sm font-black text-slate-800">{{ asset.original_name }}</h3>
                    <p class="mt-0.5 truncate font-mono text-[11px] text-slate-400">{{ asset.name }}</p>
                  </div>
                  <div class="flex shrink-0 flex-col items-end gap-1">
                    <span
                      class="rounded-full px-2 py-0.5 text-[10px] font-black"
                      :class="asset.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
                    >
                      {{ asset.status === 'active' ? '启用' : '归档' }}
                    </span>
                    <span
                      class="rounded-full px-2 py-0.5 text-[10px] font-black"
                      :class="asset.font_config ? 'bg-indigo-50 text-indigo-700' : 'bg-amber-50 text-amber-700'"
                    >
                      {{ asset.font_config ? '已注册' : '未注册' }}
                    </span>
                  </div>
                </div>

                <div class="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
                  <p v-if="asset.font_config" class="truncate font-bold text-slate-700">font-family：{{ asset.font_config.font_family }}</p>
                  <p v-else class="font-bold text-amber-700">未注册为主题可选字体</p>
                  <p class="mt-1 truncate">大小 {{ Math.max(1, Math.ceil(asset.file_size / 1024)) }} KB</p>
                  <p v-if="asset.archive_reason" class="mt-1 truncate">归档原因：{{ asset.archive_reason }}</p>
                </div>

                <div class="mt-3 flex items-center justify-end gap-1">
                  <button
                    v-if="asset.font_config"
                    type="button"
                    class="theme-icon-button"
                    title="编辑字体注册"
                    @click="openEditFontFromAsset(asset)"
                  >
                    <Pencil class="h-4 w-4" />
                  </button>
                  <button
                    v-else-if="asset.status === 'active'"
                    type="button"
                    class="theme-icon-button"
                    title="注册字体"
                    @click="openCreateFontForAsset(asset)"
                  >
                    <Plus class="h-4 w-4" />
                  </button>
                  <button
                    v-if="asset.status === 'active'"
                    type="button"
                    class="theme-icon-button"
                    title="替换字体文件"
                    @click="triggerReplaceFontAsset(asset)"
                  >
                    <RefreshCw class="h-4 w-4" />
                  </button>
                  <button
                    v-if="!asset.font_config && asset.status === 'active'"
                    type="button"
                    class="theme-icon-button-danger"
                    title="删除字体文件"
                    @click="deleteFontAsset(asset)"
                  >
                    <Trash2 class="h-4 w-4" />
                  </button>
                  <button
                    v-if="!asset.font_config && asset.status === 'archived'"
                    type="button"
                    class="theme-icon-button"
                    title="恢复字体文件"
                    @click="restoreFontAsset(asset)"
                  >
                    <RotateCcw class="h-4 w-4" />
                  </button>
                  <button
                    v-if="!asset.font_config && asset.status === 'archived'"
                    type="button"
                    class="theme-icon-button-danger"
                    title="删除字体文件"
                    @click="deleteFontAsset(asset)"
                  >
                    <Trash2 class="h-4 w-4" />
                  </button>
                  <button
                    v-if="asset.font_config"
                    type="button"
                    class="theme-icon-button-danger opacity-50"
                    title="已注册字体文件需要先删除字体注册"
                    disabled
                  >
                    <Trash2 class="h-4 w-4" />
                  </button>
                </div>
              </article>
            </div>
          </div>

          <PaginationControl
            compact
            :page="fontAssetPage"
            :page-size="fontAssetPageSize"
            :total="fontAssetTotal"
            :page-size-options="[10, 20, 50, 100]"
            @update:page="fontAssetPage = $event"
            @update:page-size="handleFontAssetPageSizeChange"
          />
        </template>
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
      :editing-font="editingFont"
      :font-assets="fontAssetsForRegistration"
      :initial-asset="fontEditorInitialAsset"
      :saving="savingFont"
      @save="saveFont"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, type CSSProperties } from 'vue'
import { useRoute } from 'vue-router'
import {
  ChevronRight,
  Copy,
  Pencil,
  Pin,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  SwatchBook,
  Trash2,
  Type,
  Upload,
} from '@lucide/vue'

import {
  createWorkspaceFont,
  deleteWorkspaceFontAsset,
  deleteWorkspaceFont,
  listWorkspaceAssets,
  listWorkspaceFonts,
  replaceWorkspaceAssetFile,
  restoreWorkspaceAsset,
  updateWorkspaceFont,
  uploadWorkspaceAsset,
} from '@/api/assets'
import { getWorkspace, updateWorkspace } from '@/api/catalog'
import { getErrorCode, getErrorMessage } from '@/api/http'
import { copyWorkspaceTheme, createWorkspaceTheme, deleteWorkspaceTheme, listWorkspaceThemes, updateWorkspaceTheme } from '@/api/themes'
import type { WorkspaceThemePayload } from '@/api/themes'
import PageTitleBar from '@/components/layout/PageTitleBar.vue'
import { ASSET_UPLOAD_ACCEPT, getAcceptedAssetExtensionText, isAcceptedAssetFile } from '@/components/project/asset-manager'
import FontEditorDialog from '@/components/theme/FontEditorDialog.vue'
import ThemeDetailDialog from '@/components/theme/ThemeDetailDialog.vue'
import ThemeEditorDialog from '@/components/theme/ThemeEditorDialog.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import PaginationControl from '@/components/ui/PaginationControl.vue'
import type { AssetResponse, RecordStatus, WorkspaceFontConfigItem, WorkspaceItem, WorkspaceThemeItem } from '@/types/api'
import { createConfirm, Message } from '@/utils/message'

const route = useRoute()
const workspaceId = computed(() => Number.parseInt(route.params.workspaceId as string, 10))

const workspace = ref<WorkspaceItem | null>(null)
const themes = ref<WorkspaceThemeItem[]>([])
const fonts = ref<WorkspaceFontConfigItem[]>([])
const fontAssets = ref<AssetResponse[]>([])
const themeTotal = ref(0)
const fontTotal = ref(0)
const fontAssetTotal = ref(0)
const themePage = ref(1)
const themePageSize = ref(10)
const fontPage = ref(1)
const fontPageSize = ref(10)
const fontAssetPage = ref(1)
const fontAssetPageSize = ref(10)
const themeKeyword = ref('')
const fontKeyword = ref('')
const fontStatus = ref<RecordStatus | ''>('')
const fontAssetKeyword = ref('')
const fontAssetStatus = ref<RecordStatus | ''>('')
const loadingThemes = ref(false)
const loadingFonts = ref(false)
const loadingFontAssets = ref(false)
const uploadingFontAsset = ref(false)
const savingTheme = ref(false)
const savingFont = ref(false)
const replacingFontAsset = ref<AssetResponse | null>(null)
const fontPanelTab = ref<'registrations' | 'files'>('registrations')
const themeDetailVisible = ref(false)
const detailThemeId = ref<number | null>(null)
const themeEditorVisible = ref(false)
const fontEditorVisible = ref(false)
const editingTheme = ref<WorkspaceThemeItem | null>(null)
const editingFont = ref<WorkspaceFontConfigItem | null>(null)
const fontEditorInitialAsset = ref<AssetResponse | null>(null)
const fontFileInput = ref<HTMLInputElement | null>(null)
const fontReplaceFileInput = ref<HTMLInputElement | null>(null)

const fontAssetsForRegistration = computed(() => {
  const items = fontAssets.value.filter(asset => asset.status === 'active' && !asset.font_config)
  const initialAsset = fontEditorInitialAsset.value
  if (initialAsset && initialAsset.status === 'active' && !initialAsset.font_config && !items.some(asset => asset.id === initialAsset.id)) {
    return [initialAsset, ...items]
  }
  return items
})

interface FontEditorSavePayload {
  asset_id: number
  font_family: string
  font_format: string
  font_weight: string
  font_style: string
  font_display: string
  status: RecordStatus
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

watch([fontPage, fontPageSize, fontKeyword, fontStatus], () => {
  void loadFonts()
})

watch([fontAssetPage, fontAssetPageSize, fontAssetKeyword, fontAssetStatus], () => {
  void loadFontAssets()
})

watch(themeKeyword, () => {
  themePage.value = 1
})

watch([fontKeyword, fontStatus], () => {
  fontPage.value = 1
})

watch([fontAssetKeyword, fontAssetStatus], () => {
  fontAssetPage.value = 1
})

watch(fonts, (items) => {
  let styleTag = document.getElementById('theme-font-preview')
  if (!styleTag) {
    styleTag = document.createElement('style')
    styleTag.id = 'theme-font-preview'
    document.head.appendChild(styleTag)
  }
  styleTag.innerHTML = items
    .filter(font => font.asset_url)
    .map(font => `@font-face { font-family: 'theme-font-preview-${font.id}'; src: url('${font.asset_url}'); font-display: swap; }`)
    .join('\n')
})

async function reloadAll(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  try {
    workspace.value = await getWorkspace(workspaceId.value)
  } catch (error) {
    Message.error(getErrorMessage(error, '加载工作空间失败。'))
  }
  await Promise.all([loadThemes(), loadFonts(), loadFontAssets()])
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
  if (!Number.isFinite(workspaceId.value)) return
  loadingFonts.value = true
  try {
    const response = await listWorkspaceFonts(workspaceId.value, {
      page: fontPage.value,
      page_size: fontPageSize.value,
      keyword: fontKeyword.value.trim() || undefined,
      status: fontStatus.value || undefined,
    })
    fonts.value = response.items
    fontTotal.value = response.total
  } catch (error) {
    Message.error(getErrorMessage(error, '加载字体注册失败。'))
  } finally {
    loadingFonts.value = false
  }
}

async function loadFontAssets(): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  loadingFontAssets.value = true
  try {
    const response = await listWorkspaceAssets(workspaceId.value, {
      assetType: 'font',
      page: fontAssetPage.value,
      page_size: fontAssetPageSize.value,
      keyword: fontAssetKeyword.value.trim() || undefined,
      status: fontAssetStatus.value || undefined,
      sort_by: 'updated_at',
      sort_order: 'desc',
    })
    fontAssets.value = response.items
    fontAssetTotal.value = response.total
  } catch (error) {
    fontAssets.value = []
    fontAssetTotal.value = 0
    Message.error(getErrorMessage(error, '加载字体文件失败。'))
  } finally {
    loadingFontAssets.value = false
  }
}

async function loadFontAssetsWithPageFallback(): Promise<void> {
  const currentPage = fontAssetPage.value
  await loadFontAssets()
  if (fontAssets.value.length === 0 && currentPage > 1) {
    fontAssetPage.value = currentPage - 1
  }
}

function triggerFontUpload(): void {
  if (!Number.isFinite(workspaceId.value) || uploadingFontAsset.value) return
  fontFileInput.value?.click()
}

async function handleFontFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  if (!target.files || target.files.length === 0 || !Number.isFinite(workspaceId.value)) return

  const files = Array.from(target.files)
  uploadingFontAsset.value = true
  let successCount = 0
  let firstUploadedAsset: AssetResponse | null = null
  let firstError = ''

  try {
    for (const file of files) {
      try {
        const uploaded = await uploadFontAssetWithOverwriteConfirm(file)
        if (uploaded) {
          successCount += 1
          firstUploadedAsset ??= uploaded
        }
      } catch (error) {
        firstError ||= getErrorMessage(error, '上传字体文件失败。')
      }
    }

    if (successCount > 0) {
      Message.success(files.length === 1 ? '字体文件已上传。' : `已上传 ${successCount} 个字体文件。`)
      fontPanelTab.value = 'files'
      fontAssetKeyword.value = ''
      fontAssetStatus.value = ''
      fontAssetPage.value = 1
      await loadFontAssets()
      if (firstUploadedAsset && files.length === 1) {
        openCreateFontForAsset(firstUploadedAsset)
      }
    }
    if (firstError) {
      Message.error(successCount > 0 ? `部分字体上传失败：${firstError}` : firstError)
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
      `${conflictMessage} 覆盖后主题和预览中引用该资源 name 的位置会指向新文件，确认覆盖吗？`,
      '覆盖同名字体资源',
    )
    if (!confirmed) return null

    return await uploadWorkspaceAsset(workspaceId.value, file, 'font', [], undefined, undefined, true)
  }
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
    await Promise.all([loadThemes(), loadFonts(), loadWorkspaceOnly()])
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

function openCreateFont(): void {
  editingFont.value = null
  fontEditorInitialAsset.value = fontAssetsForRegistration.value[0] ?? null
  if (!fontEditorInitialAsset.value) {
    fontPanelTab.value = 'files'
    Message.info('请先上传或选择一个未注册的字体文件。')
    return
  }
  fontEditorVisible.value = true
}

function openCreateFontForAsset(asset: AssetResponse): void {
  if (asset.font_config) {
    Message.warning('该字体文件已注册，请直接编辑字体注册。')
    return
  }
  if (asset.status !== 'active') {
    Message.warning('归档字体文件需要先恢复后再注册。')
    return
  }
  editingFont.value = null
  fontEditorInitialAsset.value = asset
  fontEditorVisible.value = true
}

function openEditFont(font: WorkspaceFontConfigItem): void {
  editingFont.value = font
  fontEditorInitialAsset.value = null
  fontEditorVisible.value = true
}

async function saveFont(payload: FontEditorSavePayload): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  if (!editingFont.value && !payload.asset_id) {
    Message.error('请选择字体资源。')
    return
  }
  if (!payload.font_family.trim()) {
    Message.error('请填写 font-family。')
    return
  }
  savingFont.value = true
  try {
    if (editingFont.value) {
      await updateWorkspaceFont(workspaceId.value, editingFont.value.id, {
        font_family: payload.font_family.trim(),
        font_format: payload.font_format,
        font_weight: payload.font_weight.trim(),
        font_style: payload.font_style,
        font_display: payload.font_display,
        status: payload.status,
      })
    } else {
      await createWorkspaceFont(workspaceId.value, {
        asset_id: payload.asset_id,
        font_family: payload.font_family.trim(),
        font_format: payload.font_format,
        font_weight: payload.font_weight.trim(),
        font_style: payload.font_style,
        font_display: payload.font_display,
        status: payload.status,
      })
    }
    Message.success('字体配置已保存。')
    fontEditorVisible.value = false
    await Promise.all([loadFonts(), loadFontAssets(), loadThemes()])
  } catch (error) {
    Message.error(getErrorMessage(error, '保存字体配置失败。'))
  } finally {
    savingFont.value = false
  }
}

async function deleteFont(font: WorkspaceFontConfigItem): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  const ok = await createConfirm(`确认删除字体注册 "${font.font_family}" 吗？默认会同时硬删除关联字体文件和历史记录。`, '删除字体注册')
  if (!ok) return
  try {
    await deleteWorkspaceFont(workspaceId.value, font.id, { deleteAsset: true })
    Message.success('字体注册和字体文件已删除。')
    await Promise.all([loadFontsWithPageFallback(), loadFontAssetsWithPageFallback(), loadThemes()])
  } catch (error) {
    Message.error(getErrorMessage(error, '删除字体注册失败。'))
  }
}

function openEditFontFromAsset(asset: AssetResponse): void {
  const registeredFont = fonts.value.find(font => font.id === asset.font_config?.id)
  if (registeredFont) {
    openEditFont(registeredFont)
    return
  }
  fontPanelTab.value = 'registrations'
  fontKeyword.value = asset.font_config?.font_family || asset.font_config?.asset_name || asset.name
  Message.info('已切换到对应字体注册，请在列表中编辑。')
}

function triggerReplaceFontAsset(asset: AssetResponse): void {
  if (asset.status !== 'active') {
    Message.warning('归档字体文件不能替换，请先恢复。')
    return
  }
  replacingFontAsset.value = asset
  fontReplaceFileInput.value?.click()
}

async function handleFontReplaceFileChange(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0] ?? null
  const asset = replacingFontAsset.value
  if (!file || !asset || !Number.isFinite(workspaceId.value)) {
    target.value = ''
    replacingFontAsset.value = null
    return
  }
  if (!isAcceptedAssetFile(file, 'font')) {
    Message.error(`字体文件仅支持 ${getAcceptedAssetExtensionText('font')}。`)
    target.value = ''
    replacingFontAsset.value = null
    return
  }
  try {
    await replaceWorkspaceAssetFile(workspaceId.value, asset.id, file)
    Message.success('字体文件已替换。')
    await Promise.all([loadFontAssets(), loadFonts(), loadThemes()])
  } catch (error) {
    Message.error(getErrorMessage(error, '替换字体文件失败。'))
  } finally {
    target.value = ''
    replacingFontAsset.value = null
  }
}

async function restoreFontAsset(asset: AssetResponse): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  try {
    await restoreWorkspaceAsset(workspaceId.value, asset.id, '恢复字体文件。')
    Message.success('字体文件已恢复。')
    await loadFontAssets()
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复字体文件失败。'))
  }
}

async function deleteFontAsset(asset: AssetResponse): Promise<void> {
  if (!Number.isFinite(workspaceId.value)) return
  if (asset.font_config) {
    Message.warning('已注册字体文件需要先删除字体注册。')
    return
  }
  const ok = await createConfirm(`确认硬删除字体文件 "${asset.original_name}" 吗？该操作会删除资产记录、历史记录，并在无复用时删除对象存储文件。`, '删除字体文件')
  if (!ok) return
  try {
    await deleteWorkspaceFontAsset(workspaceId.value, asset.id)
    Message.success('字体文件已删除。')
    await loadFontAssetsWithPageFallback()
  } catch (error) {
    Message.error(getErrorMessage(error, '删除字体文件失败。'))
  }
}

async function loadThemesWithPageFallback(): Promise<void> {
  const currentPage = themePage.value
  await loadThemes()
  if (themes.value.length === 0 && currentPage > 1) {
    themePage.value = currentPage - 1
  }
}

async function loadFontsWithPageFallback(): Promise<void> {
  const currentPage = fontPage.value
  await loadFonts()
  if (fonts.value.length === 0 && currentPage > 1) {
    fontPage.value = currentPage - 1
  }
}

function handleThemePageSizeChange(value: number): void {
  themePageSize.value = value
  themePage.value = 1
}

function handleFontPageSizeChange(value: number): void {
  fontPageSize.value = value
  fontPage.value = 1
}

function handleFontAssetPageSizeChange(value: number): void {
  fontAssetPageSize.value = value
  fontAssetPage.value = 1
}

function isDefaultTheme(theme: WorkspaceThemeItem): boolean {
  return workspace.value?.default_theme_key === theme.key
}

function getThemeFontLabel(theme: WorkspaceThemeItem, slot: 'heading' | 'body' | 'code'): string {
  const font = slot === 'heading' ? theme.heading_font : slot === 'body' ? theme.body_font : theme.code_font
  const fallback = slot === 'heading' ? theme.heading_font_label : slot === 'body' ? theme.body_font_label : theme.code_font_label
  return font?.font_family || fallback || '未绑定'
}

function isThemeFontFallback(theme: WorkspaceThemeItem, slot: 'heading' | 'body' | 'code'): boolean {
  const font = slot === 'heading' ? theme.heading_font : slot === 'body' ? theme.body_font : theme.code_font
  return !font
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

function getThemeActionStyle(theme: WorkspaceThemeItem): CSSProperties {
  return {
    color: theme.palette.text.secondary,
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

.theme-icon-button {
  display: inline-flex;
  height: 30px;
  width: 30px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: #94a3b8;
  transition: all 0.16s ease;
}

.theme-icon-button:hover {
  background: #f1f5f9;
  color: #334155;
}

.theme-icon-button-danger {
  display: inline-flex;
  height: 30px;
  width: 30px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: #94a3b8;
  transition: all 0.16s ease;
}

.theme-icon-button-danger:hover {
  background: #fff1f2;
  color: #e11d48;
}
</style>
