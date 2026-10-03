/** 文件功能：管理确认页的一次性内存 nonce、权限选择、过期与明确批准/拒绝动作。 */
import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import { beginOAuthConsent, decideOAuthConsent } from '@/api/oauth'
import { getErrorMessage } from '@/api/http'
import type { OAuthConsentView } from '@/types/api.generated'
import { navigateOAuthCallback } from '@/utils/oauth'
import { parseApiDate } from '@/utils/timezone'

/** 查询变化时丢弃旧确认状态；nonce 仅保存在本组件生命周期内。 */
export function useOAuthConsent(query: Ref<string>) {
  const view = ref<OAuthConsentView | null>(null)
  const loading = ref(false)
  const submitting = ref(false)
  const error = ref('')
  const scopes = ref<string[]>([])
  const workspaceIds = ref<number[]>([])
  const now = ref(Date.now())
  let generation = 0
  const timer = window.setInterval(() => { now.value = Date.now() }, 1000)
  onUnmounted(() => { generation += 1; window.clearInterval(timer); view.value = null })
  const expired = computed(() => {
    if (!view.value) return false
    const deadline = parseApiDate(view.value.expires_at).getTime()
    return !Number.isFinite(deadline) || deadline <= now.value
  })
  const canApprove = computed(() => !!view.value && !expired.value && scopes.value.length > 0 && workspaceIds.value.length > 0 && !submitting.value)

  /** 原始 URL 只用于向服务端准备确认，网络失败不产生默认批准。 */
  async function load(rawQuery: string) {
    const current = ++generation
    view.value = null
    scopes.value = []
    workspaceIds.value = []
    error.value = ''
    loading.value = false
    submitting.value = false
    if (!rawQuery) {
      error.value = '缺少授权请求，请从 ChatGPT 发起连接。'
      return
    }
    loading.value = true
    try {
      const result = await beginOAuthConsent({ authorization_query: rawQuery })
      if (current !== generation) return
      view.value = result
      scopes.value = result.scopes.map(item => item.scope).filter(scope => scope.endsWith(':read'))
    } catch (cause) {
      if (current === generation) error.value = getErrorMessage(cause, '无法准备授权，请从 ChatGPT 重新连接。')
    } finally {
      if (current === generation) loading.value = false
    }
  }
  watch(query, load, { immediate: true })

  /** 明确点击后才消费 nonce；拒绝不受空间/权限选择限制。 */
  async function decide(approved: boolean) {
    const pending = view.value
    if (!pending || submitting.value || expired.value || (approved && !canApprove.value)) return
    submitting.value = true
    const current = generation
    error.value = ''
    try {
      const result = await decideOAuthConsent(pending.request_id, {
        csrf_token: pending.csrf_token, approved,
        scopes: approved ? [...scopes.value] : [],
        workspace_ids: approved ? [...workspaceIds.value] : [],
      })
      if (current !== generation) return
      view.value = null
      navigateOAuthCallback(result.redirect_uri)
    } catch (cause) {
      if (current === generation) error.value = getErrorMessage(cause, '授权未完成，请从 ChatGPT 重新连接。')
    } finally {
      if (current === generation) submitting.value = false
    }
  }

  /** 选择只允许服务端本次公布的权限；写权限没有隐式默认选中。 */
  function selectScope(scope: string, checked: boolean | 'indeterminate') {
    if (!view.value?.scopes.some(item => item.scope === scope)) return
    scopes.value = scopes.value.filter(item => item !== scope)
    if (checked === true) scopes.value.push(scope)
  }

  /** 选择具体空间，不引入所有空间或未来空间通配选项。 */
  function selectWorkspace(id: number, checked: boolean | 'indeterminate') {
    if (!view.value?.workspaces.some(item => item.id === id)) return
    workspaceIds.value = workspaceIds.value.filter(item => item !== id)
    if (checked === true) workspaceIds.value.push(id)
  }
  return { view, loading, submitting, error, scopes, workspaceIds, expired, canApprove, decide, selectScope, selectWorkspace }
}
