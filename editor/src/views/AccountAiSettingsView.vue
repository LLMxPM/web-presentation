<!-- 文件功能：整合账号级 AI 设置管理后台，调度内容助手、模型与供应商配置。 -->
<template>
  <AccountAiSettingsWorkbench
    :section="adminSection"
    :assistant-tab="assistantSettingsTab"
    :agent="selectedAgentConfig"
    :models="configsQuery.data.value ?? []"
    :provider-configs="providerConfigsQuery.data.value ?? []"
    :provider-catalog="providersQuery.data.value ?? []"
    :slots="slotsQuery.data.value ?? []"
    :slot-drafts="slotDrafts"
    :binding-slot="bindingSlot"
    :prompt-draft="promptDraft"
    :prompt-dirty="promptDirty"
    :saving-prompt="savingPrompt"
    :tool-drafts="toolDrafts"
    :saving-tool-key="savingToolKey"
    :selected-tool="selectedTool"
    :tool-dialog-open="toolDialogOpen"
    :provider-dialog-open="providerDialogOpen"
    :provider-mode="providerPanelMode"
    :provider-form="providerForm"
    :selected-provider-config-id="selectedProviderConfigId"
    :selected-provider-config="selectedProviderConfig"
    :current-provider-for-provider-form="currentProviderForProviderForm"
    :provider-options="providerOptions"
    :saving-provider-config="savingProviderConfig"
    :deleting-provider-config-id="deletingProviderConfigId"
    :can-create-global="canCreateGlobal"
    :model-dialog-open="modelDialogOpen"
    :model-mode="modelPanelMode"
    :model-form="modelForm"
    :selected-config-id="selectedConfigId"
    :selected-model="selectedModel"
    :current-provider="currentProvider"
    :resolved-capability="resolvedCapability"
    :provider-config-options="providerConfigOptions"
    :advanced-config-text="advancedConfigText"
    :advanced-config-error="advancedConfigError"
    :advanced-config-collapsed="advancedConfigCollapsed"
    :saving-config="savingConfig"
    :deleting-config-id="deletingConfigId"
    @change-section="handleAdminSectionChange"
    @change-assistant-tab="handleAssistantTabChange"
    @update-slot-draft="(slot, value) => slotDrafts[slot] = value"
    @save-slot="handleSaveSlot"
    @update-prompt="promptDraft = $event"
    @save-prompt="handleSavePrompt"
    @restore-prompt="handleRestorePrompt"
    @open-tool="openToolDialog"
    @update-tool-dialog-open="handleToolDialogVisibility"
    @update-tool-enabled="(key, value) => toolDrafts[key].enabled = value"
    @update-tool-description="(key, value) => toolDrafts[key].descriptionOverride = value"
    @update-tool-instructions="(key, value) => toolDrafts[key].instructionsOverride = value"
    @save-tool="handleSaveTool"
    @restore-tool="handleRestoreTool"
    @create-provider="openProviderCreateDialog"
    @view-provider="openProviderDetailDialog"
    @edit-provider="openProviderEditDialog"
    @delete-provider="handleDeleteProviderConfig"
    @update-provider-dialog-open="handleProviderDialogVisibility"
    @cancel-provider="handleCancelProviderDialogEdit"
    @start-edit-provider="handleStartEditProviderConfig"
    @submit-provider="handleSubmitProviderConfig"
    @create-model="openModelCreateDialog"
    @view-model="openModelDetailDialog"
    @edit-model="openModelEditDialog"
    @delete-model="handleDeleteModel"
    @update-model-dialog-open="handleModelDialogVisibility"
    @cancel-model="handleCancelModelDialogEdit"
    @start-edit-model="handleStartEditModel"
    @submit-model="handleSubmitModel"
    @format-advanced="formatAdvancedConfig"
    @update-advanced-config-text="advancedConfigText = $event"
    @update-advanced-config-collapsed="advancedConfigCollapsed = $event"
  />
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import {
  createLlmConfig,
  createLlmProviderConfig,
  deleteLlmConfig,
  deleteLlmProviderConfig,
  listLlmConfigs,
  listLlmProviderConfigs,
  listLlmProviders,
  resolveLlmModelCapability,
  listLlmSlots,
  updateLlmConfig,
  updateLlmProviderConfig,
  updateLlmSlotBinding,
} from '@/api/llm'
import type { LlmConfigUpdatePayload, LlmProviderConfigUpdatePayload } from '@/api/llm'
import {
  listAgentConfigs,
  updateAgentConfig,
  updateAgentToolConfig,
} from '@/api/agent-config'
import { getErrorMessage } from '@/api/http'
import AccountAiSettingsWorkbench from '@/components/account-ai/AccountAiSettingsWorkbench.vue'
import type { AiSettingsSection, AssistantSettingsTab } from '@/components/account-ai/account-ai-settings-types'
import type { SelectOption } from '@/components/ui/select'
import { useAuthStore } from '@/stores/auth'
import type {
  AiLlmConfigScope,
  AiModelType,
  AiReasoningLevel,
  AiReasoningMode,
  AgentConfigItem,
  AgentToolConfigItem,
  LlmConfigItem,
  LlmModelCapabilityItem,
  LlmProviderCatalogItem,
  LlmProviderConfigItem,
} from '@/types/api'
import { Message, createConfirm } from '@/utils/message'

type ActiveSection = 'agents' | 'providers' | 'models'
type ActiveAgentPanel = 'binding' | 'prompts' | 'tools'
type ConfigPanelMode = 'create' | 'detail' | 'edit'

const DEFAULT_CONTEXT_WINDOW_TOKENS = 200000
const DEFAULT_NEW_MODEL_PROVIDER_KEY = 'deepseek'

interface LlmFormState {
  scope: AiLlmConfigScope
  name: string
  provider_config_id: number | null
  model_id: string
  model_type: AiModelType
  reasoning_mode: AiReasoningMode
  reasoning_level: AiReasoningLevel | null
  supports_image_input: boolean
  context_window_tokens: number
}

interface LlmProviderFormState {
  scope: AiLlmConfigScope
  name: string
  provider_key: string | null
  base_url: string
  api_key: string
}

interface ToolDraft {
  enabled: boolean
  descriptionOverride: string
  instructionsOverride: string
}

const queryClient = useQueryClient()
const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const activeSection = ref<ActiveSection>('agents')
const activeAgentPanel = ref<ActiveAgentPanel>('binding')

