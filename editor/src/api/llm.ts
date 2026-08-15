/**
 * 文件功能：为账户 AI 设置提供 Chat/Image 拆分接口，并维持页面内部统一展示类型。
 */
import { http } from '@/api/http'
import type {
  AiLlmConfigScope, AiModelType, ImageGenerationModelCatalogItem,
  LlmConfigItem, LlmModelCapabilityItem, LlmProviderCatalogItem, LlmProviderConfigItem, LlmSlotBindingItem,
} from '@/types/api'
import type {
  ChatModelCatalogItem, ChatModelConfigItem, ChatProviderCatalogItem, ChatProviderConfigItem,
  ImageModelConfigItem, ImageProviderCatalogItem, ImageProviderConfigItem,
} from '@/api/model-config'

export interface LlmProviderConfigPayload {
  name: string; scope?: AiLlmConfigScope; provider_key: string; provider_type?: AiModelType; base_url?: string | null; api_key?: string | null
}
export interface LlmProviderConfigUpdatePayload { name?: string; base_url?: string | null; api_key?: string | null }
export interface LlmConfigPayload {
  name: string; scope?: AiLlmConfigScope; provider_config_id: number; model_id: string; model_type: AiModelType
  supports_image_input: boolean
  context_window_tokens: number; advanced_config_json: Record<string, unknown>
}
export interface LlmConfigUpdatePayload extends Partial<LlmConfigPayload> {}
export interface ModelCatalogSyncState {
  catalog_version: string | null
  last_attempt_at: string | null
  last_success_at: string | null
  last_error: string | null
  syncing: boolean
}

/** 查询指定聊天供应商的 Models.dev 模型；不会访问图片模型注册表。 */
export async function listChatCatalogModels(providerKey: string, query?: string) {
  const items: ChatModelCatalogItem[] = []
  const pageSize = 200
  for (let offset = 0; offset < 2_000; offset += pageSize) {
    const { data } = await http.get<ChatModelCatalogItem[]>(`/ai/chat-provider-catalog/${providerKey}/models`, {
      params: { query, offset, limit: pageSize },
    })
    items.push(...data)
    if (data.length < pageSize) break
  }
  return items
}

/** 读取 Models.dev 本地缓存状态，供页面明确区分启动目录和联网目录。 */
export async function getModelCatalogSyncState() {
  return (await http.get<ModelCatalogSyncState>('/ai/model-catalog-sync')).data
}

/** 管理员手动刷新 Models.dev 本地缓存。 */
export async function refreshModelCatalog() {
  return (await http.post<ModelCatalogSyncState>('/ai/model-catalog-sync')).data
}

/** 合并两个独立目录，仅供现有工作台分区展示。 */
export async function listLlmProviders() {
  const [chat, image] = await Promise.all([
    http.get<ChatProviderCatalogItem[]>('/ai/chat-provider-catalog'),
    http.get<ImageProviderCatalogItem[]>('/ai/image-provider-catalog'),
  ])
  return [
    ...chat.data.map(toChatCatalog),
    toChatCatalog({
      provider_key: 'custom-openai-compatible', name: '自定义 OpenAI-compatible', api_url: null, docs_url: null,
      default_base_url: null, protocol_key: 'openai_compatible_chat', catalog_version: 'custom',
    }),
    ...image.data.map(toImageCatalog),
  ]
}

/** 根据当前供应商和模型读取 Models.dev 能力，手工模型采用保守默认。 */
export async function resolveLlmModelCapability(providerConfigId: number, modelId: string, override?: Record<string, unknown>) {
  const providers = await listLlmProviderConfigs()
  const provider = providers.find(item => item.id === providerConfigId)
  let capability: Record<string, unknown> = {
    context_tokens: 200000, input_tokens: 191808, output_tokens: 8192,
    supports_image_input: false, supports_reasoning: false, source: 'conservative_default', verified: false,
  }
  if (provider?.provider_type === 'chat') {
    const { data: models } = await http.get<Array<Record<string, unknown>>>(`/ai/chat-provider-catalog/${provider.provider_key}/models`, { params: { query: modelId } })
    const item = models.find(model => model.model_id === modelId)
    if (item) capability = {
      context_tokens: item.context_tokens, input_tokens: item.input_tokens, output_tokens: item.output_tokens,
      supports_image_input: Array.isArray(item.input_modalities) && item.input_modalities.includes('image'),
      input_modalities: item.input_modalities, supports_tool_call: item.supports_tool_call,
      supports_reasoning: item.supports_reasoning, reasoning_options: item.reasoning_options,
      source: 'models.dev', verified: true,
    }
  }
  capability = { ...capability, ...(override ?? {}) }
  return toCapability(capability)
}

