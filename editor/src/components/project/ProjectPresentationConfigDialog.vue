<!-- 文件功能：项目设置弹窗，按展示（含样式规范）与放映两个分区编辑项目级配置，并与页面结构互链。 -->
<template>
  <UiDialog
    :open="modelValue"
    title="项目设置"
    size="canvas"
    width="1480px"
    body-preset="dense"
    @update:open="handleVisibleChange"
  >
    <template #header-extra>
      <span
        v-if="isDirty"
        class="rounded-full border border-warning-border bg-warning-muted px-2.5 py-1 text-[11px] font-semibold text-warning-strong"
      >
        未保存
      </span>
    </template>

    <div v-if="project && modelValue" class="flex h-full min-h-0 flex-col">
      <UiTabs
        v-model="activeTab"
        :items="tabs"
        root-class="flex h-full min-h-0 flex-col"
        content-class="min-h-0 flex-1 overflow-y-auto pt-4"
      >
        <template #presentation>
          <div class="project-config-layout">
            <section class="project-config-panel">
              <section class="project-config-card shrink-0 bg-canvas/70">
                <WorkspaceStyleApplyField
                  v-if="workspaceId"
                  :workspace-id="workspaceId"
                  embedded
                  label="样式模板"
                  hint="从模板快速填充项目展示配置。"
                  @apply="applyWorkspaceStyle"
                />
                <div v-else>
                  <label class="text-sm font-semibold text-text-emphasis">应用样式</label>
                  <p class="mt-1 text-xs text-text-disabled">缺少工作空间上下文，暂时不能从样式库填充项目草稿。</p>
                </div>

                <div class="mt-4 border-t border-border pt-4">
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

              <section class="project-config-card project-config-card--fill bg-surface">
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

            <section class="project-config-card project-config-spec-card bg-surface">
              <UiFormField label="样式规范 Markdown" class="min-h-0 flex-1">
                <template #default="field">
                  <UiInput
                    v-model="draft.styleSpecMarkdown"
                    type="textarea"
                    textarea-mode="fill"
                    placeholder="记录内容助手生成页面时应遵循的版式、排版和视觉约束"
                    :rows="16"
                    class="project-config-spec-textarea"
                    :input-id="field.inputId"
                    :described-by="field.describedBy"
                  />
                </template>
              </UiFormField>
            </section>
          </div>
        </template>

        <template #slideshow>
          <div class="project-settings-slideshow">
            <section class="project-config-card bg-surface">
              <h3 class="text-sm font-semibold text-text-emphasis">自动放映</h3>
              <p class="mt-0.5 text-xs leading-5 text-text-disabled">
                项目默认值；逐页可在页面结构中覆盖。隐藏页不显示在目录，也不参与自动或手动翻页。
              </p>
              <div class="mt-3">
                <ProjectSlideshowFields
                  :draft="draft.slideshow"
                  :capabilities="capabilities"
                  @update:draft="updateSlideshowDraft"
                />
              </div>
            </section>

            <section class="project-config-card bg-surface">
              <h3 class="text-sm font-semibold text-text-emphasis">页面级覆盖</h3>
              <p class="mt-1 text-xs leading-5 text-text-muted">
                逐页的翻页动画和方式在“页面结构”中设置；同一页面被多次引用时可以分别设置。
              </p>
              <p class="mt-2 text-xs leading-5 text-text-disabled">
                放映配置不随“应用样式”或“另存为样式”改变，保存后会写入项目默认值。
              </p>
              <UiButton variant="secondary" size="sm" class="mt-3" @click="handleOpenRouteConfig">
                打开页面结构
              </UiButton>
            </section>
          </div>
        </template>

        <template #audio>
          <ProjectAudioSettingsPanel
            v-if="audioEnabled"
            ref="audioPanel"
            :workspace-id="workspaceId"
            :draft="draft.audio"
            @update:draft="updateAudioDraft"
          />
        </template>
      </UiTabs>
    </div>

    <div v-else class="py-10 text-center text-sm text-text-disabled">
      当前没有可编辑的项目。
    </div>

    <template #footer>
      <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
        <UiButton variant="ghost" @click="handleVisibleChange(false)">取消</UiButton>
        <div class="flex flex-wrap justify-end gap-2">
          <UiButton variant="ghost" :disabled="!project" @click="resetDraft">恢复当前值</UiButton>
          <UiButton
            v-if="activeTab === 'presentation'"
            variant="ghost"
            :disabled="!project || !workspaceId"
            @click="openSaveAsStyleDialog"
          >
            另存为样式
          </UiButton>
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