const selectedAgentId = ref('')
const promptDraft = ref('')
const savingPrompt = ref(false)
const savingToolKey = ref<string | null>(null)
const editingToolKey = ref<string | null>(null)
const toolDrafts = reactive<Record<string, ToolDraft>>({})
const slotDrafts = reactive<Record<string, number | null>>({})
const bindingSlot = ref<string | null>(null)
const toolDialogOpen = ref(false)

const selectedProviderConfigId = ref<number | null>(null)
const providerPanelMode = ref<ConfigPanelMode>('create')
const providerCreateRequested = ref(false)
const savingProviderConfig = ref(false)
const deletingProviderConfigId = ref<number | null>(null)
const applyingExistingProviderConfig = ref(false)
const providerDialogOpen = ref(false)
const providerDialogBaseline = ref('')

const selectedConfigId = ref<number | null>(null)
const modelPanelMode = ref<ConfigPanelMode>('create')
const modelCreateRequested = ref(false)
const advancedConfigText = ref('{}')
const advancedConfigError = ref('')
const advancedConfigCollapsed = ref(true)
const savingConfig = ref(false)
const deletingConfigId = ref<number | null>(null)
const applyingExistingModel = ref(false)
const modelDialogOpen = ref(false)
const modelDialogBaseline = ref('')

const modelForm = reactive<LlmFormState>({
  scope: 'personal',
  name: '',
  provider_config_id: null,
  model_id: '',
  model_type: 'chat',
  reasoning_mode: 'auto',
  reasoning_level: null,
  supports_image_input: false,
  context_window_tokens: DEFAULT_CONTEXT_WINDOW_TOKENS,
})

const resolvedCapability = ref<LlmModelCapabilityItem | null>(null)
let capabilityRequestSequence = 0

const providerForm = reactive<LlmProviderFormState>({
  scope: 'personal',
  name: '',
  provider_key: null,
  base_url: '',
  api_key: '',
})

const providersQuery = useQuery({
  queryKey: ['llm-providers'],
  queryFn: listLlmProviders,
})

const configsQuery = useQuery({
  queryKey: ['llm-configs'],
  queryFn: listLlmConfigs,
})

const providerConfigsQuery = useQuery({
  queryKey: ['llm-provider-configs'],
  queryFn: listLlmProviderConfigs,
})

const slotsQuery = useQuery({
  queryKey: ['llm-slots'],
  queryFn: listLlmSlots,
})

const agentConfigsQuery = useQuery({
  queryKey: ['agent-configs'],
  queryFn: listAgentConfigs,
})

const canCreateGlobal = computed(() => authStore.user?.role === 'platform_admin')

const selectedAgentConfig = computed<AgentConfigItem | null>(() => (
  agentConfigsQuery.data.value?.find(item => item.id === selectedAgentId.value)
  ?? agentConfigsQuery.data.value?.[0]
  ?? null
))

const adminSection = computed<AiSettingsSection>(() => activeSection.value === 'agents' ? 'assistant' : activeSection.value)
const assistantSettingsTab = computed<AssistantSettingsTab>(() => {
  if (activeAgentPanel.value === 'binding') return 'models'
  if (activeAgentPanel.value === 'prompts') return 'prompt'
  return 'tools'
})

const selectedTool = computed<AgentToolConfigItem | null>(() => (
  selectedAgentConfig.value?.tool_groups
    .flatMap(group => group.tools)
    .find(tool => tool.key === editingToolKey.value) ?? null
))

const selectedModel = computed<LlmConfigItem | null>(() => (
  configsQuery.data.value?.find(item => item.id === selectedConfigId.value) ?? null
))

const selectedProviderConfig = computed<LlmProviderConfigItem | null>(() => (
  providerConfigsQuery.data.value?.find(item => item.id === selectedProviderConfigId.value) ?? null
))

const providerDialogDirty = computed(() => providerDialogOpen.value && providerPanelMode.value !== 'detail' && providerDialogBaseline.value !== serializeProviderForm())
const modelDialogDirty = computed(() => modelDialogOpen.value && modelPanelMode.value !== 'detail' && modelDialogBaseline.value !== serializeModelForm())

const selectedModelProviderConfig = computed<LlmProviderConfigItem | null>(() => (
  providerConfigsQuery.data.value?.find(item => item.id === modelForm.provider_config_id) ?? null
))

const promptDirty = computed(() => {
  if (!selectedAgentConfig.value) return false
  return promptDraft.value.trim() !== selectedAgentConfig.value.effective_prompt.trim()
})

const slotDraftDirty = computed(() => (slotsQuery.data.value ?? []).some(slot => (
  (slotDrafts[slot.slot] ?? null) !== (slot.llm_config_id ?? null)
)))

const dirtyToolCount = computed(() => (
  selectedAgentConfig.value?.tool_groups.reduce(
    (total, group) => total + group.tools.filter(tool => isToolDirty(tool)).length,
    0,
  ) ?? 0
))

const assistantDirty = computed(() => promptDirty.value || dirtyToolCount.value > 0 || slotDraftDirty.value)


const providerOptions = computed<SelectOption[]>(() => (
  providersQuery.data.value?.map(provider => ({
    label: `${getCatalogProviderType(provider) === 'image_generation' ? '图片生成' : 'Chat'} · ${provider.label}`,
    value: provider.provider_key,
    description: getCatalogProviderType(provider) === 'image_generation'
      ? `图片生成供应商${provider.default_image_generation_model_id ? ` · ${provider.default_image_generation_model_id}` : ''}`
      : provider.supports_thinking
      ? `支持 thinking · ${provider.thinking_mode}${provider.default_model_id ? ` · ${provider.default_model_id}` : ''}`
      : '不支持 thinking',
    keywords: [provider.provider_key, provider.provider_adapter],
  })) ?? []
))

const currentProvider = computed<LlmProviderCatalogItem | null>(() => (
  providersQuery.data.value?.find(provider => provider.provider_key === selectedModelProviderConfig.value?.provider_key) ?? null
))

