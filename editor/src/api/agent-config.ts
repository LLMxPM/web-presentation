/**
 * 文件功能：封装用户级智能体提示词、工具目录与工具配置接口。
 */
import { http } from '@/api/http'
import type { AgentCatalogItem, AgentCodeStandardConfigItem, AgentConfigItem } from '@/types/api'

export interface AgentConfigUpdatePayload {
  description_override?: string | null
  prompt_override?: string | null
  restore_default?: boolean
}

export interface AgentToolConfigUpdatePayload {
  enabled?: boolean | null
  description_override?: string | null
  instructions_override?: string | null
  restore_default?: boolean
}

export interface AgentCodeStandardUpdatePayload {
  content_override?: string | null
  restore_default?: boolean
}

/**
 * 读取系统内置智能体目录。
 */
export async function listAgentCatalog() {
  const { data } = await http.get<AgentCatalogItem[]>('/ai/agent-catalog')
  return data
}

/**
 * 读取当前用户的智能体有效配置。
 */
export async function listAgentConfigs() {
  const { data } = await http.get<AgentConfigItem[]>('/ai/agent-configs')
  return data
}

/**
 * 更新指定智能体的完整提示词。
 */
export async function updateAgentConfig(agentId: string, payload: AgentConfigUpdatePayload) {
  const { data } = await http.patch<AgentConfigItem>(`/ai/agent-configs/${agentId}`, payload)
  return data
}

/**
 * 更新指定智能体中单个工具的开关或工具提示词覆盖。
 */
export async function updateAgentToolConfig(
  agentId: string,
  toolKey: string,
  payload: AgentToolConfigUpdatePayload,
) {
  const { data } = await http.patch<AgentConfigItem>(`/ai/agent-configs/${agentId}/tools/${toolKey}`, payload)
  return data
}

/**
 * 读取当前用户指定 Agent 的页面与组件代码规范。
 */
export async function listAgentCodeStandards(agentId: string) {
  const { data } = await http.get<AgentCodeStandardConfigItem[]>(`/ai/agent-configs/${agentId}/code-standards`)
  return data
}

/**
 * 更新或恢复指定 Agent 的单类代码规范。
 */
export async function updateAgentCodeStandard(
  agentId: string,
  standardType: AgentCodeStandardConfigItem['standard_type'],
  payload: AgentCodeStandardUpdatePayload,
) {
  const { data } = await http.patch<AgentCodeStandardConfigItem[]>(
    `/ai/agent-configs/${agentId}/code-standards/${standardType}`,
    payload,
  )
  return data
}
