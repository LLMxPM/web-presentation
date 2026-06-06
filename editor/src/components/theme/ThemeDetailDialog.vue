<!-- 文件功能：展示工作空间主题详情弹窗，集中查看主题预览、颜色 token，以及合并后的字体与品牌资源摘要。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    :title="theme ? `${theme.name} · 主题详情` : '主题详情'"
    width="1280px"
    body-class="max-h-[86vh] overflow-y-auto bg-slate-50/80 px-6 py-5"
    @update:model-value="handleVisibleChange"
  >
    <div v-if="loading" class="flex min-h-[320px] items-center justify-center text-sm font-bold text-slate-400">
      正在加载主题详情...
    </div>

    <div v-else-if="!theme" class="flex min-h-[320px] items-center justify-center">
      <div class="rounded-2xl border border-dashed border-slate-200 bg-white px-8 py-10 text-center shadow-sm">
        <SwatchBook class="mx-auto mb-3 h-10 w-10 text-slate-300" />
        <p class="text-sm font-bold text-slate-500">未找到主题详情</p>
      </div>
    </div>

    <div v-else data-testid="theme-detail-dialog" class="space-y-5">
      <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div class="mb-3 flex items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-black text-slate-900">快速预览</h3>
          </div>
          <BaseButton
            v-if="!isDefaultTheme"
            size="sm"
            variant="ghost"
            @click="emit('setDefault', theme)"
          >
            <Pin class="h-3.5 w-3.5" />
            设为默认
          </BaseButton>
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
          :heading-font-label="theme.heading_font?.font_family || 'sans-serif'"
          :body-font-label="theme.body_font?.font_family || 'sans-serif'"
          :code-font-label="theme.code_font?.font_family || 'monospace'"
          layout-mode="compact"
        >
          <template #title-suffix>
            <span
              v-if="isDefaultTheme"
              class="shrink-0 rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[11px] font-black text-indigo-600"
            >
              默认
            </span>
          </template>
        </ThemePreviewCard>
      </section>

      <div class="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 class="text-sm font-black text-slate-900">颜色 token</h3>
          <div class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div
              v-for="group in colorGroups"
              :key="group.key"
              class="rounded-xl border border-slate-100 bg-slate-50 p-3"
            >
              <div class="text-xs font-black text-slate-700">{{ group.label }}</div>
              <div class="mt-3 space-y-2">
                <div v-for="item in group.items" :key="item.key" class="flex items-center justify-between gap-3">
                  <div class="flex min-w-0 items-center gap-2">
                    <span
                      class="h-5 w-5 shrink-0 rounded-md border border-white shadow ring-1 ring-slate-200"
                      :style="{ backgroundColor: item.value }"
                    ></span>
                    <span class="truncate text-xs font-semibold text-slate-600">{{ item.label }}</span>
                  </div>
                  <code class="shrink-0 rounded bg-white px-1.5 py-0.5 text-[11px] font-semibold text-slate-500">
                    {{ item.value }}
                  </code>
                </div>
              </div>
            </div>
          </div>

          <div class="mt-4 rounded-xl border border-slate-100 bg-slate-50 p-3">
            <div class="text-xs font-black text-slate-700">强调色</div>
            <div class="mt-3 grid grid-cols-3 gap-2 lg:grid-cols-6">
              <div
                v-for="(color, index) in theme.palette.accent"
                :key="`${color}-${index}`"
                class="rounded-lg border border-slate-200 bg-white p-2"
              >
                <div class="h-8 rounded-md" :style="{ backgroundColor: color }"></div>
                <code class="mt-2 block truncate text-center text-[10px] font-semibold text-slate-500">{{ color }}</code>
              </div>
            </div>
          </div>
        </section>

        <aside>
          <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div>
              <h3 class="text-sm font-black text-slate-900">字体与品牌资源</h3>
              <p class="mt-1 text-xs text-slate-400">把主题绑定字体和品牌资源收敛到同一块区域，便于快速核对。</p>
            </div>

            <div class="mt-4 grid gap-4 sm:grid-cols-2">
              <section>
                <h4 class="text-xs font-black tracking-[0.12em] text-slate-500">字体绑定</h4>
                <div class="mt-2.5 space-y-2.5">
                  <ThemeDetailMetaCard label="标题字体" :value="theme.heading_font?.font_family" :description="fontDescription(theme.heading_font)" />
                  <ThemeDetailMetaCard label="正文字体" :value="theme.body_font?.font_family" :description="fontDescription(theme.body_font)" />
                  <ThemeDetailMetaCard label="代码字体" :value="theme.code_font?.font_family" :description="fontDescription(theme.code_font)" />
                </div>
              </section>

              <section>
                <h4 class="text-xs font-black tracking-[0.12em] text-slate-500">品牌资源</h4>
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
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch } from 'vue'
import { Pin, SwatchBook } from '@lucide/vue'

import { getWorkspaceTheme } from '@/api/themes'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { WorkspaceFontConfigItem, WorkspaceThemeItem } from '@/types/api'
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
const loadToken = ref(0)

const isDefaultTheme = computed(() => Boolean(theme.value && props.defaultThemeKey === theme.value.key))
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
    const response = await getWorkspaceTheme(props.workspaceId, props.themeId)
    if (loadToken.value === currentToken) {
      theme.value = response
    }
  } finally {
    if (loadToken.value === currentToken) {
      loading.value = false
    }
  }
}

/**
 * 同步详情弹窗可见状态，供 BaseDialog 的关闭行为复用。
 * @param value 弹窗目标可见状态
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 格式化字体元信息，缺失时返回统一占位。
 * @param font 字体注册项
 */
function fontDescription(font: WorkspaceFontConfigItem | null | undefined): string {
  if (!font) return '未绑定已注册字体'
  return `${font.font_format} / ${font.font_weight} / ${font.font_style} / ${font.font_display}`
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
    return () => h('div', { class: 'rounded-lg border border-slate-100 bg-slate-50 px-3 py-2.5' }, [
      h('div', { class: 'text-[11px] font-black text-slate-400' }, metaProps.label),
      h('div', { class: 'mt-1 truncate text-[13px] font-black text-slate-800' }, metaProps.value || '未设置'),
      h('div', { class: 'mt-1 truncate text-[11px] leading-4 text-slate-400' }, metaProps.description || '-'),
    ])
  },
})
</script>
