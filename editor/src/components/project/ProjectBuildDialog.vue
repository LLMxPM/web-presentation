<!-- 文件功能：提供项目构建中心弹窗，支持发起构建、查看历史与下载 ZIP 产物。 -->
<template>
  <BaseDialog v-model="visible" title="项目构建中心" width="920px">
    <div data-testid="project-build-dialog" class="space-y-6">
      <section class="rounded-3xl border border-slate-200 bg-slate-50/80 p-5">
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div class="space-y-2">
            <div class="flex items-center gap-2 text-slate-900">
              <Rocket class="h-4 w-4 text-indigo-500" />
              <h4 class="text-base font-semibold">发起新构建</h4>
            </div>
            <div v-if="latestJob" class="flex items-center gap-2 flex-wrap text-sm">
              <span class="text-slate-500">最近一次任务 #{{ latestJob.id }}</span>
              <span
                class="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold"
                :class="latestJobStatusMeta.badgeClass"
              >
                <span class="h-1.5 w-1.5 rounded-full" :class="latestJobStatusMeta.dotClass"></span>
                {{ latestJobStatusMeta.label }}
              </span>
              <span class="text-xs text-slate-400">
                {{ latestJob.finished_at ? `完成于 ${formatDateTime(latestJob.finished_at)}` : '任务仍在执行中' }}
              </span>
            </div>
          </div>

          <BaseButton variant="ghost" size="sm" :loading="historyLoading" @click="emit('refresh')">
            <template #icon>
              <RefreshCw class="h-4 w-4" />
            </template>
            刷新最新状态
          </BaseButton>
        </div>

        <div class="mt-5 flex items-end gap-3 flex-wrap">
          <div class="min-w-[280px] flex-1">
            <div class="mb-1.5 ml-1 flex items-center gap-1.5">
              <label class="text-sm font-semibold text-slate-700">部署基路径</label>
              <span
                class="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-slate-300 text-[10px] font-bold text-slate-500"
                title="填写方式：支持 ./ 或以 / 开头的路径，例如 ./、/demo/。校验规则：会自动补齐结尾 /，不支持完整域名 URL 或双斜杠路径。"
              >
                i
              </span>
            </div>
            <BaseInput
              v-model="draft.base_url"
              placeholder="./ 或 /demo/"
              :error="baseUrlError"
            />
          </div>
          <BaseButton variant="primary" :loading="loading" @click="handleSubmit">
            <template #icon>
              <Package class="h-4 w-4" />
            </template>
            发起构建
          </BaseButton>
        </div>
      </section>

      <section class="space-y-4">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="flex items-center gap-2">
            <History class="h-4 w-4 text-slate-500" />
            <h4 class="text-base font-semibold text-slate-900">构建历史</h4>
            <span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">
              最近 {{ history.length }} 条
            </span>
          </div>
          <p class="text-xs text-slate-400">成功任务可下载 ZIP，失败任务可查看错误摘要。</p>
        </div>

        <div v-if="historyLoading" class="flex h-48 items-center justify-center">
          <div class="flex items-center gap-3 text-sm font-semibold text-slate-400">
            <RefreshCw class="h-4 w-4 animate-spin" />
            正在同步构建历史...
          </div>
        </div>

        <div v-else-if="history.length === 0" class="rounded-3xl border border-dashed border-slate-200 bg-slate-50/60 p-8 text-center">
          <p class="text-sm font-semibold text-slate-500">暂无构建记录</p>
          <p class="mt-2 text-xs leading-6 text-slate-400">提交第一次构建后，这里会展示任务状态、产物体积和下载入口。</p>
        </div>

        <div v-else class="max-h-[420px] space-y-3 overflow-y-auto pr-1">
          <article
            v-for="job in history"
            :key="job.id"
            class="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div class="flex items-start justify-between gap-4 flex-wrap">
              <div class="space-y-3 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm font-semibold text-slate-900">#{{ job.id }}</span>
                  <span
                    class="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold"
                    :class="getProjectBuildStatusMeta(job.status).badgeClass"
                  >
                    <span class="h-1.5 w-1.5 rounded-full" :class="getProjectBuildStatusMeta(job.status).dotClass"></span>
                    {{ getProjectBuildStatusMeta(job.status).label }}
                  </span>
                  <span
                    v-if="latestJobId === job.id"
                    class="rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700"
                  >
                    最近一次
                  </span>
                </div>

                <div class="grid gap-2 text-xs text-slate-500 md:grid-cols-2 xl:grid-cols-4">
                  <p>部署基路径：<span class="font-mono text-slate-700">{{ job.base_url }}</span></p>
                  <p>创建时间：<span class="text-slate-700">{{ formatDateTime(job.created_at) }}</span></p>
                  <p>完成时间：<span class="text-slate-700">{{ formatDateTime(job.finished_at) }}</span></p>
                  <p>ZIP 体积：<span class="text-slate-700">{{ formatProjectBuildArtifactSize(job.artifact_size_bytes) }}</span></p>
                </div>

                <div
                  v-if="job.error_message"
                  class="rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-xs leading-6 text-red-700"
                >
                  {{ job.error_message }}
                </div>
              </div>

              <div v-if="canOpenProjectBuildArtifact(job) || canDownloadProjectBuildArtifact(job)" class="flex items-center gap-2">
                <BaseButton
                  v-if="canOpenProjectBuildArtifact(job)"
                  variant="secondary"
                  size="sm"
                  @click="emit('open', job)"
                >
                  <template #icon>
                    <ExternalLink class="h-4 w-4" />
                  </template>
                  打开产物
                </BaseButton>
                <BaseButton
                  v-if="canDownloadProjectBuildArtifact(job)"
                  variant="secondary"
                  size="sm"
                  @click="emit('download', job)"
                >
                  <template #icon>
                    <Download class="h-4 w-4" />
                  </template>
                  下载 ZIP
                </BaseButton>
              </div>
            </div>
          </article>
        </div>
      </section>
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="visible = false">关闭</BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { Download, ExternalLink, History, Package, RefreshCw, Rocket } from 'lucide-vue-next'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import type { ProjectBuildJob } from '@/types/api'
import { formatDateTime } from '@/utils/format'
import {
  canDownloadProjectBuildArtifact,
  canOpenProjectBuildArtifact,
  formatProjectBuildArtifactSize,
  getProjectBuildStatusMeta,
  normalizeProjectBuildBaseUrl,
} from '@/utils/project-build'

