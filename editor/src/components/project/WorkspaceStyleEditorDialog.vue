<!-- 文件功能：工作空间样式创建与编辑弹窗，维护展示配置、主题引用和 Markdown 样式规范。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    :title="style ? '编辑样式' : '新建样式'"
    width="1180px"
    body-class="h-[min(82vh,760px)] px-6 py-5 overflow-hidden"
    @update:model-value="handleVisibleChange"
  >
    <div class="flex h-full min-h-0 flex-col gap-4">
      <div class="shrink-0 rounded-lg bg-slate-100 p-1">
        <div class="grid grid-cols-2 gap-1">
          <button
            type="button"
            class="flex h-10 items-center justify-center rounded-md px-4 text-sm font-bold transition"
            :class="activeTab === 'style' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
            @click="activeTab = 'style'"
          >
            样式配置
          </button>
          <button
            type="button"
            class="flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-bold transition"
            :class="activeTab === 'components' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
            @click="activeTab = 'components'"
          >
            <span>建议组件</span>
            <span class="rounded-full px-2 py-0.5 text-xs" :class="activeTab === 'components' ? 'bg-indigo-50 text-indigo-600' : 'bg-white text-slate-500'">
              {{ suggestedComponentsDraft.length }}
            </span>
          </button>
        </div>
      </div>

      <div v-if="activeTab === 'style'" class="style-config-grid min-h-0 flex-1">
        <section class="style-editor-scroll min-h-0 space-y-4 overflow-y-auto pr-1">
          <div class="rounded-lg border border-slate-200 bg-white p-4">
            <div class="grid grid-cols-2 gap-3">
              <BaseInput v-model="draft.key" label="样式 key" placeholder="default" required :error="errors.key" />
              <BaseInput v-model="draft.name" label="样式名称" placeholder="默认样式" required :error="errors.name" />
            </div>
            <BaseInput v-model="draft.description" class="mt-3" label="样式描述" placeholder="说明适用场景" />
          </div>

          <div class="rounded-lg border border-slate-200 bg-white p-4">
            <ThemeSelectorField
              :workspace-id="workspaceId"
              :model-value="draft.themeKey"
              :preferred-key="defaultThemeKey"
              label="样式主题"
              :show-preview="false"
              clearable
              :auto-select="false"
              @update:model-value="draft.themeKey = $event"
            />
          </div>

          <div class="rounded-lg border border-slate-200 bg-white p-4">
            <div class="grid grid-cols-2 gap-3">
              <BaseInput v-model="draft.pageWidth" label="页面宽度(px)" placeholder="1920" />
              <BaseInput v-model="draft.pageHeight" label="页面高度(px)" placeholder="1080" />
            </div>
            <div class="mt-3 grid grid-cols-2 gap-3">
              <BaseInput v-model="draft.baseFontSize" label="基础字号" placeholder="20px" />
              <BaseInput v-model="draft.iconDefaultStrokeWidth" label="图标描边" placeholder="2" />
            </div>
          </div>

          <div class="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(220px,0.65fr)]">
            <div class="rounded-lg border border-slate-200 bg-white p-4">
              <label class="ml-1 text-sm font-semibold text-slate-700">菜单模式</label>
              <div class="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-slate-100 p-1">
                <button
                  v-for="option in menuModeOptions"
                  :key="option.value"
                  type="button"
                  class="flex min-h-11 items-center justify-center rounded-lg px-2 py-2.5 text-xs font-bold transition-all"
                  :class="draft.menuMode === option.value ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
                  @click="draft.menuMode = option.value"
                >
                  {{ option.label }}
                </button>
              </div>
            </div>

            <div class="rounded-lg border border-slate-200 bg-white p-4">
              <label class="ml-1 text-sm font-semibold text-slate-700">PDF 导出按钮</label>
              <div class="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-1">
                <button
                  v-for="option in pdfButtonOptions"
                  :key="String(option.value)"
                  type="button"
                  class="flex min-h-11 items-center justify-center rounded-lg px-3 py-2.5 text-xs font-bold transition-all"
                  :class="draft.showPdfExportButton === option.value ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
                  @click="draft.showPdfExportButton = option.value"
                >
                  {{ option.label }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <section class="min-h-0 rounded-lg border border-slate-200 bg-white p-4">
          <BaseInput
            v-model="draft.styleSpecMarkdown"
            type="textarea"
            label="样式规范 Markdown"
            placeholder="用 Markdown 记录版式、排版、色彩和组件使用约束"
            :rows="22"
          />
        </section>
      </div>

      <div v-else class="min-h-0 flex-1">
        <SuggestedComponentsSelectorPanel
          v-model="suggestedComponentsDraft"
          class="h-full"
          :workspace-id="workspaceId"
          selected-title="样式建议组件"
          unavailable-text="请先选择工作空间。"
          :loading="suggestedComponentsLoading"
        />
      </div>
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="primary" :loading="loading" :disabled="suggestedComponentsLoading" @click="handleSave">
        {{ style ? '保存样式' : '创建样式' }}
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { getErrorMessage } from '@/api/http'
import { getWorkspaceStyleSuggestedComponents, type WorkspaceStylePayload } from '@/api/styles'
import SuggestedComponentsSelectorPanel from '@/components/project/SuggestedComponentsSelectorPanel.vue'
import ThemeSelectorField from '@/components/theme/ThemeSelectorField.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import { DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN } from '@/constants/project-style'
import type { ProjectMenuMode, SuggestedComponentItem, WorkspaceStyleItem } from '@/types/api'
import { Message } from '@/utils/message'

const DEFAULT_PROJECT_PAGE_WIDTH = 1920
const DEFAULT_PROJECT_PAGE_HEIGHT = 1080
const DEFAULT_PROJECT_BASE_FONT_SIZE = '20px'

const props = withDefaults(defineProps<{
  modelValue: boolean
  workspaceId: number | null
  style?: WorkspaceStyleItem | null
  initialStyle?: Partial<WorkspaceStylePayload> | null
  defaultThemeKey?: string | null
  loading?: boolean
}>(), {
  style: null,
  initialStyle: null,
  defaultThemeKey: null,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [payload: WorkspaceStylePayload & { suggested_component_ids: number[] }]
}>()

const draft = reactive({
  key: 'default',
  name: '默认样式',
  description: '',
  pageWidth: String(DEFAULT_PROJECT_PAGE_WIDTH),
  pageHeight: String(DEFAULT_PROJECT_PAGE_HEIGHT),
  baseFontSize: DEFAULT_PROJECT_BASE_FONT_SIZE,
  iconDefaultStrokeWidth: '2',
  showPdfExportButton: true,
  menuMode: 'preview' as ProjectMenuMode,
  themeKey: null as string | null,
  styleSpecMarkdown: DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN,
})

const errors = reactive({
  key: '',
  name: '',
})
const suggestedComponentsDraft = ref<SuggestedComponentItem[]>([])
const suggestedComponentsLoading = ref(false)
const activeTab = ref<'style' | 'components'>('style')
let suggestedComponentsLoadToken = 0

const menuModeOptions = [
  { label: '侧边缩略图', value: 'preview' as const },
  { label: '底部缩略图', value: 'bottom-preview' as const },
  { label: '文本', value: 'text' as const },
]

const pdfButtonOptions = [
  { label: '显示', value: true },
  { label: '隐藏', value: false },
]

const normalizedPageWidth = computed(() => normalizeDimension(draft.pageWidth, DEFAULT_PROJECT_PAGE_WIDTH))
const normalizedPageHeight = computed(() => normalizeDimension(draft.pageHeight, DEFAULT_PROJECT_PAGE_HEIGHT))
const normalizedBaseFontSize = computed(() => normalizeBaseFontSize(draft.baseFontSize, DEFAULT_PROJECT_BASE_FONT_SIZE))
const normalizedIconDefaultStrokeWidth = computed(() => normalizeIntegerWithinRange(draft.iconDefaultStrokeWidth, 2, 1, 64))

/**
 * 将样式实体或外部预填值同步到弹窗草稿。
 */
function syncDraft(): void {
  const source = (props.style ?? props.initialStyle ?? {}) as Partial<WorkspaceStylePayload> & Partial<WorkspaceStyleItem>
  draft.key = String(source.key ?? 'default')
  draft.name = String(source.name ?? '默认样式')
  draft.description = String(source.description ?? '')
  draft.pageWidth = String(source.page_width ?? DEFAULT_PROJECT_PAGE_WIDTH)
  draft.pageHeight = String(source.page_height ?? DEFAULT_PROJECT_PAGE_HEIGHT)
  draft.baseFontSize = String(source.base_font_size ?? DEFAULT_PROJECT_BASE_FONT_SIZE)
  draft.iconDefaultStrokeWidth = String(source.icon_default_stroke_width ?? 2)
  draft.showPdfExportButton = source.show_pdf_export_button ?? true
  draft.menuMode = source.menu_mode ?? 'preview'
  draft.themeKey = source.theme_key ?? props.defaultThemeKey ?? null
  draft.styleSpecMarkdown = String(source.style_spec_markdown ?? DEFAULT_PROJECT_STYLE_SPEC_MARKDOWN)
  errors.key = ''
  errors.name = ''
}

/**
 * 读取编辑样式时已经配置的建议组件，新建样式则保持空选择。
 */
async function syncSuggestedComponents(): Promise<void> {
  const token = ++suggestedComponentsLoadToken
  if (!props.modelValue || !props.workspaceId || !props.style?.id) {
    suggestedComponentsDraft.value = []
    suggestedComponentsLoading.value = false
    return
  }
  suggestedComponentsLoading.value = true
  try {
    const response = await getWorkspaceStyleSuggestedComponents(props.workspaceId, props.style.id)
    if (token === suggestedComponentsLoadToken) {
      suggestedComponentsDraft.value = response.items
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
 * 同步弹窗可见状态。
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 校验并提交样式表单。
 */
function handleSave(): void {
  const normalizedKey = draft.key.trim().toLowerCase()
  if (!normalizedKey || !/^[a-z0-9_-]+$/.test(normalizedKey)) {
    errors.key = '请输入小写字母、数字、下划线或中划线'
    return
  }
  if (!draft.name.trim()) {
    errors.name = '请输入样式名称'
    return
  }
  errors.key = ''
  errors.name = ''
  if (suggestedComponentsDraft.value.some(component => component.available === false)) {
    activeTab.value = 'components'
    Message.warning('请先移除不可用的建议组件，再保存样式。')
    return
  }
  emit('save', {
    key: normalizedKey,
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    page_width: normalizedPageWidth.value,
    page_height: normalizedPageHeight.value,
    base_font_size: normalizedBaseFontSize.value,
    icon_default_stroke_width: normalizedIconDefaultStrokeWidth.value,
    show_pdf_export_button: draft.showPdfExportButton,
    menu_mode: draft.menuMode,
    theme_key: draft.themeKey,
    style_spec_markdown: draft.styleSpecMarkdown,
    suggested_component_ids: suggestedComponentsDraft.value.map(component => component.id),
  })
}

/**
 * 归一化页面尺寸。
 */
function normalizeDimension(value: string, fallback: number): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback
  }
  return Math.min(8192, Math.max(1, Math.round(parsed)))
}

/**
 * 归一化基础字号。
 */
function normalizeBaseFontSize(value: string, fallback: string): string {
  const normalized = String(value || '').trim().toLowerCase()
  const match = normalized.match(/^(\d+)(px)?$/)
  if (!match) {
    return fallback
  }
  const parsedValue = Number.parseInt(match[1], 10)
  if (!Number.isFinite(parsedValue) || parsedValue < 1 || parsedValue > 200) {
    return fallback
  }
  return `${parsedValue}px`
}

/**
 * 归一化整数规格字段。
 */
function normalizeIntegerWithinRange(value: string, fallback: number, min: number, max: number): number {
  const parsedValue = Number(value)
  if (!Number.isFinite(parsedValue)) {
    return fallback
  }
  return Math.min(max, Math.max(min, Math.round(parsedValue)))
}

watch(
  () => [props.modelValue, props.workspaceId, props.style, props.initialStyle] as const,
  ([visible]) => {
    if (visible) {
      activeTab.value = 'style'
      syncDraft()
      void syncSuggestedComponents()
    } else {
      suggestedComponentsLoadToken += 1
      suggestedComponentsDraft.value = []
      suggestedComponentsLoading.value = false
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.style-config-grid {
  display: grid;
  gap: 1.25rem;
  grid-template-columns: minmax(0, 0.95fr) minmax(420px, 1.05fr);
}

.style-editor-scroll {
  scrollbar-width: thin;
  scrollbar-color: rgb(203 213 225) transparent;
}

.style-editor-scroll::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}

.style-editor-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.style-editor-scroll::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgb(203 213 225);
}

@media (max-width: 1279px) {
  .style-config-grid {
    grid-template-columns: minmax(0, 1fr);
    overflow-y: auto;
    padding-right: 0.25rem;
  }
}
</style>
