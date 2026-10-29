/** 文件功能：验证页级声明的按需注册、画布隔离、卸载取消和独立静态要求，不执行真实浏览器。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { registerStaticPresentation, settleStaticPresentation } from '@/core/static-presentation/registry'
import { findPageSceneDefinition, registerPageSceneDefinition } from './page-scene-definition'
import { createPageSceneSlot } from './page-scene-slot'
import { deferred, flushScenePromises } from './session-test-helpers'
import type { SceneTaskContext } from './types'

const cleanups: Array<() => void> = []

/** 创建已挂载的独立画布，用于检查相同选择器不会混淆页级声明。 */
function root() {
  const element = document.createElement('section')
  document.body.append(element)
  return element
}

afterEach(() => { cleanups.splice(0).reverse().forEach(cleanup => cleanup()); document.body.innerHTML = '' })

describe('PageSceneDefinition', () => {
  it('登记时不执行 define；prepare 动态注册 blocking，start 才执行回调', async () => {
    const element = root(), slot = createPageSceneSlot(), run = vi.fn(), prepare = vi.fn()
    const define = vi.fn(context => {
      expect(context.root).toBe(element)
      expect(context.generation).toBeGreaterThan(0)
      context.task({ id: 'callback', role: 'blocking', prepare, run })
    })
    cleanups.push(registerPageSceneDefinition({ root: () => element, define }), slot.stop)
    expect(define).not.toHaveBeenCalled()
    const entry = findPageSceneDefinition(element)!
    const session = await slot.prepare({ execution: 'presentation', advanceMode: 'scene_end', define: entry.define })
    expect(define).toHaveBeenCalledOnce()
    expect(prepare).toHaveBeenCalledOnce()
    expect(run).not.toHaveBeenCalled()
    await session!.start()
    expect((await session!.finished).phase).toBe('completed')
    expect(run).toHaveBeenCalledOnce()
  })

  it('只发现当前画布声明，空根和卸载声明不污染其它页面', () => {
    const first = root(), second = root()
    const a = registerPageSceneDefinition({ root: () => first, define() {} })
    cleanups.push(a, registerPageSceneDefinition({ root: () => second, define() {} }), registerPageSceneDefinition({ root: () => null, define() {} }))
    expect(findPageSceneDefinition(first)!.root()).toBe(first)
    expect(findPageSceneDefinition(second)!.root()).toBe(second)
    a(); a()
    expect(findPageSceneDefinition(first)).toBeNull()
    expect(findPageSceneDefinition(second)).not.toBeNull()
  })

  it('同一画布的重复或嵌套声明明确拒绝，不随机挑选一个所有者', () => {
    const element = root(), nested = document.createElement('div'); element.append(nested)
    cleanups.push(registerPageSceneDefinition({ root: () => element, define() {} }),
      registerPageSceneDefinition({ root: () => nested, define() {} }))
    expect(() => findPageSceneDefinition(element)).toThrow('只能有一个页级 Scene')
  })

  it('声明卸载立即中止正在运行的任务，迟到完成不改变停止状态', async () => {
    const element = root(), slot = createPageSceneSlot(), pending = deferred(), cleanup = vi.fn()
    let context!: SceneTaskContext
    const unregister = registerPageSceneDefinition({ root: () => element, define: scene => {
      scene.task({ id: 'voice', role: 'blocking', run(value) { context = value; value.onCleanup(cleanup); return pending.promise } })
    } })
    cleanups.push(unregister, slot.stop)
    const session = await slot.prepare({ execution: 'presentation', advanceMode: 'scene_end', define: findPageSceneDefinition(element)!.define })
    await session!.start()
    unregister()
    expect(context.signal.aborted).toBe(true)
    expect(cleanup).toHaveBeenCalledOnce()
    expect(findPageSceneDefinition(element)).toBeNull()
    pending.resolve(); await flushScenePromises()
    expect(session!.getSnapshot().phase).toBe('stopped')
  })

  it('卸载中断尚未结束的 define，迟到清理立即执行且不再注册任务', async () => {
    const element = root(), slot = createPageSceneSlot(), pending = deferred(), cleanup = vi.fn(), run = vi.fn()
    const unregister = registerPageSceneDefinition({ root: () => element, define: async scene => {
      await pending.promise
      scene.onCleanup(cleanup)
      scene.task({ id: 'late', role: 'blocking', run })
    } })
    cleanups.push(unregister, slot.stop)
    const preparing = slot.prepare({ execution: 'presentation', advanceMode: 'scene_end', define: findPageSceneDefinition(element)!.define })
    await flushScenePromises()
    unregister()
    expect((await preparing)!.getSnapshot().phase).toBe('stopped')
    pending.resolve(); await flushScenePromises()
    expect(cleanup).toHaveBeenCalledOnce()
    expect(run).not.toHaveBeenCalled()
  })

  it('静态模式继续要求同根独立声明，同时不执行 Scene 定义', async () => {
    const element = root(), define = vi.fn()
    cleanups.push(registerPageSceneDefinition({ root: () => element, define }))
    expect((await settleStaticPresentation(element)).status).toBe('unsupported')
    cleanups.push(registerStaticPresentation({ root: () => element, ready: Promise.resolve({ status: 'ready', code: null, message: null }) }))
    expect((await settleStaticPresentation(element)).status).toBe('ready')
    const slot = createPageSceneSlot()
    expect(await slot.prepare({ execution: 'capture', advanceMode: 'scene_end', define: findPageSceneDefinition(element)!.define })).toBeNull()
    expect(define).not.toHaveBeenCalled()
  })

  it('旧声明卸载后保存的入口不能重新执行，已卸载根也不能继续 prepare', async () => {
    const element = root(), define = vi.fn(), slot = createPageSceneSlot()
    const unregister = registerPageSceneDefinition({ root: () => element, define })
    cleanups.push(unregister, slot.stop)
    const saved = findPageSceneDefinition(element)!
    unregister()
    const session = await slot.prepare({ execution: 'presentation', advanceMode: 'manual', define: saved.define })
    expect(session!.getSnapshot().phase).toBe('stopped')
    expect(define).not.toHaveBeenCalled()
  })

  it('准备前根节点失效时明确失败，不能把任务挂到已经移走的画布', async () => {
    const element = root(), define = vi.fn(), slot = createPageSceneSlot()
    let current: HTMLElement | null = element
    cleanups.push(registerPageSceneDefinition({ root: () => current, define }), slot.stop)
    const saved = findPageSceneDefinition(element)!
    current = null
    const session = await slot.prepare({ execution: 'presentation', advanceMode: 'manual', define: saved.define })
    expect(session!.getSnapshot().issue?.code).toBe('SCENE_ROOT_INVALID')
    expect(define).not.toHaveBeenCalled()
  })
})