export async function listLlmProviderConfigs() {
  const [chat, image] = await Promise.all([
    http.get<ChatProviderConfigItem[]>('/ai/chat-provider-configs'),
    http.get<ImageProviderConfigItem[]>('/ai/image-provider-configs'),
  ])
  return [...chat.data.map(toChatProvider), ...image.data.map(toImageProvider)]
}

export async function getLlmProviderConfig(id: number) {
  const item = (await listLlmProviderConfigs()).find(value => value.id === id)
  if (!item) throw new Error('供应商配置不存在。')
  return item
}

export async function createLlmProviderConfig(payload: LlmProviderConfigPayload) {
  if (payload.provider_type === 'image_generation' || payload.provider_key.endsWith('_image')) {
    const { data } = await http.post<ImageProviderConfigItem>('/ai/image-provider-configs', payload)
    return toImageProvider(data)
  }
  const { data } = await http.post<ChatProviderConfigItem>('/ai/chat-provider-configs', {
    name: payload.name, scope: payload.scope,
    catalog_provider_key: payload.provider_key === 'custom-openai-compatible' ? null : payload.provider_key,
    custom: payload.provider_key === 'custom-openai-compatible', base_url: payload.base_url, api_key: payload.api_key,
  })
  return toChatProvider(data)
}

export async function updateLlmProviderConfig(id: number, payload: LlmProviderConfigUpdatePayload) {
  const path = id < 0 ? 'image' : 'chat'
  const { data } = await http.patch<ChatProviderConfigItem | ImageProviderConfigItem>(`/ai/${path}-provider-configs/${Math.abs(id)}`, payload)
  return path === 'image' ? toImageProvider(data as ImageProviderConfigItem) : toChatProvider(data as ChatProviderConfigItem)
}

export async function deleteLlmProviderConfig(id: number) {
  const path = id < 0 ? 'image' : 'chat'
  return (await http.delete<{ message: string }>(`/ai/${path}-provider-configs/${Math.abs(id)}`)).data
}

export async function listLlmConfigs() {
  const [chat, image] = await Promise.all([
    http.get<ChatModelConfigItem[]>('/ai/chat-model-configs'),
    http.get<ImageModelConfigItem[]>('/ai/image-model-configs'),
  ])
  return [...chat.data.map(toChatModel), ...image.data.map(toImageModel)]
}

export async function getLlmConfig(id: number) {
  const item = (await listLlmConfigs()).find(value => value.id === id)
  if (!item) throw new Error('模型配置不存在。')
  return item
}

export async function createLlmConfig(payload: LlmConfigPayload) {
  const { advancedConfig, explicitCapability } = splitAdvancedConfig(payload.advanced_config_json)
  const base = { name: payload.name, scope: payload.scope, provider_config_id: Math.abs(payload.provider_config_id),
    model_id: payload.model_id, advanced_config: advancedConfig }
  if (payload.model_type === 'image_generation') {
    return toImageModel((await http.post<ImageModelConfigItem>('/ai/image-model-configs', base)).data)
  }
  return toChatModel((await http.post<ChatModelConfigItem>('/ai/chat-model-configs', {
    ...base,
    capability_override: explicitCapability,
  })).data)
}

export async function updateLlmConfig(id: number, payload: LlmConfigUpdatePayload) {
  const path = id < 0 ? 'image' : 'chat'
  const { advancedConfig, explicitCapability } = splitAdvancedConfig(payload.advanced_config_json ?? {})
  const body: Record<string, unknown> = { name: payload.name, provider_config_id: payload.provider_config_id,
    model_id: payload.model_id, advanced_config: advancedConfig }
  if (path === 'chat') body.capability_override = explicitCapability
  if (typeof body.provider_config_id === 'number') body.provider_config_id = Math.abs(body.provider_config_id)
  const { data } = await http.patch<ChatModelConfigItem | ImageModelConfigItem>(`/ai/${path}-model-configs/${Math.abs(id)}`, body)
  return path === 'image' ? toImageModel(data as ImageModelConfigItem) : toChatModel(data as ChatModelConfigItem)
}

