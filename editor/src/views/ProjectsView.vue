<!-- 文件功能：展示当前工作空间下的启用项目入口，并提供项目创建、归档与归档列表查看能力。 -->
<template>
  <div data-testid="workspace-project-list" class="projects-view pb-12">
    <header class="mb-6 animate-in fade-in slide-in-from-top-4 duration-700">
      <PageTitleBar
        :title="workspaceQuery.data.value?.name ?? '正在加载工作空间...'"
      >
        <template #actions>

          <BaseButton variant="ghost" :disabled="!workspaceDetails" @click="openWorkspaceEditDialog">
            <template #icon>
              <Settings2 class="w-4 h-4" />
            </template>
            编辑工作空间
          </BaseButton>
          <BaseButton
            variant="ghost"
            :disabled="!workspaceDetails || importValidatePending || importPackagePending"
            @click="openTemplateImportPicker"
          >
            <template #icon>
              <Upload class="w-4 h-4" />
            </template>
            导入项目
          </BaseButton>
          <button
            type="button"
            class="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-600 shadow-sm transition-all hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50"
            @click="archivedDialogVisible = true"
          >
            <Archive class="w-4 h-4" />
            <span>已归档项目</span>
          </button>
        </template>
      </PageTitleBar>
      <input
        ref="templateImportInputRef"
        class="hidden"
        type="file"
        accept=".wptemplate.zip,.zip,application/zip"
        @change="handleTemplateImportFileSelected"
      />
    </header>

    <!-- 数据加载态 -->
    <div v-if="query.isFetching.value" class="flex flex-col items-center justify-center h-64 gap-4">
      <div class="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
      <span class="text-slate-400 font-bold animate-pulse">正在获取项目数据...</span>
    </div>

    <!-- 卡片栅格区 -->
    <div v-else class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      <ProjectCard
        v-for="proj in projects"
        :key="proj.id"
        :project="proj"
        :export-pending="exportValidateProjectId === proj.id"
        :export-disabled="exportPackagePending"
        :archive-pending="archivingProjectId === proj.id"
        :theme-name="resolveProjectThemeName(proj)"
        :theme-loading="themeQuery.isFetching.value"
        @open="goToProject"
        @export-template="handleValidateExportTemplate"
        @archive="handleArchiveProject"
      />

      <!-- 新增项目卡片 -->
      <button @click="openCreateDialog"
        class="group flex min-h-[13.75rem] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50/60 p-6 text-center transition-all duration-200 hover:-translate-y-1 hover:border-indigo-400 hover:bg-indigo-50/70">
        <div
          class="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-400 shadow-sm transition-all group-hover:border-indigo-200 group-hover:bg-indigo-600 group-hover:text-white">
          <Plus class="h-7 w-7" />
        </div>
        <span class="text-base font-black text-slate-800 transition-colors group-hover:text-indigo-700">新增项目</span>
        <span class="mt-1 text-sm font-medium text-slate-400">创建新的演示内容集合</span>
      </button>
    </div>

    <ProjectMetadataDialog
      v-model="dialogVisible"
      :workspace-id="workspaceId"
      :default-theme-key="workspaceDetails?.default_theme_key ?? null"
      :loading="saving"
      @submit="handleCreateProject"
    />
    <ArchivedProjectsDialog
      v-model="archivedDialogVisible"
      :workspace-id="workspaceId"
    />
    <WorkspaceMetadataDialog
      v-model="workspaceMetadataDialogVisible"
      :workspace="workspaceDetails"
      :loading="workspaceSaving"
      @submit="handleWorkspaceUpdate"
    />
    <BaseDialog v-model="exportTemplateDialogVisible" title="导出项目" size="wide">
      <div class="space-y-4">
        <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate text-sm font-bold text-slate-800">{{ exportValidation?.project.name || selectedExportProject?.name || '项目' }}</p>
              <p v-if="exportValidation" class="mt-1 text-xs text-slate-500">
                页面 {{ exportValidation.pages.length }} 个，组件 {{ exportValidation.components.length }} 个，主题 {{ exportValidation.themes.length }} 个，资源 {{ exportAssetCount }} 个，字体 {{ exportValidation.fonts.length }} 个
              </p>
            </div>
            <span
              v-if="exportValidation"
              class="rounded-full px-2.5 py-1 text-xs font-bold"
              :class="exportValidation.can_export ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100' : 'bg-rose-50 text-rose-700 ring-1 ring-rose-100'"
            >
              {{ exportValidation.can_export ? '可导出' : '不可导出' }}
            </span>
          </div>
        </div>

        <div v-if="exportValidation?.errors.length" class="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3">
          <p class="mb-2 text-sm font-bold text-rose-700">预检未通过</p>
          <ul class="space-y-1 text-xs leading-5 text-rose-700">
            <li v-for="error in exportValidation.errors" :key="error">{{ error }}</li>
          </ul>
        </div>

        <div v-if="exportValidation?.warnings.length" class="rounded-xl border border-amber-100 bg-amber-50 px-4 py-3">
          <p class="mb-2 text-sm font-bold text-amber-800">导出提示</p>
          <ul class="space-y-1 text-xs leading-5 text-amber-800">
            <li v-for="warning in exportValidation.warnings" :key="warning">{{ warning }}</li>
          </ul>
        </div>

        <div v-if="exportPackagePending" class="rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-sm font-bold text-indigo-700">{{ exportProgressStage }}</p>
              <p class="mt-1 text-xs text-indigo-500">
                已耗时 {{ exportProgressElapsedText }}。页面较多或截图过期时会更久。
              </p>
            </div>
            <span class="shrink-0 font-mono text-xs font-bold text-indigo-600">{{ exportProgressPercent }}%</span>
          </div>
          <div class="mt-3 h-2 overflow-hidden rounded-full bg-white">
            <div
              class="h-full rounded-full bg-indigo-600 transition-all duration-500"
              :style="{ width: `${exportProgressPercent}%` }"
            />
          </div>
        </div>

        <div v-if="exportValidation" class="grid gap-3 lg:grid-cols-2">
          <section class="rounded-xl border border-slate-200 bg-white p-4">
            <h4 class="text-sm font-bold text-slate-700">页面</h4>
            <div class="mt-2 max-h-40 space-y-2 overflow-y-auto text-xs text-slate-500">
              <p v-if="exportValidation.pages.length === 0">无页面</p>
              <div v-for="page in exportValidation.pages" :key="page.source_page_code" class="flex items-center justify-between gap-3">
                <span class="min-w-0 truncate font-semibold text-slate-700">{{ page.title }}</span>
                <span class="shrink-0 font-mono text-slate-400">{{ page.source_page_code }}.{{ page.file_type }}</span>
              </div>
            </div>
          </section>

          <section class="rounded-xl border border-slate-200 bg-white p-4">
            <h4 class="text-sm font-bold text-slate-700">截图</h4>
            <div class="mt-2 space-y-2 text-xs text-slate-500">
              <p v-if="exportValidation.screenshots.cover">
                封面：{{ exportValidation.screenshots.cover.path }} · {{ exportValidation.screenshots.cover.width }}×{{ exportValidation.screenshots.cover.height }}
              </p>
              <p v-else>无封面截图</p>
              <div class="max-h-28 space-y-1 overflow-y-auto">
                <p v-for="screenshot in exportValidation.screenshots.pages" :key="screenshot.path">
                  {{ screenshot.title || screenshot.source_page_code || screenshot.path }} · {{ screenshot.width }}×{{ screenshot.height }}
                </p>
              </div>
            </div>
          </section>

          <section class="rounded-xl border border-slate-200 bg-white p-4">
            <h4 class="text-sm font-bold text-slate-700">组件</h4>
            <div class="mt-2 max-h-40 space-y-2 overflow-y-auto text-xs text-slate-500">
              <p v-if="exportValidation.components.length === 0">无组件</p>
              <div v-for="component in exportValidation.components" :key="`${component.source_component_code}-${component.source_version_no}`" class="flex items-center justify-between gap-3">
                <span class="min-w-0 truncate font-semibold text-slate-700">{{ component.name }}</span>
                <span class="shrink-0 font-mono text-slate-400">{{ component.import_name }} v{{ component.source_version_no }}</span>
              </div>
            </div>
          </section>

          <section class="rounded-xl border border-slate-200 bg-white p-4">
            <h4 class="text-sm font-bold text-slate-700">资源</h4>
            <div class="mt-2 max-h-40 space-y-2 overflow-y-auto text-xs text-slate-500">
              <p v-if="exportAssetCount === 0">无资源</p>
              <div v-for="asset in exportValidation.automatic_assets" :key="`auto-${asset.name}`" class="flex items-center justify-between gap-3">
                <span class="min-w-0 truncate font-semibold text-slate-700">{{ asset.name }}</span>
                <span class="shrink-0 text-slate-400">{{ resolveAssetTypeLabel(asset.asset_type) }} · 自动</span>
              </div>
              <div v-for="asset in exportValidation.manual_assets" :key="`manual-${asset.name}`" class="flex items-center justify-between gap-3">
                <span class="min-w-0 truncate font-semibold text-slate-700">{{ asset.name }}</span>
                <span class="shrink-0 text-slate-400">{{ resolveAssetTypeLabel(asset.asset_type) }} · 手动</span>
              </div>
            </div>
          </section>
        </div>
      </div>

      <template #footer>
        <BaseButton variant="ghost" :disabled="exportPackagePending" @click="exportTemplateDialogVisible = false">取消</BaseButton>
        <BaseButton
          variant="primary"
          :disabled="!exportValidation?.can_export || !selectedExportProject"
          :loading="exportPackagePending"
          @click="handleConfirmExportTemplate"
        >
          下载项目
        </BaseButton>
      </template>
    </BaseDialog>

    <BaseDialog v-model="importTemplateDialogVisible" title="导入项目" size="canvas">
      <div class="space-y-4">
        <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate text-sm font-bold text-slate-800">{{ importTemplateTitle }}</p>
              <p class="mt-1 text-xs text-slate-500">{{ importTemplateFile?.name || '未选择文件' }}</p>
            </div>
            <span
              v-if="importValidation"
              class="rounded-full px-2.5 py-1 text-xs font-bold"
              :class="importValidation.valid ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100' : 'bg-rose-50 text-rose-700 ring-1 ring-rose-100'"
            >
              {{ importValidation.valid ? '可导入' : '不可导入' }}
            </span>
          </div>
          <p v-if="importValidation" class="mt-2 text-xs text-slate-500">
            页面 {{ importValidation.pages.length }} 个，组件 {{ importValidation.components.length }} 个，主题 {{ importValidation.themes.length }} 个，资源 {{ importValidation.assets.length }} 个，字体 {{ importValidation.fonts.length }} 个
          </p>
          <p v-else-if="importValidatePending" class="mt-2 text-xs text-slate-500">正在预检项目...</p>
        </div>

        <div v-if="importValidation?.errors.length" class="rounded-xl border border-rose-100 bg-rose-50 px-4 py-3">
          <p class="mb-2 text-sm font-bold text-rose-700">预检未通过</p>
          <ul class="space-y-1 text-xs leading-5 text-rose-700">
            <li v-for="error in importValidation.errors" :key="error">{{ error }}</li>
          </ul>
        </div>

        <div v-if="importValidation?.warnings.length" class="rounded-xl border border-amber-100 bg-amber-50 px-4 py-3">
          <p class="mb-2 text-sm font-bold text-amber-800">导入提示</p>
          <ul class="space-y-1 text-xs leading-5 text-amber-800">
            <li v-for="warning in importValidation.warnings" :key="warning">{{ warning }}</li>
          </ul>
        </div>

        <div v-if="importValidation" class="grid gap-3 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <section class="space-y-3">
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">项目信息</h4>
              <dl class="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                <div v-for="item in importMetadataItems" :key="item.label" class="rounded-lg bg-slate-50 px-3 py-2">
                  <dt class="font-bold text-slate-400">{{ item.label }}</dt>
                  <dd class="mt-1 truncate font-semibold text-slate-700">{{ item.value }}</dd>
                </div>
              </dl>
            </div>

            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">页面与截图</h4>
              <div class="mt-2 max-h-44 space-y-2 overflow-y-auto text-xs text-slate-500">
                <p v-if="importValidation.pages.length === 0">无页面</p>
                <div v-for="page in importValidation.pages" :key="page.source_page_code" class="flex items-center justify-between gap-3">
                  <span class="min-w-0 truncate font-semibold text-slate-700">{{ page.title }}</span>
                  <span class="shrink-0 font-mono text-slate-400">{{ page.source_page_code }}.{{ page.file_type }}</span>
                </div>
                <p v-if="importValidation.screenshots.cover" class="border-t border-slate-100 pt-2">
                  封面截图：{{ importValidation.screenshots.cover.path }}
                </p>
                <p v-if="importValidation.screenshots.pages.length" class="text-slate-400">
                  页面截图 {{ importValidation.screenshots.pages.length }} 张
                </p>
              </div>
            </div>
          </section>

          <section class="space-y-3">
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <h4 class="text-sm font-bold text-slate-700">依赖预检</h4>
              <div class="mt-3 grid gap-3 sm:grid-cols-2">
                <div class="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <p class="text-xs font-bold text-slate-500">组件</p>
                  <div class="mt-2 max-h-28 space-y-1 overflow-y-auto text-xs text-slate-500">
                    <p v-if="importValidation.components.length === 0">无组件</p>
                    <p v-for="component in importValidation.components" :key="`${component.source_component_code}-${component.source_version_no}`" class="truncate">
                      {{ component.name }} · {{ resolveImportActionText(component.action) }}
                    </p>
                  </div>
                </div>
                <div class="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <p class="text-xs font-bold text-slate-500">资源</p>
                  <div class="mt-2 max-h-28 space-y-1 overflow-y-auto text-xs text-slate-500">
                    <p v-if="importValidation.assets.length === 0">无资源</p>
                    <p v-for="asset in importValidation.assets" :key="asset.name" class="truncate">
                      {{ asset.name }} · {{ resolveImportActionText(asset.action) }}
                    </p>
                  </div>
                </div>
                <div class="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <p class="text-xs font-bold text-slate-500">主题</p>
                  <div class="mt-2 max-h-24 space-y-1 overflow-y-auto text-xs text-slate-500">
                    <p v-if="importValidation.themes.length === 0">无主题</p>
                    <p v-for="theme in importValidation.themes" :key="theme.key" class="truncate">
                      {{ theme.name }} · {{ resolveImportActionText(theme.action) }}
                    </p>
                  </div>
                </div>
                <div class="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <p class="text-xs font-bold text-slate-500">字体</p>
                  <div class="mt-2 max-h-24 space-y-1 overflow-y-auto text-xs text-slate-500">
                    <p v-if="importValidation.fonts.length === 0">无字体</p>
                    <p v-for="font in importValidation.fonts" :key="font.asset_name" class="truncate">
                      {{ font.asset_name }} · {{ resolveImportActionText(font.action) }}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="importPreviewArtifact" class="rounded-xl border border-slate-200 bg-white p-4">
              <div class="mb-3 flex items-center justify-between gap-3">
                <h4 class="text-sm font-bold text-slate-700">临时预览</h4>
                <span class="font-mono text-[11px] text-slate-400">{{ importPreviewArtifact.artifact_id }}</span>
              </div>
              <RuntimePreviewFrame
                :frame-url="importPreviewArtifact.preview_url"
                title="项目预览"
                :viewport="{ width: importPreviewArtifact.viewport_width, height: importPreviewArtifact.viewport_height }"
                min-height="280px"
              />
            </div>
          </section>
        </div>
      </div>

      <template #footer>
        <BaseButton variant="ghost" @click="closeImportTemplateDialog">取消</BaseButton>
        <BaseButton
          variant="secondary"
          :disabled="!importValidation?.valid || !importTemplateFile"
          :loading="importPreviewPending"
          @click="handlePreviewImportTemplate"
        >
          <template #icon>
            <Eye class="h-4 w-4" />
          </template>
          临时预览
        </BaseButton>
        <BaseButton
          variant="primary"
          :disabled="!importValidation?.valid || !importTemplateFile"
          :loading="importPackagePending"
          @click="handleConfirmImportTemplate"
        >
          确认导入
        </BaseButton>
      </template>
    </BaseDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { Archive, Eye, Plus, Settings2, Upload } from '@lucide/vue'

