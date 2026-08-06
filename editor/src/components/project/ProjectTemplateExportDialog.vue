<!-- 文件功能：封装项目模板导出的预检、内容摘要、进度展示与文件下载流程。 -->
<template>
  <UiDialog
    :open="open"
    title="导出项目"
    description="检查项目页面、截图和依赖后下载项目模板包。"
    size="wide"
    @update:open="emit('update:open', $event)"
  >
    <div class="space-y-4">
      <div class="rounded-xl border border-border bg-canvas px-4 py-3">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="truncate text-sm font-bold text-text">{{ validation?.project.name || project?.name || '项目' }}</p>
            <p v-if="validation" class="mt-1 text-xs text-text-muted">
              页面 {{ validation.pages.length }} 个，组件 {{ validation.components.length }} 个，主题 {{ validation.themes.length }} 个，资源 {{ assetCount }} 个，字体 {{ validation.fonts.length }} 个
            </p>
            <p v-else-if="validationPending" class="mt-1 text-xs text-text-muted">正在检查项目内容…</p>
          </div>
          <span
            v-if="validation"
            class="rounded-full px-2.5 py-1 text-xs font-bold"
            :class="validation.can_export ? 'bg-success-muted text-success-strong ring-1 ring-success-border' : 'bg-danger-muted text-danger-strong ring-1 ring-danger-border'"
          >
            {{ validation.can_export ? '可导出' : '不可导出' }}
          </span>
        </div>
      </div>

      <div v-if="validation?.errors.length" class="rounded-xl border border-danger-border bg-danger-muted px-4 py-3">
        <p class="mb-2 text-sm font-bold text-danger-strong">预检未通过</p>
        <ul class="space-y-1 text-xs leading-5 text-danger-strong">
          <li v-for="error in validation.errors" :key="error">{{ error }}</li>
        </ul>
      </div>

      <div v-if="validation?.warnings.length" class="rounded-xl border border-warning-border bg-warning-muted px-4 py-3">
        <p class="mb-2 text-sm font-bold text-warning-strong">导出提示</p>
        <ul class="space-y-1 text-xs leading-5 text-warning-strong">
          <li v-for="warning in validation.warnings" :key="warning">{{ warning }}</li>
        </ul>
      </div>

      <div v-if="packagePending" class="rounded-xl border border-accent-muted bg-surface-selected px-4 py-3">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-sm font-bold text-accent-hover">{{ progressStage }}</p>
            <p class="mt-1 text-xs text-accent-emphasis">已耗时 {{ progressElapsedText }}。页面较多或截图过期时会更久。</p>
          </div>
          <span class="shrink-0 font-mono text-xs font-bold text-accent">{{ progressPercent }}%</span>
        </div>
        <div class="mt-3 h-2 overflow-hidden rounded-full bg-surface">
          <div class="h-full rounded-full bg-accent transition-all duration-500" :style="{ width: `${progressPercent}%` }" />
        </div>
      </div>

      <div v-if="validation" class="grid gap-3 lg:grid-cols-2">
        <section class="rounded-xl border border-border bg-surface p-4">
          <h4 class="text-sm font-bold text-text-emphasis">页面</h4>
          <div class="mt-2 max-h-40 space-y-2 overflow-y-auto text-xs text-text-muted">
            <p v-if="validation.pages.length === 0">无页面</p>
            <div v-for="page in validation.pages" :key="page.source_page_code" class="flex items-center justify-between gap-3">
              <span class="min-w-0 truncate font-semibold text-text-emphasis">{{ page.title }}</span>
              <span class="shrink-0 font-mono text-text-disabled">{{ page.source_page_code }}.{{ page.file_type }}</span>
            </div>
          </div>
        </section>

        <section class="rounded-xl border border-border bg-surface p-4">
          <h4 class="text-sm font-bold text-text-emphasis">截图</h4>
          <div class="mt-2 space-y-2 text-xs text-text-muted">
            <p v-if="validation.screenshots.cover">
              封面：{{ validation.screenshots.cover.path }} · {{ validation.screenshots.cover.width }}×{{ validation.screenshots.cover.height }}
            </p>
            <p v-else>无封面截图</p>
            <div class="max-h-28 space-y-1 overflow-y-auto">
              <p v-for="screenshot in validation.screenshots.pages" :key="screenshot.path">
                {{ screenshot.title || screenshot.source_page_code || screenshot.path }} · {{ screenshot.width }}×{{ screenshot.height }}
              </p>
            </div>
          </div>
        </section>

        <section class="rounded-xl border border-border bg-surface p-4">
          <h4 class="text-sm font-bold text-text-emphasis">组件</h4>
          <div class="mt-2 max-h-40 space-y-2 overflow-y-auto text-xs text-text-muted">
            <p v-if="validation.components.length === 0">无组件</p>
            <div v-for="component in validation.components" :key="`${component.source_component_code}-${component.source_version_no}`" class="flex items-center justify-between gap-3">
              <span class="min-w-0 truncate font-semibold text-text-emphasis">{{ component.name }}</span>
              <span class="shrink-0 font-mono text-text-disabled">{{ component.import_name }} v{{ component.source_version_no }}</span>
            </div>
          </div>
        </section>

        <section class="rounded-xl border border-border bg-surface p-4">
          <h4 class="text-sm font-bold text-text-emphasis">资源</h4>
          <div class="mt-2 max-h-40 space-y-2 overflow-y-auto text-xs text-text-muted">
            <p v-if="assetCount === 0">无资源</p>
            <div v-for="asset in validation.automatic_assets" :key="`auto-${asset.name}`" class="flex items-center justify-between gap-3">
              <span class="min-w-0 truncate font-semibold text-text-emphasis">{{ asset.name }}</span>
              <span class="shrink-0 text-text-disabled">{{ resolveAssetTypeLabel(asset.asset_type) }} · 自动</span>
            </div>
            <div v-for="asset in validation.manual_assets" :key="`manual-${asset.name}`" class="flex items-center justify-between gap-3">
              <span class="min-w-0 truncate font-semibold text-text-emphasis">{{ asset.name }}</span>
              <span class="shrink-0 text-text-disabled">{{ resolveAssetTypeLabel(asset.asset_type) }} · 手动</span>
            </div>
          </div>
        </section>
      </div>
    </div>

    <template #footer>
      <UiButton variant="ghost" :disabled="packagePending" @click="emit('update:open', false)">取消</UiButton>
      <UiButton
        variant="primary"
        :disabled="validationPending || !validation?.can_export || !project"
        :loading="packagePending"
        @click="handleExport"
      >
        下载项目
      </UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { getErrorMessage } from '@/api/http'
