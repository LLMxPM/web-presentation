/** 文件功能：使用 Backend 生成契约访问 Cookie 授权确认与外部授权管理接口。 */
import { http } from '@/api/http'
import type { OAuthConsentBegin, OAuthConsentDecision, OAuthConsentResult, OAuthConsentView, OAuthGrantList } from '@/types/api.generated'

/** 创建与当前 Cookie 会话绑定的确认请求，保留原始查询参数而不声明用户身份。 */
export async function beginOAuthConsent(payload: OAuthConsentBegin): Promise<OAuthConsentView> {
  const { data } = await http.post<OAuthConsentView>('/v1/account/oauth/consents', payload)
  return data
}

/** 一次性批准或拒绝；响应回调只能在服务器提交后返回。 */
export async function decideOAuthConsent(requestId: string, payload: OAuthConsentDecision): Promise<OAuthConsentResult> {
  const { data } = await http.post<OAuthConsentResult>(`/v1/account/oauth/consents/${requestId}/decision`, payload)
  return data
}

/** 列出本人授权及服务启用状态，不查询或缓存原始协议 Token。 */
export async function listOAuthGrants(): Promise<OAuthGrantList> {
  const { data } = await http.get<OAuthGrantList>('/v1/account/oauth/grants')
  return data
}

/** 幂等撤销整条本人授权；已经接受的后台任务继续遵循领域队列规则。 */
export async function revokeOAuthGrant(grantId: string): Promise<void> {
  await http.post(`/v1/account/oauth/grants/${grantId}/revoke`)
}