import { createProject, getWorkspace, listProjects, updateProject, updateWorkspace } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import {
  createProjectTemplatePackagePreviewArtifact,
  exportProjectTemplatePackage,
  importProjectTemplatePackage,
  validateProjectTemplatePackageExport,
  validateProjectTemplatePackageImport,
} from '@/api/templates'
import { listWorkspaceThemes } from '@/api/themes'
import PageTitleBar from '@/components/layout/PageTitleBar.vue'
import ArchivedProjectsDialog from '@/components/project/ArchivedProjectsDialog.vue'
import ProjectCard from '@/components/project/ProjectCard.vue'
import ProjectMetadataDialog from '@/components/project/ProjectMetadataDialog.vue'
import WorkspaceMetadataDialog from '@/components/project/WorkspaceMetadataDialog.vue'
import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import { createConfirm, Message } from '@/utils/message'
import BaseButton from '@/components/ui/BaseButton.vue'
import { downloadBlob } from '@/utils/zip-download'
import type {
  PreviewArtifactResponse,
  ProjectItem,
  ProjectMenuMode,
  ProjectTemplateExportRequest,
  ProjectTemplateExportValidationResult,
  ProjectTemplateImportValidationResult,
} from '@/types/api'
import { buildProjectPagesPath } from '@/utils/workspace-routes'

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()

