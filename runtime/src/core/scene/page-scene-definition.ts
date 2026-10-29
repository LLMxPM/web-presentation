/** 文件功能：登记页级 Scene 声明并提供任务/视觉创作上下文；挂载和静态探测不执行定义或创建会话。 */
import { registerManagedPresentation } from '@/core/static-presentation/registry'
import { createGsapSceneTask } from './gsap-scene-task'
import { SceneSessionError, type SceneRegistration, type SceneTask } from './types'
import type { SceneVisualOptions } from './visual-types'

export interface PageSceneAuthoringContext extends Omit<SceneRegistration, 'register' | 'linkSignal'> {
  root: HTMLElement
  task(task: SceneTask): void
  visual(options: Omit<SceneVisualOptions, 'root'>): void
}

export interface PageSceneDefinition {
  root(): HTMLElement | null | undefined
  define(context: PageSceneAuthoringContext): void | Promise<void>
}

export interface RegisteredPageScene {
  root: PageSceneDefinition['root']
  define(context: SceneRegistration): void | Promise<void>
}

const definitions = new Map<symbol, RegisteredPageScene>()

/** 注册只记录根节点 getter 和填充函数，GSAP/媒体任务在宿主 prepare 后才构造。 */
export function registerPageSceneDefinition(options: PageSceneDefinition): () => void {
  const token = Symbol('page-scene')
  const { root, define } = options
  const lifetime = new AbortController()
  const unregisterManaged = registerManagedPresentation(root)
  definitions.set(token, { root, define(context) {
    context.linkSignal(lifetime.signal)
    if (context.signal.aborted) return
    const element = root()
    if (!(element instanceof HTMLElement)) throw new SceneSessionError('SCENE_ROOT_INVALID', 'Scene 缺少已挂载的页面根节点。')
    return define({ root: element, generation: context.generation, signal: context.signal, onCleanup: context.onCleanup,
      task: context.register,
      visual(visual) { context.register(createGsapSceneTask({ ...visual, root: element })) },
    })
  } })
  /** 先移出发现范围，再取消绑定会话；重入清理不能再次发现已经卸载的声明。 */
  return () => {
    definitions.delete(token)
    unregisterManaged()
    lifetime.abort()
  }
}

/** 宿主只发现当前画布的一份页级声明，多条动画由该声明内部登记，避免多个播放所有者。 */
export function findPageSceneDefinition(scope: ParentNode): RegisteredPageScene | null {
  const active = [...definitions.values()].filter(entry => {
    const element = entry.root()
    return element && (element === scope || scope.contains(element))
  })
  if (active.length > 1) throw new SceneSessionError('SCENE_DEFINITION_DUPLICATED', '当前画布只能有一个页级 Scene 声明，多条序列请在该声明中登记。')
  return active[0] ?? null
}
