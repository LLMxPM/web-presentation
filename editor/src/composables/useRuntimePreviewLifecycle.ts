/**
 * 文件功能：封装页面 Runtime 预览的生成、加载、弱网、超时、成功与失败状态生命周期。
 */
import { onUnmounted, ref } from 'vue'

import type { RuntimePreviewStatus } from '@/types/runtime-preview'

const DEFAULT_SLOW_DELAY_MS = 8000
const DEFAULT_TIMEOUT_MS = 30000

export interface RuntimePreviewLifecycleOptions {
  slowDelayMs?: number
  timeoutMs?: number
  slowMessage?: string
  timeoutMessage?: string
}

/**
 * 创建可接收迟到 ready 的预览生命周期；超时只更新 UI，不销毁实际 iframe。
 * @param options 阈值与提示文本
 */
export function useRuntimePreviewLifecycle(options: RuntimePreviewLifecycleOptions = {}) {
  const status = ref<RuntimePreviewStatus>('idle')
  const message = ref('')
  let lifecycleSeq = 0
  let slowTimer: number | null = null
  let timeoutTimer: number | null = null

  /** 启动 artifact 生成或 iframe 加载周期。 */
  function start(nextStatus: 'generating' | 'loading'): void {
    clearTimers()
    const currentSeq = lifecycleSeq + 1
    lifecycleSeq = currentSeq
    status.value = nextStatus
    message.value = ''
    slowTimer = window.setTimeout(() => {
      if (currentSeq !== lifecycleSeq) return
      status.value = 'slow'
      message.value = options.slowMessage || '网络较慢或浏览器正在建立冷缓存，Runtime 仍在继续加载。'
    }, options.slowDelayMs ?? DEFAULT_SLOW_DELAY_MS)
    timeoutTimer = window.setTimeout(() => {
      if (currentSeq !== lifecycleSeq) return
      status.value = 'error'
      message.value = options.timeoutMessage || '页面预览加载超过 30 秒，可以重新生成预览。'
      clearTimers()
    }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS)
  }

  /** 接收当前 artifact 的 ready；即使 UI 已超时也允许恢复。 */
  function markReady(): void {
    lifecycleSeq += 1
    clearTimers()
    status.value = 'ready'
    message.value = ''
  }

  /** 记录 Runtime 或 artifact 创建错误。 */
  function markError(errorMessage: string): void {
    lifecycleSeq += 1
    clearTimers()
    status.value = 'error'
    message.value = errorMessage || '页面预览加载失败。'
  }

  /** 回到无预览状态并使此前计时器失效。 */
  function reset(): void {
    lifecycleSeq += 1
    clearTimers()
    status.value = 'idle'
    message.value = ''
  }

  /** 释放生命周期内部计时器。 */
  function dispose(): void {
    lifecycleSeq += 1
    clearTimers()
  }

  /** 清理两个等待阈值计时器。 */
  function clearTimers(): void {
    if (slowTimer !== null) window.clearTimeout(slowTimer)
    if (timeoutTimer !== null) window.clearTimeout(timeoutTimer)
    slowTimer = null
    timeoutTimer = null
  }

  onUnmounted(dispose)

  return { status, message, start, markReady, markError, reset, dispose }
}

