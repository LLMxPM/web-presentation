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
      <SwatchBook class="h-5 w-5 text-accent" />
    </template>

    <template #actions>
      <UiButton
        v-if="workspaceId"
        type="button"
        variant="ghost"
        size="sm"
        title="打开主题与字体管理页"
        @click="openThemeFontPage"
      >
        <ArrowUpRight class="h-4 w-4" />
        <span class="hidden lg:inline">管理</span>
      </UiButton>
    </template>

    <div class="shrink-0 border-b border-border-muted bg-canvas/80 px-4 py-3">
      <div class="grid grid-cols-2 rounded-xl bg-surface-muted p-1">
        <UiButton
          variant="ghost"
          size="sm"
          :class="activeTab === 'themes' ? 'bg-surface text-accent shadow-sm' : 'text-text-muted hover:text-text'"
          @click="activeTab = 'themes'"
        >
          主题
        </UiButton>
        <UiButton
          variant="ghost"
          size="sm"
          :class="activeTab === 'fonts' ? 'bg-surface text-accent shadow-sm' : 'text-text-muted hover:text-text'"
          @click="activeTab = 'fonts'"
        >
          字体
        </UiButton>
      </div>
    </div>

    <div v-if="activeTab === 'themes'" class="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      <DataState :state="themeDataState" :title="themeDataState === 'empty' ? (searchKeyword ? '未找到相关主题' : '暂无主题') : undefined">
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
        :heading-font-label="theme.heading_font_family?.name || theme.heading_font_label || 'sans-serif'"
        :body-font-label="theme.body_font_family?.name || theme.body_font_label || 'sans-serif'"
        :code-font-label="theme.code_font_family?.name || theme.code_font_label || 'monospace'"
        :heading-font-family="fontFamilyById.get(theme.heading_font_family_id || -1) || null"
        :body-font-family="fontFamilyById.get(theme.body_font_family_id || -1) || null"
        :code-font-family="fontFamilyById.get(theme.code_font_family_id || -1) || null"
        collapsible
        :default-expanded="workspace?.default_theme_key === theme.key"
      >
        <template #title-suffix>
          <span
            v-if="workspace?.default_theme_key === theme.key"
            class="rounded-full border border-accent-muted bg-surface-selected px-2 py-0.5 text-[10px] font-bold text-accent"
          >
            默认
          </span>
        </template>
      </ThemePreviewCard>
      </DataState>
    </div>

    <div v-else class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
      <DataState :state="fontDataState" :title="fontDataState === 'empty' ? (searchKeyword ? '未找到相关字体' : '暂无字体注册') : undefined">
      <article
        v-for="font in filteredFonts"
        :key="font.id"
        class="rounded-xl border border-border bg-surface p-3 shadow-sm transition-colors hover:border-accent-ring"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="truncate text-sm font-bold text-text">{{ font.font_family }}</h3>
            <p class="mt-0.5 truncate font-mono text-[11px] text-text-disabled">{{ font.asset_name }}</p>
          </div>
          <span
            class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold"
            :class="font.status === 'active' ? 'bg-success-muted text-success-strong' : 'bg-surface-muted text-text-muted'"
          >
            {{ font.status === 'active' ? '启用' : '归档' }}
          </span>
        </div>

        <div class="mt-3 rounded-lg bg-canvas p-3 text-text" :style="{ fontFamily: resolveSidebarFontFamily(font) }">
          <div class="text-2xl font-semibold">Aa 中文 0123</div>
          <div class="mt-1 text-xs text-text-muted">{{ font.font_weight }} / {{ font.font_style }} / {{ font.font_format }}</div>
        </div>

        <div class="mt-3 flex items-center justify-end gap-2">
          <UiButton
            type="button"
            variant="secondary"
            size="sm"
            title="预览字体"
            @click="previewFont = font"
          >
            <Eye class="h-3.5 w-3.5" />
            预览
          </UiButton>
          <UiButton
            type="button"
            variant="secondary"
            size="sm"
            title="复制 font-family"
            @click="copyFontFamily(font)"
          >
            <Copy class="h-3.5 w-3.5" />
            复制名称
          </UiButton>
        </div>
      </article>
      </DataState>
    </div>
  </LibrarySidebarPanel>

  <UiDialog
    :open="!!previewFont"
    :title="previewFont?.font_family || '字体预览'"
    :description="previewFont?.asset_name || ''"
    size="standard"
    body-preset="auto"
    :z-index="240"
    @update:open="handlePreviewDialogVisibleChange"
  >
    <div v-if="previewFont" class="space-y-4" :style="{ fontFamily: resolveSidebarFontFamily(previewFont) }">
      <p class="text-5xl leading-tight text-text-strong">AaBbCc 012345</p>
      <p class="text-3xl leading-relaxed text-text">字体效果预览：主题标题、正文与数字展示</p>
      <p class="text-lg leading-8 text-text-secondary">Web Presentation 主题字体预览，用于快速确认字体注册后的视觉效果。</p>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowUpRight, Copy, Eye, SwatchBook } from '@lucide/vue'

