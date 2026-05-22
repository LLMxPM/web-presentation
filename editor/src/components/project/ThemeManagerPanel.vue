<!-- 文件功能：提供只读主题与字体侧边栏，用于快速浏览主题、预览字体和复制字体名称。 -->
<template>
  <LibrarySidebarPanel
    :model-value="modelValue"
    title="主题字体"
    show-search
    v-model:search-value="searchKeyword"
    search-placeholder="搜索主题、字体或资源名..."
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #icon>
      <SwatchBook class="h-5 w-5 text-indigo-600" />
    </template>

    <template #actions>
      <button
        v-if="workspaceId"
        type="button"
        class="flex items-center gap-1 rounded-lg p-1.5 text-xs font-bold text-indigo-600 transition-colors hover:bg-indigo-50"
        title="打开主题与字体管理页"
        @click="openThemeFontPage"
      >
        <ArrowUpRight class="h-4 w-4" />
        <span class="hidden lg:inline">管理</span>
      </button>
    </template>

    <div class="shrink-0 border-b border-slate-100 bg-slate-50/80 px-4 py-3">
      <div class="grid grid-cols-2 rounded-xl bg-slate-100 p-1">
        <button
          type="button"
          class="h-8 rounded-lg px-3 text-xs font-bold transition-colors"
          :class="activeTab === 'themes' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
          @click="activeTab = 'themes'"
        >
          主题
        </button>
        <button
          type="button"
          class="h-8 rounded-lg px-3 text-xs font-bold transition-colors"
          :class="activeTab === 'fonts' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-800'"
          @click="activeTab = 'fonts'"
        >
          字体
        </button>
      </div>
    </div>

    <div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-slate-400">
      正在加载主题与字体...
    </div>

    <div v-else-if="activeTab === 'themes'" class="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      <div
        v-if="filteredThemes.length === 0"
        class="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-100 bg-slate-50 px-4 py-12 text-center"
      >
        <SwatchBook class="mb-3 h-10 w-10 text-slate-300" />
        <p class="text-sm font-semibold text-slate-500">{{ searchKeyword ? '未找到相关主题' : '暂无主题' }}</p>
      </div>

      <ThemePreviewCard
        v-for="theme in filteredThemes"
        :key="theme.id"
        class="rounded-2xl"
        :key-name="theme.key"
        :name="theme.name"
        :description="theme.description"
        :palette="theme.palette"
        :logo-url="theme.logo_asset?.url"
        :invert-logo-url="theme.invert_logo_asset?.url"
        :project-icon-url="theme.project_icon_asset?.url"
        :project-icon-name="theme.project_icon_name"
        :project-icon-analysis="theme.project_icon_asset?.analysis_metadata || null"
        :heading-font-label="theme.heading_font?.font_family || 'sans-serif'"
        :body-font-label="theme.body_font?.font_family || 'sans-serif'"
        :code-font-label="theme.code_font?.font_family || 'monospace'"
        collapsible
        :default-expanded="workspace?.default_theme_key === theme.key"
      >
        <template #title-suffix>
          <span
            v-if="workspace?.default_theme_key === theme.key"
            class="rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-600"
          >
            默认
          </span>
        </template>
      </ThemePreviewCard>
    </div>

    <div v-else class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
      <div
        v-if="filteredFonts.length === 0"
        class="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-100 bg-slate-50 px-4 py-12 text-center"
      >
        <Type class="mb-3 h-10 w-10 text-slate-300" />
        <p class="text-sm font-semibold text-slate-500">{{ searchKeyword ? '未找到相关字体' : '暂无字体注册' }}</p>
      </div>

      <article
        v-for="font in filteredFonts"
        :key="font.id"
        class="rounded-xl border border-slate-200 bg-white p-3 shadow-sm transition-colors hover:border-indigo-200"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="truncate text-sm font-bold text-slate-800">{{ font.font_family }}</h3>
            <p class="mt-0.5 truncate font-mono text-[11px] text-slate-400">{{ font.asset_name }}</p>
          </div>
          <span
            class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold"
            :class="font.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
          >
            {{ font.status === 'active' ? '启用' : '归档' }}
          </span>
        </div>

        <div class="mt-3 rounded-lg bg-slate-50 p-3 text-slate-800" :style="{ fontFamily: `'theme-sidebar-font-${font.id}'` }">
          <div class="text-2xl font-semibold">Aa 中文 0123</div>
          <div class="mt-1 text-xs text-slate-500">{{ font.font_weight }} / {{ font.font_style }} / {{ font.font_format }}</div>
        </div>

        <div class="mt-3 flex items-center justify-end gap-2">
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-xs font-bold text-slate-600 transition-colors hover:border-indigo-200 hover:text-indigo-600"
            title="预览字体"
            @click="previewFont = font"
          >
            <Eye class="h-3.5 w-3.5" />
            预览
          </button>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-xs font-bold text-slate-600 transition-colors hover:border-indigo-200 hover:text-indigo-600"
            title="复制 font-family"
            @click="copyFontFamily(font)"
          >
            <Copy class="h-3.5 w-3.5" />
            复制名称
          </button>
        </div>
      </article>
    </div>
  </LibrarySidebarPanel>

  <Teleport to="body">
    <Transition name="fade">
      <div v-if="previewFont" class="fixed inset-0 z-[240] flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-slate-950/60 backdrop-blur-sm" @click="previewFont = null"></div>
        <div class="relative w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl">
          <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
              <h2 class="truncate text-lg font-bold text-slate-800">{{ previewFont.font_family }}</h2>
              <p class="mt-1 truncate font-mono text-xs text-slate-400">{{ previewFont.asset_name }}</p>
            </div>
            <button class="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" @click="previewFont = null">
              <X class="h-4 w-4" />
            </button>
          </div>

          <div class="mt-6 space-y-4" :style="{ fontFamily: `'theme-sidebar-font-${previewFont.id}'` }">
            <p class="text-5xl leading-tight text-slate-900">AaBbCc 012345</p>
            <p class="text-3xl leading-relaxed text-slate-800">字体效果预览：主题标题、正文与数字展示</p>
            <p class="text-lg leading-8 text-slate-600">Web Presentation 主题字体预览，用于快速确认字体注册后的视觉效果。</p>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowUpRight, Copy, Eye, SwatchBook, Type, X } from 'lucide-vue-next'