watch(
  () => modelForm.model_type,
  (modelType, previousType) => {
    if (modelType === previousType) return
    const selectedConfig = selectedModelProviderConfig.value
    if (selectedConfig && getProviderConfigType(selectedConfig) !== modelType) {
      const nextConfig = findDefaultProviderConfigForScope(modelForm.scope, modelType)
      modelForm.provider_config_id = nextConfig?.id ?? null
    }
    const provider = findProviderForConfig(selectedModelProviderConfig.value)
    modelForm.model_id = modelType === 'image_generation'
      ? provider?.default_image_generation_model_id ?? ''
      : provider?.default_model_id ?? ''
    if (modelType === 'image_generation') {
      modelForm.reasoning_mode = 'auto'
      modelForm.reasoning_level = null
      modelForm.supports_image_input = false
    }
  },
)

const currentProviderForProviderForm = computed<LlmProviderCatalogItem | null>(() => (
  providersQuery.data.value?.find(provider => provider.provider_key === providerForm.provider_key) ?? null
))

const providerConfigOptions = computed<SelectOption[]>(() => (
  (providerConfigsQuery.data.value ?? [])
    .filter(config => config.scope === modelForm.scope)
    .filter(config => getProviderConfigType(config) === modelForm.model_type)
    .filter(config => config.status === 'active' || config.id === modelForm.provider_config_id)
    .map(config => ({
      label: config.name,
      value: config.id,
      description: `${config.scope === 'global' ? '全局供应商' : '个人供应商'} · ${config.provider_label}${config.status === 'active' ? '' : ' · 不可用'}`,
      keywords: [config.provider_key, config.provider_label, config.base_url ?? ''],
    }))
))


watch(
  () => agentConfigsQuery.data.value,
  (items) => {
    if (!items?.length) {
      selectedAgentId.value = ''
      return
    }
    if (!items.some(item => item.id === selectedAgentId.value)) {
      selectedAgentId.value = items[0].id
    }
  },
  { immediate: true },
)

watch(
  () => [modelForm.provider_config_id, modelForm.model_id, modelForm.model_type] as const,
  async ([providerConfigId, modelId, modelType]) => {
    const sequence = ++capabilityRequestSequence
    const shouldApplyResolvedDefaults = !applyingExistingModel.value
    if (modelType !== 'chat' || !providerConfigId || !modelId.trim()) {
      resolvedCapability.value = null
      return
    }
    try {
      const capability = await resolveLlmModelCapability(providerConfigId, modelId.trim())
      if (sequence !== capabilityRequestSequence) return
      resolvedCapability.value = capability
      if (shouldApplyResolvedDefaults) {
        modelForm.context_window_tokens = capability.context_window_tokens
        modelForm.supports_image_input = capability.supports_image_input
        syncResolvedCapabilityIntoBaseline(capability)
      }
      if (!capability.supports_reasoning) {
        modelForm.reasoning_mode = 'auto'
        modelForm.reasoning_level = null
      } else if (modelForm.reasoning_mode === 'disabled' && !capability.supports_explicit_disable) {
        modelForm.reasoning_mode = 'auto'
      }
    } catch {
      if (sequence === capabilityRequestSequence) resolvedCapability.value = null
    }
  },
  { immediate: true },
)

watch(
  selectedAgentConfig,
  (config) => {
    if (!config) return
    promptDraft.value = config.effective_prompt
    editingToolKey.value = null
    resetToolDrafts(config)
  },
  { immediate: true },
)

watch(
  () => [route.query.section, route.query.tab] as const,
  ([section, tab]) => {
    activeSection.value = resolveLegacySection(section)
    activeAgentPanel.value = resolveAssistantPanel(tab)
    const normalizedSection = adminSection.value
    const normalizedTab = assistantSettingsTab.value
    const queryIsValid = section === normalizedSection
      && (normalizedSection === 'assistant' ? tab === normalizedTab : tab === undefined)
    if (!queryIsValid) {
      void replaceNavigationQuery(normalizedSection, normalizedTab)
    }
  },
  { immediate: true },
)

watch(
  () => slotsQuery.data.value,
  (slots) => {
    for (const slot of slots ?? []) {
      slotDrafts[slot.slot] = slot.llm_config_id
    }
  },
  { immediate: true },
)

watch(
  () => providersQuery.data.value,
  (providers) => {
    if (!providerForm.provider_key && providers?.length) {
      const provider = findDefaultNewModelProvider(providers)
      providerForm.provider_key = provider.provider_key
      prefillProviderFormFromProvider(provider)
    }
  },
  { immediate: true },
)

watch(
  () => configsQuery.data.value,
  () => {
    if (activeSection.value === 'models') {
      openDefaultModelDetail()
    }
  },
  { immediate: true },
)

watch(
  () => providerConfigsQuery.data.value,
  () => {
    if (activeSection.value === 'providers') {
      openDefaultProviderDetail()
    }
  },
  { immediate: true },
)

watch(
  () => [providerConfigsQuery.data.value, modelForm.scope] as const,
  () => {
    if (selectedConfigId.value || modelForm.provider_config_id) {
      return
    }
    const option = providerConfigOptions.value.find(item => !item.disabled)
    const providerConfig = typeof option?.value === 'number'
      ? providerConfigsQuery.data.value?.find(item => item.id === option.value) ?? null
      : null
    modelForm.provider_config_id = providerConfig?.id ?? null
    prefillModelFormFromProvider(findProviderForConfig(providerConfig))
  },
  { immediate: true },
)

watch(
  () => modelForm.scope,
  (scope, previousScope) => {
    if (selectedConfigId.value || scope === previousScope) {
      return
    }
    const providerConfig = findDefaultProviderConfigForScope(scope)
    modelForm.provider_config_id = providerConfig?.id ?? null
    prefillModelFormFromProvider(findProviderForConfig(providerConfig))
  },
)

watch(
  () => providerForm.provider_key,
  (providerKey, previousProviderKey) => {
    const provider = providersQuery.data.value?.find(item => item.provider_key === providerKey) ?? null
    if (!provider || applyingExistingProviderConfig.value) {
      return
    }
    if (providerKey !== previousProviderKey && (!providerForm.base_url || providerForm.base_url === findProviderDefaultBaseUrl(previousProviderKey))) {
      providerForm.base_url = provider.supports_base_url ? provider.default_base_url ?? '' : ''
    }
    if (!provider.supports_api_key) {
      providerForm.api_key = ''
    }
  },
)

