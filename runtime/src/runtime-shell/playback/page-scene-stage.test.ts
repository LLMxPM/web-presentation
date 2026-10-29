/** 文件功能：使用真实 Router 和 Scene 会话验证过渡/资源准备屏障、共享期限、快速切页与静态零副作用。 */
import { h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { gsap } from 'gsap'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getRuntimeSession } from '@/core/router/runtime-session'
import { registerPageSceneDefinition } from '@/core/scene/page-scene-definition'
import { deferred } from '@/core/scene/session-test-helpers'
import type { SceneTaskContext } from '@/core/scene/types'
import { createPageSceneStage } from './page-scene-stage'

const { assets } = vi.hoisted(() => ({ assets: vi.fn() }))
vi.mock('@/core/utils/visual-assets', () => ({ waitForEditorVisualAssets: assets }))
const READY = { ok: true, timedOut: false, total: 0, loaded: 0, failed: [], pending: [], waitedMs: 0 }
const cleanups: Array<() => void> = []
beforeEach(() => { gsap.ticker.sleep(); vi.useFakeTimers(); assets.mockReset(); assets.mockResolvedValue(READY) })
afterEach(() => { cleanups.splice(0).reverse().forEach(cleanup => cleanup()); document.body.innerHTML = ''; gsap.ticker.sleep(); vi.useRealTimers() })

/** 刷新导航、响应式观察和异步 prepare 链路，不消耗页面停留时长。 */
async function flush(): Promise<void> { for (let i = 0; i < 40; i += 1) await Promise.resolve() }

/** 受控资源回执与 void 任务分开，避免把未定义的测试值误当作加载成功。 */
function resourceDeferred() {
  let resolve!: (value: typeof READY) => void
  const promise = new Promise<typeof READY>(yes => { resolve = yes })
  return { promise, resolve }
}

/** 创建双页 Router 与已挂载的画布；页面声明仍由真实登记器负责。 */
async function fixture() {
  const router = createRouter({ history: createMemoryHistory(), routes: ['/a', '/b'].map(path => ({ path, component: { render: () => h('div') } })) })
  await router.push('/a'); await router.isReady()
  const session = getRuntimeSession(router), stage = createPageSceneStage(router)
  session.transitionSettled.value = { path: '/a', generation: 1 }
  const roots = ['/a', '/b'].map(path => {
    const root = document.createElement('section')
    root.className = 'runtime-page-print-source'; root.dataset.runtimeRoutePath = path; document.body.append(root)
    return root
  })
  const runs = [vi.fn(), vi.fn()]
  const defines = roots.map((root, index) => vi.fn(scene => { scene.task({ id: 'content', role: 'blocking', run: runs[index] }) }))
  const unregister = roots.map((root, index) => registerPageSceneDefinition({ root: () => root, define: defines[index] }))
  cleanups.push(...unregister, stage.stop)
  return { router, session, stage, roots, runs, defines, unregister }
}

it('当前稳定页 prepare 只准备任务，宿主显式 start 才播放', async () => {
  const f = await fixture()
  const scene = await f.stage.prepare({ path: '/a', execution: 'presentation', advanceMode: 'scene_end' })
  expect(scene!.getSnapshot().phase).toBe('ready')
  expect(f.defines[0]).toHaveBeenCalledOnce()
  expect(f.runs[0]).not.toHaveBeenCalled()
  expect(assets.mock.calls[0][0]).toMatchObject({ root: f.roots[0], includeAnimations: false })
  await scene!.start()
  expect((await scene!.finished).phase).toBe('completed')
  expect(f.runs[0]).toHaveBeenCalledOnce()
})

it('路由尚未提交时，即使目标页过渡信号到达也不探测或执行 define', async () => {
  const f = await fixture(), navigation = deferred()
  f.router.beforeEach(async to => { if (to.path === '/b') await navigation.promise })
  const preparing = f.stage.prepare({ path: '/b', execution: 'presentation', advanceMode: 'scene_end' })
  await flush()
  f.session.transitionSettled.value = { path: '/b', generation: 2 }; await flush()
  expect(assets).not.toHaveBeenCalled()
  navigation.resolve(); await preparing
  expect(f.router.currentRoute.value.path).toBe('/b')
  expect(f.defines[1]).toHaveBeenCalledOnce()
  expect(f.runs[1]).not.toHaveBeenCalled()
})

