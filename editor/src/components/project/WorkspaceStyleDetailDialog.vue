<!-- 文件功能：展示工作空间样式详情弹窗，集中呈现展示配置字段与 Markdown 样式规范。 -->
<template>
  <UiDialog
    :open="modelValue"
    :title="styleItem ? `${styleItem.name} · 样式详情` : '样式详情'"
    size="wide"
    body-preset="dense"
    @update:open="handleVisibleChange"
  >
    <div v-if="styleItem" class="grid h-full min-h-0 gap-3 overflow-y-auto lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:overflow-hidden">
      <div class="flex min-h-0 min-w-0 flex-col gap-3 lg:overflow-y-auto lg:pr-1">
        <section class="shrink-0 rounded-lg border border-border bg-surface p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <h3 class="truncate text-lg font-black text-text-strong">{{ styleItem.name }}</h3>
              <p class="mt-1 font-mono text-xs text-text-disabled">{{ styleItem.key }}</p>
            </div>
            <UiButton
              v-if="styleItem.theme_key"
              type="button"
              variant="ghost"
              size="xs"
              :disabled="!matchedTheme"
              :title="matchedTheme ? '查看主题详情' : '未找到主题详情'"
              @click="openThemeDetail"
            >
              {{ themeBadgeText }}
            </UiButton>
            <span v-else class="rounded-full bg-surface-muted px-3 py-1 text-xs font-black text-text-muted">
              不覆盖主题
            </span>
          </div>
          <p class="mt-3 text-sm leading-6 text-text-muted">{{ styleItem.description || '未填写样式说明。' }}</p>
        </section>

        <section class="shrink-0 rounded-lg border border-border bg-surface p-4">
          <h4 class="text-sm font-black text-text-strong">展示配置</h4>
          <div class="mt-3 grid gap-2.5 sm:grid-cols-2">
            <div
              v-for="item in detailItems"
              :key="item.label"
              class="rounded-lg border border-border-muted bg-canvas px-3 py-2.5"
            >
              <p class="text-[11px] font-bold text-text-disabled">{{ item.label }}</p>
              <p class="mt-1 text-sm font-black text-text">{{ item.value }}</p>
            </div>
          </div>
        </section>

        <section class="shrink-0 rounded-lg border border-border bg-surface p-4">
          <h4 class="text-sm font-black text-text-strong">建议组件</h4>
          <p v-if="suggestedComponentsLoading" class="mt-3 text-sm text-text-disabled">正在加载建议组件...</p>
          <div v-else-if="suggestedComponents.length" class="mt-3 space-y-2">
            <div
              v-for="component in suggestedComponents"
              :key="component.id"
              class="rounded-lg border border-border-muted bg-canvas px-3 py-2.5"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="flex min-w-0 items-baseline gap-2">
                  <span class="truncate text-sm font-bold text-text-emphasis">{{ component.name }}</span>
                  <span class="shrink-0 font-mono text-[11px] text-text-disabled">{{ component.import_name }}</span>
                </div>
                <div class="flex shrink-0 items-center gap-1.5">
                  <span
                    v-if="component.available === false"
                    class="rounded-full bg-danger-muted px-2 py-0.5 text-[10px] font-bold text-danger-strong"
                    :title="component.unavailable_reason || '组件当前不可用'"
                  >
                    不可用
                  </span>
                  <span class="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-bold text-text-muted">
                    {{ component.component_type }}
                  </span>
                </div>
              </div>
              <p v-if="component.summary" class="mt-1 line-clamp-1 text-xs text-text-muted">{{ component.summary }}</p>
            </div>
          </div>
          <p v-else class="mt-3 text-sm text-text-disabled">暂未配置建议组件。</p>
        </section>
      </div>

      <section class="flex min-h-0 min-w-0 flex-col rounded-lg border border-border bg-surface p-4">
        <h4 class="shrink-0 text-sm font-black text-text-strong">样式规范</h4>
        <div v-if="selectedStyleSpecMarkdown" class="mt-3 min-h-0 flex-1 overflow-y-auto rounded-lg border border-border-muted bg-canvas px-5 py-4">
          <StyleSpecMarkdownPreview :markdown="selectedStyleSpecMarkdown" />
        </div>
        <div v-else class="mt-3 flex min-h-[160px] flex-1 items-center justify-center rounded-lg border border-dashed border-border bg-canvas text-sm text-text-disabled">
          当前样式还没有维护样式规范。
        </div>
      </section>
    </div>

    <div v-else class="flex h-full items-center justify-center py-10 text-center text-sm text-text-disabled">
      当前没有可查看的样式。
    </div>

    <template #footer>
      <UiButton variant="ghost" @click="handleVisibleChange(false)">关闭</UiButton>
      <UiButton variant="primary" :disabled="!styleItem" @click="handleEditStyle">编辑样式</UiButton>
    </template>
  </UiDialog>

  <ThemeDetailDialog
    v-model="themeDetailVisible"
    :workspace-id="workspaceId"
    :theme-id="matchedTheme?.id ?? null"
    :default-theme-key="defaultThemeKey"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { listWorkspaceThemes } from '@/api/themes'
