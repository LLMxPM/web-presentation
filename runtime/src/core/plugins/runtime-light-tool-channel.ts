/**
 * 文件用途：为可视化编辑与资源比例测量等轻量内部工具提供独立有界并发通道，
 * 保证短请求不排在完整编译诊断之后，并在超限时返回结构化 429/504。
 */

import {
  RuntimeViteTaskScheduler,
  RuntimeViteTaskSchedulerError,
} from './runtime-vite-task-scheduler'
import { resolveLightToolTimeoutMs, type RuntimeViteTaskKind } from './runtime-role'

const LIGHT_KIND: RuntimeViteTaskKind = 'light'

let sharedChannel: RuntimeViteTaskScheduler | null = null

/**
 * 获取进程内共享的轻量工具调度通道；仅使用 light 类别容量。
 */
export function getRuntimeLightToolChannel(): RuntimeViteTaskScheduler {
  if (!sharedChannel) {
    sharedChannel = new RuntimeViteTaskScheduler({
      kinds: {
        light: {
          // 并发/排队预算从 RUNTIME_LIGHT_TOOL_* 解析，见 resolveRuntimeKindBudget('light')。
        },
      },
    })
  }
  return sharedChannel
}

/**
 * 重置共享轻量通道（测试用）。
 */
export function resetRuntimeLightToolChannel(): void {
  sharedChannel?.close()
  sharedChannel = null
}

/**
 * 在独立轻量通道内执行内部工具任务，并施加单次执行时限。
 * @param run 轻量工具实现；不得同步长时间阻塞事件循环
 * @param timeoutMs 单次执行时限，缺省读 RUNTIME_LIGHT_TOOL_TIMEOUT_MS
 */
export async function runWithLightToolBudget<T>(
  run: () => Promise<T>,
  timeoutMs?: number,
): Promise<T> {
  const channel = getRuntimeLightToolChannel()
  return channel.schedule(LIGHT_KIND, () => runWithLightToolTimeout(run, timeoutMs ?? resolveLightToolTimeoutMs()))
}

/**
 * 施加轻量工具执行时限；超时抛出结构化 504。
 */
async function runWithLightToolTimeout<T>(run: () => Promise<T>, timeoutMs: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      run(),
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new RuntimeLightToolTimeoutError(timeoutMs)), timeoutMs)
      }),
    ])
  } finally {
    if (timer) {
      clearTimeout(timer)
    }
  }
}

/**
 * 轻量工具超过执行时限时返回的可重试基础设施错误。
 */
export class RuntimeLightToolTimeoutError extends Error {
  statusCode = 504
  code = 'RUNTIME_LIGHT_TOOL_TIMEOUT'

  constructor(timeoutMs: number) {
    super(`Runtime 轻量内部工具超过 ${timeoutMs}ms 执行时限。`)
    this.name = 'RuntimeLightToolTimeoutError'
  }
}

export { RuntimeViteTaskSchedulerError }
