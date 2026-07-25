<!-- 文件功能：承载智能体工具确认 HITL 交互，展示待执行工具、可选 Diff 预览与允许/拒绝入口。 -->
<template>
  <AgentHitlShell
    :title="confirmTitle"
    :subtitle="confirmSubtitle"
    badge="HITL"
    :loading="loading"
    @ignore="emit('reject')"
    @submit="emit('confirm')"
  >
    <div class="rounded-ui-md border border-warning/20 bg-warning-muted px-2.5 py-2">
      <p class="text-sm font-semibold leading-5 text-warning">允许后继续执行</p>
      <p class="text-xs leading-5 text-text-secondary">确认后工具会继续执行，并可能写入后端数据。</p>
    </div>

    <div v-if="requirement.note" class="mt-2 rounded-ui-md border border-border bg-surface-hover px-2.5 py-2 text-xs leading-5 text-text-secondary">
      {{ requirement.note }}
    </div>

    <InspectorSection title="工具详情" class="mt-2 rounded-ui-md border border-border bg-surface-hover">
      <div class="space-y-2">
        <section v-if="requirement.suggested_patch" class="space-y-2">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <p class="text-xs font-semibold text-text-secondary">
              {{ requirement.suggested_patch.change_note || '页面改写建议' }}
            </p>
            <div v-if="canApplySuggestedPatch" class="flex items-center gap-1.5">
              <UiButton variant="ghost" size="sm" @click="emit('applySuggestedPatch', requirement.suggested_patch)">
                应用到编辑器
              </UiButton>
              <UiButton variant="ghost" size="sm" @click="emit('saveDraftPatch', requirement.suggested_patch)">
                加入草稿箱
              </UiButton>
            </div>
          </div>
          <pre class="max-h-40 overflow-auto overscroll-contain rounded-ui-md bg-text p-2 font-mono text-xs leading-5 text-text-inverse">{{ requirement.suggested_patch.unified_diff || requirement.suggested_patch.proposed_content }}</pre>
        </section>
        <section class="space-y-1">
          <p class="text-xs font-semibold text-text-secondary">工具参数</p>
          <pre class="max-h-36 overflow-auto overscroll-contain rounded-ui-md bg-text p-2 font-mono text-xs leading-5 text-text-inverse">{{ formattedToolArgs }}</pre>
        </section>
      </div>
    </InspectorSection>

    <template #footer-left>
      <UiButton
        v-if="forceReleaseAvailable"
        variant="danger"
        size="sm"
        :disabled="loading"
        @click="emit('forceRelease')"
      >
        强制释放
      </UiButton>
    </template>
  </AgentHitlShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import AgentHitlShell from '@/components/agent/AgentHitlShell.vue'
import InspectorSection from '@/components/patterns/InspectorSection.vue'
import { UiButton } from '@/components/ui'
import type { AgentPendingRequirement, AgentSuggestedPatch } from '@/types/api'

const props = withDefaults(defineProps<{
  requirement: AgentPendingRequirement
  loading?: boolean
  canApplySuggestedPatch?: boolean
  forceReleaseAvailable?: boolean
}>(), {
  loading: false,
  canApplySuggestedPatch: false,
  forceReleaseAvailable: false,
})

const emit = defineEmits<{
  confirm: []
  reject: []
  forceRelease: []
  applySuggestedPatch: [patch: AgentSuggestedPatch]
  saveDraftPatch: [patch: AgentSuggestedPatch]
}>()

const toolName = computed(() => props.requirement.tool_name || '未知工具')
const toolSourceName = computed(() => props.requirement.member_agent_name || '')
const confirmTitle = computed(() => `允许执行 ${toolSourceName.value ? `${toolSourceName.value} · ` : ''}${toolName.value} 吗？`)
const confirmSubtitle = computed(() => toolSourceName.value ? `来自 ${toolSourceName.value} 的工具正在等待你的确认。` : '该工具正在等待你的确认。')
const formattedToolArgs = computed(() => {
  const toolArgs = props.requirement.tool_execution?.['tool_args'] ?? props.requirement.tool_execution
  return JSON.stringify(toolArgs ?? {}, null, 2)
})
</script>
