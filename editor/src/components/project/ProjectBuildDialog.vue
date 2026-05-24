<!-- 文件功能：提供项目构建中心弹窗，编排构建设置、额外资源、资源问题与构建历史。 -->
<template>
  <BaseDialog v-model="visible" title="项目构建中心" width="1220px" body-class="overflow-hidden px-6 py-5">
    <div
      data-testid="project-build-dialog"
      class="grid min-w-0 gap-4 overflow-hidden lg:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.85fr)]"
      style="height: clamp(420px, 72vh, 760px); max-height: calc(100vh - 170px);"
    >
      <div class="flex min-h-0 min-w-0 flex-col gap-3 overflow-hidden">
        <ProjectBuildSettingsPanel
          v-model:base-url="draft.base_url"
          class="shrink-0"
          :base-url-error="baseUrlError"
          :latest-job="latestJob"
          :loading="loading"
          @submit="handleSubmit"
        />

        <ProjectBuildResourceIssuePanel
          v-if="resourceIssueTitle"
          class="shrink-0"
          :title="resourceIssueTitle"
          :description="resourceIssueDescription"
          :dynamic-module-paths="dynamicModulePaths"
          :missing-asset-names="missingAssetNames"
          :candidate-asset-names="candidateAssetNames"
          :selected-asset-names="draft.extraAssetNames"
          :can-save-extra-assets="canSaveExtraAssets"
          :extra-assets-saving="extraAssetsSaving"
          :loading="loading"
          @add-asset="addExtraAsset"
          @save-extra-assets="handleSaveExtraAssets"
          @submit="handleSubmit"
        />

        <ProjectBuildExtraAssetsPanel
          v-model:asset-keyword="assetKeyword"
          class="min-h-0 flex-1"
          :workspace-id="workspaceId"
          :automatic-asset-names="automaticAssetNames"
          :extra-asset-names="draft.extraAssetNames"
          :asset-options="assetOptions"
          :asset-options-loading="assetOptionsLoading"
          :extra-assets-saving="extraAssetsSaving"
          :can-save-extra-assets="canSaveExtraAssets"
          @load-assets="loadWorkspaceAssets"
          @toggle-asset="toggleExtraAsset"
          @remove-asset="removeExtraAsset"
          @restore="syncExtraAssetsFromProps"
          @save-extra-assets="handleSaveExtraAssets"
        />
      </div>

      <ProjectBuildHistoryPanel
        :history="history"
        :history-loading="historyLoading"
        :latest-job-id="latestJobId"
        @refresh="emit('refresh')"
        @open="job => emit('open', job)"
        @download="job => emit('download', job)"
      />
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'

import { listWorkspaceAssets } from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import ProjectBuildExtraAssetsPanel from '@/components/project/ProjectBuildExtraAssetsPanel.vue'
import ProjectBuildHistoryPanel from '@/components/project/ProjectBuildHistoryPanel.vue'
import ProjectBuildResourceIssuePanel from '@/components/project/ProjectBuildResourceIssuePanel.vue'
import ProjectBuildSettingsPanel from '@/components/project/ProjectBuildSettingsPanel.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { AssetResponse, ProjectBuildExtraAssetsJson, ProjectBuildJob, ProjectBuildResourceIssueData } from '@/types/api'
import { Message } from '@/utils/message'
import { isProjectBuildJobActive, normalizeProjectBuildBaseUrl } from '@/utils/project-build'

const props = withDefaults(defineProps<{
  modelValue: boolean
  history?: ProjectBuildJob[]
  historyLoading?: boolean
  latestJob?: ProjectBuildJob | null
  latestJobId?: number | null
  defaultBaseUrl?: string | null
  workspaceId?: number | null
  buildExtraAssetsJson?: ProjectBuildExtraAssetsJson | null
  automaticAssetNames?: string[]
  resourceIssueCode?: string | null
  resourceIssue?: ProjectBuildResourceIssueData | null
  extraAssetsSaving?: boolean
  loading?: boolean
}>(), {
  history: () => [],
  historyLoading: false,
  latestJob: null,
  latestJobId: null,
  defaultBaseUrl: './',
  workspaceId: null,
  buildExtraAssetsJson: null,
  automaticAssetNames: () => [],
  resourceIssueCode: null,
  resourceIssue: null,
  extraAssetsSaving: false,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: { base_url: string, extra_asset_names: string[] }]
  saveExtraAssets: [assetNames: string[]]
  refresh: []
  open: [job: ProjectBuildJob]
  download: [job: ProjectBuildJob]
}>()