import { exportProjectTemplatePackage, validateProjectTemplatePackageExport } from '@/api/templates'
import { UiButton, UiDialog } from '@/components/ui'
import type { ProjectItem, ProjectTemplateExportRequest, ProjectTemplateExportValidationResult } from '@/types/api'
import { Message } from '@/utils/message'
import { downloadBlob } from '@/utils/zip-download'

const props = defineProps<{
  open: boolean
  project: ProjectItem | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'validation-change': [projectId: number | null]
  'package-change': [pending: boolean]
}>()

const validation = ref<ProjectTemplateExportValidationResult | null>(null)
const validationPending = ref(false)
const packagePending = ref(false)
const progressPercent = ref(0)
const progressStartedAt = ref<number | null>(null)
const progressTick = ref(0)
let progressTimer: number | null = null

const assetCount = computed(() => (
  (validation.value?.automatic_assets.length ?? 0) + (validation.value?.manual_assets.length ?? 0)
))
const progressElapsedSeconds = computed(() => {
  progressTick.value
  return progressStartedAt.value ? Math.max(0, Math.floor((Date.now() - progressStartedAt.value) / 1000)) : 0
})
const progressElapsedText = computed(() => {
  const totalSeconds = progressElapsedSeconds.value
  return totalSeconds < 60 ? `${totalSeconds} 秒` : `${Math.floor(totalSeconds / 60)} 分 ${totalSeconds % 60} 秒`
})
const progressStage = computed(() => {
  if (progressPercent.value < 30) return '准备导出请求'
  if (progressPercent.value < 60) return '刷新页面截图'
  if (progressPercent.value < 86) return '收集依赖并打包'
  return '等待下载响应'
})

watch([() => props.open, () => props.project?.id], ([open]) => {
  if (open && props.project) {
    void validateProject(props.project)
  }
})

onBeforeUnmount(stopProgress)

/** 对当前项目执行模板导出预检。 */
async function validateProject(project: ProjectItem): Promise<void> {
  validation.value = null
  validationPending.value = true
  emit('validation-change', project.id)
  try {
    validation.value = await validateProjectTemplatePackageExport(project.id, buildExportPayload(project))
  } catch (error) {
    Message.error(getErrorMessage(error, '项目导出预检失败。'))
    emit('update:open', false)
  } finally {
    validationPending.value = false
    emit('validation-change', null)
  }
}

/** 导出预检通过的项目并触发浏览器下载。 */
async function handleExport(): Promise<void> {
  if (!props.project) return
  packagePending.value = true
  emit('package-change', true)
  startProgress()
  try {
    const { blob, filename } = await exportProjectTemplatePackage(props.project.id, buildExportPayload(props.project))
    progressPercent.value = 100
    downloadBlob(blob, filename)
    emit('update:open', false)
    Message.success('项目已开始下载。')
  } catch (error) {
    Message.error(getErrorMessage(error, '项目导出失败。'))
  } finally {
    packagePending.value = false
    emit('package-change', false)
    stopProgress()
  }
}

/** 构建项目模板导出请求。 */
function buildExportPayload(project: ProjectItem): ProjectTemplateExportRequest {
  return {
    metadata: {
      slug: project.code.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || 'project-template',
      name: project.name,
      summary: project.description || null,
      description: project.description || null,
    },
    refresh_screenshots: true,
  }
}

/** 启动导出阶段进度估算。 */
function startProgress(): void {
  stopProgress()
  progressStartedAt.value = Date.now()
  progressTick.value = 0
  progressPercent.value = 8
  progressTimer = window.setInterval(() => {
    progressTick.value += 1
    const seconds = progressElapsedSeconds.value
    if (seconds <= 5) progressPercent.value = Math.min(30, 8 + seconds * 4)
    else if (seconds <= 25) progressPercent.value = Math.min(60, 30 + (seconds - 5) * 1.5)
    else if (seconds <= 80) progressPercent.value = Math.min(86, 60 + Math.floor((seconds - 25) * 0.5))
    else progressPercent.value = 90
  }, 1000)
}

/** 停止进度估算并释放计时器。 */
function stopProgress(): void {
  if (progressTimer !== null) window.clearInterval(progressTimer)
  progressTimer = null
  progressStartedAt.value = null
}

/** 转换资源类型为中文标签。 */
function resolveAssetTypeLabel(type: string): string {
  return ({ image: '图片', icon: '图标', font: '字体', video: '视频', drawio: 'Draw.io', mermaid: 'Mermaid', chart: '图表', formula: '公式' } as Record<string, string>)[type] ?? type
}
</script>
