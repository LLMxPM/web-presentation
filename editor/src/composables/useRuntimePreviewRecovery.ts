/**
 * 文件功能：管理预览 iframe 的票据生命周期，支持到期自动续签、失效恢复与标签页激活检测。
 */
import { onMounted, onUnmounted, watch } from 'vue'
import { renewPreviewArtifactAccess } from '@/api/preview'

export interface PreviewRecoveryOptions {
  frameUrl: () => string
  sourceKey: () => unknown
  recover: () => void | Promise<unknown>
  artifactId?: () => string
  onRenewed?: (newUrl: string) => void
  enabled?: () => boolean
  isPending?: () => boolean
  onFailure?: (error: unknown) => void
}

const RECOVERABLE_CODES = new Set(['PREVIEW_CONTEXT_INVALID', 'PREVIEW_CONTEXT_REQUIRED', 'ARTIFACT_NOT_FOUND'])

/** 新 URL 不重置失败链预算；只有成功 ready、用户重试或切换目标才能开始新恢复周期。 */
export function useRuntimePreviewRecovery(options: PreviewRecoveryOptions) {
  let attempted = false
  let pending = false
  let sequence = 0
  let renewTimer: ReturnType<typeof setTimeout> | null = null

  function clearRenewTimer(): void {
    if (renewTimer !== null) {
      clearTimeout(renewTimer)
      renewTimer = null
    }
  }

  /** 为当前票据排期自动续签（到期前 45 秒触发）。 */
  function scheduleAutoRenew(): void {
    clearRenewTimer()
    if (!options.artifactId || !options.onRenewed) return
    const expiresAt = previewTokenExpiresAt(options.frameUrl())
    if (expiresAt === null) return
    const now = Date.now()
    if (expiresAt <= now) return
    const delay = Math.max(3000, expiresAt - now - 45000)
    renewTimer = setTimeout(() => {
      void executeRenewOrRecover()
    }, delay)
  }

  /** 尝试对现有有效 artifact 续签；若失败或已被回收则回退到全量重建。 */
  async function executeRenewOrRecover(): Promise<void> {
    if (pending || options.enabled?.() === false || options.isPending?.()) return
    const currentSequence = sequence
    const artId = options.artifactId?.()
    if (artId && options.onRenewed) {
      pending = true
      try {
        const renewal = await renewPreviewArtifactAccess(artId)
        if (currentSequence === sequence && renewal?.preview_url) {
          options.onRenewed(renewal.preview_url)
          attempted = false
          return
        }
      } catch {
        // 续签失败（如 artifact 已 410 过期或无权限），回退至全量重建
      } finally {
        if (currentSequence === sequence) pending = false
      }
    }
    if (currentSequence === sequence && options.enabled?.() !== false && !options.isPending?.()) {
      tryRecover('PREVIEW_CONTEXT_INVALID')
    }
  }

  /** 根据结构化错误尝试一次重建；忽略重复消息、进行中的创建和不可恢复错误。 */
  function tryRecover(code?: string): boolean {
    if (!code || !RECOVERABLE_CODES.has(code) || attempted || pending
      || options.enabled?.() === false || options.isPending?.()) return false
    attempted = true
    pending = true
    const currentSequence = sequence
    const sourceKey = options.sourceKey()
    void Promise.resolve().then(() => {
      if (currentSequence === sequence && sourceKey === options.sourceKey()
        && options.enabled?.() !== false && !options.isPending?.()) return options.recover()
    }).catch((error: unknown) => {
      if (currentSequence === sequence) options.onFailure?.(error)
    }).finally(() => {
      if (currentSequence === sequence) pending = false
    })
    return true
  }

  /** 用户重试、成功 ready 或切换预览目标时重置预算，并作废旧异步回调。 */
  function reset(): void {
    clearRenewTimer()
    attempted = false
    pending = false
    sequence += 1
    scheduleAutoRenew()
  }

  /** 重新激活标签页时依据票据 exp 检查有效期；若已过期或即将到期立即触发续签。 */
  function handleVisibilityChange(): void {
    if (document.visibilityState !== 'visible') return
    const expiresAt = previewTokenExpiresAt(options.frameUrl())
    if (expiresAt !== null && expiresAt - Date.now() <= 45000) {
      void executeRenewOrRecover()
    }
  }

  watch(options.sourceKey, reset)
  if (options.artifactId) watch(options.artifactId, () => {
    // 自动重建会更换 artifact；作废旧续签回调但保留失败链预算，防止循环重建。
    clearRenewTimer()
    pending = false
    sequence += 1
    scheduleAutoRenew()
  })
  watch(options.frameUrl, scheduleAutoRenew)

  onMounted(() => {
    scheduleAutoRenew()
    document.addEventListener('visibilitychange', handleVisibilityChange)
  })
  onUnmounted(() => {
    clearRenewTimer()
    sequence += 1
    pending = false
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  })
  return { tryRecover, reset, executeRenewOrRecover }
}

/** 读取已获得预览 URL 的有效期；缺失或损坏的票据不触发前置自动刷新。 */
export function previewTokenExpiresAt(frameUrl: string): number | null {
  try {
    const token = new URL(frameUrl).searchParams.get('token') || ''
    const payload = token.split('.')[1]
    if (!payload) return null
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const claims = JSON.parse(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '='))) as { exp?: unknown }
    return typeof claims.exp === 'number' && Number.isFinite(claims.exp) ? claims.exp * 1000 : null
  } catch {
    return null
  }
}