const workspaceId = computed(() => parseInt(route.params.workspaceId as string, 10))

const workspaceQuery = useQuery(
  computed(() => ({
    queryKey: ['workspace', workspaceId.value],
    queryFn: () => getWorkspace(workspaceId.value),
    enabled: !!workspaceId.value,
  })),
)

const query = useQuery(
  computed(() => ({
    queryKey: ['projects-by-ws', workspaceId.value, 'active'],
    queryFn: () => listProjects({ page: 1, page_size: 100, workspace_id: workspaceId.value, status: 'active' }),
    enabled: !!workspaceId.value,
  })),
)

const themeQuery = useQuery(
  computed(() => ({
    queryKey: ['workspace-themes', workspaceId.value, 'project-card-labels'],
    queryFn: () => listWorkspaceThemes(workspaceId.value, { page: 1, page_size: 100 }),
    enabled: !!workspaceId.value,
  })),
)

const workspaceDetails = computed(() => workspaceQuery.data.value ?? null)
const projects = computed(() => query.data.value?.items ?? [])
const themeNameByKey = computed(() => new Map(
  (themeQuery.data.value?.items ?? []).map(theme => [theme.key, theme.name]),
))
const dialogVisible = ref(false)
const archivedDialogVisible = ref(false)
const saving = ref(false)
const archivingProjectId = ref<number | null>(null)
const workspaceMetadataDialogVisible = ref(false)
const workspaceSaving = ref(false)
const templateImportInputRef = ref<HTMLInputElement | null>(null)
const exportTemplateDialogVisible = ref(false)
const selectedExportProject = ref<ProjectItem | null>(null)
const exportValidation = ref<ProjectTemplateExportValidationResult | null>(null)
const exportValidateProjectId = ref<number | null>(null)
const exportPackagePending = ref(false)
const exportProgressPercent = ref(0)
const exportProgressStartedAt = ref<number | null>(null)
const exportProgressTick = ref(0)
let exportProgressTimer: number | null = null
const importTemplateDialogVisible = ref(false)
const importTemplateFile = ref<File | null>(null)
const importValidation = ref<ProjectTemplateImportValidationResult | null>(null)
const importValidatePending = ref(false)
const importPackagePending = ref(false)
const importPreviewPending = ref(false)
const importPreviewArtifact = ref<PreviewArtifactResponse | null>(null)

