<!-- 文件功能：项目主题配置弹窗，负责选择项目引用的工作空间主题。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    title="主题配置"
    size="standard"
    @update:model-value="handleVisibleChange"
  >
    <div v-if="project" class="space-y-4">
      <div class="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div class="text-lg font-bold text-slate-900">{{ project.name }}</div>
          <div class="mt-1 text-xs font-mono text-slate-400">{{ project.code }}</div>
        </div>
        <div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          当前项目将直接引用工作空间主题库中的主题。
          <br>
          保存后，Runtime 预览会按所选主题动态组装 `themes.config.yaml`。
        </div>
      </div>

      <div class="rounded-2xl border border-slate-200 bg-white p-4">
        <ThemeSelectorField
          :workspace-id="workspaceId"
          :model-value="draftThemeKey"
          :preferred-key="defaultThemeKey"
          label="项目主题"
          hint="选择后会保存 `theme_key`，并用于项目预览与运行时配置填充。"
          @update:model-value="updateThemeKey"
        />
      </div>
    </div>

    <div v-else class="py-10 text-center text-sm text-slate-400">
      当前没有可编辑的项目。
    </div>

    <template #footer>
      <BaseButton variant="ghost" @click="handleVisibleChange(false)">取消</BaseButton>
      <BaseButton variant="primary" :loading="loading" :disabled="!project" @click="handleSave">
        保存主题
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import ThemeSelectorField from '@/components/theme/ThemeSelectorField.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { ProjectItem } from '@/types/api'

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
  save: [{
    theme_key: string | null
  }]
}>()

const draftThemeKey = ref<string | null>(null)

/**
 * 根据当前项目刷新主题草稿，确保弹窗每次打开时都以最新后端状态为准。
 */
function syncDraftFromProject(project: ProjectItem | null): void {
  draftThemeKey.value = project?.theme_key ?? props.defaultThemeKey ?? null
}

/**
 * 更新主题草稿。
 */
function updateThemeKey(value: string | null): void {
  draftThemeKey.value = value
}

/**
 * 向父组件同步弹窗开关状态。
 */
function handleVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 提交当前主题配置。
 */
function handleSave(): void {
  emit('save', {
    theme_key: draftThemeKey.value,
  })
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