const props = withDefaults(defineProps<{
  modelValue: boolean
  history?: ProjectBuildJob[]
  historyLoading?: boolean
  latestJob?: ProjectBuildJob | null
  latestJobId?: number | null
  defaultBaseUrl?: string | null
  loading?: boolean
}>(), {
  history: () => [],
  historyLoading: false,
  latestJob: null,
  latestJobId: null,
  defaultBaseUrl: './',
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  submit: [payload: { base_url: string }]
  refresh: []
  open: [job: ProjectBuildJob]
  download: [job: ProjectBuildJob]
}>()

const draft = reactive({
  base_url: './',
})

const baseUrlError = computed(() => {
  try {
    normalizeProjectBuildBaseUrl(draft.base_url)
    return ''
  } catch (error) {
    return error instanceof Error ? error.message : '部署基路径格式不正确。'
  }
})

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})
const latestJobStatusMeta = computed(() => getProjectBuildStatusMeta(props.latestJob?.status))

watch(
  () => props.modelValue,
  (nextVisible) => {
    if (nextVisible) {
      draft.base_url = props.defaultBaseUrl || './'
      emit('refresh')
    }
  },
)

/**
 * 提交构建参数。
 */
function handleSubmit(): void {
  if (baseUrlError.value) {
    return
  }

  emit('submit', { base_url: normalizeProjectBuildBaseUrl(draft.base_url) })
}
</script>
