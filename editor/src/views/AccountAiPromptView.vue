<!-- 文件功能：个人设置 - 助手提示词视图，维护内容助手全局系统提示词（System Prompt），支持自定义与恢复系统默认。 -->
<template>
  <div class="account-ai-prompt-view flex h-full min-h-0 flex-1 flex-col space-y-4">
    <SettingsPageHeader
      title="助手提示词"
      description="设定内容助手的业务角色、思考风格与输出约束，对当前工作空间生效。"
      class="shrink-0"
    >
      <template #meta>
        <span
          class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
          :class="agentConfig?.prompt_customized ? 'bg-ai-muted text-ai-strong' : 'bg-surface-muted text-text-secondary'"
        >
          {{ agentConfig?.prompt_customized ? '账号自定义' : '系统默认' }}
        </span>
      </template>

      <template #actions>
        <UiButton
          variant="ghost"
          size="sm"
          :loading="savingPrompt"
          :disabled="!agentConfig?.prompt_customized && !promptDirty"
          @click="handleRestorePrompt"
        >
          恢复系统默认
        </UiButton>
        <UiButton
          size="sm"
          :loading="savingPrompt"
          :disabled="!promptDirty"
          @click="handleSavePrompt"
        >
          保存提示词
        </UiButton>
      </template>
    </SettingsPageHeader>

    <section class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-ui-xl border border-border bg-surface shadow-xs">
      <div class="flex min-h-0 flex-1 flex-col p-4 sm:p-5">
        <label for="assistant-prompt-textarea" class="sr-only">完整提示词内容</label>
        <UiInput
          input-id="assistant-prompt-textarea"
          class="prompt-textarea font-mono text-xs leading-relaxed"
          textarea-mode="fill"
          :model-value="promptDraft"
          type="textarea"
          placeholder="输入内容助手系统提示词，支持 Markdown..."
          @update:model-value="promptDraft = String($event)"
        />
      </div>

      <footer class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border-muted bg-canvas/40 px-5 py-3">
        <div class="flex items-center gap-2 text-xs">
          <span :class="promptDirty ? 'font-semibold text-warning-strong' : 'text-text-muted'">
            {{ promptDirty ? '提示词修改尚未保存，离开前请先保存。' : '当前内容已与云端保持一致。' }}
          </span>
          <span class="text-text-disabled">·</span>
          <span class="text-text-muted font-mono">字符数：{{ promptDraft.length }}</span>
        </div>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { onBeforeRouteLeave } from 'vue-router'

import { listAgentConfigs, updateAgentConfig } from '@/api/agent-config'
import { getErrorMessage } from '@/api/http'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import { UiButton, UiInput } from '@/components/ui'
import { Message, createConfirm } from '@/utils/message'

const queryClient = useQueryClient()

const agentConfigsQuery = useQuery({
  queryKey: ['agent-configs'],
  queryFn: listAgentConfigs,
})

const agentConfig = computed(() => agentConfigsQuery.data.value?.[0] ?? null)
const promptDraft = ref('')
const savingPrompt = ref(false)

const promptDirty = computed(() => {
  if (!agentConfig.value) return false
  return promptDraft.value.trim() !== (agentConfig.value.effective_prompt ?? '').trim()
})

watch(
  agentConfig,
  config => {
    if (!config) return
    promptDraft.value = config.effective_prompt ?? ''
  },
  { immediate: true },
)

/** 保存用户修改的系统提示词。 */
async function handleSavePrompt() {
  if (!agentConfig.value) return
  try {
    savingPrompt.value = true
    await updateAgentConfig(agentConfig.value.id, {
      prompt_override: promptDraft.value.trim() || null,
    })
    Message.success('提示词已保存')
    await queryClient.invalidateQueries({ queryKey: ['agent-configs'] })
  } catch (err) {
    Message.error(getErrorMessage(err, '保存提示词失败'))
  } finally {
    savingPrompt.value = false
  }
}

/** 恢复系统内置默认提示词。 */
async function handleRestorePrompt() {
  if (!agentConfig.value) return
  const confirmed = await createConfirm('确定要恢复为系统默认提示词吗？未保存的内容将被丢弃。', '恢复系统默认')
  if (!confirmed) return
  try {
    savingPrompt.value = true
    await updateAgentConfig(agentConfig.value.id, { prompt_override: null })
    Message.success('已恢复系统默认提示词')
    await queryClient.invalidateQueries({ queryKey: ['agent-configs'] })
    promptDraft.value = agentConfig.value.system_prompt ?? ''
  } catch (err) {
    Message.error(getErrorMessage(err, '恢复系统默认失败'))
  } finally {
    savingPrompt.value = false
  }
}

// 离开路由前保护未保存内容
onBeforeRouteLeave(async () => {
  if (!promptDirty.value) return true
  return createConfirm('当前提示词有未保存修改，确定离开并丢弃修改吗？', '放弃修改')
})
</script>

<style scoped>
:deep(.prompt-textarea textarea) {
  line-height: 1.75;
}
</style>
