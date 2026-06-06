<!-- 文件功能：展示工作空间样式详情弹窗，集中呈现展示配置字段与 Markdown 样式规范。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    :title="style ? `${style.name} · 样式详情` : '样式详情'"
    width="860px"
    @update:model-value="handleVisibleChange"
  >
    <div v-if="style" class="space-y-5">
      <section class="rounded-lg border border-slate-200 bg-white p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="truncate text-lg font-black text-slate-900">{{ style.name }}</h3>
            <p class="mt-1 font-mono text-xs text-slate-400">{{ style.key }}</p>
          </div>
          <button
            v-if="style.theme_key"
            type="button"
            class="rounded-full bg-indigo-50 px-3 py-1 text-left text-xs font-black text-indigo-600 ring-1 ring-indigo-100 transition-colors hover:bg-indigo-100"
            :disabled="!matchedTheme"
            :title="matchedTheme ? '查看主题详情' : '未找到主题详情'"
            @click="openThemeDetail"
          >
            {{ themeBadgeText }}
          </button>
          <span v-else class="rounded-full bg-slate-100 px-3 py-1 text-xs font-black text-slate-500">
            不覆盖主题
          </span>
        </div>
        <p class="mt-3 text-sm leading-6 text-slate-500">{{ style.description || '未填写样式说明。' }}</p>
      </section>

      <section class="rounded-lg border border-slate-200 bg-white p-4">
        <h4 class="text-sm font-black text-slate-900">展示配置</h4>
        <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div
            v-for="item in detailItems"
            :key="item.label"
            class="rounded-lg border border-slate-100 bg-slate-50 px-4 py-3"
          >
            <p class="text-[11px] font-bold text-slate-400">{{ item.label }}</p>
            <p class="mt-1 text-sm font-black text-slate-800">{{ item.value }}</p>
          </div>
        </div>
      </section>

      <section class="rounded-lg border border-slate-200 bg-white p-4">
        <h4 class="text-sm font-black text-slate-900">样式规范</h4>
        <div v-if="selectedStyleSpecMarkdown" class="style-spec-markdown mt-3 rounded-lg border border-slate-100 bg-slate-50 px-5 py-4">
          <MarkdownRender :nodes="selectedStyleSpecNodes" />
        </div>
        <div v-else class="mt-3 flex min-h-[160px] items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-sm text-slate-400">
          当前样式还没有维护样式规范。
        </div>
      </section>
    </div>

    <div v-else class="py-10 text-center text-sm text-slate-400">
      当前没有可查看的样式。
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">关闭</BaseButton>
      <BaseButton variant="primary" :disabled="!style" @click="handleEditStyle">编辑样式</BaseButton>
    </template>
  </BaseDialog>

  <ThemeDetailDialog
    v-model="themeDetailVisible"
    :workspace-id="workspaceId"
    :theme-id="matchedTheme?.id ?? null"
    :default-theme-key="defaultThemeKey"
  />
</template>

<script setup lang="ts">
import 'markstream-vue/index.css'

import { computed, ref, watch } from 'vue'
import MarkdownRender, { getMarkdown, parseMarkdownToStructure } from 'markstream-vue'

import { listWorkspaceThemes } from '@/api/themes'
import ThemeDetailDialog from '@/components/theme/ThemeDetailDialog.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { ProjectMenuMode, WorkspaceStyleItem, WorkspaceThemeItem } from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  workspaceId: number | null
  style: WorkspaceStyleItem | null
  defaultThemeKey?: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  edit: [style: WorkspaceStyleItem]
}>()

const markdownParser = getMarkdown()
const matchedTheme = ref<WorkspaceThemeItem | null>(null)
const themeLoading = ref(false)
const themeDetailVisible = ref(false)
const themeLoadToken = ref(0)

