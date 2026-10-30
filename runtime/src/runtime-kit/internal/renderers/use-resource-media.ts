/** 文件功能：将资源组件的用途显式登记到 Scene，普通内容只由 AudioBus 持有，静态上下文不创建播放通道。 */
import { onBeforeUnmount, watch, type Ref } from 'vue'
import { useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { runtimeAudioBus } from '@/core/audio/runtime-audio-bus'
import type { AudioLease } from '@/core/audio/audio-bus'
import { registerSceneMedia } from '@/core/media/scene-media-registration'

interface ResourceMediaOptions { src: string; purpose: 'content' | 'narration' | 'automatic'; gain: number; muted: boolean; loop: boolean }

/** 媒体节点/源/用途替换即撤销旧声明；增益变化只改音量，不重新开始内容媒体。 */
export function useResourceMedia(element: Ref<HTMLMediaElement | null>, read: () => ResourceMediaOptions) {
  const policy = useRuntimeExecutionPolicy()
  let lease: AudioLease | null = null, unregister: (() => void) | null = null
  /** 停止之前的唯一所有者并通知正在使用旧元素的 Scene。 */
  function release(): void { lease?.release(); lease = null; unregister?.(); unregister = null }
  /** 内容通道和自动通道在用途上互斥；静态只保留标记与可读内容。 */
  function bind(): void {
    release()
    const target = element.value, options = read()
    if (!target) return
    unregister = registerSceneMedia(target, { purpose: options.purpose, gain: options.gain, getGain: () => read().gain, muted: options.muted, loop: options.loop })
    if (!policy.value.allowMediaPlayback) { target.muted = true; target.preload = 'none'; target.autoplay = false; return }
    if (options.purpose === 'content') lease = runtimeAudioBus.claim(target, { owner: 'content', group: 'content', gain: options.gain, muted: options.muted })
    else { target.volume = options.gain; target.muted = options.muted }
  }
  const stopBinding = watch([element, () => read().src, () => read().purpose, () => read().muted, () => read().loop, () => policy.value.kind], bind, { flush: 'post', immediate: true })
  const stopGain = watch(() => read().gain, gain => { lease?.configure({ gain }); if (!lease && element.value) element.value.volume = gain }, { flush: 'sync' })
  onBeforeUnmount(() => { stopBinding(); stopGain(); release() })
  return { refresh() { if (lease) lease.configure({ gain: read().gain, muted: read().muted }) } }
}