import { getErrorMessage } from '@/api/http'
import { getWorkspaceStyleSuggestedComponents } from '@/api/styles'
import StyleSpecMarkdownPreview from '@/components/project/StyleSpecMarkdownPreview.vue'
import ThemeDetailDialog from '@/components/theme/ThemeDetailDialog.vue'
import { UiButton, UiDialog } from '@/components/ui'
import type { ProjectMenuMode, SuggestedComponentItem, WorkspaceStyleItem, WorkspaceThemeItem } from '@/types/api'
import { Message } from '@/utils/message'

const props = defineProps<{
  modelValue: boolean
  workspaceId: number | null
  styleItem: WorkspaceStyleItem | null
  defaultThemeKey?: string | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  edit: [style: WorkspaceStyleItem]
}>()

const matchedTheme = ref<WorkspaceThemeItem | null>(null)
const themeLoading = ref(false)
const themeDetailVisible = ref(false)
const themeLoadToken = ref(0)
const suggestedComponents = ref<SuggestedComponentItem[]>([])
const suggestedComponentsLoading = ref(false)
let suggestedComponentsLoadToken = 0

const selectedStyleSpecMarkdown = computed(() => props.styleItem?.style_spec_markdown?.trim() || '')
const themeBadgeText = computed(() => {
  const themeKey = props.styleItem?.theme_key
  if (!themeKey) return '不覆盖主题'
  if (themeLoading.value) return `${themeKey} / 加载中`
  if (matchedTheme.value) return `${matchedTheme.value.name} / ${matchedTheme.value.key}`
  return `${themeKey} / 未找到主题`
})
const detailItems = computed(() => {
  const style = props.styleItem
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
  () => [props.modelValue, props.workspaceId, props.styleItem?.theme_key] as const,
  ([visible]) => {
    if (!visible) {
      themeDetailVisible.value = false
      return
    }
    void loadMatchedTheme()
  },
  { immediate: true },
)

watch(
  () => [props.modelValue, props.workspaceId, props.styleItem?.id] as const,
  ([visible]) => {
    if (!visible) {
      return
    }
    void loadSuggestedComponents()
  },
  { immediate: true },
)

/**
 * 加载当前样式已配置的建议组件，用于详情中展示引用组件清单。
 */
async function loadSuggestedComponents(): Promise<void> {
  const token = ++suggestedComponentsLoadToken
  if (!props.workspaceId || !props.styleItem?.id) {
    suggestedComponents.value = []
    suggestedComponentsLoading.value = false
    return
  }
  suggestedComponentsLoading.value = true
  try {
    const response = await getWorkspaceStyleSuggestedComponents(props.workspaceId, props.styleItem.id)
    if (token === suggestedComponentsLoadToken) {
      suggestedComponents.value = response.items
    }
  } catch (error) {
    if (token === suggestedComponentsLoadToken) {
      Message.error(getErrorMessage(error, '加载样式建议组件失败。'))
    }
  } finally {
    if (token === suggestedComponentsLoadToken) {
      suggestedComponentsLoading.value = false
    }
  }
}

/**
 * 根据样式中的主题 key 加载主题摘要，用于顶部主题入口展示名称并打开详情。
 */
async function loadMatchedTheme(): Promise<void> {
  const themeKey = props.styleItem?.theme_key?.trim()
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
  if (!props.styleItem) {
    return
  }
  emit('edit', props.styleItem)
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

