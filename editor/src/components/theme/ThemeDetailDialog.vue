<!-- 文件功能：展示工作空间主题详情弹窗，集中查看主题预览、颜色 token，以及合并后的字体与品牌资源摘要。 -->
<template>
  <UiDialog
    :open="modelValue"
    :title="theme ? `${theme.name} · 主题详情` : '主题详情'"
    size="canvas"
    body-preset="auto"
    @update:open="handleVisibleChange"
  >
    <div v-if="loading" class="flex min-h-[320px] items-center justify-center rounded-2xl bg-canvas/80 text-sm font-bold text-text-disabled">
      正在加载主题详情...
    </div>

    <div v-else-if="!theme" class="flex min-h-[320px] items-center justify-center rounded-2xl bg-canvas/80">
      <div class="rounded-2xl border border-dashed border-border bg-surface px-8 py-10 text-center shadow-sm">
        <SwatchBook class="mx-auto mb-3 h-10 w-10 text-text-faint" />
        <p class="text-sm font-bold text-text-muted">未找到主题详情</p>
      </div>
    </div>

    <div v-else data-testid="theme-detail-dialog" class="space-y-5 rounded-2xl bg-canvas/80 p-0.5">
      <section class="rounded-2xl border border-border bg-surface p-4 shadow-sm">
        <div class="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-black text-text-strong">快速预览</h3>
          </div>
          <UiButton
            v-if="!isDefaultTheme"
            size="sm"
            variant="ghost"
            @click="emit('setDefault', theme)"
          >
            <Pin class="h-3.5 w-3.5" />
            设为默认
          </UiButton>
        </div>
        <ThemePreviewCard
          class="w-full rounded-xl shadow-none"
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
          layout-mode="compact"
        >
          <template #title-suffix>
            <span
              v-if="isDefaultTheme"
              class="shrink-0 rounded-full border border-accent-muted bg-surface-selected px-2 py-0.5 text-[11px] font-black text-accent"
            >
              默认
            </span>
          </template>
        </ThemePreviewCard>
      </section>

      <div class="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <section class="rounded-2xl border border-border bg-surface p-4 shadow-sm">
          <h3 class="text-sm font-black text-text-strong">颜色 token</h3>
          <div class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div
              v-for="group in colorGroups"
              :key="group.key"
              class="rounded-xl border border-border-muted bg-canvas p-3"
            >
              <div class="text-xs font-black text-text-emphasis">{{ group.label }}</div>
              <div class="mt-3 space-y-2">
                <div v-for="item in group.items" :key="item.key" class="flex items-center justify-between gap-3">
                  <div class="flex min-w-0 items-center gap-2">
                    <span
                      class="h-5 w-5 shrink-0 rounded-md border border-surface shadow ring-1 ring-border"
                      :style="{ backgroundColor: item.value }"
                    ></span>
                    <span class="truncate text-xs font-semibold text-text-secondary">{{ item.label }}</span>
                  </div>
                  <code class="shrink-0 rounded bg-surface px-1.5 py-0.5 text-[11px] font-semibold text-text-muted">
                    {{ item.value }}
                  </code>
                </div>
              </div>
            </div>
          </div>

          <div class="mt-4 rounded-xl border border-border-muted bg-canvas p-3">
            <div class="text-xs font-black text-text-emphasis">强调色</div>
            <div class="mt-3 grid grid-cols-3 gap-2 lg:grid-cols-6">
              <div
                v-for="(color, index) in theme.palette.accent"
                :key="`${color}-${index}`"
                class="rounded-lg border border-border bg-surface p-2"
              >
                <div class="h-8 rounded-md" :style="{ backgroundColor: color }"></div>
                <code class="mt-2 block truncate text-center text-[10px] font-semibold text-text-muted">{{ color }}</code>
              </div>
            </div>
          </div>
        </section>

        <aside>
          <section class="rounded-2xl border border-border bg-surface p-4 shadow-sm">
            <div>
              <h3 class="text-sm font-black text-text-strong">字体与品牌资源</h3>
            </div>

            <div class="mt-4 grid gap-4 sm:grid-cols-2">
              <section>
                <h4 class="text-xs font-black tracking-[0.12em] text-text-muted">字体绑定</h4>
                <div class="mt-2.5 space-y-2.5">
                  <ThemeDetailMetaCard label="标题字体" :value="theme.heading_font_family?.name || theme.heading_font_label || undefined" :description="fontDescription(theme.heading_font_family, theme.heading_font_label)" />
                  <ThemeDetailMetaCard label="正文字体" :value="theme.body_font_family?.name || theme.body_font_label || undefined" :description="fontDescription(theme.body_font_family, theme.body_font_label)" />
                  <ThemeDetailMetaCard label="代码字体" :value="theme.code_font_family?.name || theme.code_font_label || undefined" :description="fontDescription(theme.code_font_family, theme.code_font_label)" />
                </div>
              </section>

              <section>
                <h4 class="text-xs font-black tracking-[0.12em] text-text-muted">品牌资源</h4>
                <div class="mt-2.5 space-y-2.5">
                  <ThemeDetailMetaCard label="主题 Logo" :value="theme.logo_asset?.name" :description="theme.logo_asset?.original_name" />
                  <ThemeDetailMetaCard label="反色 Logo" :value="theme.invert_logo_asset?.name" :description="theme.invert_logo_asset?.original_name" />
                  <ThemeDetailMetaCard label="项目图标" :value="theme.project_icon_asset?.name || theme.project_icon_name || ''" :description="theme.project_icon_asset?.original_name" />
                </div>
              </section>
            </div>
          </section>
        </aside>
      </div>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch } from 'vue'