watch(
  () => modelForm.provider_config_id,
  (providerConfigId, previousProviderConfigId) => {
    const providerConfig = providerConfigsQuery.data.value?.find(item => item.id === providerConfigId) ?? null
    const previousProviderConfig = providerConfigsQuery.data.value?.find(item => item.id === previousProviderConfigId) ?? null
    const provider = providersQuery.data.value?.find(item => item.provider_key === providerConfig?.provider_key) ?? null
    const previousProviderKey = previousProviderConfig?.provider_key
    if (!provider || applyingExistingModel.value) {
      return
    }
    if (providerConfigId !== previousProviderConfigId && (!modelForm.model_id || modelForm.model_id === findProviderDefaultModelId(previousProviderKey))) {
      modelForm.model_id = modelForm.model_type === 'image_generation'
        ? provider.default_image_generation_model_id ?? ''
        : provider.default_model_id ?? ''
    }
    if (!provider.supports_thinking) {
      modelForm.reasoning_mode = 'auto'
      modelForm.reasoning_level = null
    } else if (providerConfigId !== previousProviderConfigId && !applyingExistingModel.value) {
      modelForm.reasoning_mode = 'auto'
      modelForm.reasoning_level = null
    }
    if (
      providerConfigId !== previousProviderConfigId
      && modelForm.supports_image_input === findProviderDefaultSupportsImageInput(previousProviderKey)
    ) {
      modelForm.supports_image_input = provider.default_supports_image_input
    }
    if (
      providerConfigId !== previousProviderConfigId
      && shouldReplaceContextWindowDefault(modelForm.context_window_tokens, previousProviderKey)
    ) {
      modelForm.context_window_tokens = DEFAULT_CONTEXT_WINDOW_TOKENS
    }
    if (advancedConfigText.value.trim() === '{}' && Object.keys(provider.advanced_json_hint ?? {}).length > 0) {
      advancedConfigText.value = JSON.stringify(provider.advanced_json_hint, null, 2)
    }
  },
)

/** 选择新建模型的默认供应商；DeepSeek 不可用时回退到目录首项。 */
function findDefaultNewModelProvider(providers: LlmProviderCatalogItem[]) {
  return providers.find(provider => provider.provider_key === DEFAULT_NEW_MODEL_PROVIDER_KEY) ?? providers[0]
}

/** 使用供应商目录默认值预填新建表单，不影响已有模型装载。 */
function prefillModelFormFromProvider(provider: LlmProviderCatalogItem | null) {
  modelForm.model_id = modelForm.model_type === 'image_generation'
    ? provider?.default_image_generation_model_id ?? ''
    : provider?.default_model_id ?? ''
  modelForm.reasoning_mode = 'auto'
  modelForm.reasoning_level = null
  modelForm.supports_image_input = Boolean(provider?.default_supports_image_input)
  modelForm.context_window_tokens = DEFAULT_CONTEXT_WINDOW_TOKENS
}

/** 使用供应商目录默认值预填供应商配置表单。 */
function prefillProviderFormFromProvider(provider: LlmProviderCatalogItem | null) {
  providerForm.base_url = provider?.supports_base_url ? provider.default_base_url ?? '' : ''
  if (!provider?.supports_api_key) {
    providerForm.api_key = ''
  }
}

/** 将路由查询参数解析为旧页面内部使用的一级分区。 */
function resolveLegacySection(value: unknown): ActiveSection {
  if (value === 'models' || value === 'providers') return value
  return 'agents'
}

/** 将公开的助手 Tab 参数解析为旧页面内部面板标识。 */
function resolveAssistantPanel(value: unknown): ActiveAgentPanel {
  if (value === 'prompt') return 'prompts'
  if (value === 'tools') return 'tools'
  return 'binding'
}

/** 写入可刷新恢复的管理后台导航状态，不新增子路由。 */
async function replaceNavigationQuery(section: AiSettingsSection, tab: AssistantSettingsTab = assistantSettingsTab.value) {
  const query: Record<string, string | string[] | null | undefined> = { ...route.query, section }
  if (section === 'assistant') query.tab = tab
  else delete query.tab
  await router.replace({ query })
}

/** 丢弃内容助手所有未保存草稿，并恢复服务端有效值。 */
function discardAssistantDrafts() {
  const config = selectedAgentConfig.value
  if (config) {
    promptDraft.value = config.effective_prompt
    resetToolDrafts(config)
  }
  for (const slot of slotsQuery.data.value ?? []) {
    slotDrafts[slot.slot] = slot.llm_config_id
  }
}

/** 在离开含未保存草稿的助手区域前请求确认。 */
async function confirmDiscardAssistantDrafts(): Promise<boolean> {
  if (!assistantDirty.value) return true
  const confirmed = await createConfirm('当前内容助手配置有未保存修改，确定放弃吗？', '放弃未保存修改')
  if (confirmed) discardAssistantDrafts()
  return confirmed
}

/** 切换一级管理模块，并同步 URL 查询参数。 */
async function handleAdminSectionChange(section: AiSettingsSection) {
  if (section === adminSection.value) return
  if (adminSection.value === 'assistant' && !(await confirmDiscardAssistantDrafts())) return
  activeSection.value = section === 'assistant' ? 'agents' : section
  await replaceNavigationQuery(section)
}

/** 切换内容助手的二级配置面板，并保护未保存草稿。 */
async function handleAssistantTabChange(tab: AssistantSettingsTab) {
  if (tab === assistantSettingsTab.value) return
  const previousPanel = activeAgentPanel.value
  activeAgentPanel.value = resolveAssistantPanel(tab)
  if (!(await confirmDiscardAssistantDrafts())) {
    activeAgentPanel.value = previousPanel
    return
  }
  await replaceNavigationQuery('assistant', tab)
}

/** 序列化供应商表单，供弹窗脏状态判断。 */
function serializeProviderForm(): string {
  return JSON.stringify(providerForm)
}

/** 序列化模型表单及高级参数，供弹窗脏状态判断。 */
function serializeModelForm(): string {
  return JSON.stringify({ ...modelForm, advancedConfigText: advancedConfigText.value })
}

/** 只同步异步解析出的能力默认值，避免把用户输入误记为弹窗初始状态。 */
function syncResolvedCapabilityIntoBaseline(capability: LlmModelCapabilityItem) {
  if (!modelDialogBaseline.value) return
  try {
    const baseline = JSON.parse(modelDialogBaseline.value) as Record<string, unknown>
    baseline.context_window_tokens = capability.context_window_tokens
    baseline.supports_image_input = capability.supports_image_input
    modelDialogBaseline.value = JSON.stringify(baseline)
  } catch {
    // 基线只由本模块生成；解析异常时保留原值，让关闭保护继续按更安全的脏状态处理。
  }
}

