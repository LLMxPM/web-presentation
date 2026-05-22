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
    <div class="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2">
      <p class="text-xs font-semibold leading-5 text-amber-900">1. 是，允许执行</p>
      <p class="text-[11px] leading-5 text-amber-700">提交后工具会继续执行并写入后端。</p>
    </div>

    <div v-if="requirement.note" class="mt-2 rounded-md border border-amber-100 bg-white px-2.5 py-2 text-xs leading-5 text-amber-800">
      {{ requirement.note }}
    </div>

    <details class="mt-2 rounded-md border border-slate-200 bg-slate-50">
      <summary class="cursor-pointer px-2.5 py-2 text-xs font-semibold text-slate-600">查看工具详情</summary>
      <div class="space-y-2 border-t border-slate-200 p-2.5">
        <section v-if="requirement.suggested_patch" class="space-y-2">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <p class="text-xs font-semibold text-slate-700">
              {{ requirement.suggested_patch.change_note || '页面改写建议' }}
            </p>
            <div v-if="canApplySuggestedPatch" class="flex items-center gap-1.5">
              <BaseButton variant="ghost" size="sm" custom-class="rounded-md px-2 py-1 text-xs shadow-none" @click="emit('applySuggestedPatch', requirement.suggested_patch)">
                应用到编辑器
              </BaseButton>
              <BaseButton variant="ghost" size="sm" custom-class="rounded-md px-2 py-1 text-xs shadow-none" @click="emit('saveDraftPatch', requirement.suggested_patch)">
                加入草稿箱
              </BaseButton>
            </div>
          </div>
          <pre class="max-h-40 overflow-auto rounded-md bg-slate-950 p-2 text-[11px] leading-5 text-slate-100">{{ requirement.suggested_patch.unified_diff || requirement.suggested_patch.proposed_content }}</pre>
        </section>
        <section class="space-y-1">
          <p class="text-xs font-semibold text-slate-700">工具参数</p>
          <pre class="max-h-36 overflow-auto rounded-md bg-slate-950 p-2 text-[11px] leading-5 text-slate-100">{{ formattedToolArgs }}</pre>
        </section>
      </div>
    </details>
  </AgentHitlShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import AgentHitlShell from '@/components/agent/AgentHitlShell.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import type { AgentPendingRequirement, AgentSuggestedPatch } from '@/types/api'

const props = withDefaults(defineProps<{
  requirement: AgentPendingRequirement
  loading?: boolean
  canApplySuggestedPatch?: boolean
}>(), {
  loading: false,
  canApplySuggestedPatch: false,
})

const emit = defineEmits<{
  confirm: []
  reject: []
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
