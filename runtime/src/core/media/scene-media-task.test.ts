/** 文件功能：使用真实 Scene 聚合和原生媒体事件替身，验证显式认领、许可重试、缓冲与离页清理。 */
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AudioBus } from '@/core/audio/audio-bus'
import { scene, flushScenePromises } from '@/core/scene/session-test-helpers'
import { registerSceneMedia } from './scene-media-registration'
import { createSceneMediaTask } from './scene-media-task'

const cleanups: Array<() => void> = []
beforeEach(() => vi.useFakeTimers())
afterEach(() => { cleanups.splice(0).reverse().forEach(cleanup => cleanup()); document.body.innerHTML = ''; vi.useRealTimers() })

/** 元素播放结果由用例控制，完成只通过 ended 事件，绝不由模拟 duration 定时结算。 */
function media(options: { muted?: boolean; loop?: boolean; purpose?: 'content' | 'narration' | 'automatic' } = {}, bus = new AudioBus()) {
  const element = document.createElement('video'), play = vi.fn().mockResolvedValue(undefined), pause = vi.fn()
  element.src = '/asset.mp4'; element.play = play; element.pause = pause; document.body.append(element)
  const unregister = registerSceneMedia(element, { purpose: options.purpose ?? 'automatic', gain: 1, loop: options.loop ?? false, muted: options.muted ?? false })
  cleanups.push(unregister, () => bus.dispose())
  return { element, play, pause, bus, unregister, task: (extra = {}) => createSceneMediaTask({ id: 'media', role: 'blocking', target: () => element, ...extra }, bus) }
}

/** 使用生产聚合器，不复制媒体或 Scene 完成语义。 */
async function start(task: ReturnType<ReturnType<typeof media>['task']>, manual = false) {
  const session = scene([task], { advanceMode: manual ? 'manual' : 'scene_end' }); cleanups.push(session.stop)
  await session.prepare(); await session.start(); await flushScenePromises(); return session
}

it('prepare 不播放，必须 ended 才完成；退出取消后旧事件不再执行', async () => {
  const m = media(), session = scene([m.task()]); cleanups.push(session.stop)
  await session.prepare(); expect(m.play).not.toHaveBeenCalled()
  await session.start(); await flushScenePromises(); expect(m.play).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(10000); expect(session.getSnapshot().phase).toBe('running')
  m.element.dispatchEvent(new Event('ended')); await flushScenePromises(); expect(session.getSnapshot().phase).toBe('completed')
  session.stop(); expect(m.bus.state.value.channels).toBe(0)
  m.element.dispatchEvent(new Event('canplay')); await flushScenePromises(); expect(m.play).toHaveBeenCalledOnce()
})

it('首次 NotAllowed 进入 blocked；只有本地重试调用新 play，离页后旧重试失效', async () => {
  const m = media(); m.play.mockRejectedValueOnce(new DOMException('策略阻止', 'NotAllowedError'))
  const session = await start(m.task())
  expect(session.getSnapshot().phase).toBe('blocked'); expect(m.bus.state.value.blocked).toBe(1)
  await m.bus.retryBlocked(); await flushScenePromises()
  expect(m.play).toHaveBeenCalledTimes(2); expect(session.getSnapshot().phase).toBe('running')
  m.element.dispatchEvent(new Event('ended')); await flushScenePromises(); session.stop()
  await m.bus.retryBlocked(); expect(m.play).toHaveBeenCalledTimes(2)
})

it('等待缓冲不因自己的阻塞而暂停原生加载，canplay 后恢复；外部冻结要暂停', async () => {
  const m = media(), session = await start(m.task())
  m.element.dispatchEvent(new Event('waiting')); expect(session.getSnapshot().phase).toBe('blocked')
  expect(m.pause).not.toHaveBeenCalled()
  m.element.dispatchEvent(new Event('canplay')); await flushScenePromises()
  expect(session.getSnapshot().phase).toBe('running')
  session.setSuspended(true); expect(m.pause).toHaveBeenCalledOnce()
  session.setSuspended(false); await flushScenePromises(); expect(m.play).toHaveBeenCalledTimes(3)
})

it('每个 Scene 最多一个自动发声主媒体，静音循环只允许 ambient，普通内容不能被自动认领', async () => {
  const bus = new AudioBus(), first = media({}, bus), second = media({}, bus)
  const limited = scene([first.task(), second.task({ id: 'second' })]); cleanups.push(limited.stop)
  await limited.prepare(); expect(limited.getSnapshot()).toMatchObject({ phase: 'failed', issue: { code: 'SCENE_MEDIA_PRIMARY_LIMIT' } })
  const content = media({ purpose: 'content' }), rejected = await start(content.task())
  expect(rejected.getSnapshot()).toMatchObject({ phase: 'failed', issue: { code: 'SCENE_MEDIA_PURPOSE_REQUIRED' } })
  const loop = media({ muted: true, loop: true }), ambient = await start(loop.task({ role: 'ambient' }), true)
  expect(ambient.getSnapshot().phase).toBe('completed'); expect(loop.play).toHaveBeenCalledOnce()
  ambient.stop(); expect(loop.bus.state.value.channels).toBe(0)
})

it('组件注销或源替换立即终止任务，有限必需失败不被伪装为完成', async () => {
  const m = media(), session = await start(m.task())
  m.unregister(); await flushScenePromises()
  expect(session.getSnapshot()).toMatchObject({ phase: 'failed', issue: { code: 'SCENE_MEDIA_REPLACED' } })
  expect(m.bus.state.value.channels).toBe(0)
  const next = media(), other = await start(next.task())
  next.element.src = '/changed.mp4'; next.element.dispatchEvent(new Event('loadstart')); await flushScenePromises()
  expect(other.getSnapshot().phase).toBe('failed')
})