const selectedStyleSpecMarkdown = computed(() => props.style?.style_spec_markdown?.trim() || '')
const selectedStyleSpecNodes = computed(() => parseMarkdownToStructure(selectedStyleSpecMarkdown.value, markdownParser, {
  final: true,
}))
const themeBadgeText = computed(() => {
  const themeKey = props.style?.theme_key
  if (!themeKey) return '不覆盖主题'
  if (themeLoading.value) return `${themeKey} / 加载中`
  if (matchedTheme.value) return `${matchedTheme.value.name} / ${matchedTheme.value.key}`
  return `${themeKey} / 未找到主题`
})
const detailItems = computed(() => {
  const style = props.style
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

watch(
  () => [props.modelValue, props.workspaceId, props.style?.theme_key] as const,
  ([visible]) => {
    if (!visible) {
      themeDetailVisible.value = false
      return
    }
    void loadMatchedTheme()
  },
  { immediate: true },
)

/**
 * 根据样式中的主题 key 加载主题摘要，用于顶部主题入口展示名称并打开详情。
 */
async function loadMatchedTheme(): Promise<void> {
  const themeKey = props.style?.theme_key?.trim()
  if (!props.workspaceId || !themeKey) {
    matchedTheme.value = null
    return
  }
  const currentToken = themeLoadToken.value + 1
  themeLoadToken.value = currentToken
  themeLoading.value = true
  try {
    const response = await listWorkspaceThemes(props.workspaceId, { page: 1, page_size: 100, keyword: themeKey })
    if (themeLoadToken.value !== currentToken) {
      return
    }
    matchedTheme.value = response.items.find(theme => theme.key === themeKey) ?? null
  } finally {
    if (themeLoadToken.value === currentToken) {
      themeLoading.value = false
    }
  }
}

/**
 * 打开当前样式绑定主题的详情弹窗。
 */
function openThemeDetail(): void {
  if (!matchedTheme.value) {
    return
  }
  themeDetailVisible.value = true
}

/**
 * 向父组件同步详情弹窗可见状态。
 * @param value 目标可见状态
 */
function handleVisibleChange(value: boolean): void {
  if (!value) {
    themeDetailVisible.value = false
  }
  emit('update:modelValue', value)
}

/**
 * 从详情弹窗进入当前样式编辑。
 */
function handleEditStyle(): void {
  if (!props.style) {
    return
  }
  emit('edit', props.style)
  handleVisibleChange(false)
}

/**
 * 格式化菜单模式展示文本。
 * @param mode 菜单模式
 */
function formatMenuMode(mode: ProjectMenuMode): string {
  if (mode === 'bottom-preview') return '底部缩略图导航'
  if (mode === 'text') return '文本导航'
  return '侧边缩略图导航'
}

/**
 * 将页面宽高格式化为最简比例。
 * @param width 页面宽度
 * @param height 页面高度
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
 * @param left 第一个整数
 * @param right 第二个整数
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
</script>

<style scoped>
.style-spec-markdown :deep(.markstream-vue) {
  background: transparent;
  color: rgb(51 65 85);
  font-size: 0.875rem;
  line-height: 1.75;
}

.style-spec-markdown :deep(.markstream-vue > :first-child) {
  margin-top: 0;
}

.style-spec-markdown :deep(.markstream-vue > :last-child) {
  margin-bottom: 0;
}

.style-spec-markdown :deep(.markstream-vue > * + *) {
  margin-top: 0.75rem;
}

.style-spec-markdown :deep(h1),
.style-spec-markdown :deep(h2),
.style-spec-markdown :deep(h3) {
  color: rgb(15 23 42);
  font-weight: 800;
  line-height: 1.3;
}

.style-spec-markdown :deep(h1) {
  font-size: 1.25rem;
}

.style-spec-markdown :deep(h2) {
  font-size: 1.125rem;
}

.style-spec-markdown :deep(h3) {
  font-size: 1rem;
}

.style-spec-markdown :deep(ul),
.style-spec-markdown :deep(ol) {
  padding-left: 1.25rem;
}

.style-spec-markdown :deep(code:not(pre code)) {
  border-radius: 0.375rem;
  background: rgb(241 245 249);
  padding: 0.125rem 0.375rem;
  color: rgb(30 41 59);
  font-size: 0.8125rem;
}

.style-spec-markdown :deep(pre) {
  overflow-x: auto;
  border-radius: 0.75rem;
  background: rgb(15 23 42);
  padding: 1rem;
  color: rgb(226 232 240);
}
</style>
