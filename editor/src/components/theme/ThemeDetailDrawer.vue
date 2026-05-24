<!-- 文件功能：展示工作空间主题详情抽屉，集中查看主题预览、资源绑定、颜色 token 与运行时 YAML。 -->
<template>
  <Teleport to="body">
    <Transition name="theme-detail-fade">
      <div v-if="modelValue" class="fixed inset-0 z-[260] flex justify-end">
        <div class="absolute inset-0 bg-slate-950/45 backdrop-blur-sm" @click="closeDrawer"></div>

        <Transition name="theme-detail-slide">
          <aside
            v-if="modelValue"
            class="relative flex h-full w-[min(960px,calc(100vw-72px))] min-w-[720px] flex-col overflow-hidden border-l border-slate-200 bg-white shadow-2xl"
          >
            <header class="flex shrink-0 items-start justify-between gap-4 border-b border-slate-200 bg-white px-6 py-5">
              <div class="min-w-0">
                <div class="flex min-w-0 items-center gap-2">
                  <h2 class="truncate text-xl font-black tracking-tight text-slate-900">
                    {{ theme?.name || '主题详情' }}
                  </h2>
                  <span
                    v-if="isDefaultTheme"
                    class="shrink-0 rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[11px] font-black text-indigo-600"
                  >
                    默认
                  </span>
                </div>
                <p class="mt-1 truncate font-mono text-xs text-slate-400">{{ theme?.key || '正在加载...' }}</p>
              </div>

              <div class="flex shrink-0 items-center gap-2">
                <BaseButton
                  v-if="theme && !isDefaultTheme"
                  size="sm"
                  variant="ghost"
                  @click="emit('setDefault', theme)"
                >
                  <Pin class="h-3.5 w-3.5" />
                  设为默认
                </BaseButton>
                <BaseButton v-if="theme" size="sm" variant="ghost" @click="emit('copy', theme)">
                  <Copy class="h-3.5 w-3.5" />
                  复制
                </BaseButton>
                <BaseButton v-if="theme" size="sm" @click="emit('edit', theme)">
                  <Pencil class="h-3.5 w-3.5" />
                  编辑
                </BaseButton>
                <BaseCloseButton label="关闭主题详情" @click="closeDrawer" />
              </div>
            </header>

            <div v-if="loading" class="flex flex-1 items-center justify-center text-sm font-bold text-slate-400">
              正在加载主题详情...
            </div>

            <div v-else-if="!theme" class="flex flex-1 items-center justify-center p-8">
              <div class="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-8 py-10 text-center">
                <SwatchBook class="mx-auto mb-3 h-10 w-10 text-slate-300" />
                <p class="text-sm font-bold text-slate-500">未找到主题详情</p>
              </div>
            </div>

            <div v-else class="min-h-0 flex-1 overflow-y-auto bg-slate-50/80 p-6">
              <div class="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
                <section class="space-y-5">
                  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div class="mb-3 flex items-center justify-between gap-3">
                      <div>
                        <h3 class="text-sm font-black text-slate-900">完整预览</h3>
                        <p class="mt-1 text-xs text-slate-400">按当前主题配置渲染页面组件、图标、Logo 和颜色关系。</p>
                      </div>
                    </div>
                    <ThemePreviewCard
                      class="rounded-xl shadow-none"
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
                    />
                  </section>

                  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <h3 class="text-sm font-black text-slate-900">颜色 token</h3>
                    <div class="mt-4 grid gap-4 lg:grid-cols-2">
                      <div v-for="group in colorGroups" :key="group.key" class="rounded-xl border border-slate-100 bg-slate-50 p-3">
                        <div class="text-xs font-black text-slate-700">{{ group.label }}</div>
                        <div class="mt-3 space-y-2">
                          <div v-for="item in group.items" :key="item.key" class="flex items-center justify-between gap-3">
                            <div class="flex min-w-0 items-center gap-2">
                              <span class="h-5 w-5 shrink-0 rounded-md border border-white shadow ring-1 ring-slate-200" :style="{ backgroundColor: item.value }"></span>
                              <span class="truncate text-xs font-semibold text-slate-600">{{ item.label }}</span>
                            </div>
                            <code class="shrink-0 rounded bg-white px-1.5 py-0.5 text-[11px] font-semibold text-slate-500">{{ item.value }}</code>
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

                  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div class="flex items-center justify-between gap-3">
                      <div>
                        <h3 class="text-sm font-black text-slate-900">Runtime YAML</h3>
                        <p class="mt-1 text-xs text-slate-400">后端动态组装后下发给 Runtime 的主题配置。</p>
                      </div>
                    </div>
                    <pre class="mt-4 max-h-[360px] overflow-auto rounded-xl border border-slate-200 bg-slate-950 p-4 text-xs leading-5 text-slate-100">{{ theme.resolved_theme_config_yaml || '暂无配置内容' }}</pre>
                  </section>
                </section>

                <aside class="space-y-4">
                  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <h3 class="text-sm font-black text-slate-900">配置摘要</h3>
                    <dl class="mt-4 grid grid-cols-2 gap-3 text-xs">
                      <div class="rounded-xl bg-slate-50 p-3">
                        <dt class="text-slate-400">主题 key</dt>
                        <dd class="mt-1 truncate font-black text-slate-800">{{ theme.key }}</dd>
                      </div>
                      <div class="rounded-xl bg-slate-50 p-3">
                        <dt class="text-slate-400">标题字体</dt>
                        <dd class="mt-1 truncate font-black text-slate-800">{{ theme.heading_font?.font_family || '未绑定' }}</dd>
                      </div>
                      <div class="rounded-xl bg-slate-50 p-3">
                        <dt class="text-slate-400">正文字体</dt>
                        <dd class="mt-1 truncate font-black text-slate-800">{{ theme.body_font?.font_family || '未绑定' }}</dd>
                      </div>
                      <div class="rounded-xl bg-slate-50 p-3">
                        <dt class="text-slate-400">更新时间</dt>
                        <dd class="mt-1 truncate font-black text-slate-800">{{ formatDate(theme.updated_at) }}</dd>
                      </div>
                    </dl>
                    <p class="mt-4 text-xs leading-5 text-slate-500">{{ theme.description || '未填写主题说明。' }}</p>
                  </section>

                  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <h3 class="text-sm font-black text-slate-900">字体绑定</h3>
                    <div class="mt-4 space-y-3">
                      <ThemeDetailMetaCard label="标题字体" :value="theme.heading_font?.font_family" :description="fontDescription(theme.heading_font)" />
                      <ThemeDetailMetaCard label="正文字体" :value="theme.body_font?.font_family" :description="fontDescription(theme.body_font)" />
                      <ThemeDetailMetaCard label="代码字体" :value="theme.code_font?.font_family" :description="fontDescription(theme.code_font)" />
                    </div>
                  </section>

                  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <h3 class="text-sm font-black text-slate-900">品牌资源</h3>
                    <div class="mt-4 space-y-3">
                      <ThemeDetailMetaCard label="主题 Logo" :value="theme.logo_asset?.name" :description="theme.logo_asset?.original_name" />
                      <ThemeDetailMetaCard label="反色 Logo" :value="theme.invert_logo_asset?.name" :description="theme.invert_logo_asset?.original_name" />
                      <ThemeDetailMetaCard label="项目图标" :value="theme.project_icon_asset?.name || theme.project_icon_name || ''" :description="theme.project_icon_asset?.original_name" />
                    </div>
                  </section>

                  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                    <h3 class="text-sm font-black text-slate-900">危险操作</h3>
                    <button
                      type="button"
                      class="mt-4 inline-flex h-9 w-full items-center justify-center gap-2 rounded-xl border border-rose-100 bg-white text-sm font-bold text-rose-600 transition-colors hover:bg-rose-50"
                      @click="emit('delete', theme)"
                    >
                      <Trash2 class="h-4 w-4" />
                      删除主题
                    </button>
                  </section>
                </aside>
              </div>
            </div>
          </aside>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch } from 'vue'