import { listWorkspaceFonts } from '@/api/assets'
import { getWorkspace } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import { listWorkspaceThemes } from '@/api/themes'
import type { WorkspaceFontConfigItem, WorkspaceItem, WorkspaceThemeItem } from '@/types/api'
import { Message } from '@/utils/message'
import { buildWorkspaceThemesPath } from '@/utils/workspace-routes'
import ThemePreviewCard from '@/components/theme/ThemePreviewCard.vue'
import LibrarySidebarPanel from '@/components/project/LibrarySidebarPanel.vue'

type SidebarTab = 'themes' | 'fonts'

const props = defineProps<{
  modelValue: boolean
  workspaceId: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const router = useRouter()
const loading = ref(false)
const themes = ref<WorkspaceThemeItem[]>([])
const fonts = ref<WorkspaceFontConfigItem[]>([])
const searchKeyword = ref('')
const workspace = ref<WorkspaceItem | null>(null)
const activeTab = ref<SidebarTab>('themes')
const previewFont = ref<WorkspaceFontConfigItem | null>(null)

const filteredThemes = computed(() => {
  const keyword = normalizeSearchKeyword(searchKeyword.value)
  if (!keyword) return themes.value
  return themes.value.filter(theme => isThemeMatchedByKeyword(theme, keyword))
})

const filteredFonts = computed(() => {
  const keyword = normalizeSearchKeyword(searchKeyword.value)
  if (!keyword) return fonts.value
  return fonts.value.filter(font => isFontMatchedByKeyword(font, keyword))
})

watch(
  () => [props.modelValue, props.workspaceId] as const,
  async ([visible, workspaceId]) => {
    if (!visible || !workspaceId) return
    await loadData(workspaceId)
  },
  { immediate: true },
)

watch(fonts, (items) => {
  let styleTag = document.getElementById('theme-sidebar-font-preview')
  if (!styleTag) {
    styleTag = document.createElement('style')
    styleTag.id = 'theme-sidebar-font-preview'
    document.head.appendChild(styleTag)
  }
  styleTag.innerHTML = items
    .filter(font => font.asset_url)
    .map(font => `@font-face { font-family: 'theme-sidebar-font-${font.id}'; src: url('${font.asset_url}'); font-display: swap; }`)
    .join('\n')
})

async function loadData(workspaceId: number): Promise<void> {
  loading.value = true
  try {
    const [themeResponse, fontResponse, workspaceDetail] = await Promise.all([
      listWorkspaceThemes(workspaceId, { page: 1, page_size: 100 }),
      listWorkspaceFonts(workspaceId, { page: 1, page_size: 100 }),
      getWorkspace(workspaceId),
    ])
    themes.value = themeResponse.items
    fonts.value = fontResponse.items
    workspace.value = workspaceDetail
  } catch (error) {
    Message.error(getErrorMessage(error, '加载主题与字体失败。'))
  } finally {
    loading.value = false
  }
}

/**
 * 规范化搜索关键字，统一大小写与首尾空白处理。
 * @param keyword 用户输入的原始搜索文本
 * @returns 用于包含匹配的关键字
 */
function normalizeSearchKeyword(keyword: string): string {
  return keyword.trim().toLowerCase()
}

/**
 * 判断主题是否命中搜索关键字。
 * @param theme 待匹配的主题
 * @param keyword 已规范化的关键字
 * @returns 是否展示该主题
 */
function isThemeMatchedByKeyword(theme: WorkspaceThemeItem, keyword: string): boolean {
  return [
    theme.key,
    theme.name,
    theme.description || '',
    theme.project_icon_name || '',
    theme.heading_font?.font_family || '',
    theme.body_font?.font_family || '',
    theme.code_font?.font_family || '',
  ].some(value => String(value || '').toLowerCase().includes(keyword))
}

/**
 * 判断字体是否命中搜索关键字。
 * @param font 待匹配的字体配置
 * @param keyword 已规范化的关键字
 * @returns 是否展示该字体
 */
function isFontMatchedByKeyword(font: WorkspaceFontConfigItem, keyword: string): boolean {
  return [
    font.font_family,
    font.asset_name,
    font.font_format,
    font.font_weight,
    font.font_style,
    font.font_display,
  ].some(value => String(value || '').toLowerCase().includes(keyword))
}

async function copyFontFamily(font: WorkspaceFontConfigItem): Promise<void> {
  try {
    await navigator.clipboard.writeText(font.font_family)
    Message.success('字体名称已复制。')
  } catch {
    Message.error('复制字体名称失败，请检查浏览器剪贴板权限。')
  }
}

function openThemeFontPage(): void {
  if (!props.workspaceId) return
  emit('update:modelValue', false)
  void router.push(buildWorkspaceThemesPath(props.workspaceId))
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
