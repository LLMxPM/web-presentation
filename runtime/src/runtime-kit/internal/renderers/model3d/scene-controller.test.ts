/** 文件功能：使用真实 Three.js Mixer 与 Scene 验证正向片段完成、冻结、独立实例和资源替换；不启动 WebGL。 */
import * as THREE from 'three'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { scene, flushScenePromises } from '@/core/scene/session-test-helpers'
import type { SceneTask } from '@/core/scene/types'
import { createModelSceneController } from './scene-controller'
import type { Model3dEngine, ParsedModelResource } from './engine'

const cleanups: Array<() => void> = []
beforeEach(() => vi.useFakeTimers())
afterEach(() => { cleanups.splice(0).reverse().forEach(cleanup => cleanup()); vi.useRealTimers() })

/** 同一真实片段供多个根使用，模拟缓存只读共享；每个控制器自行创建独立 Mixer/action。 */
function fixture(staticMode = false, clips = [new THREE.AnimationClip('move', 0.1, [new THREE.NumberKeyframeTrack('.position[x]', [0, 0.1], [0, 10])])]) {
  const root = new THREE.Group(), wrapper = new THREE.Group(), camera = new THREE.PerspectiveCamera(45)
  wrapper.add(root); camera.position.set(0, 0, 5)
  const render = vi.fn(), parsed = { animations: clips, animationSignatures: clips.map((_, index) => `sig-${index}`) } as ParsedModelResource
  const controller = createModelSceneController({ engine: { THREE } as Model3dEngine, parsed, root, wrapper, camera, target: new THREE.Vector3(),
    isReady: () => true, isStatic: () => staticMode, render })
  cleanups.push(controller.dispose)
  return { ...controller, root, wrapper, camera, render, task: (extra = {}) => controller.handle.animation({ id: 'clip', role: 'blocking', clipIndex: 0, signature: 'sig-0', ...extra }) }
}

/** 使用生产会话聚合，而不直接触发 finished 或手写预估结束计时器。 */
async function start(task: SceneTask) {
  const session = scene([task], { advanceMode: task.role === 'ambient' ? 'manual' : 'scene_end' }); cleanups.push(session.stop)
  await session.prepare(); await session.start()
  return session
}

it('真实 Mixer 正向 update，有限 finished 只结算一次且 stop 恢复原始节点', async () => {
  const model = fixture(), session = await start(model.task()), changes = vi.fn()
  session.subscribe(changes)
  await vi.advanceTimersByTimeAsync(64)
  expect(model.root.position.x).toBeGreaterThan(0); expect(model.root.position.x).toBeLessThan(10)
  await vi.advanceTimersByTimeAsync(160); await flushScenePromises()
  expect(session.getSnapshot().phase).toBe('completed')
  expect(model.root.position.x).toBeCloseTo(10)
  expect(changes.mock.calls.filter(([snapshot]) => snapshot.phase === 'completed')).toHaveLength(1)
  session.stop(); expect(model.root.position.x).toBe(0)
  expect(vi.getTimerCount()).toBe(0)
})

it('两个实例共享片段数据但动作和姿态互不影响，停止一个不停止另一个', async () => {
  const clip = new THREE.AnimationClip('move', 0.1, [new THREE.NumberKeyframeTrack('.position[x]', [0, 0.1], [0, 10])])
  const first = fixture(false, [clip]), second = fixture(false, [clip])
  const a = await start(first.task()), b = await start(second.task({ repeat: -1, role: 'ambient', rate: 0.5 }))
  await vi.advanceTimersByTimeAsync(64)
  expect(first.root.position.x).toBeGreaterThan(second.root.position.x)
  a.stop(); const position = second.root.position.x
  await vi.advanceTimersByTimeAsync(48)
  expect(first.root.position.x).toBe(0); expect(second.root.position.x).not.toBe(position)
  expect(b.getSnapshot().phase).toBe('completed')
  b.stop(); expect(second.root.position.x).toBe(0)
})

it('冻结恢复不补跑墙钟，Viewer 暂挂与 Scene 暂挂互不覆盖', async () => {
  const model = fixture(), session = await start(model.task())
  await vi.advanceTimersByTimeAsync(48)
  const position = model.root.position.x
  session.setSuspended(true); model.setViewerSuspended(true)
  await vi.advanceTimersByTimeAsync(5000)
  session.setSuspended(false); await vi.advanceTimersByTimeAsync(100)
  expect(model.root.position.x).toBe(position)
  model.setViewerSuspended(false); await vi.advanceTimersByTimeAsync(16)
  expect(model.root.position.x).toBe(position)
  await vi.advanceTimersByTimeAsync(150); expect(session.getSnapshot().phase).toBe('completed')
})

it('失效签名与 blocking 无限动作在准备拒绝，静态路径不推进 Mixer', async () => {
  for (const model of [fixture(), fixture(true)]) {
    const task = model.task({ signature: 'stale' }), session = scene([task]); cleanups.push(session.stop)
    await session.prepare(); expect(session.getSnapshot().phase).toBe('failed'); expect(model.render).not.toHaveBeenCalled()
  }
  const model = fixture(), session = scene([model.task({ repeat: -1 })]); cleanups.push(session.stop)
  await session.prepare(); expect(session.getSnapshot().phase).toBe('failed')
  expect(vi.getTimerCount()).toBe(0)
})

it('资源实例释放使正在执行和保存的旧句柄失效，迟到 RAF 不复活旧模型', async () => {
  const model = fixture(), session = await start(model.task())
  await vi.advanceTimersByTimeAsync(32); model.dispose(); await flushScenePromises()
  expect(session.getSnapshot().phase).toBe('failed'); expect(model.handle.isReady()).toBe(false)
  const count = model.render.mock.calls.length
  await vi.advanceTimersByTimeAsync(1000); expect(model.render).toHaveBeenCalledTimes(count)
  const next = scene([model.task()]); cleanups.push(next.stop); await next.prepare(); expect(next.getSnapshot().phase).toBe('failed')
})

it('只暴露数值副本，整体变换和相机属于本实例且可恢复', () => {
  const a = fixture(), b = fixture()
  a.handle.transform.x = 3; a.handle.transform.rotationY = 90; a.handle.camera.x = 4; a.handle.invalidate()
  expect(a.wrapper.position.x).toBe(3); expect(a.camera.position.x).toBe(4)
  expect(b.wrapper.position.x).toBe(0); expect(b.camera.position.x).toBe(0)
  expect(a.handle).not.toHaveProperty('root'); expect(a.handle).not.toHaveProperty('mixer')
  a.handle.reset(); expect(a.wrapper.position.x).toBe(0); expect(a.camera.position.x).toBe(0)
})