const exportAssetCount = computed(() => (
  (exportValidation.value?.automatic_assets.length ?? 0) + (exportValidation.value?.manual_assets.length ?? 0)
))
const exportProgressElapsedSeconds = computed(() => {
  exportProgressTick.value
  return exportProgressStartedAt.value ? Math.max(0, Math.floor((Date.now() - exportProgressStartedAt.value) / 1000)) : 0
})
const exportProgressElapsedText = computed(() => {
  const totalSeconds = exportProgressElapsedSeconds.value
  if (totalSeconds < 60) {
    return `${totalSeconds} 秒`
  }
  return `${Math.floor(totalSeconds / 60)} 分 ${totalSeconds % 60} 秒`
})
const exportProgressStage = computed(() => {
  const percent = exportProgressPercent.value
  if (percent < 30) {
    return '准备导出请求'
  }
  if (percent < 60) {
    return '刷新页面截图'
  }
  if (percent < 86) {
    return '收集依赖并打包'
  }
  return '等待下载响应'
})
const importTemplateTitle = computed(() => (
  readTemplateMetadataText('name')
  || importValidation.value?.project?.name
  || importTemplateFile.value?.name
  || '项目'
))
const importMetadataItems = computed(() => [
  { label: 'Slug', value: readTemplateMetadataText('slug') || '-' },
  { label: '作者', value: readTemplateMetadataText('author') || '-' },
  { label: '页面比例', value: readTemplateMetadataText('aspect_ratio') || resolveImportPageSizeText() },
])

