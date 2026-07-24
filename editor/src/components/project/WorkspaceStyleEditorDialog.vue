<!-- 文件功能：工作空间样式创建与编辑弹窗，维护展示配置、主题引用和 Markdown 样式规范。 -->
<template>
  <UiDialog
    :open="modelValue"
    :title="style ? '编辑样式' : '新建样式'"
    size="canvas"
    body-preset="editor"
    @update:open="handleVisibleChange"
  >
    <div class="flex h-full min-h-0 flex-col gap-2">
      <div class="shrink-0 rounded-lg bg-slate-100 p-1">
        <div class="grid grid-cols-2 gap-1">
          <UiButton
            variant="ghost"
            class="h-10"
            :class="activeTab === 'style' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
            @click="activeTab = 'style'"
          >
            样式配置
          </UiButton>
          <UiButton
            variant="ghost"
            class="h-10 gap-2"
            :class="activeTab === 'components' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
            @click="activeTab = 'components'"
          >
            <span>建议组件</span>
            <span class="rounded-full px-2 py-0.5 text-xs" :class="activeTab === 'components' ? 'bg-indigo-50 text-indigo-600' : 'bg-white text-slate-500'">
              {{ suggestedComponentsDraft.length }}
            </span>
          </UiButton>
        </div>
      </div>

      <div v-if="activeTab === 'style'" class="style-config-grid min-h-0 flex-1">
        <ToolPanel class="style-editor-scroll min-h-0" title="基础配置">
          <div class="rounded-lg border border-slate-200 bg-white p-4">
            <div class="grid grid-cols-2 gap-3">
              <UiFormField label="样式 key" required :error="errors.key"><template #default="field"><UiInput v-model="draft.key" placeholder="NEW_STYLE_KEY" required :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" /></template></UiFormField>
              <UiFormField label="样式名称" required :error="errors.name"><template #default="field"><UiInput v-model="draft.name" placeholder="样式名称" required :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" /></template></UiFormField>
            </div>
            <UiFormField label="样式描述" class="mt-3"><template #default="field"><UiInput v-model="draft.description" placeholder="说明适用场景" :input-id="field.inputId" :described-by="field.describedBy" /></template></UiFormField>
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
              <UiFormField label="页面宽度(px)"><template #default="field"><UiInput v-model="draft.pageWidth" placeholder="1920" :input-id="field.inputId" :described-by="field.describedBy" /></template></UiFormField>
              <UiFormField label="页面高度(px)"><template #default="field"><UiInput v-model="draft.pageHeight" placeholder="1080" :input-id="field.inputId" :described-by="field.describedBy" /></template></UiFormField>
            </div>
            <div class="mt-3 grid grid-cols-2 gap-3">
              <UiFormField label="基础字号"><template #default="field"><UiInput v-model="draft.baseFontSize" placeholder="20px" :input-id="field.inputId" :described-by="field.describedBy" /></template></UiFormField>
              <UiFormField label="图标描边"><template #default="field"><UiInput v-model="draft.iconDefaultStrokeWidth" placeholder="2" :input-id="field.inputId" :described-by="field.describedBy" /></template></UiFormField>
            </div>
          </div>

          <div class="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(220px,0.65fr)]">
            <div class="rounded-lg border border-slate-200 bg-white p-4">
              <label class="ml-1 text-sm font-semibold text-slate-700">菜单模式</label>
              <div class="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-slate-100 p-1">
                <UiButton
                  v-for="option in menuModeOptions"
                  :key="option.value"
                  variant="ghost"
                  class="min-h-11"
                  :class="draft.menuMode === option.value ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
                  @click="draft.menuMode = option.value"
                >
                  {{ option.label }}
                </UiButton>
              </div>
            </div>

            <div class="rounded-lg border border-slate-200 bg-white p-4">
              <label class="ml-1 text-sm font-semibold text-slate-700">导出按钮</label>
              <div class="mt-3 grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-1">
                <UiButton
                  v-for="option in pdfButtonOptions"
                  :key="String(option.value)"
                  variant="ghost"
                  class="min-h-11"
                  :class="draft.showPdfExportButton === option.value ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
                  @click="draft.showPdfExportButton = option.value"
                >
                  {{ option.label }}
                </UiButton>
              </div>
            </div>
          </div>
        </ToolPanel>

        <ToolPanel class="min-h-0" title="样式规范 Markdown">
          <UiInput
            v-model="draft.styleSpecMarkdown"
            type="textarea"
            placeholder="用 Markdown 记录版式、排版、色彩和组件使用约束"
            :rows="22"
          />
        </ToolPanel>
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
      <UiButton variant="ghost" @click="handleVisibleChange(false)">取消</UiButton>
      <UiButton variant="primary" :loading="loading" :disabled="suggestedComponentsLoading" @click="handleSave">
        {{ style ? '保存样式' : '创建样式' }}
      </UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { getErrorMessage } from '@/api/http'
import { getWorkspaceStyleSuggestedComponents, type WorkspaceStylePayload } from '@/api/styles'
import SuggestedComponentsSelectorPanel from '@/components/project/SuggestedComponentsSelectorPanel.vue'
import ThemeSelectorField from '@/components/theme/ThemeSelectorField.vue'
import ToolPanel from '@/components/patterns/ToolPanel.vue'
import { UiButton, UiDialog, UiFormField, UiInput } from '@/components/ui'
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
  key: 'NEW_STYLE_KEY',
  name: '样式名称',
  description: '',
  pageWidth: String(DEFAULT_PROJECT_PAGE_WIDTH),
  pageHeight: String(DEFAULT_PROJECT_PAGE_HEIGHT),
  baseFontSize: DEFAULT_PROJECT_BASE_FONT_SIZE,
  iconDefaultStrokeWidth: '2',
  showPdfExportButton: true,
  menuMode: 'bottom-preview' as ProjectMenuMode,
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
  draft.key = String(source.key ?? 'NEW_STYLE_KEY')
  draft.name = String(source.name ?? '样式名称')
  draft.description = String(source.description ?? '')
  draft.pageWidth = String(source.page_width ?? DEFAULT_PROJECT_PAGE_WIDTH)
  draft.pageHeight = String(source.page_height ?? DEFAULT_PROJECT_PAGE_HEIGHT)
  draft.baseFontSize = String(source.base_font_size ?? DEFAULT_PROJECT_BASE_FONT_SIZE)
  draft.iconDefaultStrokeWidth = String(source.icon_default_stroke_width ?? 2)
  draft.showPdfExportButton = source.show_pdf_export_button ?? true
  draft.menuMode = source.menu_mode ?? 'bottom-preview'
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

