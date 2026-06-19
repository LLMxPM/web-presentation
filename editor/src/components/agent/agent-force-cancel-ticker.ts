/**
 * 文件功能：封装智能体停止中状态的强制结束可用性计时器。
 */
import { ref } from 'vue'

/**
 * 管理强制结束按钮需要的当前时间 tick，避免面板持有定时器细节。
 */
export function useAgentForceCancelTicker() {
  const forceCancelTick = ref(Date.now())
  let forceCancelTimer: number | null = null

  /**
   * 启动强制结束按钮的可用状态刷新计时。
   */
  function startForceCancelTicker() {
    if (forceCancelTimer !== null) {
      return
    }
    forceCancelTick.value = Date.now()
    forceCancelTimer = window.setInterval(() => {
      forceCancelTick.value = Date.now()
    }, 1000)
  }

  /**
   * 停止强制结束状态刷新计时。
   */
  function stopForceCancelTicker() {
    if (forceCancelTimer === null) {
      return
    }
    window.clearInterval(forceCancelTimer)
    forceCancelTimer = null
  }

  return {
    forceCancelTick,
    startForceCancelTicker,
    stopForceCancelTicker,
  }
}