export async function deleteLlmConfig(id: number) {
  const path = id < 0 ? 'image' : 'chat'
  return (await http.delete<{ message: string }>(`/ai/${path}-model-configs/${Math.abs(id)}`)).data
}

export async function listLlmSlots() {
  const [agent, vision, image] = await Promise.all([
    http.get('/ai/chat-model-bindings/agent_coordinator'), http.get('/ai/chat-model-bindings/image_understanding'),
    http.get('/ai/image-model-bindings/image_generation'),
  ])
  return [toBinding(agent.data, 'agent_coordinator', '内容助手', 'chat'), toBinding(vision.data, 'image_understanding', '图片理解', 'chat'),
    toBinding(image.data, 'image_generation', '图片生成', 'image_generation')]
}

export async function updateLlmSlotBinding(slot: string, id: number | null, scope: AiLlmConfigScope = 'personal') {
  if (slot === 'image_generation') {
    const { data } = await http.put('/ai/image-model-bindings/image_generation', { model_config_id: id == null ? null : Math.abs(id), scope })
    return toBinding(data, slot, '图片生成', 'image_generation')
  }
  const { data } = await http.put(`/ai/chat-model-bindings/${slot}`, { model_config_id: id, scope })
  return toBinding(data, slot, slot === 'agent_coordinator' ? '内容助手' : '图片理解', 'chat')
}

function toChatCatalog(item: ChatProviderCatalogItem): LlmProviderCatalogItem {
  return { provider_key: item.provider_key, label: item.name, provider_type: 'chat', provider_adapter: item.protocol_key,
    docs_url: item.docs_url ?? '', supports_base_url: true,
    requires_base_url: item.protocol_key === 'openai_compatible_chat' && !item.default_base_url,
    supports_api_key: true, supports_thinking: true, thinking_mode: item.protocol_key,
    default_base_url: item.default_base_url, default_model_id: null, default_thinking_enabled: false,
    default_thinking_effort: null, default_context_window_tokens: null, default_max_output_tokens: null,
    default_supports_image_input: false, supported_model_types: ['chat'], thinking_effort_options: [], advanced_json_hint: {} }
}

function toImageCatalog(item: ImageProviderCatalogItem): LlmProviderCatalogItem {
  return { provider_key: item.provider_key, label: item.name, provider_type: 'image_generation', provider_adapter: item.provider_key,
    docs_url: item.docs_url, supports_base_url: true, requires_base_url: item.requires_base_url, supports_api_key: true,
    supports_thinking: false, thinking_mode: 'none', default_base_url: item.default_base_url,
    default_model_id: null, default_thinking_enabled: false, default_thinking_effort: null,
    default_context_window_tokens: null, default_max_output_tokens: null, default_supports_image_input: false,
    supported_model_types: ['image_generation'], default_image_generation_model_id: String(item.models[0]?.model_id ?? ''),
    thinking_effort_options: [], advanced_json_hint: {}, image_generation_models: item.models as unknown as ImageGenerationModelCatalogItem[] }
}

function toChatProvider(item: ChatProviderConfigItem): LlmProviderConfigItem {
  return { id: item.id, scope: item.scope, owner_user_id: null, editable: item.editable, name: item.name,
    provider_key: item.catalog_provider_key ?? item.provider_key, provider_label: item.provider_name, provider_type: 'chat',
    base_url: item.base_url, status: item.status as 'active' | 'archived', has_api_key: item.has_api_key,
    api_key_masked: item.api_key_masked, created_at: null, updated_at: null }
}

function toImageProvider(item: ImageProviderConfigItem): LlmProviderConfigItem {
  return { id: -item.id, scope: item.scope, owner_user_id: null, editable: item.editable, name: item.name,
    provider_key: item.provider_key, provider_label: item.provider_name, provider_type: 'image_generation', base_url: item.base_url,
    status: item.status as 'active' | 'archived', has_api_key: item.has_api_key, api_key_masked: item.api_key_masked,
    created_at: null, updated_at: null }
}

