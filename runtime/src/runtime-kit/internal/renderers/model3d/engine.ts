/**
 * 文件用途：三维查看器的懒加载引擎适配层。
 *
 * 唯一负责动态 import Three.js 与 examples/jsm 扩展的模块：
 * - 页面不使用三维时不会触发任何 Three.js chunk 加载（本模块被动态 import）；
 * - 引擎版本、色彩空间、色调映射、曝光与 DPR 上限集中声明为 MODEL3D_ENGINE_POLICY，
 *   用于缓存分区与渲染日志身份；
 * - 解析结果的所有权由调用方与 model-cache 管理，这里只提供解析、克隆与释放原语。
 */

import type { GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { ModelCache, type DisposableModelResource } from './model-cache'

/** 引擎与渲染策略身份，参与缓存分区与日志。 */
export const MODEL3D_ENGINE_POLICY = {
  engineVersion: '0.186.1',
  colorSpace: 'srgb',
  toneMapping: 'ACESFilmic',
  exposure: 1,
  maxPixelRatio: 2,
  validationProfile: 'model3d-glb-v2',
} as const

export type ThreeModule = typeof import('three')
export type OrbitControlsConstructor = typeof import('three/examples/jsm/controls/OrbitControls.js')['OrbitControls']
export type SkeletonUtilsModule = typeof import('three/examples/jsm/utils/SkeletonUtils.js')

/** 已加载的引擎能力集合。 */
export interface Model3dEngine {
  THREE: ThreeModule
  GLTFLoader: typeof import('three/examples/jsm/loaders/GLTFLoader.js')['GLTFLoader']
  SkeletonUtils: SkeletonUtilsModule
  OrbitControls?: OrbitControlsConstructor
}

/** 解析后的模型资源：共享几何/材质/纹理的 CPU 数据，由缓存按引用计数持有。 */
export interface ParsedModelResource extends DisposableModelResource {
  gltf: GLTF
  scenes: import('three').Group[]
  cameras: import('three').Camera[]
  animations: import('three').AnimationClip[]
}

/**
 * 页面级共享模型资源缓存；引擎版本与校验策略参与分区，条目淘汰时释放几何/材质/纹理。
 */
export const sharedModelResourceCache = new ModelCache<ParsedModelResource>({
  capacity: 4,
  onEvict: (_key, value) => {
    value.dispose()
  },
})

let enginePromise: Promise<Model3dEngine> | null = null
let interactiveEnginePromise: Promise<Model3dEngine> | null = null

/**
 * 懒加载三维引擎；同一页面重复调用复用同一个 Promise，避免重复加载。
 *
 * 基础引擎包含 three、GLTFLoader 与 SkeletonUtils（多实例克隆骨骼必需）；
 * interactive 为 true 时额外加载 OrbitControls。
 * @param interactive 是否需要查看交互
 * @returns 引擎能力集合
 */
export async function loadModel3dEngine(interactive = false): Promise<Model3dEngine> {
  if (!interactive) {
    if (!enginePromise) {
      enginePromise = createBaseEngine()
      // 动态 import 失败（网络抖动、chunk 缺失）时重置缓存，允许后续调用重新加载。
      enginePromise.catch(() => {
        enginePromise = null
      })
    }
    return enginePromise
  }

  if (!interactiveEnginePromise) {
    interactiveEnginePromise = (async () => {
      const base = await loadModel3dEngine(false)
      const { OrbitControls } = await import('three/examples/jsm/controls/OrbitControls.js')
      return { ...base, OrbitControls }
    })()
    // 同基础引擎：失败后重置，避免页面生命周期内永久持有 rejected Promise。
    interactiveEnginePromise.catch(() => {
      interactiveEnginePromise = null
    })
  }
  return interactiveEnginePromise
}

/**
 * 创建基础引擎（three + GLTFLoader + SkeletonUtils）。
 * @returns 引擎能力集合
 */
async function createBaseEngine(): Promise<Model3dEngine> {
  const [THREE, loaderModule, skeletonUtils] = await Promise.all([
    import('three'),
    import('three/examples/jsm/loaders/GLTFLoader.js'),
    import('three/examples/jsm/utils/SkeletonUtils.js'),
  ])
  return {
    THREE,
    GLTFLoader: loaderModule.GLTFLoader,
    SkeletonUtils: skeletonUtils,
  }
}

/**
 * 按统一策略配置 WebGL 渲染器：sRGB 输出、ACESFilmic 色调映射与固定曝光。
 * @param renderer Three.js WebGLRenderer
 * @param engine 已加载引擎
 */
export function configureModel3dRenderer(
  renderer: import('three').WebGLRenderer,
  engine: Model3dEngine,
): void {
  const { THREE } = engine
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = MODEL3D_ENGINE_POLICY.exposure
}

/**
 * 计算渲染用设备像素比，上限由策略固定。
 * @param devicePixelRatio 设备像素比
 * @returns 收敛后的像素比
 */
export function resolveModel3dPixelRatio(devicePixelRatio: number): number {
  const normalized = Number(devicePixelRatio)
  if (!Number.isFinite(normalized) || normalized <= 0) {
    return 1
  }
  return Math.min(normalized, MODEL3D_ENGINE_POLICY.maxPixelRatio)
}

/**
 * 用带鉴权的 arrayBuffer 直接解析自包含 GLB。
 *
 * 显式传入空 path，绝不把外部相对 URI 交给 loader 解析；GLB 自包含由 Backend 保证，
 * 这里再做一次防御性检查：一旦发现外部依赖直接拒绝，避免 loader 去请求页面相对地址。
 * @param buffer GLB 字节
 * @param engine 已加载引擎
 * @returns 解析后的共享资源
 */
export async function parseGlbToResource(buffer: ArrayBuffer, engine: Model3dEngine): Promise<ParsedModelResource> {
  assertSelfContainedGlb(buffer)

  const loader = new engine.GLTFLoader()
  const gltf = await new Promise<GLTF>((resolve, reject) => {
    loader.parse(
      buffer,
      '',
      result => resolve(result),
      error => reject(error instanceof Error ? error : new Error('GLB 解析失败，请检查文件内容。')),
    )
  })

  const scenes = gltf.scenes?.length ? gltf.scenes : (gltf.scene ? [gltf.scene] : [])

  return {
    gltf,
    scenes,
    cameras: gltf.cameras ?? [],
    animations: gltf.animations ?? [],
    dispose: () => {
      for (const scene of scenes) {
        disposeObject3DResources(scene)
      }
    },
  }
}

/**
 * 为单个实例克隆场景图；SkeletonUtils 保证骨骼与蒙皮网格独立。
 * @param scene 源场景图（缓存共享，不可修改）
 * @param engine 已加载引擎
 * @returns 独立实例节点
 */
export function cloneSceneForInstance(scene: import('three').Object3D, engine: Model3dEngine): import('three').Object3D {
  return engine.SkeletonUtils.clone(scene)
}

/**
 * 释放对象树上的几何、材质与纹理资源（仅当缓存引用计数归零时调用）。
 * @param root 对象树根节点
 */
export function disposeObject3DResources(root: import('three').Object3D | null | undefined): void {
  if (!root) {
    return
  }
  root.traverse((object) => {
    const mesh = object as unknown as {
      geometry?: { dispose?: () => void }
      material?: unknown
    }
    mesh.geometry?.dispose?.()

    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    for (const material of materials) {
      disposeMaterial(material)
    }
  })
}

/**
 * 释放单个材质及其引用的纹理；内嵌纹理的 Blob URL 一并回收。
 * @param material 材质对象
 */
function disposeMaterial(material: unknown): void {
  if (!material || typeof material !== 'object') {
    return
  }
  const record = material as Record<string, unknown>
  for (const key of Object.keys(record)) {
    const value = record[key] as { isTexture?: boolean; dispose?: () => void; image?: { src?: string } } | null
    if (value && value.isTexture === true) {
      revokeBlobImageSource(value.image)
      value.dispose?.()
    }
  }
  const disposable = material as { dispose?: () => void }
  disposable.dispose?.()
}

/**
 * 回收 GLTFLoader 为内嵌纹理创建的 Blob URL（仅当纹理图片使用 blob: 地址时）。
 * @param image 纹理图片对象
 */
function revokeBlobImageSource(image: { src?: string } | null | undefined): void {
  const source = image?.src
  if (typeof source !== 'string' || !source.startsWith('blob:')) {
    return
  }
  try {
    URL.revokeObjectURL(source)
  } catch {
    // 非浏览器环境或已回收时忽略。
  }
}

/** GLB 容器魔数（小端 `glTF`）。 */
const GLB_MAGIC = 0x46546c67
/** GLB JSON chunk 类型（小端 `JSON`）。 */
const GLB_JSON_CHUNK_TYPE = 0x4e4f534a

/**
 * 防御性检查：自包含 GLB 不应出现外部 buffer/image URI；发现时直接拒绝。
 *
 * 非 GLB、chunk 结构异常或 JSON 解析失败时不做判断，交由 loader 给出标准错误。
 * @param buffer GLB 字节
 */
function assertSelfContainedGlb(buffer: ArrayBuffer): void {
  if (buffer.byteLength < 20) {
    return
  }
  const view = new DataView(buffer)
  if (view.getUint32(0, true) !== GLB_MAGIC) {
    return
  }
  const jsonChunkLength = view.getUint32(12, true)
  if (view.getUint32(16, true) !== GLB_JSON_CHUNK_TYPE) {
    return
  }
  const start = 20
  const end = Math.min(start + jsonChunkLength, buffer.byteLength)
  if (end <= start) {
    return
  }

  let json: { buffers?: Array<{ uri?: string }>; images?: Array<{ uri?: string }> }
  try {
    json = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, start, end - start)))
  } catch {
    return
  }

  const groups: Array<[string, Array<{ uri?: string }> | undefined]> = [
    ['buffer', json.buffers],
    ['image', json.images],
  ]
  for (const [label, list] of groups) {
    for (const item of list ?? []) {
      const uri = item?.uri
      // 只放行 data: 内嵌数据；blob: 是运行时会话内地址，出现在源 GLB 中跨会话必失效，
      // 放行只会把错误推迟到 loader 的 fetch 阶段，难以排查。
      if (typeof uri === 'string' && uri && !/^data:/i.test(uri)) {
        throw new Error(`三维资源包含外部 ${label} 依赖 ${uri}，首期只支持自包含 GLB。`)
      }
    }
  }
}