/** 打开供应商新建弹窗并记录初始表单快照。 */
async function openProviderCreateDialog() {
  resetProviderForm()
  await nextTick()
  providerDialogBaseline.value = serializeProviderForm()
  providerDialogOpen.value = true
}

/** 打开供应商只读详情弹窗。 */
async function openProviderDetailDialog(config: LlmProviderConfigItem) {
  await handleEditProviderConfig(config)
  providerDialogBaseline.value = serializeProviderForm()
  providerDialogOpen.value = true
}

/** 直接打开供应商编辑弹窗。 */
async function openProviderEditDialog(config: LlmProviderConfigItem) {
  await handleEditProviderConfig(config)
  providerDialogBaseline.value = serializeProviderForm()
  handleStartEditProviderConfig()
  providerDialogOpen.value = true
}

/** 处理供应商弹窗关闭请求，避免静默丢弃输入。 */
async function handleProviderDialogVisibility(open: boolean) {
  if (open) {
    providerDialogOpen.value = true
    return
  }
  if (providerDialogDirty.value && !(await createConfirm('当前供应商配置有未保存修改，确定关闭吗？', '放弃未保存修改'))) return
  providerDialogOpen.value = false
}

/** 取消供应商编辑前检查表单修改，并恢复服务端详情。 */
async function handleCancelProviderDialogEdit() {
  if (providerDialogDirty.value && !(await createConfirm('当前供应商配置有未保存修改，确定取消编辑吗？', '取消编辑'))) return
  handleCancelProviderEdit()
}

/** 打开模型新建弹窗并记录初始表单快照。 */
async function openModelCreateDialog() {
  resetModelForm()
  await nextTick()
  modelDialogBaseline.value = serializeModelForm()
  modelDialogOpen.value = true
}

/** 打开模型只读详情弹窗。 */
async function openModelDetailDialog(config: LlmConfigItem) {
  await handleEditModel(config)
  modelDialogBaseline.value = serializeModelForm()
  modelDialogOpen.value = true
}

/** 直接打开模型编辑弹窗。 */
async function openModelEditDialog(config: LlmConfigItem) {
  await handleEditModel(config)
  modelDialogBaseline.value = serializeModelForm()
  handleStartEditModel()
  modelDialogOpen.value = true
}

/** 处理模型弹窗关闭请求，避免静默丢弃输入。 */
async function handleModelDialogVisibility(open: boolean) {
  if (open) {
    modelDialogOpen.value = true
    return
  }
  if (modelDialogDirty.value && !(await createConfirm('当前模型配置有未保存修改，确定关闭吗？', '放弃未保存修改'))) return
  modelDialogOpen.value = false
}

/** 取消模型编辑前检查表单修改，并恢复服务端详情。 */
async function handleCancelModelDialogEdit() {
  if (modelDialogDirty.value && !(await createConfirm('当前模型配置有未保存修改，确定取消编辑吗？', '取消编辑'))) return
  handleCancelModelEdit()
}

/** 打开单个工具配置弹窗。 */
function openToolDialog(tool: AgentToolConfigItem) {
  editingToolKey.value = tool.key
  toolDialogOpen.value = true
}

/** 处理工具弹窗关闭请求，并仅恢复当前工具的未保存草稿。 */
async function handleToolDialogVisibility(open: boolean) {
  if (open) {
    toolDialogOpen.value = true
    return
  }
  const tool = selectedTool.value
  if (tool && isToolDirty(tool)) {
    const confirmed = await createConfirm('当前工具配置有未保存修改，确定关闭吗？', '放弃未保存修改')
    if (!confirmed) return
    toolDrafts[tool.key] = {
      enabled: tool.enabled,
      descriptionOverride: tool.description_override ?? '',
      instructionsOverride: tool.instructions_override ?? '',
    }
  }
  toolDialogOpen.value = false
  editingToolKey.value = null
}

/** 浏览器刷新或关闭前提示尚未保存的配置。 */
function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!assistantDirty.value && !providerDialogDirty.value && !modelDialogDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(async () => {
  if (!(await confirmDiscardAssistantDrafts())) return false
  if (providerDialogDirty.value || modelDialogDirty.value) {
    return await createConfirm('当前配置弹窗有未保存修改，确定离开 AI 设置吗？', '离开 AI 设置')
  }
  return true
})

onMounted(() => window.addEventListener('beforeunload', handleBeforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload))

/** 进入供应商分区时优先展示已有供应商详情，避免把新建表单作为默认落点。 */
function openDefaultProviderDetail() {
  if (selectedProviderConfigId.value || providerCreateRequested.value) {
    return
  }
  const firstProviderConfig = providerConfigsQuery.data.value?.[0]
  if (!firstProviderConfig) {
    return
  }
  void handleEditProviderConfig(firstProviderConfig)
}

/** 进入模型分区时优先展示已有模型详情，避免把新建表单作为默认落点。 */
function openDefaultModelDetail() {
  if (selectedConfigId.value || modelCreateRequested.value) {
    return
  }
  const firstModel = configsQuery.data.value?.[0]
  if (!firstModel) {
    return
  }
  void handleEditModel(firstModel)
}

/** 从供应商列表中查找默认 Base URL。 */
function findProviderDefaultBaseUrl(providerKey: string | null | undefined) {
  return providersQuery.data.value?.find(item => item.provider_key === providerKey)?.default_base_url ?? ''
}

/** 从供应商列表中查找默认模型 ID。 */
function findProviderDefaultModelId(providerKey: string | null | undefined) {
  return providersQuery.data.value?.find(item => item.provider_key === providerKey)?.default_model_id ?? ''
}

/** 把供应商原生强度压缩为平台固定四档。 */
function normalizePlatformReasoningLevel(value: string | null | undefined): AiReasoningLevel {
  const normalized = String(value ?? '').trim().toLowerCase()
  if (normalized === 'minimal') return 'low'
  if (['xhigh', 'max', 'ultra'].includes(normalized)) return 'max'
  if (normalized === 'low' || normalized === 'high') return normalized
  return 'medium'
}