import { listWorkspaceFontFamilies } from '@/api/assets'
import { getWorkspace } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import { listWorkspaceThemes } from '@/api/themes'
import { UiButton, UiDialog } from '@/components/ui'
import DataState from '@/components/patterns/DataState.vue'
import { resolveFontPreviewFamily, useFontPreviewRegistry } from '@/composables/useFontPreviewRegistry'
import type { WorkspaceFontConfigItem, WorkspaceFontFamilyItem, WorkspaceItem, WorkspaceThemeItem } from '@/types/api'
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
const themeDataState = computed<'loading' | 'empty' | 'ready'>(() => (
  loading.value ? 'loading' : filteredThemes.value.length ? 'ready' : 'empty'
))
const fontDataState = computed<'loading' | 'empty' | 'ready'>(() => (
  loading.value ? 'loading' : filteredFonts.value.length ? 'ready' : 'empty'
))
const themes = ref<WorkspaceThemeItem[]>([])
const fonts = ref<WorkspaceFontConfigItem[]>([])
const fontFamilies = ref<WorkspaceFontFamilyItem[]>([])
const fontFamilyById = computed(() => new Map(fontFamilies.value.map(family => [family.id, family])))
const searchKeyword = ref('')
const workspace = ref<WorkspaceItem | null>(null)
const activeTab = ref<SidebarTab>('themes')
const previewFont = ref<WorkspaceFontConfigItem | null>(null)

useFontPreviewRegistry(computed(() => fontFamilies.value))

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

async function loadData(workspaceId: number): Promise<void> {
  loading.value = true
  try {
    const [themeResponse, fontResponse, workspaceDetail] = await Promise.all([
      listWorkspaceThemes(workspaceId, { page: 1, page_size: 100 }),
      listWorkspaceFontFamilies(workspaceId, { page: 1, page_size: 100 }),
      getWorkspace(workspaceId),
    ])
    themes.value = themeResponse.items
    fontFamilies.value = fontResponse.items
    fonts.value = fontResponse.items.flatMap(family => family.faces)
    workspace.value = workspaceDetail
  } catch (error) {
    Message.error(getErrorMessage(error, '加载主题与字体失败。'))
  } finally {
    loading.value = false
  }
}

/**
 * 解析字体侧栏卡片和弹窗实际使用的预览字体族。
 * @param font 当前字体 face
 */
function resolveSidebarFontFamily(font: WorkspaceFontConfigItem): string {
  return resolveFontPreviewFamily(fontFamilyById.value.get(font.family_id), font.font_family)
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
    theme.heading_font_family?.name || '',
    theme.body_font_family?.name || '',
    theme.code_font_family?.name || '',
    theme.heading_font_label || '',
    theme.body_font_label || '',
    theme.code_font_label || '',
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

/**
 * 同步字体预览弹窗可见状态，关闭时清空当前预览字体。
 * @param value 弹窗目标可见状态
 */
function handlePreviewDialogVisibleChange(value: boolean): void {
  if (!value) {
    previewFont.value = null
  }
}
</script>
