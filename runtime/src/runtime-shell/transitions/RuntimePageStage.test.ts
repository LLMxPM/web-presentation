/** 文件功能：验证页面过渡开始和卸载撤销稳定回执，防止快速往返或过渡层重挂复用旧状态。 */
import { createApp, defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, expect, it, vi } from 'vitest'
import { getRuntimeSession } from '@/core/router/runtime-session'
import type { TransitionSettledEvent, TransitionStartedEvent } from '@/core/types/page-transition'
import RuntimePageStage from './RuntimePageStage.vue'

const fixture = vi.hoisted(() => ({ emit: null as null | ((name: 'started' | 'settled', value: unknown) => void) }))
vi.mock('./PageTransitionHost.vue', () => ({ default: defineComponent({ emits: ['started', 'settled', 'error'],
  setup(_props, { emit }) { fixture.emit = emit; return () => h('div') },
}) }))
const cleanups: Array<() => void> = []
afterEach(() => { cleanups.splice(0).forEach(cleanup => cleanup()); document.body.innerHTML = ''; fixture.emit = null })

/** 真实挂载 RuntimePageStage，只替换 CSS 过渡子层以显式控制开始/完成。 */
async function mount() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/a', component: { render: () => h('div') } }] })
  await router.push('/a'); await router.isReady()
  const started = vi.fn(), settled = vi.fn(), host = document.createElement('div'); document.body.append(host)
  const app = createApp({ render: () => h(RuntimePageStage, { onStarted: started, onSettled: settled }) })
  app.use(router); app.mount(host)
  let mounted = true
  const unmount = () => { if (mounted) { mounted = false; app.unmount() } }
  cleanups.push(unmount)
  return { session: getRuntimeSession(router), unmount, started, settled }
}

it('新过渡开始先撤销旧稳定回执，完成后才发布新的回执', async () => {
  const page = await mount()
  const previous: TransitionSettledEvent = { path: '/a', generation: 1 }
  fixture.emit!('settled', previous)
  expect(page.session.transitionSettled.value).toEqual(previous)
  const transition: TransitionStartedEvent = { generation: 2, fromPath: '/a', toPath: '/b', direction: 1, effect: 'fade' }
  fixture.emit!('started', transition)
  expect(page.session.transitionSettled.value).toBeNull()
  expect(page.started).toHaveBeenCalledWith(transition)
  const next: TransitionSettledEvent = { path: '/b', generation: 2 }
  fixture.emit!('settled', next)
  expect(page.session.transitionSettled.value).toEqual(next)
  expect(page.settled).toHaveBeenLastCalledWith(next)
})

it('过渡层卸载清除自己留下的稳定状态，重挂不继承旧计数', async () => {
  const page = await mount()
  fixture.emit!('settled', { path: '/a', generation: 20 })
  page.unmount()
  expect(page.session.transitionSettled.value).toBeNull()
})

it('旧宿主卸载不会清除另一个宿主已经发布的新回执', async () => {
  const page = await mount()
  fixture.emit!('settled', { path: '/a', generation: 1 })
  page.session.transitionSettled.value = { path: '/b', generation: 2 }
  page.unmount()
  expect(page.session.transitionSettled.value).toEqual({ path: '/b', generation: 2 })
})