function openCreateDialog() {
  dialogVisible.value = true
}

/**
 * 打开工作空间基础信息编辑弹窗。
 */
function openWorkspaceEditDialog(): void {
  workspaceMetadataDialogVisible.value = true
}

/**
 * 打开项目导入文件选择器。
 */
function openTemplateImportPicker(): void {
  templateImportInputRef.value?.click()
}

const saveMutation = useMutation({
  mutationFn: (payload: {
    name: string
    description: string | null
    status: 'active' | 'archived'
    page_width: number
    page_height: number
    base_font_size: string
    icon_default_stroke_width: number
    show_pdf_export_button: boolean
    menu_mode: ProjectMenuMode
    theme_key: string | null
    style_spec_markdown?: string
    suggested_component_source_style_id?: number | null
  }) => createProject({ ...payload, workspace_id: workspaceId.value }),
})

const archiveMutation = useMutation({
  mutationFn: (projectId: number) => updateProject(projectId, { status: 'archived' }),
})

onBeforeUnmount(() => {
  stopExportProgress()
})

/**
 * 创建新项目，并在成功后跳转到页面管理页继续操作。
 */
async function handleCreateProject(payload: {
  name: string
  description: string | null
  status: 'active' | 'archived'
  page_width: number
  page_height: number
  base_font_size: string
  icon_default_stroke_width: number
  show_pdf_export_button: boolean
  menu_mode: ProjectMenuMode
  theme_key: string | null
  style_spec_markdown?: string
  suggested_component_source_style_id?: number | null
}) {
  saving.value = true
  try {
    const res = await saveMutation.mutateAsync(payload)
    await queryClient.invalidateQueries({ queryKey: ['projects-by-ws', workspaceId.value] })
    dialogVisible.value = false
    Message.success('新项目已建立。')
    goToProject(res.id)
  } catch (error) {
    Message.error(getErrorMessage(error, '创建失败。'))
  } finally {
    saving.value = false
  }
}

