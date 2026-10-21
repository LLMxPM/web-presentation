/** 文件功能：登记页面时间轴初始化和静态准备任务，让渲染校验等待并收集有界内容错误。 */
import { toMotionError } from './errors'

export interface MotionReadinessEntry {
  root(): HTMLElement | null | undefined
  ready: Promise<void>
  prepareStatic(): Promise<void>
}

const entries = new Map<symbol, MotionReadinessEntry>()

/** 每个页面实例独立登记；卸载必须注销，不能把历史页面错误带到新页面。 */
export function registerMotionReadiness(entry: MotionReadinessEntry): () => void {
  const key = Symbol('motion-readiness')
  entries.set(key, entry)
  return () => { entries.delete(key) }
}

/** 只等待目标画布中的实例；静态上下文准备并固化 poster，全程不播放媒体。 */
export async function settleMotionReadiness(root: ParentNode, prepareStatic: boolean) {
  const belongsToRoot = (entry: MotionReadinessEntry): boolean => {
    const element = entry.root()
    return !element || element === root || root.contains(element)
  }
  const results = await Promise.all([...entries].map(async ([key, entry]) => {
    try {
      if (!belongsToRoot(entry)) return null
      await entry.ready
      if (!entries.has(key) || !belongsToRoot(entry)) return null
      if (prepareStatic) await entry.prepareStatic()
      return null
    } catch (error) {
      return entries.has(key) ? toMotionError(error).toDiagnostic() : null
    }
  }))
  return results.filter(result => result !== null).slice(0, 20)
}
