/** 文件功能：用真实 Three.js Mixer、Scene 与媒体 ended 替身验证联合样例的完成与取消，不声称 WebGL/音频实机通过。 */
import * as THREE from 'three'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPageSceneSession } from '@/core/scene/page-scene-session'
import { flushScenePromises } from '@/core/scene/session-test-helpers'
import { registerSceneMedia } from '@/core/media/scene-media-registration'
import { runtimeAudioBus } from '@/core/audio/runtime-audio-bus'
import { createModelSceneController } from '@/runtime-kit/internal/renderers/model3d/scene-controller'
import type { Model3dEngine, ParsedModelResource } from '@/runtime-kit/internal/renderers/model3d/engine'
import { defineModelNarration } from './define-model-narration'
const cleanups: Array<() => void> = []
beforeEach(() => vi.useFakeTimers())
afterEach(() => { cleanups.splice(0).reverse().forEach(clean => clean()); vi.useRealTimers(); document.body.innerHTML = '' })

/** 构造两个真实剪辑与一个显式旁白目标；不手动调用 Mixer finished，不使用时长估计完成。 */
function fixture(count = 2) {
  const root = new THREE.Group(), wrapper = new THREE.Group(), camera = new THREE.PerspectiveCamera(45)
  wrapper.add(root)
  const animations = [0, 1].slice(0, count).map(index => new THREE.AnimationClip(`action-${index}`, 0.1, [new THREE.NumberKeyframeTrack('.position[x]', [0, 0.1], [index * 10, (index + 1) * 10])]))
  const controller = createModelSceneController({ engine: { THREE } as Model3dEngine, parsed: { animations, animationSignatures: ['sig-a', 'sig-b'] } as ParsedModelResource,
    root, wrapper, camera, target: new THREE.Vector3(), isReady: () => true, isStatic: () => false, render: vi.fn() })
  const audio = document.createElement('audio'); audio.src = '/narration.mp3'; audio.play = vi.fn().mockResolvedValue(undefined); audio.pause = vi.fn(); document.body.append(audio)
  const unregister = registerSceneMedia(audio, { purpose: 'narration', gain: 1, muted: false, loop: false }), cue = vi.fn().mockResolvedValue('blocked')
  const session = createPageSceneSession({ generation: 1, advanceMode: 'scene_end', define(context) {
    defineModelNarration({ ...context, root: document.body, task: context.register, visual() { throw new Error('本测试只验证联合资源分支') } }, controller.handle, audio, cue)
  } })
  cleanups.push(controller.dispose, unregister, session.stop)
  return { session, root, audio, cue }
}

it('两段动作按真实 finished 顺序运行，旁白没有 ended 时整页不能提前完成', async () => {
  const { session, root, audio, cue } = fixture()
  await session.prepare(); expect(audio.play).not.toHaveBeenCalled()
  await session.start(); await vi.advanceTimersByTimeAsync(64)
  expect(root.position.x).toBeGreaterThan(0); expect(root.position.x).toBeLessThan(10)
  await vi.advanceTimersByTimeAsync(1000); await flushScenePromises()
  expect(root.position.x).toBeCloseTo(20)
  expect(cue).toHaveBeenCalledOnce(); expect(cue).toHaveBeenCalledWith('interaction.scene-finished')
  expect(session.getSnapshot().phase).toBe('running')
  audio.dispatchEvent(new Event('ended')); await flushScenePromises()
  expect(session.getSnapshot().phase).toBe('completed')
  session.stop(); expect(root.position.x).toBe(0); expect(runtimeAudioBus.state.value.channels).toBe(0)
  expect(vi.getTimerCount()).toBe(0)
})
it('离页同时停止两段依赖和旁白，迟到 ended 不再触发 cue', async () => {
  const { session, audio, cue } = fixture()
  await session.prepare(); await session.start(); await vi.advanceTimersByTimeAsync(32)
  session.stop(); audio.dispatchEvent(new Event('ended')); await vi.advanceTimersByTimeAsync(2000)
  expect(session.getSnapshot().phase).toBe('stopped'); expect(cue).not.toHaveBeenCalled()
  expect(runtimeAudioBus.state.value.channels).toBe(0); expect(vi.getTimerCount()).toBe(0)
})
it('少于两个真实已签名片段时明确失败，不猜动作或降为单片段', async () => {
  const { session, audio } = fixture(1)
  await session.prepare()
  expect(session.getSnapshot().phase).toBe('failed'); expect(audio.play).not.toHaveBeenCalled()
})
