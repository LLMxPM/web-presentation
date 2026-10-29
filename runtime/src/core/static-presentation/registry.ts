/** 文件功能：按页面根登记静态声明和受托管动画，聚合目标画布的独立静态就绪结果。 */
import { staticReceipt, STATIC_PRESENTATION_TIMEOUT, type StaticPresentationReceipt } from './types'

interface StaticEntry {
  root(): HTMLElement | null | undefined
  ready: Promise<StaticPresentationReceipt>
}

const declarations = new Map<symbol, StaticEntry>()
const managed = new Map<symbol, StaticEntry['root']>()

/** 注册独立声明；调用方必须在实例卸载时注销。 */
export function registerStaticPresentation(entry: StaticEntry): () => void {
  const key = Symbol('static-presentation')
  declarations.set(key, entry)
  return () => { declarations.delete(key) }
}

/** 受托管动画只登记声明要求；静态模式不得为此创建播放执行器。 */
export function registerManagedPresentation(root: StaticEntry['root']): () => void {
  const key = Symbol('managed-presentation')
  managed.set(key, root)
  return () => { managed.delete(key) }
}

/** 只处理当前画布，旁边的缩略图及卸载实例不影响本次结果。 */
export async function settleStaticPresentation(scope: ParentNode, timeoutMs = 25000): Promise<StaticPresentationReceipt> {
  const contains = (element: HTMLElement | null | undefined): element is HTMLElement => Boolean(element && (element === scope || scope.contains(element)))
  const active = [...declarations].filter(([, entry]) => contains(entry.root()))
  for (const root of managed.values()) {
    const element = root()
    if (contains(element) && !active.some(([, entry]) => entry.root() === element)) {
      return staticReceipt('unsupported', '受托管动画页面必须通过 useStaticPresentation.v1 声明静态呈现。')
    }
  }
  const roots = new Set<HTMLElement>()
  for (const [, entry] of active) {
    const element = entry.root()!
    if (roots.has(element)) return staticReceipt('failed', '同一页面根只能注册一个静态呈现声明。')
    roots.add(element)
  }
  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    const results = await Promise.race([
      Promise.all(active.map(async ([key, entry]) => {
        try {
          const receipt = await entry.ready
          return declarations.has(key) && contains(entry.root()) ? receipt : staticReceipt('ready')
        } catch {
          return declarations.has(key) ? staticReceipt('failed', '静态呈现准备失败。') : staticReceipt('ready')
        }
      })),
      new Promise<StaticPresentationReceipt[]>(resolve => {
        timer = setTimeout(() => resolve([staticReceipt('failed', '静态呈现准备超时。', STATIC_PRESENTATION_TIMEOUT)]), Math.max(1, timeoutMs))
      }),
    ])
    return results.find(result => result.status === 'failed')
      ?? results.find(result => result.status === 'unsupported') ?? staticReceipt('ready')
  } finally {
    clearTimeout(timer)
  }
}