/** 从供应商列表中查找默认图片输入能力。 */
function findProviderDefaultSupportsImageInput(providerKey: string | null | undefined) {
  return Boolean(providersQuery.data.value?.find(item => item.provider_key === providerKey)?.default_supports_image_input)
}

/** 判断上下文窗口是否仍是供应商默认值，可在切换供应商时替换。 */
function shouldReplaceContextWindowDefault(value: number, providerKey: string | null | undefined) {
  const provider = providersQuery.data.value?.find(item => item.provider_key === providerKey)
  return value === DEFAULT_CONTEXT_WINDOW_TOKENS || value === provider?.default_context_window_tokens
}

/** 用服务端配置重置工具草稿。 */
function resetToolDrafts(config: AgentConfigItem) {
  for (const key of Object.keys(toolDrafts)) {
    delete toolDrafts[key]
  }
  for (const group of config.tool_groups) {
    for (const tool of group.tools) {
      toolDrafts[tool.key] = {
        enabled: tool.enabled,
        descriptionOverride: tool.description_override ?? '',
        instructionsOverride: tool.instructions_override ?? '',
      }
    }
  }
}

/** 保存固定槽位；管理员设置全局默认时仅允许选择全局模型。 */
async function handleSaveSlot(slot: string, scope: AiLlmConfigScope = 'personal') {
  const selectedModelId = slotDrafts[slot] ?? null
  if (scope === 'global') {
    const selected = configsQuery.data.value?.find(config => config.id === selectedModelId)
    if (!selected || selected.scope !== 'global') {
      Message.error('全局默认槽位只能绑定管理员全局模型。')
      return
    }
  }
  bindingSlot.value = scope === 'global' ? `global:${slot}` : slot
  try {
    await updateLlmSlotBinding(slot, selectedModelId, scope)
    await refreshLlmQueries()
    Message.success(scope === 'global' ? '全局默认模型已保存。' : '模型绑定已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存模型绑定失败。'))
  } finally {
    bindingSlot.value = null
  }
}

/** 保存当前智能体的完整提示词。 */
async function handleSavePrompt() {
  if (!selectedAgentConfig.value) return
  savingPrompt.value = true
  try {
    const normalizedPrompt = promptDraft.value.trim()
    await updateAgentConfig(selectedAgentConfig.value.id, {
      prompt_override: normalizedPrompt || null,
    })
    await refreshAgentQueries()
    Message.success('智能体提示词已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存智能体提示词失败。'))
  } finally {
    savingPrompt.value = false
  }
}

/** 恢复当前智能体默认完整提示词。 */
async function handleRestorePrompt() {
  if (!selectedAgentConfig.value) return
  savingPrompt.value = true
  try {
    await updateAgentConfig(selectedAgentConfig.value.id, { prompt_override: null })
    await refreshAgentQueries()
    Message.success('智能体提示词已恢复默认。')
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复智能体提示词失败。'))
  } finally {
    savingPrompt.value = false
  }
}

/** 保存单个工具的启停状态与说明覆盖。 */
async function handleSaveTool(tool: AgentToolConfigItem) {
  if (!selectedAgentConfig.value || !toolDrafts[tool.key]) return
  const draft = toolDrafts[tool.key]
  savingToolKey.value = tool.key
  try {
    await updateAgentToolConfig(selectedAgentConfig.value.id, tool.key, {
      enabled: draft.enabled,
      description_override: draft.descriptionOverride.trim() || null,
      instructions_override: draft.instructionsOverride.trim() || null,
    })
    await refreshAgentQueries()
    Message.success('工具配置已保存。')
  } catch (error) {
    Message.error(getErrorMessage(error, '保存工具配置失败。'))
  } finally {
    savingToolKey.value = null
  }
}

/** 恢复单个工具默认配置。 */
async function handleRestoreTool(tool: AgentToolConfigItem) {
  if (!selectedAgentConfig.value) return
  savingToolKey.value = tool.key
  try {
    await updateAgentToolConfig(selectedAgentConfig.value.id, tool.key, { restore_default: true })
    await refreshAgentQueries()
    Message.success('工具配置已恢复默认。')
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复工具配置失败。'))
  } finally {
    savingToolKey.value = null
  }
}
/** 判断工具草稿是否发生变化。 */
function isToolDirty(tool: AgentToolConfigItem) {
  const draft = toolDrafts[tool.key]
  if (!draft) return false
  return draft.enabled !== tool.enabled
    || draft.descriptionOverride.trim() !== (tool.description_override ?? '')
    || draft.instructionsOverride.trim() !== (tool.instructions_override ?? '')
}

/** 按范围选择默认供应商配置，优先使用 DeepSeek。 */
function findDefaultProviderConfigForScope(scope: AiLlmConfigScope, modelType: AiModelType = modelForm.model_type) {
  const candidates = (providerConfigsQuery.data.value ?? []).filter(config => (
    config.scope === scope
    && config.status === 'active'
    && getProviderConfigType(config) === modelType
  ))
  return candidates.find(config => config.provider_key === DEFAULT_NEW_MODEL_PROVIDER_KEY) ?? candidates[0] ?? null
}

/** 根据供应商配置找到静态目录项。 */
function findProviderForConfig(config: LlmProviderConfigItem | null) {
  return providersQuery.data.value?.find(provider => provider.provider_key === config?.provider_key) ?? null
}

/** 兼容旧响应并返回目录声明的单一供应商类型。 */
function getCatalogProviderType(provider: LlmProviderCatalogItem | null | undefined): AiModelType {
  if (provider?.provider_type) return provider.provider_type
  return provider?.supported_model_types?.length === 1 && provider.supported_model_types[0] === 'image_generation'
    ? 'image_generation'
    : 'chat'
}

/** 从供应商配置或静态目录解析供应商类型。 */
function getProviderConfigType(config: LlmProviderConfigItem): AiModelType {
  return config.provider_type ?? getCatalogProviderType(findProviderForConfig(config))
}

/** 重置供应商表单并切换到新建状态。 */
function resetProviderForm() {
  activeSection.value = 'providers'
  providerPanelMode.value = 'create'
  providerCreateRequested.value = true
  selectedProviderConfigId.value = null
  providerForm.scope = 'personal'
  providerForm.name = ''
  const provider = providersQuery.data.value?.length
    ? findDefaultNewModelProvider(providersQuery.data.value)
    : null
  providerForm.provider_key = provider?.provider_key ?? null
  providerForm.api_key = ''
  prefillProviderFormFromProvider(provider)
}

