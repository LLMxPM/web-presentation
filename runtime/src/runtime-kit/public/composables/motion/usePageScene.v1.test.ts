/** 文件功能：验证 Vue 页面只声明 Scene、非静态 prepare 才注册任务，以及卸载和静态呈现的真实接线。 */
import { createApp, defineComponent, h, ref } from 'vue'
import { gsap } from 'gsap'
import { afterEach, expect, it, vi } from 'vitest'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { settleStaticPresentation } from '@/core/static-presentation/registry'
import { findPageSceneDefinition } from '@/core/scene/page-scene-definition'
import { createPageSceneSlot } from '@/core/scene/page-scene-slot'
import { deferred, flushScenePromises } from '@/core/scene/session-test-helpers'
import type { SceneTaskContext } from '@/core/scene/types'
import { useStaticPresentation } from '@/runtime-kit/public/composables/static/useStaticPresentation.v1'
import { usePageScene } from './usePageScene.v1'

const cleanups: Array<() => void> = []

afterEach(() => {
  cleanups.splice(0).reverse().forEach(cleanup => cleanup())
  document.body.innerHTML = ''
  resetRuntimeExecutionForTests()
})

/** 挂载真实 setup 组合式声明，使用异步假任务模拟旁白或页面自有动画。 */
function mount(context = 'presentation', declareStatic = false) {
  initializeRuntimeExecution(`?runtimeExecution=${context}`)
  const host = document.createElement('div'); document.body.append(host)
  const pending = deferred(), run = vi.fn((value: SceneTaskContext) => { active = value; return pending.promise })
  const define = vi.fn(scene => { scene.task({ id: 'managed', role: 'blocking', run }) })
  let active: SceneTaskContext
  const app = createApp(defineComponent({ setup() {
    const root = ref<HTMLElement | null>(null)
    usePageScene({ root, define })
    if (declareStatic) useStaticPresentation({ root, mode: 'default' })
    return () => h('section', { ref: root }, '独立可读内容')
  } }))
  app.mount(host)
  const unmount = () => { if (host.hasChildNodes()) app.unmount() }
  cleanups.push(unmount)
  return { host, define, run, pending, unmount, getActive: () => active }
}

it('挂载和发现不构造时间轴，用户播放 prepare 后才执行 define，卸载立即停止', async () => {
  const timeline = vi.spyOn(gsap, 'timeline')
  const page = mount()
  const entry = findPageSceneDefinition(page.host)!
  expect(entry).not.toBeNull()
  expect(page.define).not.toHaveBeenCalled()
  expect(timeline).not.toHaveBeenCalled()
  const slot = createPageSceneSlot(); cleanups.push(slot.stop)
  const session = await slot.prepare({ execution: 'interactive-preview', advanceMode: 'manual', define: entry.define })
  expect(page.define).toHaveBeenCalledOnce()
  expect(page.run).not.toHaveBeenCalled()
  await session!.start()
  expect(page.run).toHaveBeenCalledOnce()
  page.unmount()
  expect(page.getActive().signal.aborted).toBe(true)
  expect(session!.getSnapshot().phase).toBe('stopped')
  expect(findPageSceneDefinition(page.host)).toBeNull()
  page.pending.resolve(); await flushScenePromises()
  expect(session!.getSnapshot().phase).toBe('stopped')
})

it.each(['capture', 'export', 'thumbnail'] as const)('%s 挂载只要求独立静态声明，不执行 Scene 或构造 GSAP', async execution => {
  const timeline = vi.spyOn(gsap, 'timeline'), page = mount(execution, true)
  const slot = createPageSceneSlot(); cleanups.push(slot.stop)
  const entry = findPageSceneDefinition(page.host)!
  expect((await settleStaticPresentation(page.host)).status).toBe('ready')
  expect(await slot.prepare({ execution, advanceMode: 'scene_end', define: entry.define })).toBeNull()
  expect(page.define).not.toHaveBeenCalled()
  expect(page.run).not.toHaveBeenCalled()
  expect(timeline).not.toHaveBeenCalled()
  expect(page.host.textContent).toBe('独立可读内容')
})

it('缺失独立静态声明时给出不可呈现，仍然不运行 Scene 来生成海报', async () => {
  const page = mount('capture')
  expect(await settleStaticPresentation(page.host)).toMatchObject({ status: 'unsupported', code: 'STATIC_PRESENTATION_UNAVAILABLE' })
  expect(page.define).not.toHaveBeenCalled()
})