import { Copy, Pencil, Pin, SwatchBook, Trash2 } from '@lucide/vue'

import { getWorkspaceTheme } from '@/api/themes'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'
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
  edit: [theme: WorkspaceThemeItem]
  copy: [theme: WorkspaceThemeItem]
  delete: [theme: WorkspaceThemeItem]
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
 * 拉取当前主题详情，保证抽屉展示的是接口返回的最新完整配置。
 */
async function loadThemeDetail(): Promise<void> {
  if (!props.workspaceId || !props.themeId) {
    theme.value = null
    return
  }

  const currentToken = loadToken.value + 1
  loadToken.value = currentToken
  loading.value = true
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
 * 关闭详情抽屉并通知父级同步可见状态。
 */
function closeDrawer(): void {
  emit('update:modelValue', false)
}

/**
 * 格式化字体元信息，缺失时返回统一占位。
 * @param font 字体注册项
 */
function fontDescription(font: WorkspaceFontConfigItem | null | undefined): string {
  if (!font) return '未绑定已注册字体'
  return `${font.font_format} / ${font.font_weight} / ${font.font_style} / ${font.font_display}`
}

/**
 * 格式化更新时间，非法时间显示占位。
 * @param value 接口返回的 ISO 时间
 */
function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
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
    return () => h('div', { class: 'rounded-xl border border-slate-100 bg-slate-50 p-3' }, [
      h('div', { class: 'text-[11px] font-black text-slate-400' }, metaProps.label),
      h('div', { class: 'mt-1 truncate text-sm font-black text-slate-800' }, metaProps.value || '未设置'),
      h('div', { class: 'mt-1 truncate text-[11px] text-slate-400' }, metaProps.description || '-'),
    ])
  },
})
</script>

<style scoped>
.theme-detail-fade-enter-active,
.theme-detail-fade-leave-active {
  transition: opacity 0.2s ease;
}

.theme-detail-fade-enter-from,
.theme-detail-fade-leave-to {
  opacity: 0;
}

.theme-detail-slide-enter-active,
.theme-detail-slide-leave-active {
  transition: transform 0.24s ease;
}

.theme-detail-slide-enter-from,
.theme-detail-slide-leave-to {
  transform: translateX(100%);
}
</style>
