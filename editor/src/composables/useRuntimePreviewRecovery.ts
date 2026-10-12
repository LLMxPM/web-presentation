/**
 * 文件功能：限制预览失效自动恢复次数，并在重新激活标签页时依据票据 exp 检查有效期。
 */
import { onMounted, onUnmounted, watch } from 'vue'

interface PreviewRecoveryOptions {
  frameUrl: () => string
  sourceKey: () => unknown
  recover: () => void | Promise<unknown>
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
    attempted = false
    pending = false
    sequence += 1
  }

  /** 重新激活标签页时只把 JWT exp 作为刷新提示，权限仍由创建接口校验。 */
  function handleVisibilityChange(): void {
    if (document.visibilityState !== 'visible') return
    const expiresAt = previewTokenExpiresAt(options.frameUrl())
    if (expiresAt !== null && expiresAt <= Date.now()) tryRecover('PREVIEW_CONTEXT_INVALID')
  }

  watch(options.sourceKey, reset)
  onMounted(() => document.addEventListener('visibilitychange', handleVisibilityChange))
  onUnmounted(() => {
    reset()
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  })
  return { tryRecover, reset }
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