/** 把已有供应商配置装载到右侧表单。 */
async function handleEditProviderConfig(config: LlmProviderConfigItem) {
  activeSection.value = 'providers'
  providerPanelMode.value = 'detail'
  providerCreateRequested.value = false
  applyingExistingProviderConfig.value = true
  selectedProviderConfigId.value = config.id
  providerForm.scope = config.scope
  providerForm.name = config.name
  providerForm.provider_key = config.provider_key
  providerForm.base_url = config.base_url ?? ''
  providerForm.api_key = ''
  await nextTick()
  applyingExistingProviderConfig.value = false
}

/** 从供应商详情进入编辑态。 */
function handleStartEditProviderConfig() {
  if (!selectedProviderConfig.value?.editable) {
    Message.error('管理员全局供应商只读，不能由当前用户修改。')
    return
  }
  providerPanelMode.value = 'edit'
}

/** 取消供应商编辑，重新装载详情数据以丢弃草稿。 */
function handleCancelProviderEdit() {
  const config = selectedProviderConfig.value
  if (!config) {
    resetProviderForm()
    return
  }
  void handleEditProviderConfig(config)
}

/** 重置模型表单并切换到新建状态。 */
function resetModelForm() {
  activeSection.value = 'models'
  modelPanelMode.value = 'create'
  modelCreateRequested.value = true
  selectedConfigId.value = null
  modelForm.scope = 'personal'
  modelForm.model_type = 'chat'
  modelForm.name = ''
  const providerConfig = findDefaultProviderConfigForScope(modelForm.scope)
  modelForm.provider_config_id = providerConfig?.id ?? null
  const provider = findProviderForConfig(providerConfig)
  prefillModelFormFromProvider(provider)
  advancedConfigText.value = '{}'
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
}

/** 把已有模型装载到右侧表单。 */
async function handleEditModel(config: LlmConfigItem) {
  activeSection.value = 'models'
  modelPanelMode.value = 'detail'
  modelCreateRequested.value = false
  applyingExistingModel.value = true
  selectedConfigId.value = config.id
  modelForm.scope = config.scope
  modelForm.name = config.name
  modelForm.provider_config_id = config.provider_config_id
  modelForm.model_type = config.model_type ?? 'chat'
  modelForm.model_id = config.model_id
  modelForm.reasoning_mode = config.reasoning_mode ?? (config.thinking_enabled ? 'enabled' : 'auto')
  modelForm.reasoning_level = config.reasoning_level ?? (config.thinking_enabled ? normalizePlatformReasoningLevel(config.thinking_effort) : null)
  modelForm.supports_image_input = config.supports_image_input
  modelForm.context_window_tokens = config.context_window_tokens
  advancedConfigText.value = JSON.stringify(config.advanced_config_json ?? {}, null, 2)
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
  await nextTick()
  applyingExistingModel.value = false
}

/** 从模型详情进入编辑态。 */
function handleStartEditModel() {
  if (!selectedModel.value?.editable) {
    Message.error('管理员全局模型只读，不能由当前用户修改。')
    return
  }
  modelPanelMode.value = 'edit'
}

/** 取消模型编辑，重新装载详情数据以丢弃草稿。 */
function handleCancelModelEdit() {
  const config = selectedModel.value
  if (!config) {
    resetModelForm()
    return
  }
  void handleEditModel(config)
}

/** 解析高级 JSON 配置并同步错误提示。 */
function parseAdvancedConfig() {
  const rawText = advancedConfigText.value.trim() || '{}'
  try {
    const parsed = JSON.parse(rawText) as Record<string, unknown>
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      throw new Error('高级 JSON 配置必须是对象。')
    }
    advancedConfigError.value = ''
    return parsed
  } catch (error) {
    advancedConfigError.value = error instanceof Error ? error.message : '高级 JSON 配置格式不正确。'
    throw error
  }
}

/** 格式化高级 JSON 配置。 */
function formatAdvancedConfig() {
  try {
    advancedConfigText.value = JSON.stringify(parseAdvancedConfig(), null, 2)
    advancedConfigCollapsed.value = false
  } catch {
    Message.error('当前高级 JSON 不合法，无法格式化。')
  }
}

/** 归一化 token 数配置，避免空值或非法值提交到后端。 */
function normalizePositiveInteger(value: number, fallback: number) {
  const normalized = Math.floor(Number(value))
  return Number.isFinite(normalized) && normalized > 0 ? normalized : fallback
}

/** 创建或更新供应商配置。 */
async function handleSubmitProviderConfig() {
  if (selectedProviderConfig.value && !selectedProviderConfig.value.editable) {
    Message.error('管理员全局供应商只读，不能由当前用户修改。')
    return
  }
  const providerKey = providerForm.provider_key
  if (!providerForm.name.trim() || !providerKey) {
    Message.error('请先填写供应商配置名称和供应商。')
    return
  }

  const provider = currentProviderForProviderForm.value
  const baseUrl = provider?.supports_base_url ? providerForm.base_url.trim() || null : null
  const apiKey = provider?.supports_api_key ? providerForm.api_key.trim() || null : null
  if (provider?.requires_base_url && !baseUrl) {
    Message.error('当前供应商必须填写 Base URL。')
    return
  }

  savingProviderConfig.value = true
  try {
    if (selectedProviderConfigId.value) {
      const updatePayload: LlmProviderConfigUpdatePayload = {
        name: providerForm.name.trim(),
        base_url: baseUrl,
      }
      if (apiKey) {
        updatePayload.api_key = apiKey
      }
      const updatedProviderConfig = await updateLlmProviderConfig(selectedProviderConfigId.value, updatePayload)
      queryClient.setQueryData<LlmProviderConfigItem[]>(['llm-provider-configs'], currentItems => (
        currentItems?.map(item => item.id === updatedProviderConfig.id ? updatedProviderConfig : item) ?? [updatedProviderConfig]
      ))
      await handleEditProviderConfig(updatedProviderConfig)
      Message.success('供应商已更新。')
    } else {
      const createdProviderConfig = await createLlmProviderConfig({
        name: providerForm.name.trim(),
        scope: providerForm.scope,
        provider_key: providerKey,
        base_url: baseUrl,
        api_key: apiKey,
      })
      queryClient.setQueryData<LlmProviderConfigItem[]>(['llm-provider-configs'], currentItems => [
        createdProviderConfig,
        ...(currentItems ?? []).filter(item => item.id !== createdProviderConfig.id),
      ])
      await handleEditProviderConfig(createdProviderConfig)
      Message.success('供应商已创建。')
    }
    await refreshProviderQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '保存供应商失败。'))
  } finally {
    savingProviderConfig.value = false
  }
}

