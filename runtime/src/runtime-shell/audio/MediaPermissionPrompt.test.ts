/** 文件功能：验证受阻媒体在当前 Runtime frame 的提示按钮接线与静态零通道；不模拟真实浏览器播放许可。 */
import { createApp, defineComponent, h, nextTick } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { runtimeAudioBus } from '@/core/audio/runtime-audio-bus'
import { initializeRuntimeExecution, resetRuntimeExecutionForTests } from '@/core/execution/execution-scope'
import { registerSceneMedia } from '@/core/media/scene-media-registration'
import { createSceneMediaTask } from '@/core/media/scene-media-task'
import { scene, flushScenePromises } from '@/core/scene/session-test-helpers'
import AudioViewer from '@/runtime-kit/internal/renderers/AudioViewer.vue'
import VideoViewer from '@/runtime-kit/internal/renderers/VideoViewer.vue'
import MediaPermissionPrompt from './MediaPermissionPrompt.vue'

const cleanups: Array<() => void> = []
beforeEach(() => { resetRuntimeExecutionForTests(); runtimeAudioBus.muted.value = false; runtimeAudioBus.setSuspended(false); vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {}) })
afterEach(() => { cleanups.splice(0).reverse().forEach(cleanup => cleanup()); document.body.innerHTML = ''; resetRuntimeExecutionForTests(); vi.restoreAllMocks() })

/** 挂载生产提示组件，按钮必须实际位于当前文档，而不是父窗口代理的控件。 */
function mount(component = MediaPermissionPrompt) {
  const root = document.createElement('div'); document.body.append(root)
  const app = createApp(component); app.mount(root); cleanups.push(() => app.unmount())
  return root
}

it('真实受阻状态显示本地按钮，当前 frame 点击后才发起第二次 play 并隐藏提示', async () => {
  const target = document.createElement('audio'); target.src = '/voice.mp3'; document.body.append(target)
  const play = vi.fn().mockRejectedValueOnce(new DOMException('blocked', 'NotAllowedError')).mockResolvedValue(undefined)
  target.play = play
  cleanups.push(registerSceneMedia(target, { purpose: 'narration', gain: 1, muted: false, loop: false }))
  const session = scene([createSceneMediaTask({ id: 'voice', role: 'blocking', target: () => target })]); cleanups.push(session.stop)
  const root = mount(); await session.prepare(); await session.start(); await flushScenePromises(); await nextTick()
  expect(root.textContent).toContain('此窗口允许播放')
  expect(play).toHaveBeenCalledOnce()
  root.querySelector<HTMLButtonElement>('button')!.click(); await flushScenePromises(); await nextTick()
  expect(play).toHaveBeenCalledTimes(2); expect(root.querySelector('button')).toBeNull()
  expect(session.getSnapshot().phase).toBe('running')
})

it('静态音频和自动视频不创建总线通道、不播放，也不提供许可提示', async () => {
  initializeRuntimeExecution('?runtimeExecution=capture')
  const play = vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  const root = mount(defineComponent({ setup: () => () => h('section', [h(AudioViewer, { src: '/voice.mp3', purpose: 'narration' }), h(VideoViewer, { src: '/movie.mp4', purpose: 'automatic' }), h(MediaPermissionPrompt)]) }))
  await nextTick(); await nextTick()
  expect(runtimeAudioBus.state.value.channels).toBe(0); expect(play).not.toHaveBeenCalled()
  expect(root.querySelector('video')?.autoplay).toBe(false); expect(root.querySelector('button')).toBeNull()
})