import { createWorkspaceStyle, type WorkspaceStylePayload } from '@/api/styles'
import { useSlideshowCapabilities } from '@/composables/useSlideshowCapabilities'
import ThemeSelectorField from '@/components/theme/ThemeSelectorField.vue'
import { UiButton, UiDialog, UiFormField, UiInput, UiTabs } from '@/components/ui'
import type { ProjectAudioSettings, ProjectItem, ProjectMenuMode, SlideshowSettings, WorkspaceStyleItem } from '@/types/api'
import { Message, createConfirm } from '@/utils/message'
import { getErrorMessage } from '@/api/http'
import WorkspaceStyleApplyField from './WorkspaceStyleApplyField.vue'
import WorkspaceStyleEditorDialog from './WorkspaceStyleEditorDialog.vue'
import ProjectAudioSettingsPanel from './ProjectAudioSettingsPanel.vue'
import ProjectPresentationFields from './ProjectPresentationFields.vue'
import ProjectSlideshowFields from './ProjectSlideshowFields.vue'
import type { SlideshowDraft } from './project-slideshow-values'
import { createSlideshowDraft, normalizeSlideshowDraft } from './project-slideshow-values'
import {
  createAudioSettingsDraft,
  normalizeAudioSettingsDraft,
  validateAudioSettingsDraft,
  type AudioSettingsDraft,
} from './project-audio-values'
import {
  DEFAULT_PROJECT_BASE_FONT_SIZE,
  DEFAULT_PROJECT_PAGE_HEIGHT,
  DEFAULT_PROJECT_PAGE_WIDTH,
  normalizeProjectBaseFontSize as normalizeBaseFontSize,
  normalizeProjectDimension as normalizeDimension,
  normalizeProjectInteger as normalizeIntegerWithinRange,
} from './project-presentation-values'

type ProjectSettingsTab = 'presentation' | 'slideshow' | 'audio'

const props = withDefaults(defineProps<{
  modelValue: boolean
  project: ProjectItem | null
  workspaceId: number | null
  defaultThemeKey?: string | null
  initialTab?: ProjectSettingsTab
  loading?: boolean
}>(), {
  defaultThemeKey: null,
  initialTab: 'presentation',
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
    slideshow: SlideshowSettings
    audio_settings?: ProjectAudioSettings
    source_style_id?: number | null
  }]
  'open-route-config': []
}>()

const tabs = computed(() => [
  { label: '展示', value: 'presentation' },
  { label: '放映', value: 'slideshow' },
  ...(audioEnabled.value ? [{ label: '音频', value: 'audio' }] : []),
])

const draft = reactive({
  pageWidth: String(DEFAULT_PROJECT_PAGE_WIDTH),
  pageHeight: String(DEFAULT_PROJECT_PAGE_HEIGHT),
  baseFontSize: DEFAULT_PROJECT_BASE_FONT_SIZE,
  iconDefaultStrokeWidth: '2',
  showPdfExportButton: true,
  menuMode: 'preview' as ProjectMenuMode,
  themeKey: null as string | null,
  styleSpecMarkdown: '',
  slideshow: createSlideshowDraft(null),
  audio: createAudioSettingsDraft(null),
})

const activeTab = ref<string>('presentation')
const saveAsStyleDialogVisible = ref(false)
const saveAsStyleSaving = ref(false)
const appliedWorkspaceStyleId = ref<number | null>(null)
const initialSnapshot = ref('')
const closeConfirming = ref(false)
const audioPanel = ref<InstanceType<typeof ProjectAudioSettingsPanel> | null>(null)
const { capabilities, load: loadSlideshowCapabilities } = useSlideshowCapabilities()
// cue 配置只在服务端开放 audio_cues 后展示；关闭时不提交 audio_settings，保护旧 Runtime。
const audioEnabled = computed(() => capabilities.value?.audio?.audio_cues === true)

const normalizedPageWidth = computed(() => normalizeDimension(draft.pageWidth, DEFAULT_PROJECT_PAGE_WIDTH))
const normalizedPageHeight = computed(() => normalizeDimension(draft.pageHeight, DEFAULT_PROJECT_PAGE_HEIGHT))
const normalizedBaseFontSize = computed(() => normalizeBaseFontSize(draft.baseFontSize, DEFAULT_PROJECT_BASE_FONT_SIZE))
const normalizedIconDefaultStrokeWidth = computed(() => normalizeIntegerWithinRange(draft.iconDefaultStrokeWidth, 2, 1, 64))
const isDirty = computed(() => JSON.stringify(draft) !== initialSnapshot.value)
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
 * 根据项目详情刷新设置草稿，并重置脏检查基线。
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
  draft.slideshow = createSlideshowDraft(project?.slideshow)
  draft.audio = createAudioSettingsDraft(project?.audio_settings)
  appliedWorkspaceStyleId.value = null
  initialSnapshot.value = JSON.stringify(draft)
}

/**
 * 接收放映表单回传的完整草稿。
 * @param value 放映草稿
 */
function updateSlideshowDraft(value: SlideshowDraft): void {
  draft.slideshow = value
}

/**
 * 接收音频表单回传的完整草稿。
 * @param value 音频草稿
 */
function updateAudioDraft(value: AudioSettingsDraft): void {
  draft.audio = value
}

/**
 * 拦截关闭请求，存在未保存修改时先确认。
 * @param value 目标可见状态
 */
