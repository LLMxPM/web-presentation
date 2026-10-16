/**
 * 文件用途：验证 GLB 解析链路的自包含防护与 loader 调用约定（jsdom，不触发真实 Three.js）。
 *
 * @vitest-environment jsdom
 */

import { describe, expect, it, vi } from 'vitest'

import { parseGlbToResource, type Model3dEngine } from './engine'

/**
 * 构造最小 GLB 容器（仅含 JSON chunk），padding 使用空格以满足 JSON 解析。
 * @param json glTF JSON 内容
 * @returns GLB 字节
 */
function buildGlb(json: unknown): ArrayBuffer {
  const jsonBytes = Array.from(new TextEncoder().encode(JSON.stringify(json)))
  const padding = (4 - (jsonBytes.length % 4)) % 4
  const chunkBytes = [...jsonBytes, ...new Array<number>(padding).fill(0x20)]
  const total = 12 + 8 + chunkBytes.length

  const buffer = new ArrayBuffer(total)
  const view = new DataView(buffer)
  view.setUint32(0, 0x46546c67, true)
  view.setUint32(4, 2, true)
  view.setUint32(8, total, true)
  view.setUint32(12, chunkBytes.length, true)
  view.setUint32(16, 0x4e4f534a, true)
  new Uint8Array(buffer, 20, chunkBytes.length).set(chunkBytes)
  return buffer
}

/**
 * 构造 GLTFLoader 桩：记录调用并回传最小 gltf 结果。
 * @returns 引擎桩与解析探针
 */
function createEngineStub(): { engine: Model3dEngine; parse: ReturnType<typeof vi.fn> } {
  const scene = { traverse: () => undefined }
  const parse = vi.fn((
    _data: ArrayBuffer,
    _path: string,
    onLoad: (gltf: unknown) => void,
  ) => {
    onLoad({ scene, scenes: [scene], cameras: [], animations: [] })
  })

  const engine = {
    THREE: {},
    SkeletonUtils: {},
    GLTFLoader: class {
      parse = parse
    },
  } as unknown as Model3dEngine

  return { engine, parse }
}

describe('parseGlbToResource 加载链路', () => {
  it('自包含 GLB 应以空 path 交给 loader 解析', async () => {
    const { engine, parse } = createEngineStub()
    const buffer = buildGlb({
      asset: { version: '2.0' },
      buffers: [{ byteLength: 4 }],
      images: [{ uri: 'data:image/png;base64,AAAA' }],
      scenes: [{}],
    })

    const resource = await parseGlbToResource(buffer, engine)

    expect(parse).toHaveBeenCalledTimes(1)
    expect(parse.mock.calls[0][1]).toBe('')
    expect(resource.scenes).toHaveLength(1)
    expect(() => resource.dispose()).not.toThrow()
  })

  it('包含外部 buffer 依赖时应拒绝且不调用 loader', async () => {
    const { engine, parse } = createEngineStub()
    const buffer = buildGlb({
      asset: { version: '2.0' },
      buffers: [{ uri: 'model.bin', byteLength: 4 }],
    })

    await expect(parseGlbToResource(buffer, engine)).rejects.toThrow(/外部 buffer 依赖/)
    expect(parse).not.toHaveBeenCalled()
  })

  it('包含外部图片依赖时应拒绝', async () => {
    const { engine } = createEngineStub()
    const buffer = buildGlb({
      asset: { version: '2.0' },
      images: [{ uri: 'textures/albedo.png' }],
    })

    await expect(parseGlbToResource(buffer, engine)).rejects.toThrow(/外部 image 依赖/)
  })
})