/**
 * 将项目归档，并同步刷新启用列表与归档列表缓存。
 */
async function handleArchiveProject(project: ProjectItem) {
  const confirmed = await createConfirm(`归档后项目将从当前页面移入“已归档项目”列表，确定归档「${project.name}」吗？`, '归档项目')
  if (!confirmed) {
    return
  }

  archivingProjectId.value = project.id
  try {
    await archiveMutation.mutateAsync(project.id)
    await queryClient.invalidateQueries({ queryKey: ['projects-by-ws', workspaceId.value] })
    Message.success('项目已归档。')
  } catch (error) {
    Message.error(getErrorMessage(error, '归档项目失败。'))
  } finally {
    archivingProjectId.value = null
  }
}

function goToProject(id: number) {
  router.push(buildProjectPagesPath(workspaceId.value, id))
}

/**
 * 按项目主题 key 映射主题名称；卡片不回退展示 key，避免把内部标识暴露给用户。
 * @param project 项目列表项
 */
function resolveProjectThemeName(project: ProjectItem): string | null {
  if (!project.theme_key) {
    return null
  }
  return themeNameByKey.value.get(project.theme_key) ?? null
}

/**
 * 预检指定项目的导出内容。
 * @param project 当前选择导出的项目
 */
async function handleValidateExportTemplate(project: ProjectItem): Promise<void> {
  selectedExportProject.value = project
  exportValidation.value = null
  exportValidateProjectId.value = project.id
  try {
    exportValidation.value = await validateProjectTemplatePackageExport(project.id, buildTemplateExportPayload(project))
    exportTemplateDialogVisible.value = true
  } catch (error) {
    Message.error(getErrorMessage(error, '项目导出预检失败。'))
  } finally {
    exportValidateProjectId.value = null
  }
}

