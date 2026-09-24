/**
 * 文件功能：管理内容助手可选模型、推理强度与视觉能力展示。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { Globe2, UserRound } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'

import { listLlmConfigs, listLlmSlots } from '@/api/llm'
import type { DropdownMenuEntry } from '@/components/ui'
import type {
  AgentActiveRunItem,
  AgentDescriptor,
  AgentSessionItem,
  LlmConfigItem,
  LlmSlotBindingItem,
} from '@/types/api'
import { protocolReasoningControls, reasoningEfforts } from '@/utils/reasoning-controls'
import type { AgentReasoningPolicy } from '@/api/ai'

interface AgentSessionLlmMetadata {
  selection_kind?: 'explicit_config' | 'slot_binding'
  config_id?: number | string | null
  scope?: 'global' | 'personal' | string
  name?: string | null
  provider_config_id?: number | string | null
  provider_config_name?: string | null
  provider_key?: string | null
  provider_label?: string | null
  model_id?: string | null
  supports_image_input?: boolean | null
}

interface AgentModelSelectionContext {
  activeSessionId: Ref<string>
  activeSession: ComputedRef<AgentSessionItem | null>
  activeRun: ComputedRef<AgentActiveRunItem | null>
  selectedAgent: ComputedRef<AgentDescriptor | null>
  agentId: ComputedRef<string>
}

/** 返回下一轮 Run 的模型与推理选项；会话切换时重新采用该会话的固化模型。 */
export function useAgentModelSelection(context: AgentModelSelectionContext) {
  const selectedRunLlmConfigId = ref<number | null>(null)
  const selectedRunReasoning = ref<AgentReasoningPolicy>({ mode: 'auto' })
  const llmConfigsQuery = useQuery({
    queryKey: ['llm-configs', 'agent-conversation'],
    queryFn: listLlmConfigs,
  })
  const llmSlotsQuery = useQuery({
    queryKey: ['llm-slots', 'agent-conversation'],
    queryFn: listLlmSlots,
  })

  const isNewSessionDraft = computed(() => !context.activeSessionId.value)
  const activeLlmConfigs = computed<LlmConfigItem[]>(() => (
    (llmConfigsQuery.data.value ?? []).filter(item => (
      item.status === 'active'
      && (item.model_type ?? 'chat') === 'chat'
      && (item.scope === 'global' || item.scope === 'personal')
    ))
  ))
  const activeGlobalLlmConfigs = computed(() => activeLlmConfigs.value.filter(item => item.scope === 'global'))
  const activePersonalLlmConfigs = computed(() => activeLlmConfigs.value.filter(item => item.scope === 'personal'))
  const llmConfigById = computed(() => new Map(activeLlmConfigs.value.map(item => [item.id, item])))
  const llmModelDropdownItems = computed<DropdownMenuEntry[]>(() =>
    activeLlmConfigs.value.map(item => ({
      label: item.name,
      value: String(item.id),
      description: `${item.provider_label} / ${item.model_id}`,
      icon: item.scope === 'global' ? Globe2 : UserRound,
      active: item.id === selectedRunLlmConfigId.value,
    })),
  )
  const selectableModelCount = computed(() => activeLlmConfigs.value.length)
  const modelSelectionDisabled = computed(() => (
    llmConfigsQuery.isFetching.value
    || selectableModelCount.value === 0
    || Boolean(context.activeRun.value && !['completed', 'cancelled', 'failed'].includes(context.activeRun.value.status))
  ))
  const boundDraftLlmConfigId = computed(() => {
    const slot = context.selectedAgent.value?.llm_slot
    if (!slot) return null
    const binding = (llmSlotsQuery.data.value ?? []).find((item: LlmSlotBindingItem) => item.slot === slot)
    const configId = binding?.binding_ready ? binding.llm_config_id : null
    return configId && llmConfigById.value.has(configId) ? configId : null
  })
  const defaultNewSessionLlmConfigId = computed(() => (
    boundDraftLlmConfigId.value
    ?? activeGlobalLlmConfigs.value[0]?.id
    ?? activePersonalLlmConfigs.value[0]?.id
    ?? null
  ))
  const selectedRunLlmConfig = computed(() => (
    selectedRunLlmConfigId.value ? llmConfigById.value.get(selectedRunLlmConfigId.value) ?? null : null
  ))
  const selectedRunReasoningOptions = computed(() => selectedRunLlmConfig.value?.model_capability_json?.reasoning_options)
  const selectedRunProtocol = computed(() => String(selectedRunLlmConfig.value?.model_capability_json?.protocol_key ?? ''))
  const runReasoningEfforts = computed(() => {
    const capability = selectedRunLlmConfig.value?.model_capability_json ?? {}
    if (!capability.supports_reasoning || !protocolReasoningControls(selectedRunProtocol.value).has('effort')) return []
    return reasoningEfforts(selectedRunReasoningOptions.value).filter(value => value !== 'none')
  })
  const runReasoningDropdownItems = computed<DropdownMenuEntry[]>(() => [
    { label: '自动', value: 'auto', active: selectedRunReasoning.value.mode === 'auto' },
    ...runReasoningEfforts.value.map(value => ({
      label: value,
      value: `effort:${value}`,
      active: selectedRunReasoning.value.mode === 'effort' && selectedRunReasoning.value.value === value,
    })),
  ])
  const reasoningPolicyLabel = computed(() => (
    selectedRunReasoning.value.mode === 'effort' ? String(selectedRunReasoning.value.value || '') : '自动'
  ))
  const reasoningRestrictionText = computed(() => {
    const capability = selectedRunLlmConfig.value?.model_capability_json ?? {}
    if (!capability.supports_reasoning) return '当前模型未在 Models.dev 或能力覆盖中声明推理能力，因此只能使用自动模式。'
    if (!protocolReasoningControls(selectedRunProtocol.value).size) return '当前连接使用通用 OpenAI-compatible 协议，平台不知道其推理参数方言，因此只能使用自动模式。'
    return '当前模型没有公布可由该协议安全控制的推理参数，因此只能使用自动模式。'
  })
  const reasoningButtonTitle = computed(() => runReasoningEfforts.value.length
    ? `下一轮推理强度：${reasoningPolicyLabel.value}`
    : reasoningRestrictionText.value)
  const activeSessionLlmMetadata = computed(() => extractSessionLlmMetadata(context.activeSession.value))
  const activeSessionLlmConfigId = computed(() => normalizeLlmConfigId(activeSessionLlmMetadata.value?.config_id))
  const activeSessionLlmConfig = computed(() => (
    activeSessionLlmConfigId.value ? llmConfigById.value.get(activeSessionLlmConfigId.value) ?? null : null
  ))
  const activeSessionLlmLabel = computed(() => {
    if (!context.activeSession.value) return ''
    if (activeSessionLlmConfig.value) return formatLlmConfigLabel(activeSessionLlmConfig.value)
    if (activeSessionLlmMetadata.value) return formatLlmMetadataLabel(activeSessionLlmMetadata.value)
    return context.selectedAgent.value?.bound_llm_name || ''
  })
  const currentLlmModelLabel = computed(() => (
    selectedRunLlmConfig.value ? formatLlmConfigLabel(selectedRunLlmConfig.value) : activeSessionLlmLabel.value
  ))
  const currentLlmScope = computed(() => (
    selectedRunLlmConfig.value?.scope ?? activeSessionLlmConfig.value?.scope ?? activeSessionLlmMetadata.value?.scope ?? 'personal'
  ))
  const currentLlmCompactName = computed(() => (
    selectedRunLlmConfig.value?.name ?? activeSessionLlmConfig.value?.name ?? activeSessionLlmMetadata.value?.name ?? '选择模型'
  ))
  const llmModelButtonTitle = computed(() => {
    const label = currentLlmModelLabel.value || currentLlmCompactName.value
    return context.activeSessionId.value ? `下次运行模型：${label}` : `新会话模型：${label}`
  })
  const showVisualCapabilityStatus = computed(() => (
    context.agentId.value === 'agent-coordinator' && context.selectedAgent.value !== null
  ))
  const imageAnalysisAvailable = computed(() => Boolean(context.selectedAgent.value?.image_analysis_available))
  const imageGenerationAvailable = computed(() => Boolean(context.selectedAgent.value?.image_generation_available))
  const visualAttachmentCapabilityAvailable = computed(() => (
    imageAnalysisAvailable.value || imageGenerationAvailable.value
  ))
  const visualCapabilityConfigurationRequired = computed(() => (
    !imageAnalysisAvailable.value || !imageGenerationAvailable.value
  ))
  const imageAnalysisCapabilityTitle = computed(() => (
    imageAnalysisAvailable.value
      ? 'analyze_visuals 已配置，可按需分析附件、工作空间图片资源或页面截图'
      : context.selectedAgent.value?.image_analysis_unavailable_reason || 'analyze_visuals 未配置图片理解模型'
  ))
  const imageGenerationCapabilityTitle = computed(() => (
    imageGenerationAvailable.value
      ? 'generate_image 已配置，可生成或编辑图片并保存到资源库'
      : context.selectedAgent.value?.image_generation_unavailable_reason || 'generate_image 未配置图片生成模型'
  ))

  watch(
    () => [defaultNewSessionLlmConfigId.value, selectedRunLlmConfigId.value, context.activeSessionId.value] as const,
    () => {
      if (!isNewSessionDraft.value) return
      const selectedId = selectedRunLlmConfigId.value
      if (selectedId !== null && llmConfigById.value.has(selectedId)) return
      selectedRunLlmConfigId.value = defaultNewSessionLlmConfigId.value
    },
    { immediate: true },
  )
  watch(runReasoningEfforts, (efforts) => {
    if (selectedRunReasoning.value.mode === 'effort' && !efforts.includes(String(selectedRunReasoning.value.value ?? ''))) {
      selectedRunReasoning.value = { mode: 'auto' }
    }
  }, { immediate: true })
  watch(context.activeSessionId, () => {
    const sessionModelId = normalizeLlmConfigId(extractSessionLlmMetadata(context.activeSession.value)?.config_id)
    selectedRunLlmConfigId.value = sessionModelId && llmConfigById.value.has(sessionModelId)
      ? sessionModelId
      : defaultNewSessionLlmConfigId.value
    selectedRunReasoning.value = { mode: 'auto' }
  })
  watch(activeSessionLlmConfigId, (configId) => {
    if (!context.activeSessionId.value || !configId || !llmConfigById.value.has(configId)) return
    selectedRunLlmConfigId.value = configId
  })

  /** 设置下一次 Run 的模型，并重置推理策略。 */
  function handleLlmModelSelect(value: string): void {
    const configId = Number(value)
    if (Number.isFinite(configId)) {
      selectedRunLlmConfigId.value = configId
      selectedRunReasoning.value = { mode: 'auto' }
    }
  }

  /** 仅允许选择当前模型和协议共同支持的推理强度。 */
  function handleRunReasoningSelect(value: string): void {
    const effort = value.startsWith('effort:') ? value.slice('effort:'.length) : ''
    selectedRunReasoning.value = effort && runReasoningEfforts.value.includes(effort)
      ? { mode: 'effort', value: effort }
      : { mode: 'auto' }
  }

  return {
    llmConfigsQuery,
    llmSlotsQuery,
    selectedRunLlmConfigId,
    selectedRunReasoning,
    isNewSessionDraft,
    llmModelDropdownItems,
    selectableModelCount,
    modelSelectionDisabled,
    selectedRunLlmConfig,
    activeSessionLlmLabel,
    currentLlmModelLabel,
    currentLlmScope,
    currentLlmCompactName,
    llmModelButtonTitle,
    runReasoningEfforts,
    runReasoningDropdownItems,
    reasoningPolicyLabel,
    reasoningRestrictionText,
    reasoningButtonTitle,
    showVisualCapabilityStatus,
    imageAnalysisAvailable,
    imageGenerationAvailable,
    visualAttachmentCapabilityAvailable,
    visualCapabilityConfigurationRequired,
    imageAnalysisCapabilityTitle,
    imageGenerationCapabilityTitle,
    handleLlmModelSelect,
    handleRunReasoningSelect,
  }
}

