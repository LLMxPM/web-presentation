/**
 * 文件用途：为预览 HTML/模块转换提供独立有界并发通道，使 RUNTIME_PREVIEW_VITE_TASK_* 真正生效，
 * 并向健康检查暴露排队年龄与活跃数（T1-2 / T0-3 门槛）。
 */

import { registerRuntimeCapacityProvider } from './runtime-capacity'
import type { RuntimeViteTaskKind } from './runtime-role'
import {
  RuntimeViteTaskScheduler,
  RuntimeViteTaskSchedulerError,
} from './runtime-vite-task-scheduler'

const PREVIEW_KIND: RuntimeViteTaskKind = 'preview'

let sharedPreviewScheduler: RuntimeViteTaskScheduler | null = null
let unregisterCapacity: (() => void) | null = null

/**
 * 获取进程内共享的预览调度器；仅使用 preview 类别容量。
 */
export function getRuntimePreviewScheduler(): RuntimeViteTaskScheduler {
  if (!sharedPreviewScheduler) {
    sharedPreviewScheduler = new RuntimeViteTaskScheduler({
      kinds: {
        preview: {
          // 并发/排队预算从 RUNTIME_PREVIEW_VITE_TASK_* / RUNTIME_VITE_TASK_* 解析。
        },
      },
    })
    try {
      unregisterCapacity = registerRuntimeCapacityProvider('viteTaskScheduler', () => ({
        ...sharedPreviewScheduler!.snapshot(),
      }))
    } catch {
      // 测试环境可能 mock 掉 capacity 模块；调度本身不受影响。
      unregisterCapacity = null
    }
  }
  return sharedPreviewScheduler
}

/**
 * 重置共享预览调度器（测试用）。
 */
export function resetRuntimePreviewScheduler(): void {
  unregisterCapacity?.()
  unregisterCapacity = null
  sharedPreviewScheduler?.close()
  sharedPreviewScheduler = null
}

/**
 * 在预览执行预算内运行 HTML/模块转换任务。
 * @param run 预览处理函数
 */
export function runWithPreviewBudget<T>(run: () => Promise<T>): Promise<T> {
  return getRuntimePreviewScheduler().schedule(PREVIEW_KIND, run)
}

export { RuntimeViteTaskSchedulerError }
