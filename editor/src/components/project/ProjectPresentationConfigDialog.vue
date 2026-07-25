<!-- 文件功能：项目展示配置弹窗，统一编辑主题、页面尺寸、菜单模式与导出按钮。 -->
<template>
  <UiDialog
    :open="modelValue"
    title="项目展示配置"
    size="canvas"
    width="1480px"
    body-preset="dense"
    @update:open="handleVisibleChange"
  >
    <div v-if="project && modelValue" class="project-config-layout">
      <section class="project-config-panel">
        <section class="project-config-card shrink-0 bg-slate-50/70">
          <WorkspaceStyleApplyField
            v-if="workspaceId"
            :workspace-id="workspaceId"
            embedded
            label="样式模板"
            hint="从模板快速填充项目展示配置。"
            @apply="applyWorkspaceStyle"
          />
          <div v-else>
            <label class="text-sm font-semibold text-slate-700">应用样式</label>
            <p class="mt-1 text-xs text-slate-400">缺少工作空间上下文，暂时不能从样式库填充项目草稿。</p>
          </div>

          <div class="mt-4 border-t border-slate-200 pt-4">
            <ThemeSelectorField
              :workspace-id="workspaceId"
              :model-value="draft.themeKey"
              :preferred-key="defaultThemeKey"
              label="项目主题"
              :show-preview="false"
              @update:model-value="updateThemeKey"
            />
          </div>
        </section>

        <section class="project-config-card project-config-card--fill bg-white">
          <ProjectPresentationFields
            v-model:page-width="draft.pageWidth"
            v-model:page-height="draft.pageHeight"
            v-model:base-font-size="draft.baseFontSize"
            v-model:icon-default-stroke-width="draft.iconDefaultStrokeWidth"
            v-model:show-pdf-export-button="draft.showPdfExportButton"
            v-model:menu-mode="draft.menuMode"
          />
        </section>
      </section>

      <section class="project-config-card project-config-spec-card bg-white">
        <UiFormField label="样式规范 Markdown">
          <template #default="field">
            <UiInput v-model="draft.styleSpecMarkdown" type="textarea" placeholder="记录内容助手生成页面时应遵循的版式、排版和视觉约束" :rows="16" class="project-config-spec-textarea resize-none" :input-id="field.inputId" :described-by="field.describedBy" />
          </template>
        </UiFormField>
      </section>
    </div>

    <div v-else class="py-10 text-center text-sm text-slate-400">
      当前没有可编辑的项目。
    </div>

    <template #footer>
      <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        <UiButton variant="ghost" @click="handleVisibleChange(false)">取消</UiButton>
        <div class="flex flex-wrap justify-end gap-2">
          <UiButton variant="ghost" :disabled="!project" @click="resetDraft">恢复当前值</UiButton>
          <UiButton variant="ghost" :disabled="!project || !workspaceId" @click="openSaveAsStyleDialog">另存为样式</UiButton>
          <UiButton variant="primary" :loading="loading" :disabled="!project" @click="handleSave">
            保存配置
          </UiButton>
        </div>
      </div>
    </template>
  </UiDialog>

  <WorkspaceStyleEditorDialog
    v-model="saveAsStyleDialogVisible"
    :workspace-id="workspaceId"
    :initial-style="saveAsStyleInitialValue"
    :default-theme-key="defaultThemeKey"
    :loading="saveAsStyleSaving"
    @save="handleSaveAsStyle"
  />
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { createWorkspaceStyle, updateWorkspaceStyleSuggestedComponents, type WorkspaceStylePayload } from '@/api/styles'
import ThemeSelectorField from '@/components/theme/ThemeSelectorField.vue'
import { UiButton, UiDialog, UiFormField, UiInput } from '@/components/ui'
import type { ProjectItem, ProjectMenuMode, WorkspaceStyleItem } from '@/types/api'
import { Message } from '@/utils/message'
import { getErrorMessage } from '@/api/http'
import WorkspaceStyleApplyField from './WorkspaceStyleApplyField.vue'
import WorkspaceStyleEditorDialog from './WorkspaceStyleEditorDialog.vue'
import ProjectPresentationFields from './ProjectPresentationFields.vue'
import {
  DEFAULT_PROJECT_BASE_FONT_SIZE,
  DEFAULT_PROJECT_PAGE_HEIGHT,
  DEFAULT_PROJECT_PAGE_WIDTH,
  normalizeProjectBaseFontSize as normalizeBaseFontSize,
  normalizeProjectDimension as normalizeDimension,
  normalizeProjectInteger as normalizeIntegerWithinRange,
} from './project-presentation-values'

