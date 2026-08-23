/**
 * 文件功能：提供个人访问令牌（PAT）相关的前端 API 请求方法。
 */
import { http } from '@/api/http'
import type {
  ApiAccessTokenCreateRequest,
  ApiAccessTokenCreateResponse,
  ApiAccessTokenListResponse,
  ApiAccessTokenScopeInfo,
} from '@/types/accessTokens'

/**
 * 查询当前用户的个人访问令牌列表。
 */
export async function listAccessTokens(): Promise<ApiAccessTokenListResponse> {
  const { data } = await http.get<ApiAccessTokenListResponse>('/access-tokens')
  return data
}

/**
 * 创建新访问令牌；仅在返回响应中返回一次明文 Token。
 * @param payload 创建请求载荷
 */
export async function createAccessToken(
  payload: ApiAccessTokenCreateRequest,
): Promise<ApiAccessTokenCreateResponse> {
  const { data } = await http.post<ApiAccessTokenCreateResponse>('/access-tokens', payload)
  return data
}

/**
 * 吊销指定的访问令牌。
 * @param tokenId 令牌 ID
 */
export async function revokeAccessToken(tokenId: number): Promise<{ message: string }> {
  const { data } = await http.post<{ message: string }>(`/access-tokens/${tokenId}/revoke`)
  return data
}

/**
 * 获取系统支持的所有 Scope 权限清单与操作说明。
 */
export async function listAccessTokenScopes(): Promise<ApiAccessTokenScopeInfo[]> {
  const { data } = await http.get<ApiAccessTokenScopeInfo[]>('/access-tokens/scopes')
  return data
}
