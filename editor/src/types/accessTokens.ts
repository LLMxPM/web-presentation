/**
 * 文件功能：定义个人访问令牌（PAT）相关的前端 TypeScript 类型契约。
 */

export interface ApiAccessTokenItem {
  id: number
  name: string
  token_public_id: string
  token_masked: string
  expires_at: string
  revoked_at: string | null
  last_used_at: string | null
  last_used_ip: string | null
  is_active: boolean
  workspace_ids: number[]
  scopes: string[]
  created_at: string
}

export interface ApiAccessTokenCreateRequest {
  name: string
  workspace_ids: number[]
  scopes: string[]
  expires_in_days: number
}

export interface ApiAccessTokenCreateResponse {
  id: number
  name: string
  token_public_id: string
  token: string
  expires_at: string
  workspace_ids: number[]
  scopes: string[]
  created_at: string
}

export interface ApiAccessTokenListResponse {
  items: ApiAccessTokenItem[]
  total: number
}

export interface ApiAccessTokenScopeInfo {
  scope: string
  description: string
  operation_count: number
  operations: string[]
}
