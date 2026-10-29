/** 文件功能：为 Scene 会话单测提供受控 Promise 与任务构造，不依赖浏览器、动画库或真实媒体。 */
import { vi } from 'vitest'
import { createPageSceneSession } from './page-scene-session'
import type { PageSceneOptions, SceneTask } from './types'

/** 手动决定任务完成/失败时刻，验证实际完成依赖和迟到结果。 */
export function deferred() {
  let resolve!: () => void, reject!: (error: unknown) => void
  const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

/** 默认是同步有限任务；调用方只声明当前用例关注的差异。 */
export function task(id: string, extra: Partial<SceneTask> = {}): SceneTask {
  return { id, role: 'blocking', run: vi.fn(), ...extra }
}

/** 使用相同生产入口构造会话，不复制调度或生命周期逻辑。 */
export function scene(tasks: SceneTask[], options: Partial<PageSceneOptions> = {}) {
  return createPageSceneSession({ generation: 1, advanceMode: 'scene_end', now: () => Date.now(),
    define: context => tasks.forEach(entry => context.register(entry)), ...options })
}

/** 排空短 Promise 链；不推进真实时间，也不等待真实资源。 */
export async function flushScenePromises(): Promise<void> {
  for (let index = 0; index < 12; index += 1) await Promise.resolve()
}