const props = withDefaults(defineProps<{
  modelValue: boolean
  project: ProjectItem | null
  workspaceId: number | null
  defaultThemeKey?: string | null
  loading?: boolean
}>(), {
  defaultThemeKey: null,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  save: [payload: {
    page_width: number
    page_height: number
    base_font_size: string
    icon_default_stroke_width: number
    show_pdf_export_button: boolean
    menu_mode: ProjectMenuMode
    theme_key: string | null
    style_spec_markdown: string
    suggested_component_source_style_id?: number | null
  }]
}>()

const draft = reactive({
  pageWidth: String(DEFAULT_PROJECT_PAGE_WIDTH),
  pageHeight: String(DEFAULT_PROJECT_PAGE_HEIGHT),
  baseFontSize: DEFAULT_PROJECT_BASE_FONT_SIZE,
  iconDefaultStrokeWidth: '2',
  showPdfExportButton: true,
  menuMode: 'preview' as ProjectMenuMode,
  themeKey: null as string | null,
  styleSpecMarkdown: '',
})

const saveAsStyleDialogVisible = ref(false)
const saveAsStyleSaving = ref(false)
const appliedWorkspaceStyleId = ref<number | null>(null)

const normalizedPageWidth = computed(() => normalizeDimension(draft.pageWidth, DEFAULT_PROJECT_PAGE_WIDTH))
const normalizedPageHeight = computed(() => normalizeDimension(draft.pageHeight, DEFAULT_PROJECT_PAGE_HEIGHT))
const normalizedBaseFontSize = computed(() => normalizeBaseFontSize(draft.baseFontSize, DEFAULT_PROJECT_BASE_FONT_SIZE))
const normalizedIconDefaultStrokeWidth = computed(() => normalizeIntegerWithinRange(draft.iconDefaultStrokeWidth, 2, 1, 64))
const saveAsStyleInitialValue = computed<Partial<WorkspaceStylePayload>>(() => ({
  key: buildStyleKey(props.project?.name ?? 'project-style'),
  name: `${props.project?.name ?? '项目'}样式`,
  description: props.project?.description ?? null,
  page_width: normalizedPageWidth.value,
  page_height: normalizedPageHeight.value,
  base_font_size: normalizedBaseFontSize.value,
  icon_default_stroke_width: normalizedIconDefaultStrokeWidth.value,
  show_pdf_export_button: draft.showPdfExportButton,
  menu_mode: draft.menuMode,
  theme_key: draft.themeKey,
  style_spec_markdown: draft.styleSpecMarkdown,
}))
type WorkspaceStyleEditorSavePayload = WorkspaceStylePayload & { suggested_component_ids?: number[] }

/**
 * 根据项目详情刷新展示配置草稿。
 * @param project 当前项目
 */
function syncDraftFromProject(project: ProjectItem | null): void {
  draft.pageWidth = String(project?.page_width ?? DEFAULT_PROJECT_PAGE_WIDTH)
  draft.pageHeight = String(project?.page_height ?? DEFAULT_PROJECT_PAGE_HEIGHT)
  draft.baseFontSize = project?.base_font_size ?? DEFAULT_PROJECT_BASE_FONT_SIZE
  draft.iconDefaultStrokeWidth = String(project?.icon_default_stroke_width ?? 2)
  draft.showPdfExportButton = project?.show_pdf_export_button ?? true
  draft.menuMode = project?.menu_mode ?? 'preview'
  draft.themeKey = project?.theme_key ?? props.defaultThemeKey ?? null
  draft.styleSpecMarkdown = project?.style_spec_markdown ?? ''
  appliedWorkspaceStyleId.value = null
}

/**
 * 向父组件同步弹窗可见状态。
 * @param value 目标可见状态
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 将主题选择结果写回草稿。
 * @param value 主题 key
 */
function updateThemeKey(value: string | null): void {
  draft.themeKey = value
}

/**
 * 将工作空间样式复制到项目配置草稿，不建立持久关联。
 * @param style 被应用的工作空间样式
 */
function applyWorkspaceStyle(style: WorkspaceStyleItem): void {
  draft.pageWidth = String(normalizeDimension(String(style.page_width), DEFAULT_PROJECT_PAGE_WIDTH))
  draft.pageHeight = String(normalizeDimension(String(style.page_height), DEFAULT_PROJECT_PAGE_HEIGHT))
  draft.baseFontSize = normalizeBaseFontSize(style.base_font_size, DEFAULT_PROJECT_BASE_FONT_SIZE)
  draft.iconDefaultStrokeWidth = String(normalizeIntegerWithinRange(String(style.icon_default_stroke_width), 2, 1, 64))
  draft.showPdfExportButton = style.show_pdf_export_button
  draft.menuMode = style.menu_mode
  if (style.theme_key) {
    draft.themeKey = style.theme_key
  }
  draft.styleSpecMarkdown = style.style_spec_markdown
  appliedWorkspaceStyleId.value = style.id
}

/**
 * 恢复到当前项目已保存的展示配置。
 */
function resetDraft(): void {
  syncDraftFromProject(props.project)
}

/**
 * 提交项目展示配置。
 */
function handleSave(): void {
  const payload: {
    page_width: number
    page_height: number
    base_font_size: string
    icon_default_stroke_width: number
    show_pdf_export_button: boolean
    menu_mode: ProjectMenuMode
    theme_key: string | null
    style_spec_markdown: string
    suggested_component_source_style_id?: number | null
  } = {
    page_width: normalizedPageWidth.value,
    page_height: normalizedPageHeight.value,
    base_font_size: normalizedBaseFontSize.value,
    icon_default_stroke_width: normalizedIconDefaultStrokeWidth.value,
    show_pdf_export_button: draft.showPdfExportButton,
    menu_mode: draft.menuMode,
    theme_key: draft.themeKey,
    style_spec_markdown: draft.styleSpecMarkdown,
  }
  if (appliedWorkspaceStyleId.value !== null) {
    payload.suggested_component_source_style_id = appliedWorkspaceStyleId.value
  }
  emit('save', payload)
}

/**
 * 打开另存为工作空间样式弹窗。
 */
function openSaveAsStyleDialog(): void {
  saveAsStyleDialogVisible.value = true
}

/**
 * 将当前项目样式草稿保存为工作空间样式。
 * @param payload 样式创建参数
 */
async function handleSaveAsStyle(payload: WorkspaceStyleEditorSavePayload): Promise<void> {
  if (!props.workspaceId) {
    return
  }
  const { suggested_component_ids: suggestedComponentIds, ...stylePayload } = payload
  saveAsStyleSaving.value = true
  try {
    const savedStyle = await createWorkspaceStyle(props.workspaceId, stylePayload)
    if (suggestedComponentIds) {
      await updateWorkspaceStyleSuggestedComponents(props.workspaceId, savedStyle.id, suggestedComponentIds)
    }
    saveAsStyleDialogVisible.value = false
    Message.success('样式已保存到工作空间样式库。')
  } catch (error) {
    Message.error(getErrorMessage(error, '另存为样式失败。'))
  } finally {
    saveAsStyleSaving.value = false
  }
}

/**
 * 基于项目名称生成样式 key 候选值。
 * @param value 项目名称
 */
function buildStyleKey(value: string): string {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return normalized || 'project-style'
}

watch(
  () => [props.modelValue, props.project] as const,
  ([visible, project]) => {
    if (visible) {
      syncDraftFromProject(project)
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.project-config-layout {
  display: grid;
  grid-template-columns: minmax(520px, 0.92fr) minmax(640px, 1.08fr);
  gap: 1rem;
  height: 100%;
  min-height: 0;
}

.project-config-panel {
  display: flex;
  min-height: 0;
  flex-direction: column;
  gap: 0.75rem;
  overflow-y: auto;
  padding-right: 0.25rem;
}

.project-config-card {
  min-width: 0;
  border: 1px solid rgb(226 232 240);
  border-radius: 0.5rem;
  padding: 1rem;
}

.project-config-card--fill {
  flex: 1 1 auto;
  min-height: 0;
}

.project-config-spec-card {
  min-height: 0;
}

.project-config-spec-textarea {
  height: min(620px, calc(88dvh - 250px));
  min-height: 360px;
}

@media (max-height: 820px) {
  .project-config-layout {
    gap: 0.75rem;
  }

  .project-config-card {
    padding: 0.875rem;
  }

  .project-config-spec-textarea {
    height: calc(100dvh - 330px);
    min-height: 260px;
  }
}

@media (max-width: 1280px) {
  .project-config-layout {
    display: block;
    overflow-y: auto;
    padding-right: 0.25rem;
  }

  .project-config-panel {
    min-height: auto;
    overflow: visible;
    padding-right: 0;
  }

  .project-config-card--fill {
    flex: none;
  }

  .project-config-spec-card {
    margin-top: 0.75rem;
  }

  .project-config-spec-textarea {
    height: min(420px, calc(100dvh - 330px));
  }
}
</style>