/**
 * 下载当前预检通过的项目归档文件。
 */
async function handleConfirmExportTemplate(): Promise<void> {
  if (!selectedExportProject.value) {
    return
  }

  exportPackagePending.value = true
  startExportProgress()
  try {
    const { blob, filename } = await exportProjectTemplatePackage(
      selectedExportProject.value.id,
      buildTemplateExportPayload(selectedExportProject.value),
    )
    exportProgressPercent.value = 100
    downloadBlob(blob, filename)
    exportTemplateDialogVisible.value = false
    Message.success('项目已开始下载。')
  } catch (error) {
    Message.error(getErrorMessage(error, '项目导出失败。'))
  } finally {
    exportPackagePending.value = false
    stopExportProgress()
  }
}

/**
 * 启动导出过程的前端阶段进度展示。
 */
function startExportProgress(): void {
  stopExportProgress()
  exportProgressStartedAt.value = Date.now()
  exportProgressTick.value = 0
  exportProgressPercent.value = 8
  exportProgressTimer = window.setInterval(() => {
    exportProgressTick.value += 1
    const seconds = exportProgressElapsedSeconds.value
    if (seconds <= 5) {
      exportProgressPercent.value = Math.min(30, 8 + seconds * 4)
      return
    }
    if (seconds <= 25) {
      exportProgressPercent.value = Math.min(60, 30 + (seconds - 5) * 1.5)
      return
    }
    if (seconds <= 80) {
      exportProgressPercent.value = Math.min(86, 60 + Math.floor((seconds - 25) * 0.5))
      return
    }
    exportProgressPercent.value = 90
  }, 1000)
}

/**
 * 停止导出进度计时器。
 */
function stopExportProgress(): void {
  if (exportProgressTimer !== null) {
    window.clearInterval(exportProgressTimer)
    exportProgressTimer = null
  }
  exportProgressStartedAt.value = null
}

/**
 * 读取用户选择的项目文件并发起导入预检。
 * @param event 文件输入框 change 事件
 */
async function handleTemplateImportFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  input.value = ''
  if (!file) {
    return
  }

  importTemplateFile.value = file
  importValidation.value = null
  importPreviewArtifact.value = null
  importTemplateDialogVisible.value = true
  importValidatePending.value = true
  try {
    importValidation.value = await validateProjectTemplatePackageImport(workspaceId.value, file)
  } catch (error) {
    Message.error(getErrorMessage(error, '项目预检失败。'))
    importTemplateDialogVisible.value = false
  } finally {
    importValidatePending.value = false
  }
}

/**
 * 为上传项目创建短生命周期 Runtime 预览。
 */