import { Pin, SwatchBook } from '@lucide/vue'

import { listWorkspaceFontFamilies } from '@/api/assets'
import { getWorkspaceTheme } from '@/api/themes'
import { UiButton, UiDialog } from '@/components/ui'
import type { WorkspaceFontFamilyItem, WorkspaceThemeFontFamilySummary, WorkspaceThemeItem } from '@/types/api'
import ThemePreviewCard from './ThemePreviewCard.vue'

const props = defineProps<{
  modelValue: boolean
  workspaceId: number | null
  themeId: number | null
  defaultThemeKey?: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  setDefault: [theme: WorkspaceThemeItem]
}>()

const loading = ref(false)
const theme = ref<WorkspaceThemeItem | null>(null)
const fontFamilies = ref<WorkspaceFontFamilyItem[]>([])
const loadToken = ref(0)

const isDefaultTheme = computed(() => Boolean(theme.value && props.defaultThemeKey === theme.value.key))
const fontFamilyById = computed(() => new Map(fontFamilies.value.map(family => [family.id, family])))
const colorGroups = computed(() => {
  if (!theme.value) return []
  return [
    {
      key: 'text',
      label: '文字',
      items: [
        { key: 'text.primary', label: '主文字', value: theme.value.palette.text.primary },
        { key: 'text.secondary', label: '副文字', value: theme.value.palette.text.secondary },
        { key: 'text.invert', label: '反色文字', value: theme.value.palette.text.invert },
      ],
    },
    {
      key: 'surface',
      label: '背景与边框',
      items: [
        { key: 'background.default', label: '主背景', value: theme.value.palette.background.default },
        { key: 'background.invert', label: '反色背景', value: theme.value.palette.background.invert },
        { key: 'border.default', label: '主边框', value: theme.value.palette.border.default },
        { key: 'border.subtle', label: '弱边框', value: theme.value.palette.border.subtle },
      ],
    },
    {
      key: 'link',
      label: '链接',
      items: [
        { key: 'link.default', label: '默认链接', value: theme.value.palette.link.default },
        { key: 'link.hover', label: '悬停链接', value: theme.value.palette.link.hover },
        { key: 'link.visited', label: '访问后链接', value: theme.value.palette.link.visited },
      ],
    },
  ]
})

watch(
  () => [props.modelValue, props.workspaceId, props.themeId] as const,
  ([visible]) => {
    if (!visible) return
    void loadThemeDetail()
  },
  { immediate: true },
)

/**
 * 拉取当前主题详情，保证弹窗展示的是接口返回的最新完整配置。
 */
async function loadThemeDetail(): Promise<void> {
  if (!props.workspaceId || !props.themeId) {
    theme.value = null
    return
  }

  const currentToken = loadToken.value + 1
  loadToken.value = currentToken
  loading.value = true
  theme.value = null
  try {
    const [response, familyResponse] = await Promise.all([
      getWorkspaceTheme(props.workspaceId, props.themeId),
      listWorkspaceFontFamilies(props.workspaceId, { page: 1, page_size: 100 })
        .catch(() => ({ items: [] as WorkspaceFontFamilyItem[] })),
    ])
    if (loadToken.value === currentToken) {
      theme.value = response
      fontFamilies.value = familyResponse.items
    }
  } finally {
    if (loadToken.value === currentToken) {
      loading.value = false
    }
  }
}

/**
 * 同步详情弹窗可见状态，供 UiDialog 的关闭行为复用。
 * @param value 弹窗目标可见状态
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 描述主题字体槽位的绑定状态，区分已绑定字体族、名称回退和未绑定。
 * @param family 主题绑定的字体族摘要
 * @param label 字体名称回退展示值
 */
function fontDescription(family: WorkspaceThemeFontFamilySummary | null | undefined, label: string | null): string {
  if (family) return '已绑定字体族，同族多字重自动匹配'
  if (label) return '未绑定字体族，按名称回退'
  return '未绑定已注册字体'
}

const ThemeDetailMetaCard = defineComponent({
  name: 'ThemeDetailMetaCard',
  props: {
    label: {
      type: String,
      required: true,
    },
    value: {
      type: String,
      default: '',
    },
    description: {
      type: String,
      default: '',
    },
  },
  setup(metaProps) {
    return () => h('div', { class: 'rounded-lg border border-border-muted bg-canvas px-3 py-2.5' }, [
      h('div', { class: 'text-[11px] font-black text-text-disabled' }, metaProps.label),
      h('div', { class: 'mt-1 truncate text-[13px] font-black text-text' }, metaProps.value || '未设置'),
      h('div', { class: 'mt-1 truncate text-[11px] leading-4 text-text-disabled' }, metaProps.description || '-'),
    ])
  },
})
</script>