/** 从会话 metadata 读取模型快照，兼容旧会话。 */
function extractSessionLlmMetadata(session: AgentSessionItem | null): AgentSessionLlmMetadata | null {
  const metadata = session?.metadata
  if (!metadata || typeof metadata !== 'object') return null
  const llm = (metadata as Record<string, unknown>).llm
  return llm && typeof llm === 'object' ? llm as AgentSessionLlmMetadata : null
}

/** 兼容服务端以字符串回传的配置 ID。 */
function normalizeLlmConfigId(value: AgentSessionLlmMetadata['config_id'] | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && /^\d+$/.test(value.trim())) return Number(value.trim())
  return null
}

/** 显示可选模型的作用域与供应商。 */
function formatLlmConfigLabel(config: LlmConfigItem): string {
  const scopeLabel = config.scope === 'global' ? '全局模型' : '我的模型'
  return `${scopeLabel} · ${config.name}（${config.provider_config_name || config.provider_label} / ${config.model_id}）`
}

/** 用会话快照展示已归档或删除的历史模型。 */
function formatLlmMetadataLabel(metadata: AgentSessionLlmMetadata): string {
  const scopeLabel = metadata.scope === 'global' ? '全局模型' : metadata.scope === 'personal' ? '我的模型' : '模型'
  const name = metadata.name || '已选模型'
  const provider = metadata.provider_config_name || metadata.provider_label || metadata.provider_key || ''
  const modelId = metadata.model_id || ''
  const detail = [provider, modelId].filter(Boolean).join(' / ')
  return detail ? `${scopeLabel} · ${name}（${detail}）` : `${scopeLabel} · ${name}`
}
