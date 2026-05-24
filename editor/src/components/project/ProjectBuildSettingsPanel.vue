<!-- 文件功能：项目构建弹窗的构建参数区域，编辑部署基路径并提交构建任务。 -->
<template>
  <section class="rounded-lg border border-slate-200 bg-white p-4">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div class="space-y-1">
        <div class="flex items-center gap-2 text-slate-900">
          <Rocket class="h-4 w-4 text-indigo-500" />
          <h4 class="text-base font-semibold">构建设置</h4>
        </div>
      </div>
    </div>

    <div class="mt-4 flex items-start gap-3">
      <label class="flex h-10 shrink-0 items-center text-sm font-semibold text-slate-700">部署基路径</label>
      <div class="flex min-w-0 flex-1 items-start gap-3">
        <BaseInput
          :model-value="baseUrl"
          class="min-w-0 flex-1"
          placeholder="./ 或 /demo/"
          :error="baseUrlError"
          @update:model-value="emit('update:baseUrl', String($event))"
        />
        <BaseButton
          variant="primary"
          :loading="loading"
          :disabled="buildLocked"
          :title="buildLocked ? `任务 #${latestJob?.id} ${latestJobStatusMeta.label}，完成后才能再次构建。` : '发起构建'"
          custom-class="h-10 min-w-[92px] shrink-0 px-3 text-sm whitespace-nowrap"
          @click="emit('submit')"
        >
          <template #icon>
            <Package class="h-3.5 w-3.5" />
          </template>
          {{ buildLocked ? latestJobStatusMeta.label : '发起构建' }}
        </BaseButton>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Package, Rocket } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import type { ProjectBuildJob } from '@/types/api'
import { getProjectBuildStatusMeta, isProjectBuildJobActive } from '@/utils/project-build'

const props = defineProps<{
  baseUrl: string
  baseUrlError: string
  latestJob?: ProjectBuildJob | null
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:baseUrl': [value: string]
  submit: []
}>()

const latestJobStatusMeta = computed(() => getProjectBuildStatusMeta(props.latestJob?.status))
const buildLocked = computed(() => isProjectBuildJobActive(props.latestJob))
</script>
