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
 * @param sceneOverride 可选的自定义场景桩（默认 traverse 为空实现）
 * @returns 引擎桩与解析探针
 */
function createEngineStub(sceneOverride?: unknown): { engine: Model3dEngine; parse: ReturnType<typeof vi.fn> } {
  const scene = sceneOverride ?? { traverse: () => undefined }
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

  it('源 GLB 内出现 blob: URI 时应拒绝（跨会话地址必然失效）', async () => {
    const { engine } = createEngineStub()
    const buffer = buildGlb({
      asset: { version: '2.0' },
      images: [{ uri: 'blob:https://example.com/abcd' }],
    })

    await expect(parseGlbToResource(buffer, engine)).rejects.toThrow(/外部 image 依赖/)
  })
})

describe('disposeObject3DResources 释放链路（经 parseGlbToResource.dispose）', () => {
  /**
   * 构造带真实 traverse 遍历的场景桩：遍历时回调注入的对象。
   * @param children traverse 回调需要访问的对象列表
   * @returns 场景桩
   */
  function createTraversableScene(children: unknown[]): { traverse: (cb: (object: unknown) => void) => void } {
    return {
      traverse: (cb: (object: unknown) => void) => {
        for (const child of children) {
          cb(child)
        }
      },
    }
  }

  it('dispose 应释放几何、材质、纹理并回收 blob 图片地址', async () => {
    const geometryDispose = vi.fn()
    const materialDispose = vi.fn()
    const textureDispose = vi.fn()
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    const mesh = {
      geometry: { dispose: geometryDispose },
      material: {
        map: { isTexture: true, dispose: textureDispose, image: { src: 'blob:https://example.com/tex' } },
        normalMap: { isTexture: true, dispose: vi.fn(), image: { src: 'data:image/png;base64,AAAA' } },
        dispose: materialDispose,
      },
    }
    const scene = createTraversableScene([mesh])
    const { engine } = createEngineStub(scene)
    const buffer = buildGlb({ asset: { version: '2.0' }, scenes: [{}] })

    const resource = await parseGlbToResource(buffer, engine)
    resource.dispose()

    expect(geometryDispose).toHaveBeenCalledTimes(1)
    expect(materialDispose).toHaveBeenCalledTimes(1)
    expect(textureDispose).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:https://example.com/tex')
    revokeObjectURL.mockRestore()
  })

  it('材质数组与无 dispose 方法的对象都应安全处理', async () => {
    const geometryDispose = vi.fn()
    const firstMaterialDispose = vi.fn()
    const mesh = {
      geometry: { dispose: geometryDispose },
      material: [{ dispose: firstMaterialDispose }, {}],
    }
    const scene = createTraversableScene([mesh, { geometry: undefined, material: undefined }])
    const { engine } = createEngineStub(scene)
    const buffer = buildGlb({ asset: { version: '2.0' }, scenes: [{}] })

    const resource = await parseGlbToResource(buffer, engine)
    expect(() => resource.dispose()).not.toThrow()
    expect(geometryDispose).toHaveBeenCalledTimes(1)
    expect(firstMaterialDispose).toHaveBeenCalledTimes(1)
  })
})