it('路由提交仍须等待本次目标过渡，旧路径与原回执不能放行准备', async () => {
  const f = await fixture()
  f.session.transitionSettled.value = { path: '/b', generation: 5 }
  const preparing = f.stage.prepare({ path: '/b', execution: 'presentation', advanceMode: 'scene_end' })
  await flush()
  expect(f.router.currentRoute.value.path).toBe('/b')
  expect(assets).not.toHaveBeenCalled()
  f.session.transitionSettled.value = { path: '/a', generation: 6 }; await flush()
  expect(assets).not.toHaveBeenCalled()
  f.session.transitionSettled.value = { path: '/b', generation: 7 }
  expect((await preparing)!.getSnapshot().phase).toBe('ready')
})

it('过渡层重挂后允许新的较小编号，Scene 不跨宿主比较过渡计数', async () => {
  const f = await fixture()
  f.session.transitionSettled.value = { path: '/b', generation: 30 }
  const preparing = f.stage.prepare({ path: '/b', execution: 'presentation', advanceMode: 'scene_end' })
  await flush()
  f.session.transitionSettled.value = { path: '/b', generation: 1 }
  expect((await preparing)!.getSnapshot().phase).toBe('ready')
})

it('当前页的新过渡尚未完成时不复用旧稳定状态', async () => {
  const f = await fixture()
  f.session.transitionSettled.value = null
  const preparing = f.stage.prepare({ path: '/a', execution: 'presentation', advanceMode: 'scene_end' })
  await flush(); expect(assets).not.toHaveBeenCalled()
  f.session.transitionSettled.value = { path: '/a', generation: 3 }
  expect((await preparing)!.getSnapshot().phase).toBe('ready')
})

it.each(['capture', 'export', 'thumbnail'] as const)('%s 不创建 Scene、导航、资源等待或执行定义', async execution => {
  const f = await fixture(), navigate = vi.spyOn(f.router, 'push')
  expect(await f.stage.prepare({ path: '/b', execution, advanceMode: 'scene_end' })).toBeNull()
  expect(f.stage.getCurrent()).toBeNull()
  expect(navigate).not.toHaveBeenCalled()
  expect(assets).not.toHaveBeenCalled()
  f.defines.forEach(define => expect(define).not.toHaveBeenCalled())
})