async function handlePreviewImportTemplate(): Promise<void> {
  if (!importTemplateFile.value) {
    return
  }

  importPreviewPending.value = true
  try {
    importPreviewArtifact.value = await createProjectTemplatePackagePreviewArtifact(
      workspaceId.value,
      importTemplateFile.value,
    )
  } catch (error) {
    Message.error(getErrorMessage(error, '项目预览生成失败。'))
  } finally {
    importPreviewPending.value = false
  }
}

/**
 * 正式导入项目，并跳转到新创建项目。
 */
async function handleConfirmImportTemplate(): Promise<void> {
  if (!importTemplateFile.value) {
    return
  }

  importPackagePending.value = true
  try {
    const result = await importProjectTemplatePackage(workspaceId.value, importTemplateFile.value)
    await queryClient.invalidateQueries({ queryKey: ['projects-by-ws', workspaceId.value] })
    closeImportTemplateDialog()
    Message.success(`项目已导入为「${result.project_name}」。`)
    goToProject(result.project_id)
  } catch (error) {
    Message.error(getErrorMessage(error, '项目导入失败。'))
  } finally {
    importPackagePending.value = false
  }
}

/**
 * 关闭导入弹窗并清理上传包相关状态。
 */
function closeImportTemplateDialog(): void {
  importTemplateDialogVisible.value = false
  importTemplateFile.value = null
  importValidation.value = null
  importPreviewArtifact.value = null
}

/**
 * 构建模板导出请求，v1 默认把项目描述作为模板摘要。
 * @param project 导出的源项目
 */
function buildTemplateExportPayload(project: ProjectItem): ProjectTemplateExportRequest {
  return {
    metadata: {
      slug: normalizeTemplateSlug(project.code),
      name: project.name,
      summary: project.description || null,
      description: project.description || null,
    },
    refresh_screenshots: true,
  }
}

/**
 * 从模板元数据中读取可展示文本。
 * @param key 元数据字段名
 */
function readTemplateMetadataText(key: string): string | null {
  const value = importValidation.value?.template[key]
  if (typeof value === 'string') {
    return value.trim() || null
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (Array.isArray(value)) {
    const items = value.map(item => String(item || '').trim()).filter(Boolean)
    return items.length ? items.join('、') : null
  }
  return null
}

/**
 * 读取导入包项目尺寸，作为模板比例字段的兜底展示。
 */
function resolveImportPageSizeText(): string {
  const project = importValidation.value?.project
  return project ? `${project.page_width}×${project.page_height}` : '-'
}

/**
 * 归一化导出包 slug，避免模板库读取到带空白的标识。
 * @param value 项目编码或名称
 */
function normalizeTemplateSlug(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'project-template'
}

/**
 * 转换导入预检动作标签。
 * @param action 后端动作码
 */
function resolveImportActionText(action: string): string {
  const labels: Record<string, string> = {
    create: '新建',
    reuse: '复用',
    overwrite: '覆盖',
  }
  return labels[action] ?? action
}

/**
 * 转换资源类型标签。
 * @param type 后端资源类型
 */
function resolveAssetTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    image: '图片',
    icon: '图标',
    font: '字体',
    video: '视频',
    drawio: 'Draw.io',
    mermaid: 'Mermaid',
    chart: '图表',
    formula: '公式',
  }
  return labels[type] ?? type
}

/**
 * 保存工作空间基础信息，并刷新当前工作空间详情。
 * @param payload 工作空间基础信息
 */
async function handleWorkspaceUpdate(payload: {
  name: string
  description: string | null
}) {
  if (!workspaceDetails.value) {
    return
  }

  workspaceSaving.value = true
  try {
    await updateWorkspace(workspaceDetails.value.id, payload)
    await queryClient.invalidateQueries({ queryKey: ['workspace', workspaceId.value] })
    window.dispatchEvent(new Event('workspace-list-updated'))
    workspaceMetadataDialogVisible.value = false
    Message.success('工作空间已更新。')
  } catch (error) {
    Message.error(getErrorMessage(error, '更新工作空间失败。'))
  } finally {
    workspaceSaving.value = false
  }
}

</script>
