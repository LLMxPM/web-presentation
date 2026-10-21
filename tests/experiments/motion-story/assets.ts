// 文件功能：加载原创媒体及真实骨骼 GLB，为候选 SFC 提供同一组查询与目标句柄。
import { prepare } from '../motion-wp01/media.mjs'
import { loadModel } from '../motion-wp01/model.mjs'
import type { Assets, Elements, StoryProps } from './types'

/** 准备真实资源；签名仅为此夹具的动画 JSON 摘要，生产语义签名仍由 WP07 定义。 */
export async function loadAssets(elements: Elements, props: StoryProps): Promise<Assets> {
  const base = new URLSearchParams(location.search).get('assets')!
  const url = (name: string) => `${base}/${name}?ticket=wp01-fixture`
  const file = props.modelFile ?? 'animated.glb'
  const bytes = await (await fetch(url(file))).arrayBuffer()
  const json = JSON.parse(new TextDecoder().decode(new Uint8Array(bytes, 20, new DataView(bytes).getUint32(12, true))))
  if (!json.animations?.length) throw Object.assign(new Error('CLIP_NOT_FOUND'), { code: 'CLIP_NOT_FOUND', fieldPath: 'assets.model.animations' })
  for (const [index, animation] of json.animations.entries()) for (const channel of animation.channels) {
    if (!json.nodes[channel.target.node]) throw Object.assign(new Error('CLIP_TARGET_MISSING'), { code: 'CLIP_TARGET_MISSING', fieldPath: `assets.model.animations[${index}].channels` })
  }
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(json.animations[0])))
  const signature = Array.from(new Uint8Array(hash)).map(value => value.toString(16).padStart(2, '0')).join('')
  const accessor = json.accessors[json.animations[0].samplers[0].input]
  await Promise.all([prepare(elements.audio, url('voice.wav')), prepare(elements.video, url('clock.webm'))])
  const model = await loadModel(url(file), elements.canvas)
  return {
    elements, model,
    clip: { index: 0, signature, name: json.animations[0].name, durationMs: accessor.max[0] * 1000 },
    voiceDurationMs: elements.audio.duration * 1000, videoDurationMs: elements.video.duration * 1000,
    dispose() {
      for (const media of [elements.audio, elements.video]) { media.pause(); media.removeAttribute('src'); media.load() }
      model.dispose()
    },
  }
}
