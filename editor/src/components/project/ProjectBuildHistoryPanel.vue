<!-- 文件功能：项目构建弹窗的构建历史区域，展示任务状态、产物入口与下载入口。 -->
<template>
  <section class="flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white p-4">
    <div class="flex shrink-0 items-center justify-between gap-3 flex-wrap">
      <div class="flex items-center gap-2">
        <History class="h-4 w-4 text-slate-500" />
        <h4 class="text-base font-semibold text-slate-900">构建历史</h4>
        <span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">
          {{ history.length }}
        </span>
      </div>
      <BaseButton variant="ghost" size="sm" :loading="historyLoading" @click="emit('refresh')">
        <template #icon>
          <RefreshCw class="h-4 w-4" />
        </template>
        刷新最新状态
      </BaseButton>
    </div>

    <div v-if="historyLoading" class="flex min-h-0 flex-1 items-center justify-center">
      <div class="flex items-center gap-3 text-sm font-semibold text-slate-400">
        <RefreshCw class="h-4 w-4 animate-spin" />
        正在同步构建历史
      </div>
    </div>

    <div v-else-if="history.length === 0" class="mt-4 flex min-h-0 flex-1 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-8 text-center">
      <p class="text-sm font-semibold text-slate-500">暂无构建记录</p>
    </div>

    <div v-else class="mt-4 min-h-0 flex-1 space-y-2 overflow-y-auto overflow-x-hidden pr-1">
      <article
        v-for="job in history"
        :key="job.id"
        class="min-w-0 rounded-lg border border-slate-200 bg-white px-3 py-2.5"
      >
        <div class="space-y-2">
          <div class="flex min-w-0 items-center justify-between gap-3">
            <div class="flex min-w-0 items-center gap-2">
              <span class="shrink-0 text-sm font-semibold text-slate-900">#{{ job.id }}</span>
              <span
                class="inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold"
                :class="getProjectBuildStatusMeta(job.status).badgeClass"
              >
                <span class="h-1.5 w-1.5 rounded-full" :class="getProjectBuildStatusMeta(job.status).dotClass"></span>
                {{ getCompactProjectBuildStatusLabel(job.status) }}
              </span>
              <span
                v-if="latestJobId === job.id"
                class="shrink-0 rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700"
              >
                最近一次
              </span>
            </div>
            <div class="flex min-w-0 max-w-[50%] items-center justify-end gap-2">
              <span
                class="inline-flex min-w-0 shrink items-center rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-600"
                :title="`部署路径：${job.base_url}`"
              >
                <span class="shrink-0 text-slate-400">路径</span>
                <span class="ml-1 min-w-0 truncate font-mono text-slate-700">{{ job.base_url }}</span>
              </span>
              <span class="shrink-0 text-xs text-slate-500">
                {{ formatProjectBuildArtifactSize(job.artifact_size_bytes) }}
              </span>
            </div>
          </div>

          <div class="flex min-w-0 items-center justify-between gap-3">
            <div class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
              <span>创建 <span class="text-slate-700">{{ formatDateTime(job.created_at) }}</span></span>
              <span>完成 <span class="text-slate-700">{{ formatDateTime(job.finished_at) }}</span></span>
            </div>
            <div v-if="canOpenProjectBuildArtifact(job) || canDownloadProjectBuildArtifact(job)" class="flex shrink-0 items-center gap-1.5">
              <BaseButton
                v-if="canOpenProjectBuildArtifact(job)"
                variant="secondary"
                size="sm"
                custom-class="h-8 whitespace-nowrap px-2"
                @click="emit('open', job)"
              >
                <template #icon>
                  <ExternalLink class="h-3.5 w-3.5" />
                </template>
                打开
              </BaseButton>
              <BaseButton
                v-if="canDownloadProjectBuildArtifact(job)"
                variant="secondary"
                size="sm"
                custom-class="h-8 whitespace-nowrap px-2"
                @click="emit('download', job)"
              >
                <template #icon>
                  <Download class="h-3.5 w-3.5" />
                </template>
                ZIP
              </BaseButton>
            </div>
          </div>

          <div
            v-if="job.error_message"
            class="line-clamp-4 break-words rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-xs leading-5 text-red-700"
          >
            {{ job.error_message }}
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Download, ExternalLink, History, RefreshCw } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import type { ProjectBuildJob, ProjectBuildStatus } from '@/types/api'
import { formatDateTime } from '@/utils/format'
import {
  canDownloadProjectBuildArtifact,
  canOpenProjectBuildArtifact,
  formatProjectBuildArtifactSize,
  getProjectBuildStatusMeta,
} from '@/utils/project-build'

defineProps<{
  history: ProjectBuildJob[]
  historyLoading: boolean
  latestJobId?: number | null
}>()

const emit = defineEmits<{
  refresh: []
  open: [job: ProjectBuildJob]
  download: [job: ProjectBuildJob]
}>()

/**
 * 构建历史列表使用更短的状态文案，降低单条记录宽度占用。
 * @param status 构建状态
 * @returns 历史条目中的紧凑状态文案
 */
function getCompactProjectBuildStatusLabel(status: ProjectBuildStatus): string {
  if (status === 'succeeded') {
    return '成功'
  }
  if (status === 'failed') {
    return '失败'
  }
  return getProjectBuildStatusMeta(status).label
}
</script>
