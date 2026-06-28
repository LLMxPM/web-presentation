/**
 * 文件功能：管理智能体 run 级 SSE AbortController 生命周期。
 */

/**
 * 创建 runId 到 AbortController 的轻量注册表，避免面板直接维护 Map 细节。
 */
export function useAgentStreamControllers() {
  const controllersByRun = new Map<string, AbortController>()

  /**
   * 判断指定 run 是否已有活跃流控制器。
   */
  function hasStreamAbortController(runId: string) {
    return controllersByRun.has(runId)
  }

  /**
   * 为一次流式请求创建控制器；同 runId 的旧控制器会被替换。
   */
  function createStreamAbortController(runId: string) {
    const controller = new AbortController()
    controllersByRun.set(runId, controller)
    return controller
  }

  /**
   * 读取当前 run 的控制器，用于异常收尾阶段按需清理。
   */
  function getStreamAbortController(runId: string) {
    return controllersByRun.get(runId) ?? null
  }

  /**
   * 只清理当前请求对应的控制器，避免误删后续新请求。
   */
  function clearStreamAbortController(runId: string, controller: AbortController) {
    if (controllersByRun.get(runId) === controller) {
      controllersByRun.delete(runId)
    }
  }

  /**
   * 组件销毁时中断所有未完成流，并清空注册表。
   */
  function abortAllStreamControllers() {
    for (const controller of controllersByRun.values()) {
      if (!controller.signal.aborted) {
        controller.abort()
      }
    }
    controllersByRun.clear()
  }

  return {
    abortAllStreamControllers,
    clearStreamAbortController,
    createStreamAbortController,
    getStreamAbortController,
    hasStreamAbortController,
  }
}
