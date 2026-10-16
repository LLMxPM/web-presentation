/**
 * 文件功能：管理预览 iframe 的票据生命周期，支持到期自动续签、失效恢复与标签页激活检测。
 */
import axios from 'axios'
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

/**
 * 会话级注册表：记录所有已挂载预览的续签取消函数。
 * 登出或登录态失效时统一调用，避免残留定时器在下一个会话里带着旧票据发起续签请求。
 */
const activeRenewCancels = new Set<() => void>()

/**
 * 会话结束时清理所有活跃预览的续签计时器与在途回调。
 * 组件卸载仍是常规清理路径；本函数只覆盖"登出到视图卸载"之间的窗口。
 */
export function clearAllPreviewRenewTimers(): void {
  for (const cancel of [...activeRenewCancels]) {
    cancel()
  }
}

/**
 * 终态失效错误码集合（预览 artifact 过期/缺失、文件访问类授权拒绝）。
 * 只匹配错误码文本本身，不对消息中的状态码数字做子串猜测。
 */
const TERMINAL_ERROR_CODE_PATTERN = /(?:PREVIEW_ARTIFACT_EXPIRED|ARTIFACT_NOT_FOUND|FILE_ACCESS_[A-Z]*)/

/**
 * 判断预览续签异常是否属于确定性终态失效（如 410 过期、401/403 越权或 404 缺失）。
 * 只有终态失效才触发高成本全量重建并消耗预算；网络波动或服务重启应退避重试。
 */
function isArtifactRenewalTerminalError(error: unknown): boolean {
  if (!error) return false
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    if (status === 410 || status === 404 || status === 401 || status === 403) {
      return true
    }
    const code = (error.response?.data as { code?: string } | undefined)?.code
    return typeof code === 'string' && TERMINAL_ERROR_CODE_PATTERN.test(code)
  }
  // 非 Axios 错误只接受错误码文本；"timeout of 10410ms" 这类含数字的消息必须按可重试处理。
  return error instanceof Error && TERMINAL_ERROR_CODE_PATTERN.test(error.message)
}

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

  /** 会话结束：停止本实例的续签排期并作废在途回调，不影响组件自身状态。 */
  function cancelRenewForSession(): void {
    clearRenewTimer()
    pending = false
    sequence += 1
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
    let shouldRecover = false
    if (artId && options.onRenewed) {
      pending = true
      try {
        const renewal = await renewPreviewArtifactAccess(artId)
        if (currentSequence === sequence && renewal?.preview_url) {
          options.onRenewed(renewal.preview_url)
          attempted = false
          return
        }
      } catch (error: unknown) {
        // 区分错误类型：仅在 artifact 明确过期（410）、无权限（401/403）或不存在（404）时降级全量重建
        const isTerminal = isArtifactRenewalTerminalError(error)
        if (isTerminal) {
          shouldRecover = true
        } else if (currentSequence === sequence && options.enabled?.() !== false) {
          // 瞬时网络异常或服务端重启：按退避重试排期，不消耗本轮全量重建预算
          clearRenewTimer()
          renewTimer = setTimeout(() => {
            void executeRenewOrRecover()
          }, 10000)
        }
      } finally {
        if (currentSequence === sequence) pending = false
      }
    } else {
      shouldRecover = true
    }

    if (shouldRecover && currentSequence === sequence && options.enabled?.() !== false && !options.isPending?.()) {
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
    activeRenewCancels.add(cancelRenewForSession)
    scheduleAutoRenew()
    document.addEventListener('visibilitychange', handleVisibilityChange)
  })
  onUnmounted(() => {
    activeRenewCancels.delete(cancelRenewForSession)
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

