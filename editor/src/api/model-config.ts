/**
 * 文件功能：封装拆分后的聊天目录、聊天模型、图片模型与绑定接口。
 */
import { http } from '@/api/http'

export type ConfigScope = 'global' | 'personal'

export interface ChatProviderCatalogItem {
  provider_key: string
  name: string
  api_url: string | null
  docs_url: string | null
  default_base_url: string | null
  protocol_key: string
  catalog_version: string
}

export interface ChatModelCatalogItem {
  provider_key: string
  model_id: string
  name: string
  protocol_key: string
  context_tokens: number | null
  input_tokens: number | null
  output_tokens: number | null
  input_modalities: string[]
  supports_tool_call: boolean
  supports_reasoning: boolean
  reasoning_options: Record<string, unknown>
  catalog_version: string
}

export interface ChatProviderConfigItem {
  id: number
  scope: ConfigScope
  editable: boolean
  name: string
  provider_key: string
  catalog_provider_key: string | null
  provider_name: string
  protocol_key: string
  base_url: string | null
  has_api_key: boolean
  api_key_masked: string | null
  status: string
}

export interface ChatModelConfigItem {
  id: number
  scope: ConfigScope
  editable: boolean
  name: string
  provider_config_id: number
  provider_name: string
  provider_key: string
  protocol_key: string
  model_id: string
  catalog_version: string | null
  capability: Record<string, unknown>
  capability_override: Record<string, unknown>
  advanced_config: Record<string, unknown>
  status: string
}

export interface ImageProviderCatalogItem {
  provider_key: string
  name: string
  docs_url: string
  default_base_url: string | null
  requires_base_url: boolean
  models: Array<Record<string, unknown>>
}

export interface ImageProviderConfigItem {
  id: number
  scope: ConfigScope
  editable: boolean
  name: string
  provider_key: string
  provider_name: string
  base_url: string | null
  has_api_key: boolean
  api_key_masked: string | null
  status: string
}

export interface ImageModelConfigItem {
  id: number
  scope: ConfigScope
  editable: boolean
  name: string
  provider_config_id: number
  provider_name: string
  provider_key: string
  model_id: string
  capability: Record<string, unknown>
  advanced_config: Record<string, unknown>
  status: string
}

export async function listChatProviderCatalog(query?: string) {
  const { data } = await http.get<ChatProviderCatalogItem[]>('/ai/chat-provider-catalog', { params: { query } })
  return data
}

export async function listChatModelCatalog(providerKey: string, query?: string) {
  const { data } = await http.get<ChatModelCatalogItem[]>(`/ai/chat-provider-catalog/${providerKey}/models`, { params: { query } })
  return data
}

export async function syncModelCatalog() {
  const { data } = await http.post('/ai/model-catalog-sync')
  return data
}

export async function listChatProviderConfigs() {
  const { data } = await http.get<ChatProviderConfigItem[]>('/ai/chat-provider-configs')
  return data
}

export async function createChatProviderConfig(payload: Record<string, unknown>) {
  const { data } = await http.post<ChatProviderConfigItem>('/ai/chat-provider-configs', payload)
  return data
}

export async function updateChatProviderConfig(id: number, payload: Record<string, unknown>) {
  const { data } = await http.patch<ChatProviderConfigItem>(`/ai/chat-provider-configs/${id}`, payload)
  return data
}

export async function deleteChatProviderConfig(id: number) {
  return (await http.delete(`/ai/chat-provider-configs/${id}`)).data
}

export async function listChatModelConfigs() {
  const { data } = await http.get<ChatModelConfigItem[]>('/ai/chat-model-configs')
  return data
}

export async function createChatModelConfig(payload: Record<string, unknown>) {
  const { data } = await http.post<ChatModelConfigItem>('/ai/chat-model-configs', payload)
  return data
}

export async function updateChatModelConfig(id: number, payload: Record<string, unknown>) {
  const { data } = await http.patch<ChatModelConfigItem>(`/ai/chat-model-configs/${id}`, payload)
  return data
}

export async function deleteChatModelConfig(id: number) {
  return (await http.delete(`/ai/chat-model-configs/${id}`)).data
}

export async function getChatModelBinding(slot: string) {
  return (await http.get(`/ai/chat-model-bindings/${slot}`)).data
}

export async function updateChatModelBinding(slot: string, modelConfigId: number | null, scope: ConfigScope = 'personal') {
  return (await http.put(`/ai/chat-model-bindings/${slot}`, { model_config_id: modelConfigId, scope })).data
}

export async function listImageProviderCatalog() {
  return (await http.get<ImageProviderCatalogItem[]>('/ai/image-provider-catalog')).data
}

export async function listImageProviderConfigs() {
  return (await http.get<ImageProviderConfigItem[]>('/ai/image-provider-configs')).data
}

export async function createImageProviderConfig(payload: Record<string, unknown>) {
  return (await http.post<ImageProviderConfigItem>('/ai/image-provider-configs', payload)).data
}

export async function updateImageProviderConfig(id: number, payload: Record<string, unknown>) {
  return (await http.patch<ImageProviderConfigItem>(`/ai/image-provider-configs/${id}`, payload)).data
}

export async function deleteImageProviderConfig(id: number) {
  return (await http.delete(`/ai/image-provider-configs/${id}`)).data
}

export async function listImageModelConfigs() {
  return (await http.get<ImageModelConfigItem[]>('/ai/image-model-configs')).data
}

export async function createImageModelConfig(payload: Record<string, unknown>) {
  return (await http.post<ImageModelConfigItem>('/ai/image-model-configs', payload)).data
}

export async function updateImageModelConfig(id: number, payload: Record<string, unknown>) {
  return (await http.patch<ImageModelConfigItem>(`/ai/image-model-configs/${id}`, payload)).data
}

export async function deleteImageModelConfig(id: number) {
  return (await http.delete(`/ai/image-model-configs/${id}`)).data
}

export async function getImageModelBinding() {
  return (await http.get('/ai/image-model-bindings/image_generation')).data
}

export async function updateImageModelBinding(modelConfigId: number | null, scope: ConfigScope = 'personal') {
  return (await http.put('/ai/image-model-bindings/image_generation', { model_config_id: modelConfigId, scope })).data
}
