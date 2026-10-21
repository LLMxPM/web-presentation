/** 文件功能：从实际加载的 glTF accessor 字节重建与 Backend v2 相同的动作语义签名。 */
import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { sha256Bytes } from './sha256-bytes'

const WIDTHS: Record<string, number> = { SCALAR: 1, VEC3: 3, VEC4: 4 }
const PATH_TYPES: Record<string, string> = { translation: 'VEC3', rotation: 'VEC4', scale: 'VEC3', weights: 'SCALAR' }

/** 不从资源名字或时长猜身份；不支持的 accessor 返回 null，使带签名引用明确失效。 */
export async function readAnimationSignatures(parser: GLTF['parser']): Promise<Array<string | null>> {
  const json = parser.json
  const encoder = new TextEncoder()

  /** 读取实际 bufferView，去掉 padding/stride，只保留 accessor 的有序元素字节。 */
  async function elements(index: number, type: string): Promise<Uint8Array[]> {
    const accessor = json.accessors?.[index]
    const view = json.bufferViews?.[accessor?.bufferView]
    const width = WIDTHS[type] * 4
    if (!accessor || !view || accessor.type !== type || accessor.componentType !== 5126
      || accessor.sparse || accessor.normalized || !width || accessor.count < 1) throw new Error('unsupported accessor')
    const buffer: ArrayBuffer = await parser.getDependency('bufferView', accessor.bufferView)
    const stride = view.byteStride ?? width
    const offset = accessor.byteOffset ?? 0
    if (stride < width || offset + (accessor.count - 1) * stride + width > buffer.byteLength) throw new Error('invalid accessor')
    return Array.from({ length: accessor.count }, (_, item) => new Uint8Array(buffer, offset + item * stride, width))
  }

  return Promise.all((json.animations ?? []).map(async (animation: {
    samplers: Array<{ input: number; output: number; interpolation?: string }>
    channels: Array<{ sampler: number; target: { node: number; path: string } }>
  }) => {
    try {
      const parts: Uint8Array[] = []
      const descriptors: Array<[number, string, number, string]> = []
      const targets = new Set<string>()
      if (!animation.channels.length) return null
      for (const channel of animation.channels) {
        const { node, path } = channel.target
        const sampler = animation.samplers[channel.sampler]
        const interpolation = sampler?.interpolation ?? 'LINEAR'
        const key = `${node}:${path}`
        if (!Number.isInteger(node) || !PATH_TYPES[path] || targets.has(key)
          || !['LINEAR', 'STEP', 'CUBICSPLINE'].includes(interpolation)) return null
        targets.add(key)
        const input = await elements(sampler.input, 'SCALAR')
        const output = await elements(sampler.output, PATH_TYPES[path])
        if (output.length !== input.length * (interpolation === 'CUBICSPLINE' ? 3 : 1)) return null
        const times = input.map(bytes => new DataView(bytes.buffer, bytes.byteOffset, 4).getFloat32(0, true))
        if (times.some((time, index) => !Number.isFinite(time) || (index > 0 && time <= times[index - 1]))) return null
        parts.push(encoder.encode(`${node}|${path}|${interpolation}|`), ...input, ...output)
        descriptors.push([node, path, channel.sampler, interpolation])
      }
      descriptors.sort((a, b) => a[0] - b[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0) || a[2] - b[2])
      for (const [node, path, sampler, interpolation] of descriptors) {
        parts.push(encoder.encode(`\nchannel:${node}:${path}:${sampler}:${interpolation}`))
      }
      const payload = new Uint8Array(parts.reduce((size, part) => size + part.length, 0))
      let offset = 0
      for (const part of parts) { payload.set(part, offset); offset += part.length }
      return (await sha256Bytes(payload)).slice(0, 32)
    } catch {
      return null
    }
  }))
}