const draft = reactive({
  base_url: './',
  extraAssetNames: [] as string[],
})
const assetKeyword = ref('')
const assetOptions = ref<AssetResponse[]>([])
const assetOptionsLoading = ref(false)

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const baseUrlError = computed(() => {
  try {
    normalizeProjectBuildBaseUrl(draft.base_url)
    return ''
  } catch (error) {
    return error instanceof Error ? error.message : '部署基路径格式不正确。'
  }
})
const dynamicModulePaths = computed(() => normalizeStringArray(props.resourceIssue?.dynamic_module_paths ?? []))
const candidateAssetNames = computed(() => normalizeAssetNames(props.resourceIssue?.candidate_asset_names ?? []))
const missingAssetNames = computed(() => normalizeStringArray(props.resourceIssue?.missing_asset_names ?? []))
const automaticAssetNames = computed(() => normalizeAssetNames(props.automaticAssetNames ?? []))
const savedExtraAssetNames = computed(() => excludeAutomaticAssetNames(props.buildExtraAssetsJson?.asset_names ?? []))
const canSaveExtraAssets = computed(() => {
  if (draft.extraAssetNames.length !== savedExtraAssetNames.value.length) {
    return true
  }
  return draft.extraAssetNames.some((assetName, index) => assetName !== savedExtraAssetNames.value[index])
})
const resourceIssueTitle = computed(() => {
  if (props.resourceIssueCode === 'PROJECT_BUILD_DYNAMIC_ASSET_REFERENCE') {
    return '构建需要补充动态资源'
  }
  if (props.resourceIssueCode === 'PROJECT_BUILD_ASSET_MISSING') {
    return '构建资源不存在'
  }
  return ''
})
const resourceIssueDescription = computed(() => {
  if (props.resourceIssueCode === 'PROJECT_BUILD_DYNAMIC_ASSET_REFERENCE') {
    return '源码中存在无法静态解析的资源名，请选择需要随构建打包的资源并保存到项目配置。'
  }
  if (props.resourceIssueCode === 'PROJECT_BUILD_ASSET_MISSING') {
    return '以下资源在工作空间中不存在或不是可构建的根资源，请先上传、恢复或修正资源名。'
  }
  return ''
})

watch(
  () => props.modelValue,
  (nextVisible) => {
    if (nextVisible) {
      draft.base_url = props.defaultBaseUrl || './'
      syncExtraAssetsFromProps()
      emit('refresh')
      void loadWorkspaceAssets()
    }
  },
  { immediate: true },
)

watch(
  () => props.buildExtraAssetsJson,
  () => {
    if (props.modelValue) {
      syncExtraAssetsFromProps()
    }
  },
)

watch(
  () => props.automaticAssetNames,
  () => {
    if (props.modelValue) {
      syncExtraAssetsFromProps()
    }
  },
)

/**
 * 提交构建参数。
 */
function handleSubmit(): void {
  if (isProjectBuildJobActive(props.latestJob)) {
    Message.warning('当前已有构建任务正在执行，请等待完成后再发起构建。')
    return
  }
  if (baseUrlError.value) {
    return
  }

  emit('submit', {
    base_url: normalizeProjectBuildBaseUrl(draft.base_url),
    extra_asset_names: excludeAutomaticAssetNames(draft.extraAssetNames),
  })
}

/**
 * 从项目配置同步额外构建资源草稿。
 */
function syncExtraAssetsFromProps(): void {
  draft.extraAssetNames = excludeAutomaticAssetNames(props.buildExtraAssetsJson?.asset_names ?? [])
}

/**
 * 加载工作空间资源，供额外构建资源选择。
 */
async function loadWorkspaceAssets(): Promise<void> {
  if (!props.workspaceId) {
    assetOptions.value = []
    return
  }

  assetOptionsLoading.value = true
  try {
    const response = await listWorkspaceAssets(props.workspaceId, {
      keyword: assetKeyword.value.trim(),
      page: 1,
      page_size: 100,
      sort_by: 'updated_at',
      sort_order: 'desc',
    })
    assetOptions.value = response.items
  } catch (error) {
    Message.error(getErrorMessage(error, '加载资源列表失败。'))
  } finally {
    assetOptionsLoading.value = false
  }
}

/**
 * 切换额外构建资源选择状态。
 * @param assetName 资源名
 */
function toggleExtraAsset(assetName: string): void {
  if (draft.extraAssetNames.includes(assetName)) {
    removeExtraAsset(assetName)
    return
  }
  addExtraAsset(assetName)
}

/**
 * 添加额外构建资源名。
 * @param assetName 资源名
 */
function addExtraAsset(assetName: string): void {
  if (automaticAssetNames.value.includes(assetName)) {
    return
  }
  draft.extraAssetNames = normalizeAssetNames([...draft.extraAssetNames, assetName])
}

/**
 * 移除额外构建资源名。
 * @param assetName 资源名
 */
function removeExtraAsset(assetName: string): void {
  draft.extraAssetNames = draft.extraAssetNames.filter(item => item !== assetName)
}

/**
 * 保存额外构建资源配置到项目。
 */
function handleSaveExtraAssets(): void {
  emit('saveExtraAssets', excludeAutomaticAssetNames(draft.extraAssetNames))
}

/**
 * 从资源名列表中移除当前构建已自动包含的资源。
 * @param values 原始资源名列表
 */
function excludeAutomaticAssetNames(values: string[]): string[] {
  const automatic = new Set(automaticAssetNames.value)
  return normalizeAssetNames(values).filter(assetName => !automatic.has(assetName))
}

/**
 * 归一化资源名列表。
 * @param values 原始资源名列表
 */
function normalizeAssetNames(values: string[]): string[] {
  const result: string[] = []
  const seen = new Set<string>()
  for (const value of values) {
    const normalized = String(value || '').trim().replace(/\\/g, '/').replace(/^\.?\//, '')
    if (!normalized || /^https?:\/\//i.test(normalized) || seen.has(normalized)) {
      continue
    }
    seen.add(normalized)
    result.push(normalized)
  }
  return result
}

/**
 * 归一化普通字符串数组，用于展示后端诊断路径。
 * @param values 原始字符串列表
 */
function normalizeStringArray(values: string[]): string[] {
  return values.map(item => String(item || '').trim()).filter(Boolean)
}
</script>