function toCapability(value: Record<string, unknown>): LlmModelCapabilityItem {
  const context = Number(value.context_tokens ?? 200000); const output = Number(value.output_tokens ?? 8192)
  const input = Number(value.input_tokens ?? Math.max(1, context - output)); const requestOutput = Math.min(output, 32768)
  return { source: String(value.source ?? 'conservative_default'), verified: Boolean(value.verified), profile_key: 'catalog', profile_version: 3,
    context_window_tokens: input, model_context_window_tokens: context,
    model_max_output_tokens: output, required_model_context_tokens: input + requestOutput, request_output_tokens: requestOutput,
    runtime_headroom_tokens: 0, compression_trigger_tokens: input, compression_target_tokens: 16384,
    budget_policy_version: 'fixed-context-budget.v3', request_max_output_tokens: requestOutput,
    supports_image_input: Boolean(value.supports_image_input), supports_reasoning: Boolean(value.supports_reasoning),
    supports_explicit_disable: false, default_level: null, level_mapping: { low: null, medium: null, high: null, max: null }, warnings: [] }
}

function baseModel(item: ChatModelConfigItem | ImageModelConfigItem, type: AiModelType, capability: Record<string, unknown>): LlmConfigItem {
  const parsed = toCapability(capability)
  return { id: item.id, scope: item.scope, owner_user_id: null, editable: item.editable, name: item.name,
    provider_config_id: item.provider_config_id, provider_config_name: item.provider_name, provider_key: item.provider_key,
    provider_label: item.provider_name, model_id: item.model_id, model_type: type, reasoning_mode: 'auto', reasoning_level: null,
    thinking_enabled: false, thinking_effort: null, supports_image_input: parsed.supports_image_input,
    context_window_tokens: parsed.context_window_tokens, required_model_context_tokens: parsed.required_model_context_tokens,
    request_output_tokens: parsed.request_output_tokens, runtime_headroom_tokens: parsed.runtime_headroom_tokens,
    compression_trigger_tokens: parsed.compression_trigger_tokens, compression_target_tokens: parsed.compression_target_tokens,
    budget_policy_version: parsed.budget_policy_version, model_max_output_tokens: parsed.model_max_output_tokens,
    request_max_output_tokens: parsed.request_output_tokens, max_output_tokens: parsed.request_output_tokens,
    capability_source: parsed.source, capability_verified: parsed.verified, model_capability_json: capability,
    effective_reasoning: { mode: 'auto', requested_level: null, native_value: null, degraded: false, message: '跟随模型默认。' },
    history_token_ratio: 1, compression_target_ratio: 0, advanced_config_json: item.advanced_config,
    status: item.status as 'active' | 'archived', created_at: null, updated_at: null }
}

function toChatModel(item: ChatModelConfigItem) {
  return baseModel(item, 'chat', { ...item.capability, protocol_key: item.protocol_key })
}
function toImageModel(item: ImageModelConfigItem) {
  return baseModel({ ...item, id: -item.id, provider_config_id: -item.provider_config_id }, 'image_generation', item.capability)
}

function toBinding(item: Record<string, unknown>, slot: string, label: string, type: AiModelType): LlmSlotBindingItem {
  const rawId = Number(item.model_config_id || 0) || null
  const id = rawId != null && type === 'image_generation' ? -rawId : rawId
  return { slot, slot_label: label, llm_config_id: id, llm_config_name: String(item.model_name ?? '') || null,
    provider_config_id: typeof item.provider_config_id === 'number'
      ? (type === 'image_generation' ? -item.provider_config_id : item.provider_config_id) : null,
    provider_config_name: String(item.provider_config_name ?? '') || null,
    provider_key: String(item.provider_key ?? '') || null, provider_label: String(item.provider_name ?? '') || null,
    model_id: String(item.model_id ?? '') || null,
    model_type: type, binding_ready: Boolean(item.binding_ready), supports_image_input: Boolean(item.supports_image_input),
    inherited_from_global: Boolean(item.inherited_from_global) }
}

/** 从高级 JSON 中提取显式能力覆盖，避免将平台字段发送给供应商。 */
function splitAdvancedConfig(value: Record<string, unknown>) {
  const advancedConfig = { ...value }
  const candidate = advancedConfig.capability_override
  delete advancedConfig.capability_override
  const explicitCapability = candidate && typeof candidate === 'object' && !Array.isArray(candidate)
    ? candidate as Record<string, unknown> : {}
  return { advancedConfig, explicitCapability }
}