/** 创建或更新模型。 */
async function handleSubmitModel() {
  if (selectedModel.value && !selectedModel.value.editable) {
    Message.error('管理员全局模型只读，不能由当前用户修改。')
    return
  }
  const providerConfigId = modelForm.provider_config_id
  if (!modelForm.name.trim() || !providerConfigId || !modelForm.model_id.trim()) {
    Message.error('请先填写模型名称、供应商配置和模型 ID。')
    return
  }

  let advancedConfig: Record<string, unknown>
  try {
    advancedConfig = parseAdvancedConfig()
  } catch {
    Message.error('高级 JSON 配置不合法。')
    return
  }

  const contextWindowTokens = normalizePositiveInteger(modelForm.context_window_tokens, DEFAULT_CONTEXT_WINDOW_TOKENS)

  savingConfig.value = true
  try {
    if (selectedConfigId.value) {
      const updatePayload: LlmConfigUpdatePayload = {
        name: modelForm.name.trim(),
        provider_config_id: providerConfigId,
        model_id: modelForm.model_id.trim(),
        model_type: modelForm.model_type,
        reasoning_mode: modelForm.reasoning_mode,
        reasoning_level: modelForm.reasoning_mode === 'enabled' ? modelForm.reasoning_level ?? 'medium' : null,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: contextWindowTokens,
        advanced_config_json: advancedConfig,
      }
      const updatedConfig = await updateLlmConfig(selectedConfigId.value, updatePayload)
      queryClient.setQueryData<LlmConfigItem[]>(['llm-configs'], currentItems => (
        currentItems?.map(item => item.id === updatedConfig.id ? updatedConfig : item) ?? [updatedConfig]
      ))
      await handleEditModel(updatedConfig)
      Message.success('模型已更新。')
    } else {
      const createdConfig = await createLlmConfig({
        name: modelForm.name.trim(),
        scope: modelForm.scope,
        provider_config_id: providerConfigId,
        model_id: modelForm.model_id.trim(),
        model_type: modelForm.model_type,
        reasoning_mode: modelForm.reasoning_mode,
        reasoning_level: modelForm.reasoning_mode === 'enabled' ? modelForm.reasoning_level ?? 'medium' : null,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: contextWindowTokens,
        advanced_config_json: advancedConfig,
      })
      queryClient.setQueryData<LlmConfigItem[]>(['llm-configs'], currentItems => [
        createdConfig,
        ...(currentItems ?? []).filter(item => item.id !== createdConfig.id),
      ])
      await handleEditModel(createdConfig)
      Message.success('模型已创建。')
    }
    await refreshLlmQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '保存模型失败。'))
  } finally {
    savingConfig.value = false
  }
}

/** 删除供应商配置；后端会拒绝仍有关联模型的供应商。 */
async function handleDeleteProviderConfig(config: LlmProviderConfigItem) {
  const confirmed = await createConfirm(
    `确认删除供应商「${config.name}」吗？删除前必须先删除所有关联模型。`,
    '删除供应商',
  )
  if (!confirmed) {
    return
  }

  deletingProviderConfigId.value = config.id
  try {
    await deleteLlmProviderConfig(config.id)
    const remainingProviderConfigs = (providerConfigsQuery.data.value ?? []).filter(item => item.id !== config.id)
    queryClient.setQueryData<LlmProviderConfigItem[]>(['llm-provider-configs'], remainingProviderConfigs)
    if (selectedProviderConfigId.value === config.id) {
      selectedProviderConfigId.value = null
      providerCreateRequested.value = false
      const nextProviderConfig = remainingProviderConfigs[0]
      if (nextProviderConfig) {
        await handleEditProviderConfig(nextProviderConfig)
      } else {
        resetProviderForm()
      }
    }
    Message.success('供应商已删除。')
    await refreshProviderQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '删除供应商失败。'))
  } finally {
    deletingProviderConfigId.value = null
  }
}

/** 删除模型配置；引用该模型的槽位会被后端自动解绑。 */
async function handleDeleteModel(config: LlmConfigItem) {
  const confirmed = await createConfirm(
    `确认删除模型「${config.name}」吗？删除后已关联会话无法继续发起运行，相关模型绑定会自动移除。`,
    '删除模型',
  )
  if (!confirmed) {
    return
  }

  deletingConfigId.value = config.id
  try {
    await deleteLlmConfig(config.id)
    const remainingConfigs = (configsQuery.data.value ?? []).filter(item => item.id !== config.id)
    queryClient.setQueryData<LlmConfigItem[]>(['llm-configs'], remainingConfigs)
    if (selectedConfigId.value === config.id) {
      selectedConfigId.value = null
      modelCreateRequested.value = false
      const nextModel = remainingConfigs[0]
      if (nextModel) {
        await handleEditModel(nextModel)
      } else {
        resetModelForm()
      }
    }
    Message.success('模型已删除。')
    await refreshLlmQueries()
  } catch (error) {
    Message.error(getErrorMessage(error, '删除模型失败。'))
  } finally {
    deletingConfigId.value = null
  }
}

/** 刷新模型、模型绑定与运行入口相关缓存。 */
async function refreshLlmQueries() {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['llm-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['llm-provider-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['llm-slots'] }),
    queryClient.invalidateQueries({ queryKey: ['ai-agents'] }),
  ])
}

/** 刷新供应商、模型绑定与运行入口相关缓存。 */
async function refreshProviderQueries() {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['llm-provider-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['llm-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['llm-slots'] }),
    queryClient.invalidateQueries({ queryKey: ['ai-agents'] }),
  ])
}

/** 刷新智能体配置及运行入口相关缓存。 */
async function refreshAgentQueries() {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['agent-configs'] }),
    queryClient.invalidateQueries({ queryKey: ['agent-catalog'] }),
    queryClient.invalidateQueries({ queryKey: ['ai-agents'] }),
  ])
}
</script>