it('过渡中退出立即取消准备，迟到 settled 不再探测资源', async () => {
  const f = await fixture()
  const preparing = f.stage.prepare({ path: '/b', execution: 'presentation', advanceMode: 'scene_end' })
  await flush(); f.stage.stop()
  expect(await preparing).toBeNull()
  f.session.transitionSettled.value = { path: '/b', generation: 2 }; await flush()
  expect(assets).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('资源探测不合作时退出仍立即返回，原 Promise 迟到拒绝被消费', async () => {
  const f = await fixture(), waiting = deferred()
  assets.mockReturnValue(waiting.promise)
  const preparing = f.stage.prepare({ path: '/a', execution: 'presentation', advanceMode: 'scene_end' })
  await flush()
  const signal = assets.mock.calls[0][0].signal as AbortSignal
  f.stage.stop(); expect(await preparing).toBeNull()
  expect(signal.aborted).toBe(true)
  waiting.reject(new Error('迟到失败')); await flush()
  expect(f.defines[0]).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('快速从待提交的新页回到原页，不等待旧导航也不复活旧定义', async () => {
  const f = await fixture(), navigation = deferred()
  f.router.beforeEach(async to => { if (to.path === '/b') await navigation.promise })
  const old = f.stage.prepare({ path: '/b', execution: 'presentation', advanceMode: 'scene_end' })
  await flush()
  const current = await f.stage.prepare({ path: '/a', execution: 'presentation', advanceMode: 'scene_end' })
  expect(await old).toBeNull()
  navigation.resolve(); await flush()
  expect(f.router.currentRoute.value.path).toBe('/a')
  expect(f.stage.getCurrent()).toBe(current)
  expect(f.defines[1]).not.toHaveBeenCalled()
})

it('导航、资源和任务准备共享同一次期限，不逐阶段重置预算', async () => {
  const f = await fixture(), navigation = deferred(), resources = resourceDeferred(), taskReady = deferred()
  let task!: SceneTaskContext
  f.unregister[1]()
  cleanups.push(registerPageSceneDefinition({ root: () => f.roots[1], define: scene => {
    scene.task({ id: 'model', role: 'blocking', prepare(context) { task = context; return taskReady.promise }, run() {} })
  } }))
  f.router.beforeEach(async to => { if (to.path === '/b') await navigation.promise })
  assets.mockReturnValue(resources.promise)
  const preparing = f.stage.prepare({ path: '/b', execution: 'presentation', advanceMode: 'scene_end', prepareTimeoutMs: 100 })
  await flush(); await vi.advanceTimersByTimeAsync(40)
  navigation.resolve(); f.session.transitionSettled.value = { path: '/b', generation: 2 }; await flush()
  await vi.advanceTimersByTimeAsync(30); resources.resolve(READY); await flush()
  expect(task.signal.aborted).toBe(false)
  await vi.advanceTimersByTimeAsync(30)
  expect((await preparing)!.getSnapshot().issue?.code).toBe('SCENE_PREPARE_TIMEOUT')
  expect(task.signal.aborted).toBe(true)
  taskReady.resolve(); await flush()
  expect(vi.getTimerCount()).toBe(0)
})

it('导航被守卫拒绝后明确失败，不等准备超时也不使用旧画布', async () => {
  const f = await fixture()
  f.router.beforeEach(to => to.path === '/b' ? false : undefined)
  const scene = await f.stage.prepare({ path: '/b', execution: 'presentation', advanceMode: 'scene_end' })
  expect(scene!.getSnapshot().issue?.code).toBe('SCENE_PAGE_NAVIGATION_FAILED')
  expect(assets).not.toHaveBeenCalled()
  expect(vi.getTimerCount()).toBe(0)
})

it('资源错误不执行定义，也不把资源地址带入 Scene 摘要', async () => {
  const f = await fixture()
  assets.mockResolvedValue({ ...READY, ok: false, failed: [{ type: 'image', url: '/secret/path', message: '任意资源细节' }] })
  const scene = await f.stage.prepare({ path: '/a', execution: 'presentation', advanceMode: 'scene_end' })
  expect(scene!.getSnapshot().issue).toMatchObject({ code: 'SCENE_PAGE_ASSETS_FAILED', message: '页面资源未就绪，无法开始播放。' })
  expect(f.defines[0]).not.toHaveBeenCalled()
})

it('准备期间根节点被替换后不能启动原画布的声明', async () => {
  const f = await fixture(), waiting = resourceDeferred()
  assets.mockReturnValue(waiting.promise)
  const preparing = f.stage.prepare({ path: '/a', execution: 'presentation', advanceMode: 'scene_end' })
  await flush()
  f.roots[0].replaceWith(f.roots[0].cloneNode(true)); waiting.resolve(READY)
  expect((await preparing)!.getSnapshot().issue?.code).toBe('SCENE_PAGE_REPLACED')
  expect(f.defines[0]).not.toHaveBeenCalled()
})

it.each(['manual', 'timer', 'scene_end'] as const)('无 Scene 的普通页使用 %s 时仍执行对应完成约束', async advanceMode => {
  const f = await fixture(); f.unregister[0]()
  const scene = await f.stage.prepare({ path: '/a', execution: 'presentation', advanceMode })
  if (advanceMode === 'scene_end') expect(scene!.getSnapshot().issue?.code).toBe('SCENE_COMPLETION_REQUIRED')
  else {
    expect(scene!.getSnapshot().phase).toBe('ready')
    await scene!.start(); expect(scene!.getSnapshot().phase).toBe('completed')
  }
})
