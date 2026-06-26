/**
 * 文件功能：封装用户级模型、供应商目录与智能体模型绑定接口。
 */
import { http } from '@/api/http'
import type {
  AiLlmConfigScope,
  LlmConfigItem,
  LlmProviderCatalogItem,
  LlmProviderConfigItem,
  LlmSlotBindingItem,
  RecordStatus,
} from '@/types/api'

export interface LlmProviderConfigPayload {
  name: string
  scope?: AiLlmConfigScope
  provider_key: string
  base_url?: string | null
  api_key?: string | null
}

export interface LlmProviderConfigUpdatePayload {
  name?: string
  base_url?: string | null
  api_key?: string | null
  status?: RecordStatus
}

export interface LlmConfigPayload {
  name: string
  scope?: AiLlmConfigScope
  provider_config_id: number
  model_id: string
  thinking_enabled: boolean
  thinking_effort?: string | null
  supports_image_input: boolean
  context_window_tokens: number
  max_output_tokens: number
  history_token_ratio: number
  compression_target_ratio: number
  advanced_config_json: Record<string, unknown>
}

export interface LlmConfigUpdatePayload {
  name?: string
  provider_config_id?: number
  model_id?: string
  thinking_enabled?: boolean
  thinking_effort?: string | null
  supports_image_input?: boolean
  context_window_tokens?: number
  max_output_tokens?: number
  history_token_ratio?: number
  compression_target_ratio?: number
  advanced_config_json?: Record<string, unknown>
  status?: RecordStatus
}

/**
 * 读取后端供应商目录。
 */
export async function listLlmProviders() {
  const { data } = await http.get<LlmProviderCatalogItem[]>('/ai/llm-providers')
  return data
}

/**
 * 读取当前用户可见的供应商配置。
 */
export async function listLlmProviderConfigs() {
  const { data } = await http.get<LlmProviderConfigItem[]>('/ai/llm-provider-configs')
  return data
}

/**
 * 读取单条供应商配置详情。
 */
export async function getLlmProviderConfig(providerConfigId: number) {
  const { data } = await http.get<LlmProviderConfigItem>(`/ai/llm-provider-configs/${providerConfigId}`)
  return data
}

/**
 * 创建新的供应商配置。
 */
export async function createLlmProviderConfig(payload: LlmProviderConfigPayload) {
  const { data } = await http.post<LlmProviderConfigItem>('/ai/llm-provider-configs', payload)
  return data
}

/**
 * 更新指定的供应商配置。
 */
export async function updateLlmProviderConfig(providerConfigId: number, payload: LlmProviderConfigUpdatePayload) {
  const { data } = await http.patch<LlmProviderConfigItem>(`/ai/llm-provider-configs/${providerConfigId}`, payload)
  return data
}

/**
 * 读取当前用户的模型列表。
 */
export async function listLlmConfigs() {
  const { data } = await http.get<LlmConfigItem[]>('/ai/llm-configs')
  return data
}

/**
 * 读取单条模型详情。
 */
export async function getLlmConfig(configId: number) {
  const { data } = await http.get<LlmConfigItem>(`/ai/llm-configs/${configId}`)
  return data
}

/**
 * 创建新的模型。
 */
export async function createLlmConfig(payload: LlmConfigPayload) {
  const { data } = await http.post<LlmConfigItem>('/ai/llm-configs', payload)
  return data
}

/**
 * 更新指定的模型。
 */
export async function updateLlmConfig(configId: number, payload: LlmConfigUpdatePayload) {
  const { data } = await http.patch<LlmConfigItem>(`/ai/llm-configs/${configId}`, payload)
  return data
}

/**
 * 读取智能体模型绑定状态。
 */
export async function listLlmSlots() {
  const { data } = await http.get<LlmSlotBindingItem[]>('/ai/llm-slots')
  return data
}

/**
 * 更新指定绑定项使用的模型。
 */
export async function updateLlmSlotBinding(
  slot: string,
  llmConfigId: number | null,
  scope: AiLlmConfigScope = 'personal',
) {
  const { data } = await http.put<LlmSlotBindingItem>(`/ai/llm-slots/${slot}`, {
    llm_config_id: llmConfigId,
    scope,
  })
  return data
}
