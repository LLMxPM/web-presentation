<!-- 文件功能：个人设置 - 代码规范视图，维护面向智能体生成页面与组件代码的技术约束与工程范式。 -->
<template>
  <div class="account-ai-code-standards-view flex h-full min-h-0 flex-1 flex-col space-y-4">
    <SettingsPageHeader
      title="代码规范"
      description="维护面向 AI 生成页面与工作空间组件的技术约束与工程范式，支持 Markdown。"
      class="shrink-0"
    >
      <template #actions>
        <UiButton
          variant="ghost"
          size="sm"
          :loading="saving"
          :disabled="!selectedStandard?.customized && !currentDirty"
          @click="handleRestore"
        >
          恢复系统默认
        </UiButton>
        <UiButton
          size="sm"
          :loading="saving"
          :disabled="!currentDirty"
          @click="handleSave"
        >
          保存规范
        </UiButton>
      </template>
    </SettingsPageHeader>

    <section v-if="selectedStandard" class="flex min-h-0 flex-1 flex-col overflow-hidden rounded-ui-xl border border-border bg-surface shadow-xs">
      <header class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border-muted px-5 py-3">
        <UiTabs
          :model-value="selectedType"
          :items="standardTypes"
          class="min-w-0"
          list-class="border-b-0"
          content-class="hidden"
          @update:model-value="handleChangeType($event as StandardType)"
        />
        <span
          class="shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold"
          :class="selectedStandard.customized ? 'bg-ai-muted text-ai-strong' : 'bg-surface-muted text-text-secondary'"
        >
          {{ selectedStandard.customized ? '账号自定义' : '系统默认' }}
        </span>
      </header>

      <div class="flex min-h-0 flex-1 flex-col p-4 sm:p-5">
        <label for="code-standard-textarea" class="sr-only">代码规范内容</label>
        <UiInput
          input-id="code-standard-textarea"
          class="code-standard-textarea font-mono text-xs leading-relaxed"
          textarea-mode="fill"
          :model-value="currentDraft"
          type="textarea"
          :placeholder="`输入${selectedType === 'page' ? '页面' : '组件'}代码规范，支持 Markdown...`"
          @update:model-value="handleDraftInput(String($event))"
        />
      </div>

      <footer class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border-muted bg-canvas/40 px-5 py-3 text-xs">
        <span :class="currentDirty ? 'font-semibold text-warning-strong' : 'text-text-muted'">
          {{ currentDirty ? '代码规范修改尚未保存，离开前请先保存。' : '当前内容已与云端保持一致。' }}
        </span>
        <span class="text-text-muted font-mono">字符数：{{ currentDraft.length }}</span>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { onBeforeRouteLeave } from 'vue-router'

import { listAgentConfigs, listAgentCodeStandards, updateAgentCodeStandard } from '@/api/agent-config'
import { getErrorMessage } from '@/api/http'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import { UiButton, UiInput, UiTabs } from '@/components/ui'
import type { AgentCodeStandardConfigItem } from '@/types/api'
import { Message, createConfirm } from '@/utils/message'

type StandardType = AgentCodeStandardConfigItem['standard_type']

const standardTypes: Array<{ label: string; value: StandardType }> = [
  { label: '页面代码规范', value: 'page' },
  { label: '组件代码规范', value: 'component' },
]

const queryClient = useQueryClient()
const selectedType = ref<StandardType>('page')
const codeStandardDrafts = reactive<Record<StandardType, string>>({ page: '', component: '' })
const saving = ref(false)

const agentConfigsQuery = useQuery({
  queryKey: ['agent-configs'],
  queryFn: listAgentConfigs,
})

const agentId = computed(() => agentConfigsQuery.data.value?.[0]?.id ?? '')

const codeStandardsQuery = useQuery({
  queryKey: computed(() => ['agent-code-standards', agentId.value]),
  queryFn: () => listAgentCodeStandards(agentId.value),
  enabled: computed(() => Boolean(agentId.value)),
})

const standards = computed(() => codeStandardsQuery.data.value ?? [])
const selectedStandard = computed(() => standards.value.find(s => s.standard_type === selectedType.value) ?? null)

const currentDraft = computed(() => codeStandardDrafts[selectedType.value] ?? '')
const currentDirty = computed(() => {
  if (!selectedStandard.value) return false
  return currentDraft.value.trim() !== (selectedStandard.value.content ?? '').trim()
})

const anyDirty = computed(() => (
  standards.value.some(item => (codeStandardDrafts[item.standard_type] ?? '').trim() !== (item.content ?? '').trim())
))

watch(
  standards,
  items => {
    for (const item of items) {
      codeStandardDrafts[item.standard_type] = item.content ?? ''
    }
  },
  { immediate: true },
)

function handleDraftInput(value: string) {
  codeStandardDrafts[selectedType.value] = value
}

async function handleChangeType(type: StandardType) {
  if (type === selectedType.value) return
  if (currentDirty.value) {
    const confirmed = await createConfirm(`当前${selectedType.value === 'page' ? '页面' : '组件'}规范有未保存修改，确定切换并丢弃吗？`, '放弃修改')
    if (!confirmed) return
    if (selectedStandard.value) {
      codeStandardDrafts[selectedType.value] = selectedStandard.value.content ?? ''
    }
  }
  selectedType.value = type
}

async function handleSave() {
  if (!agentId.value || !selectedStandard.value) return
  try {
    saving.value = true
    await updateAgentCodeStandard(agentId.value, selectedType.value, {
      content_override: currentDraft.value.trim() || null,
    })
    Message.success(`${selectedType.value === 'page' ? '页面' : '组件'}规范已保存`)
    await queryClient.invalidateQueries({ queryKey: ['agent-code-standards', agentId.value] })
  } catch (err) {
    Message.error(getErrorMessage(err, '保存代码规范失败'))
  } finally {
    saving.value = false
  }
}

async function handleRestore() {
  if (!agentId.value || !selectedStandard.value) return
  const confirmed = await createConfirm(`确定恢复为系统内置的${selectedType.value === 'page' ? '页面' : '组件'}默认规范吗？未保存内容将丢失。`, '恢复系统默认')
  if (!confirmed) return
  try {
    saving.value = true
    await updateAgentCodeStandard(agentId.value, selectedType.value, { restore_default: true })
    Message.success(`已恢复系统默认${selectedType.value === 'page' ? '页面' : '组件'}规范`)
    await queryClient.invalidateQueries({ queryKey: ['agent-code-standards', agentId.value] })
    codeStandardDrafts[selectedType.value] = selectedStandard.value.default_content ?? ''
  } catch (err) {
    Message.error(getErrorMessage(err, '恢复系统默认规范失败'))
  } finally {
    saving.value = false
  }
}

onBeforeRouteLeave(async () => {
  if (!anyDirty.value) return true
  return createConfirm('代码规范有未保存修改，确定离开并丢弃修改吗？', '放弃修改')
})
</script>

<style scoped>
:deep(.code-standard-textarea textarea) {
  line-height: 1.75;
}
</style>