async function handleVisibleChange(value: boolean): Promise<void> {
  if (value) {
    emit('update:modelValue', true)
    return
  }
  if (props.loading || closeConfirming.value) {
    return
  }
  if (!isDirty.value) {
    emit('update:modelValue', false)
    return
  }
  closeConfirming.value = true
  const confirmed = await createConfirm(
    '项目设置有未保存的修改，关闭后将丢失。确定放弃这些修改吗？',
    '放弃未保存的修改？',
    { dangerous: true, confirmLabel: '放弃并关闭', cancelLabel: '继续编辑' },
  )
  closeConfirming.value = false
  if (confirmed) {
    emit('update:modelValue', false)
  }
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
 * 恢复到当前项目已保存的设置。
 */
function resetDraft(): void {
  syncDraftFromProject(props.project)
}

/**
 * 提交项目设置。
 */
function handleSave(): void {
  if (audioEnabled.value) {
    const audioError = validateAudioSettingsDraft(draft.audio)
    if (audioError) {
      activeTab.value = 'audio'
      Message.warning(audioError)
      return
    }
  }
  const payload: {
    page_width: number
    page_height: number
    base_font_size: string
    icon_default_stroke_width: number
    show_pdf_export_button: boolean
    menu_mode: ProjectMenuMode
    theme_key: string | null
    style_spec_markdown: string
    slideshow: SlideshowSettings
    audio_settings?: ProjectAudioSettings
    source_style_id?: number | null
  } = {
    page_width: normalizedPageWidth.value,
    page_height: normalizedPageHeight.value,
    base_font_size: normalizedBaseFontSize.value,
    icon_default_stroke_width: normalizedIconDefaultStrokeWidth.value,
    show_pdf_export_button: draft.showPdfExportButton,
    menu_mode: draft.menuMode,
    theme_key: draft.themeKey,
    style_spec_markdown: draft.styleSpecMarkdown,
    slideshow: normalizeSlideshowDraft(draft.slideshow),
  }
  if (audioEnabled.value) {
    payload.audio_settings = normalizeAudioSettingsDraft(draft.audio)
  }
  if (appliedWorkspaceStyleId.value !== null) {
    payload.source_style_id = appliedWorkspaceStyleId.value
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
 * 跳转到页面结构；有未保存修改时先确认。
 */
async function handleOpenRouteConfig(): Promise<void> {
  if (props.loading) {
    return
  }
  if (isDirty.value) {
    const confirmed = await createConfirm(
      '项目设置有未保存的修改，打开页面结构将丢失这些修改。确定继续吗？',
      '打开页面结构？',
      { dangerous: true, confirmLabel: '继续打开', cancelLabel: '继续编辑' },
    )
    if (!confirmed) {
      return
    }
  }
  emit('update:modelValue', false)
  emit('open-route-config')
}

/**
 * 将当前项目样式草稿保存为工作空间样式。
 * @param payload 样式创建参数
 */
async function handleSaveAsStyle(payload: WorkspaceStyleEditorSavePayload): Promise<void> {
  if (!props.workspaceId) {
    return
  }
  saveAsStyleSaving.value = true
  try {
    await createWorkspaceStyle(props.workspaceId, payload)
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
      activeTab.value = props.initialTab
      syncDraftFromProject(project)
      void loadSlideshowCapabilities()
    }
  },
  { immediate: true },
)

// 能力关闭后不能停留在已隐藏的音频标签页，避免保存隐藏草稿。
watch(audioEnabled, enabled => {
  if (!enabled && activeTab.value === 'audio') activeTab.value = 'presentation'
})
// 标签切换和弹窗关闭都停止试听，避免后台继续发声。
watch(activeTab, () => audioPanel.value?.stopPreview(true))
watch(() => props.modelValue, visible => {
  if (!visible) audioPanel.value?.stopPreview(true)
})
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
  border: 1px solid rgb(var(--ui-border));
  border-radius: 0.5rem;
  padding: 1rem;
}

/* 卡片至少包住自身内容（不可收缩），高度不足时由左侧面板滚动，避免内容溢出背景框。 */
.project-config-card--fill {
  flex: 1 0 auto;
}

/* 右侧规范卡片用纵向 flex 撑满弹窗高度，textarea 走 fill 模式占据剩余空间。
 * textarea 是 UiInput 内部非根节点，必须用 :deep() 才能命中透传 class。 */
.project-config-spec-card {
  display: flex;
  min-height: 0;
  flex-direction: column;
}

.project-config-spec-card :deep(.project-config-spec-textarea) {
  min-height: 260px;
}

.project-settings-slideshow {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 1rem;
  min-height: 100%;
  align-items: start;
}

@media (max-height: 820px) {
  .project-config-layout {
    gap: 0.75rem;
  }

  .project-config-card {
    padding: 0.875rem;
  }
}

@media (max-width: 1280px) {
  /* 窄屏改为纵向流式；滚动交给标签页内容区，避免与弹窗内容区形成双重滚动。 */
  .project-config-layout {
    display: block;
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

  .project-settings-slideshow {
    display: block;
    height: auto;
  }

  .project-settings-slideshow > * + * {
    margin-top: 0.75rem;
  }

  /* 窄屏下布局改为纵向流式，卡片没有确定高度，改回固定高度避免塌陷。 */
  .project-config-spec-card :deep(.project-config-spec-textarea) {
    height: min(420px, calc(100dvh - 330px));
    flex: none;
  }
}
</style>
