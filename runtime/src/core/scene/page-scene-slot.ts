/** 文件功能：为一个页面宿主分配本地 generation，替换时先停止旧会话，并在静态执行下跳过 Scene 创建。 */
import type { ExecutionContextKind } from '@/core/execution/execution-policy'
import { isStaticExecution } from '@/core/static-presentation/types'
import { createPageSceneSession } from './page-scene-session'
import type { PageSceneOptions, PageSceneSession } from './types'

type SceneSlotInput = Omit<PageSceneOptions, 'generation' | 'isCurrent'> & { execution: ExecutionContextKind }

/** 宿主独占当前会话；generation 不参与跨窗口协商，也不进入静态身份。 */
export function createPageSceneSlot() {
  let generation = 0
  let current: PageSceneSession | null = null
  /** 创建并准备本次会话；快速切页后只返回仍属于当前 generation 的结果。 */
  async function prepare(input: SceneSlotInput): Promise<PageSceneSession | null> {
    const token = ++generation
    const previous = current
    current = null
    previous?.stop()
    if (token !== generation) return null
    if (isStaticExecution(input.execution)) return null
    const session = createPageSceneSession({ ...input, generation: token, isCurrent: () => generation === token })
    current = session
    await session.prepare()
    return token === generation ? session : null
  }
  /** 退出立即使旧结果失效；不必等待任务 Promise 自行结束。 */
  function stop(): void { generation += 1; const previous = current; current = null; previous?.stop() }
  return { prepare, stop, getCurrent: () => current }
}
