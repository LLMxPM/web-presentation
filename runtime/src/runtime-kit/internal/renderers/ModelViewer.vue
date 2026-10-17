<!--
  文件用途：三维模型（GLB）内部渲染器，负责懒加载 Three.js、按实例独立取景、生命周期与状态探针。
  根节点声明 data-runtime-model-state/message 与 data-runtime-kit-media 契约，供首帧探针与 PPTX 导出识别，勿删。
-->

<template>
  <div
    v-bind="$attrs"
    ref="viewerRoot"
    class="model-viewer"
    :class="{
      'model-viewer--loading': state === 'loading',
      'model-viewer--error': state === 'error',
      'model-viewer--interactive': interactive,
    }"
    :data-runtime-model-state="state"
    :data-runtime-model-message="stateMessage"
    data-runtime-kit-media="v1"
    data-runtime-kit-media-kind="model3d"
  >
    <div v-if="state === 'loading'" class="model-viewer__loading">
      <span class="model-viewer__loading-text">正在加载三维模型...</span>
    </div>

    <div v-if="state === 'error'" class="model-viewer__error">
      <span class="model-viewer__error-message">{{ fallbackMessage }}</span>
      <span v-if="stateMessage" class="model-viewer__error-detail">{{ stateMessage }}</span>
    </div>

    <div ref="surfaceRef" class="model-viewer__surface" :class="{ 'model-viewer__surface--hidden': state !== 'ready' }"></div>
  </div>
</template>

<script setup lang="ts">
/**
 * ModelViewer
 *
 * 内部渲染器：一个实例对应一个 WebGL 渲染器与一棵独立的场景克隆。
 * 解析结果（几何/材质/纹理）由 model3d/model-cache 按引用计数共享，
 * 卸载本实例只递减引用；仅当缓存引用归零时才释放共享 GPU 资源。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type * as ThreeNamespace from 'three'

import { getRuntimePreloadedConfig } from '@/core/utils/path'
import { normalizeAssetKey } from '@/core/shared/runtime-preview'
import {
  MODEL_STATIC_FRAME_HANDLE_KEY,
  type ModelStaticFrameCapture,
  type ModelStaticFrameHandle,
  type ModelStaticFrameIdentity,
} from '@/core/shared/model-static-frame-contract'
import {
  MODEL3D_ENGINE_POLICY,
  cloneSceneForInstance,
  configureModel3dRenderer,
  loadModel3dEngine,
  parseGlbToResource,
  resolveModel3dPixelRatio,
  sharedModelResourceCache,
  type Model3dEngine,
  type ParsedModelResource,
} from './model3d/engine'
import { buildModelCacheKey } from './model3d/model-cache'
import { buildModelCameraViewKey, resizeAutoFitCamera } from './model3d/camera-state'
import {
  adaptOrthographicFrustum,
  resolveCameraAspect,
  resolveOrthographicSourceFrustum,
  type BoundingSphere,
  type OrthoFrustum,
} from './model3d/camera-fit'
import { DEFAULT_MODEL_FALLBACK_MESSAGE, buildModelViewIdentityKey, normalizeModelViewOptions, isTransparentBackground, parseBackgroundColor } from './model3d/view-options'

defineOptions({ inheritAttrs: false })

type ModelRenderState = 'loading' | 'ready' | 'error'
type CameraMode = 'auto' | 'source'

interface OrbitControlsLike {
  enableDamping?: boolean
  /** 轨道中心；默认值在原点，必须在首次 update 前显式对齐当前相机姿态。 */
  target?: { copy: (target: { x: number; y: number; z: number }) => void }
  update: () => void
  dispose: () => void
  addEventListener?: (type: 'change', listener: () => void) => void
  removeEventListener?: (type: 'change', listener: () => void) => void
}

interface Props {
  /** 资源逻辑名，用于 manifest render_type 校验与诊断。 */
  name?: string
  /** 已由 resolveResourcePath 解析好的 GLB 地址（含预览票据）。 */
  src?: string
  /** 源文件场景索引；缺省取 glTF 默认场景，仍缺省时取第一个有效场景。 */
  sceneIndex?: number
  /** 源文件相机索引，须属于选中场景。 */
  cameraIndex?: number
  /** 显式相机位置。 */
  cameraPosition?: [number, number, number]
  /** 显式相机目标。 */
  cameraTarget?: [number, number, number]
  /** 显式相机垂直视场角（度）。 */
  cameraFov?: number
  /** 背景色：transparent 或 #RGB/#RRGGBB/#RRGGBBAA。 */
  background?: string
  /** 光照来源。 */
  lighting?: 'auto' | 'source'
  /** 是否启用查看交互。 */
  interactive?: boolean
  /** 兜底文案。 */
  fallback?: string
}

const props = withDefaults(defineProps<Props>(), {
  name: '',
  src: '',
  sceneIndex: undefined,
  cameraIndex: undefined,
  cameraPosition: undefined,
  cameraTarget: undefined,
  cameraFov: undefined,
  background: 'transparent',
  lighting: 'auto',
  interactive: false,
  fallback: DEFAULT_MODEL_FALLBACK_MESSAGE,
})

const viewerRoot = ref<HTMLElement | null>(null)
const surfaceRef = ref<HTMLElement | null>(null)

const state = ref<ModelRenderState>('loading')
const stateMessage = ref('')
const fallbackMessage = computed(() => props.fallback || DEFAULT_MODEL_FALLBACK_MESSAGE)

// —— 运行时句柄（非响应式，避免 Vue 代理 Three.js 对象） ——
let engine: Model3dEngine | null = null
let renderer: ThreeNamespace.WebGLRenderer | null = null
let activeCamera: ThreeNamespace.Camera | null = null
let activeScene: ThreeNamespace.Scene | null = null
let controls: OrbitControlsLike | null = null
let cachedKey: string | null = null
let canvasElement: HTMLCanvasElement | null = null

let cameraMode: CameraMode = 'auto'
let autoFitSphere: BoundingSphere | null = null
let orthoSourceFrustum: OrthoFrustum | null = null

let frameHandle: number | null = null
let needsRender = false
let paused = false
let hasRenderedFrame = false
/** 上下文丢失后置位：要求恢复后重新取得一次真实渲染证据才能回到 ready。 */
let pendingRenderProof = false
let disposed = false
let requestToken = 0
let abortController: AbortController | null = null

let resizeObserver: ResizeObserver | null = null
let intersectionObserver: IntersectionObserver | null = null
let visibilityHandler: (() => void) | null = null
let contextLostHandler: ((event: Event) => void) | null = null
let contextRestoredHandler: (() => void) | null = null

// —— 导出静态帧身份（采集句柄在 describe/capture 时读取最新值） ——
/** 当前加载使用的资源地址；未加载成功时为空串。 */
let activeStaticFrameSrc = ''
/** 当前加载使用的视角身份键；由规范化展示参数派生。 */
let activeStaticFrameViewKey = ''
/** 已注册到根元素的采集句柄；卸载时按同一引用注销。 */
let registeredStaticFrameHandle: ModelStaticFrameHandle | null = null

/**
 * 有界化错误/诊断文案，避免超长消息进入探针。
 * @param message 原始消息
 * @returns 不超过 200 字符的消息
 */
function boundMessage(message: string): string {
  const text = String(message || '').trim() || DEFAULT_MODEL_FALLBACK_MESSAGE
  return text.length > 200 ? `${text.slice(0, 197)}...` : text
}

/**
 * 将未知错误统一转为可展示文案。
 * @param reason 原始错误
 * @returns 错误消息
 */
function toErrorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason || '未知错误')
}

/**
 * 请求一次绘制帧（invalidate 模式）；暂停或已有待执行帧时不重复排队。
 */
function requestRender(): void {
  needsRender = true
  if (paused || disposed || frameHandle !== null) {
    return
  }
  frameHandle = scheduleAnimationFrame(() => {
    frameHandle = null
    if (paused || disposed || !needsRender) {
      return
    }
    needsRender = false
    renderFrame()
  })
}

/**
 * 执行一次渲染；成功渲染后标记已绘制。
 */
function renderFrame(): void {
  if (!renderer || !activeScene || !activeCamera) {
    return
  }
  controls?.update()
  renderer.render(activeScene, activeCamera)
  hasRenderedFrame = true
  pendingRenderProof = false
}

/**
 * 取消在途动画帧。
 */
function cancelScheduledFrame(): void {
  if (frameHandle !== null) {
    cancelAnimationFrameHandle(frameHandle)
    frameHandle = null
  }
  needsRender = false
}

/**
 * 调度一次动画帧；jsdom 等缺少 requestAnimationFrame 时回退到 timeout。
 * @param callback 帧回调
 * @returns 帧句柄
 */
function scheduleAnimationFrame(callback: () => void): number {
  if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
    return window.requestAnimationFrame(callback)
  }
  return window.setTimeout(callback, 16)
}

/**
 * 取消动画帧。
 * @param handle 帧句柄
 */
function cancelAnimationFrameHandle(handle: number): void {
  if (typeof window !== 'undefined' && typeof window.cancelAnimationFrame === 'function') {
    window.cancelAnimationFrame(handle)
    return
  }
  window.clearTimeout(handle)
}

/**
 * 等待一帧浏览器绘制。
 */
function waitForAnimationFrame(): Promise<void> {
  return new Promise(resolve => {
    scheduleAnimationFrame(() => resolve())
  })
}

/**
 * 读取容器当前尺寸。
 * @returns 容器宽高（像素）
 */
function readContainerSize(): { width: number; height: number } {
  const element = surfaceRef.value ?? viewerRoot.value
  if (!element) {
    return { width: 0, height: 0 }
  }
  return { width: element.clientWidth, height: element.clientHeight }
}

/**
 * 读取 manifest 中资源名对应的元数据。
 * @param name 资源逻辑名
 * @returns 资源元数据；未命中时为 null
 */
function resolveAssetMetadata(name: string) {
  const assetKey = normalizeAssetKey(name)
  if (!assetKey) {
    return null
  }
  return getRuntimePreloadedConfig()?.manifest?.asset_metadata?.[assetKey] ?? null
}

/**
 * 标记加载失败并进入 error 态。
 * @param message 失败原因
 * @param token 本次加载令牌
 * @param options.keepRuntime 为 true 时保留已建立的渲染上下文（如 context lost）
 */
function fail(message: string, token: number, options: { keepRuntime?: boolean } = {}): void {
  if (token !== requestToken || disposed) {
    return
  }
  state.value = 'error'
  stateMessage.value = boundMessage(message)
  if (!options.keepRuntime) {
    teardownInstance()
  }
}

/**
 * 标记就绪：仅当真实渲染过一帧后生效。
 * @param token 本次加载令牌
 */
async function markReady(token: number): Promise<void> {
  await waitForAnimationFrame()
  if (token !== requestToken || disposed) {
    return
  }
  state.value = 'ready'
  stateMessage.value = ''
}

/**
 * WebGL 上下文恢复后的就绪门禁：等待真实渲染出新的一帧才回到 ready。
 *
 * 与首次加载不同，恢复后的 rAF 可能先于调度渲染触发，且历史 hasRenderedFrame
 * 无法证明恢复后的绘制成功，因此这里循环等待并主动补排帧；超时则保持 error 态。
 * @param token 恢复时的加载令牌
 */
async function markReadyAfterRenderedFrame(token: number): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await waitForAnimationFrame()
    if (token !== requestToken || disposed) {
      return
    }
    if (hasRenderedFrame && !pendingRenderProof) {
      state.value = 'ready'
      stateMessage.value = ''
      return
    }
    requestRender()
  }
  if (token === requestToken && !disposed) {
    state.value = 'error'
    stateMessage.value = boundMessage('WebGL 上下文已恢复，但未能完成渲染，请刷新后重试。')
  }
}

/**
 * 释放当前实例：取消在途请求、断开控制器、释放渲染器与缓存引用。
 */
function teardownInstance(): void {
  cancelScheduledFrame()

  if (abortController) {
    abortController.abort()
    abortController = null
  }
  if (controls) {
    try {
      controls.dispose()
    } catch {
      // 控制器释放失败不阻断卸载流程。
    }
    controls = null
  }
  if (canvasElement) {
    contextLostHandler && canvasElement.removeEventListener('webglcontextlost', contextLostHandler)
    contextRestoredHandler && canvasElement.removeEventListener('webglcontextrestored', contextRestoredHandler)
  }
  if (renderer) {
    try {
      renderer.dispose()
      renderer.forceContextLoss?.()
    } catch {
      // 上下文已丢失时忽略释放异常。
    }
    renderer = null
  }
  if (canvasElement?.parentElement) {
    canvasElement.parentElement.removeChild(canvasElement)
  }
  canvasElement = null

  // 共享资源只递减引用计数；仅当缓存引用归零时才真正释放。
  if (cachedKey) {
    sharedModelResourceCache.release(cachedKey)
    cachedKey = null
  }

  activeCamera = null
  activeScene = null
  autoFitSphere = null
  orthoSourceFrustum = null
  cameraMode = 'auto'
  hasRenderedFrame = false
  pendingRenderProof = false
}

/**
 * 选择要渲染的场景。
 * @param parsed 解析结果
 * @param sceneIndex 源文件场景索引；null 表示缺省
 * @param engineRef 已加载引擎
 * @returns 选中的源场景
 */
function selectScene(
  parsed: ParsedModelResource,
  sceneIndex: number | null,
  engineRef: Model3dEngine,
): ThreeNamespace.Group {
  if (sceneIndex !== null) {
    const scene = parsed.scenes[sceneIndex]
    if (!scene) {
      throw new Error(`sceneIndex ${sceneIndex} 越界：该资源没有对应场景。`)
    }
    return scene
  }
  if (parsed.gltf.scene) {
    return parsed.gltf.scene
  }
  const firstScene = parsed.scenes.find(scene => Boolean(scene))
  if (!firstScene) {
    throw new Error('该三维资源不包含任何有效场景。')
  }
  return firstScene
}

/**
 * 收集选中场景中出现的源相机，并按源索引排序。
 * @param scene 源场景
 * @param parsed 解析结果
 * @returns 场景内相机与源索引
 */
function collectSceneCameras(
  scene: ThreeNamespace.Group,
  parsed: ParsedModelResource,
): Array<{ camera: ThreeNamespace.Camera; index: number }> {
  const indexByCamera = new Map<ThreeNamespace.Camera, number>()
  parsed.cameras.forEach((camera, index) => indexByCamera.set(camera, index))

  const found: Array<{ camera: ThreeNamespace.Camera; index: number }> = []
  scene.traverse((object) => {
    const camera = object as ThreeNamespace.Camera
    const index = indexByCamera.get(camera)
    if (index !== undefined) {
      found.push({ camera, index })
    }
  })
  found.sort((a, b) => a.index - b.index)
  return found
}

/**
 * 克隆源相机到世界坐标系，保证实例独立且不受父节点局部变换影响。
 * @param source 源相机（缓存共享，不可修改）
 * @param engineRef 已加载引擎
 * @returns 独立的相机副本
 */
function cloneCameraToWorld(source: ThreeNamespace.Camera, engineRef: Model3dEngine): ThreeNamespace.Camera {
  const { THREE } = engineRef
  source.updateMatrixWorld(true)
  const position = new THREE.Vector3()
  const quaternion = new THREE.Quaternion()
  const scale = new THREE.Vector3()
  source.matrixWorld.decompose(position, quaternion, scale)

  const clone = source.clone() as ThreeNamespace.Camera
  clone.position.copy(position)
  clone.quaternion.copy(quaternion)
  clone.scale.copy(scale)
  clone.parent = null
  clone.updateMatrixWorld(true)
  return clone
}

/**
 * 按容器宽高比适配源相机（保持投影类型）。
 * @param camera 已克隆的源相机
 * @param aspect 容器宽高比
 */
function adaptSourceCamera(camera: ThreeNamespace.Camera, aspect: number): void {
  const perspective = camera as ThreeNamespace.PerspectiveCamera
  if (perspective.isPerspectiveCamera) {
    perspective.aspect = aspect
    perspective.updateProjectionMatrix()
    return
  }
  const orthographic = camera as ThreeNamespace.OrthographicCamera
  if (orthographic.isOrthographicCamera) {
    // 首次适配时记录源视锥，后续 resize 必须基于该基线重算，避免逐次放大累积。
    const sourceFrustum = orthoSourceFrustum ?? resolveOrthographicSourceFrustum({
      left: orthographic.left,
      right: orthographic.right,
      top: orthographic.top,
      bottom: orthographic.bottom,
      xmag: Number((orthographic.userData as { xmag?: number } | undefined)?.xmag),
      ymag: Number((orthographic.userData as { ymag?: number } | undefined)?.ymag),
    })
    orthoSourceFrustum = sourceFrustum
    const adapted = adaptOrthographicFrustum(sourceFrustum, aspect)
    orthographic.left = adapted.left
    orthographic.right = adapted.right
    orthographic.top = adapted.top
    orthographic.bottom = adapted.bottom
    orthographic.updateProjectionMatrix()
  }
}

/**
 * 计算显式相机的近远裁剪面。
 * @param position 相机位置
 * @param target 目标点
 * @returns 近远裁剪面
 */
function resolveExplicitClipping(position: [number, number, number], target: [number, number, number]): { near: number; far: number } {
  const distance = Math.hypot(position[0] - target[0], position[1] - target[1], position[2] - target[2])
  const safeDistance = Number.isFinite(distance) && distance > 0 ? distance : 1
  const near = Math.max(safeDistance * 1e-3, 1e-4)
  const far = Math.max(safeDistance * 1e3, near * 10)
  return { near, far }
}

/**
 * 用自动取景结果创建透视相机。
 * @param sphere 场景包围球
 * @param fovDeg 垂直视场角（度）
 * @param aspect 容器宽高比
 * @param engineRef 已加载引擎
 * @returns 自动取景相机
 */
function createAutoFitCamera(
  sphere: BoundingSphere,
  fovDeg: number,
  aspect: number,
  engineRef: Model3dEngine,
): ThreeNamespace.PerspectiveCamera {
  const { THREE } = engineRef
  const camera = new THREE.PerspectiveCamera(fovDeg, aspect)
  resizeAutoFitCamera(camera, sphere, fovDeg, aspect, false)
  return camera
}

/**
 * 计算场景包围球（空场景返回零半径）。
 * @param scene 实例场景
 * @param engineRef 已加载引擎
 * @returns 包围球
 */
function computeSceneBoundingSphere(scene: ThreeNamespace.Object3D, engineRef: Model3dEngine): BoundingSphere {
  const { THREE } = engineRef
  const box = new THREE.Box3().setFromObject(scene)
  if (box.isEmpty()) {
    return { center: { x: 0, y: 0, z: 0 }, radius: 0 }
  }
  const sphere = box.getBoundingSphere(new THREE.Sphere())
  return {
    center: { x: sphere.center.x, y: sphere.center.y, z: sphere.center.z },
    radius: sphere.radius,
  }
}

/**
 * 按相机优先级选择相机：显式位置 → cameraIndex → 场景内首个有效源相机 → 自动取景。
 * @param params 选相机参数
 * @returns 选中的相机
 */
function resolveCamera(params: {
  sourceScene: ThreeNamespace.Group
  renderScene: ThreeNamespace.Scene
  parsed: ParsedModelResource
  options: ReturnType<typeof normalizeModelViewOptions>['options']
  aspect: number
  engineRef: Model3dEngine
}): ThreeNamespace.Camera {
  const { options, aspect, engineRef, sourceScene, renderScene, parsed } = params
  const { THREE } = engineRef

  if (options.cameraPosition && options.cameraTarget) {
    const { near, far } = resolveExplicitClipping(options.cameraPosition, options.cameraTarget)
    const camera = new THREE.PerspectiveCamera(options.cameraFov, aspect, near, far)
    camera.position.set(options.cameraPosition[0], options.cameraPosition[1], options.cameraPosition[2])
    camera.lookAt(options.cameraTarget[0], options.cameraTarget[1], options.cameraTarget[2])
    camera.updateMatrixWorld(true)
    cameraMode = 'source'
    return camera
  }

  const sceneCameras = collectSceneCameras(sourceScene, parsed)

  if (options.cameraIndex !== null) {
    const sourceCamera = parsed.cameras[options.cameraIndex]
    if (!sourceCamera) {
      throw new Error(`cameraIndex ${options.cameraIndex} 越界：该资源没有对应相机。`)
    }
    if (!sceneCameras.some(entry => entry.camera === sourceCamera)) {
      throw new Error(`cameraIndex ${options.cameraIndex} 不属于所选场景。`)
    }
    const camera = cloneCameraToWorld(sourceCamera, engineRef)
    adaptSourceCamera(camera, aspect)
    cameraMode = 'source'
    return camera
  }

  const firstSceneCamera = sceneCameras[0]
  if (firstSceneCamera) {
    const camera = cloneCameraToWorld(firstSceneCamera.camera, engineRef)
    adaptSourceCamera(camera, aspect)
    cameraMode = 'source'
    return camera
  }

  const sphere = computeSceneBoundingSphere(renderScene, engineRef)
  autoFitSphere = sphere
  cameraMode = 'auto'
  return createAutoFitCamera(sphere, options.cameraFov, aspect, engineRef)
}

/**
 * 按光照策略补默认光照：仅 auto 且场景无任何光源时添加。
 * @param scene 实例场景
 * @param lighting 光照策略
 * @param engineRef 已加载引擎
 */
function applyLighting(scene: ThreeNamespace.Scene, lighting: 'auto' | 'source', engineRef: Model3dEngine): void {
  if (lighting === 'source') {
    return
  }
  let hasLight = false
  scene.traverse((object) => {
    if ((object as ThreeNamespace.Light).isLight) {
      hasLight = true
    }
  })
  if (hasLight) {
    return
  }
  const { THREE } = engineRef
  const ambient = new THREE.AmbientLight(0xffffff, 1.1)
  const directional = new THREE.DirectionalLight(0xffffff, 1.6)
  directional.position.set(1, 2, 3)
  scene.add(ambient, directional)
}

/**
 * 收集实例材质引用到的纹理。
 * @param scene 实例场景
 * @returns 纹理集合
 */
function collectSceneTextures(scene: ThreeNamespace.Object3D): Set<ThreeNamespace.Texture> {
  const textures = new Set<ThreeNamespace.Texture>()
  scene.traverse((object) => {
    const mesh = object as unknown as { material?: unknown }
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    for (const material of materials) {
      if (!material || typeof material !== 'object') {
        continue
      }
      for (const key of Object.keys(material as Record<string, unknown>)) {
        const value = (material as Record<string, unknown>)[key] as { isTexture?: boolean } | null
        if (value && value.isTexture === true) {
          textures.add(value as ThreeNamespace.Texture)
        }
      }
    }
  })
  return textures
}

/**
 * 等待纹理就绪：ImageBitmap 视为已解码，HTMLImageElement 等待 decode()，并预热纹理。
 * @param targetRenderer 当前渲染器
 * @param scene 实例场景
 */
async function waitForTexturesReady(
  targetRenderer: ThreeNamespace.WebGLRenderer,
  scene: ThreeNamespace.Object3D,
): Promise<void> {
  const textures = collectSceneTextures(scene)
  for (const texture of textures) {
    const image = texture.image as { decode?: () => Promise<void> } | null | undefined
    const isBitmap = typeof ImageBitmap !== 'undefined' && image instanceof ImageBitmap
    if (image && !isBitmap && typeof image.decode === 'function') {
      try {
        await image.decode()
      } catch {
        // 解码失败交由后续渲染与探针兜底，不阻断就绪流程。
      }
    }
    try {
      targetRenderer.initTexture?.(texture)
    } catch {
      // 部分后端不支持预热，忽略。
    }
  }
}

/**
 * 应用背景色。
 * @param targetRenderer 当前渲染器
 * @param background 背景色声明
 * @param engineRef 已加载引擎
 */
function applyBackground(
  targetRenderer: ThreeNamespace.WebGLRenderer,
  background: string,
  engineRef: Model3dEngine,
): void {
  const { THREE } = engineRef
  const color = parseBackgroundColor(background)
  if (!color || isTransparentBackground(background)) {
    targetRenderer.setClearColor(0x000000, 0)
    return
  }
  // 组件色值按 sRGB 声明；直接传分量会被 Three.js 当作线性工作空间，导致背景明显偏亮。
  const clearColor = new THREE.Color().setRGB(color.r, color.g, color.b, THREE.SRGBColorSpace)
  targetRenderer.setClearColor(clearColor, color.a)
}

/**
 * 更新渲染器尺寸与相机长宽比并请求重绘；零尺寸时暂停渲染。
 */
function applyContainerSize(): void {
  const { width, height } = readContainerSize()
  if (width <= 0 || height <= 0) {
    paused = true
    return
  }
  paused = false
  const aspect = resolveCameraAspect(width, height)

  if (renderer) {
    renderer.setPixelRatio(resolveModel3dPixelRatio(typeof window !== 'undefined' ? window.devicePixelRatio : 1))
    renderer.setSize(width, height, false)
  }

  if (activeCamera && engine) {
    if (cameraMode === 'auto' && autoFitSphere) {
      resizeAutoFitCamera(
        activeCamera as ThreeNamespace.PerspectiveCamera,
        autoFitSphere, props.cameraFov ?? 45, aspect, controls !== null,
      )
    } else if (cameraMode === 'source') {
      adaptSourceCamera(activeCamera, aspect)
    }
  }

  requestRender()
}

/**
 * 处理尺寸变化：零尺寸暂停渲染，恢复后重绘。
 */
function handleResize(): void {
  applyContainerSize()
}

/**
 * 处理可见性变化：隐藏时暂停，恢复时重绘。
 */
function handleVisibilityChange(): void {
  if (typeof document === 'undefined') {
    return
  }
  if (document.hidden) {
    paused = true
    return
  }
  paused = false
  requestRender()
}

/**
 * 处理 WebGL 上下文丢失：preventDefault 以允许恢复，并进入 error 态提示。
 * @param event 上下文丢失事件
 */
function handleContextLost(event: Event): void {
  event.preventDefault()
  const token = requestToken
  if (token === requestToken && !disposed) {
    state.value = 'error'
    stateMessage.value = boundMessage('WebGL 上下文丢失，正在尝试恢复。')
  }
  paused = true
  // 丢失前的渲染证据不再可信：恢复后必须重新渲染成功才能回到 ready。
  pendingRenderProof = true
}

/**
 * 处理 WebGL 上下文恢复：重建绘制，等待新的一帧真实渲染后再回到 ready。
 */
function handleContextRestored(): void {
  const token = requestToken
  paused = false
  requestRender()
  void markReadyAfterRenderedFrame(token)
}

/**
 * 解析交互控制器的初始轨道中心。
 *
 * OrbitControls 默认 target 为原点，首次 update 会把相机强行转向原点；
 * 这里按当前相机类型给出与既有姿态一致的目标点，保证启用交互不改变初始视角。
 * @param camera 当前相机
 * @param options 规范化后的展示参数
 * @param engineRef 已加载引擎
 * @returns 轨道中心
 */
function resolveControlsTarget(
  camera: ThreeNamespace.Camera,
  options: ReturnType<typeof normalizeModelViewOptions>['options'],
  engineRef: Model3dEngine,
): ThreeNamespace.Vector3 {
  const { THREE } = engineRef
  if (options.cameraTarget) {
    return new THREE.Vector3(options.cameraTarget[0], options.cameraTarget[1], options.cameraTarget[2])
  }
  if (cameraMode === 'auto' && autoFitSphere) {
    return new THREE.Vector3(autoFitSphere.center.x, autoFitSphere.center.y, autoFitSphere.center.z)
  }
  // 源相机没有可用的目标点：沿当前视线取场景包围球半径处，保持朝向不变且轨道半径合理。
  const forward = new THREE.Vector3()
  camera.getWorldDirection(forward)
  const radius = activeScene ? computeSceneBoundingSphere(activeScene, engineRef).radius : 0
  const distance = Number.isFinite(radius) && radius > 0 ? radius : Math.max(camera.position.length(), 1)
  return camera.position.clone().add(forward.multiplyScalar(distance))
}

/**
 * 把相机上方向同步为当前世界姿态的上方向。
 *
 * OrbitControls 与 lookAt 都按 `camera.up` 扶正画面；源相机可能带滚转，
 * 只恢复视线仍会被默认 +Y 上方向扶正，因此构造控制器前必须从世界矩阵取上方向。
 * @param camera 当前相机
 * @param engineRef 已加载引擎
 */
function alignCameraUpToWorldPose(camera: ThreeNamespace.Camera, engineRef: Model3dEngine): void {
  const { THREE } = engineRef
  const elements = camera.matrixWorld.elements
  const up = new THREE.Vector3(elements[4], elements[5], elements[6])
  if (up.lengthSq() > 0) {
    camera.up.copy(up.normalize())
  }
}

/**
 * 绑定 canvas 事件与控制器。
 * @param options 规范化后的展示参数
 * @param engineRef 已加载引擎
 */
function bindCanvasRuntime(
  options: ReturnType<typeof normalizeModelViewOptions>['options'],
  engineRef: Model3dEngine,
): void {
  const canvas = renderer?.domElement as HTMLCanvasElement
  canvasElement = canvas
  contextLostHandler = handleContextLost
  contextRestoredHandler = handleContextRestored
  canvas.addEventListener('webglcontextlost', contextLostHandler, false)
  canvas.addEventListener('webglcontextrestored', contextRestoredHandler, false)

  if (options.interactive && engineRef.OrbitControls && renderer && activeCamera) {
    // OrbitControls 构造函数会立即 update 并把相机转向默认 target（原点），
    // 因此必须在构造前保存原始视线与上方向；构造后再写回 target 并 update 恢复完整姿态。
    const controlsTarget = resolveControlsTarget(activeCamera, options, engineRef)
    alignCameraUpToWorldPose(activeCamera, engineRef)
    const instance = new engineRef.OrbitControls(activeCamera, canvas) as unknown as OrbitControlsLike
    instance.enableDamping = false
    instance.target?.copy(controlsTarget)
    instance.addEventListener?.('change', () => requestRender())
    instance.update()
    controls = instance
  }
}

/**
 * 执行完整的加载与渲染流程。
 * @param token 本次加载令牌
 */
async function startLoad(token: number): Promise<void> {
  const name = String(props.name || '').trim()
  const src = String(props.src || '').trim()

  const normalized = normalizeModelViewOptions({
    name,
    sceneIndex: props.sceneIndex,
    cameraIndex: props.cameraIndex,
    cameraPosition: props.cameraPosition,
    cameraTarget: props.cameraTarget,
    cameraFov: props.cameraFov,
    background: props.background,
    lighting: props.lighting,
    interactive: props.interactive,
    fallback: props.fallback,
  })
  if (!normalized.ok) {
    fail(normalized.errors.join(' '), token)
    return
  }
  const options = normalized.options

  // 记录本次加载的资源与视角身份，供导出静态帧采集句柄分区使用。
  activeStaticFrameSrc = src
  activeStaticFrameViewKey = buildModelViewIdentityKey(options)

  const metadata = resolveAssetMetadata(name)
  if (metadata?.render_type && metadata.render_type !== 'model3d') {
    fail(`资源 ${name} 的 render_type 为 ${metadata.render_type}，不是三维模型资源。`, token)
    return
  }

  if (!src) {
    fail(fallbackMessage.value, token)
    return
  }

  const localEngine = await loadModel3dEngine(options.interactive)
  if (token !== requestToken || disposed) {
    return
  }
  engine = localEngine

  abortController = new AbortController()
  const response = await fetch(src, { signal: abortController.signal })
  if (token !== requestToken || disposed) {
    return
  }
  if (!response.ok) {
    throw new Error(`三维资源加载失败：HTTP ${response.status}。`)
  }
  const buffer = await response.arrayBuffer()
  if (token !== requestToken || disposed) {
    return
  }

  const key = buildModelCacheKey({
    fileHashOrUrl: src,
    engineVersion: MODEL3D_ENGINE_POLICY.engineVersion,
    validationProfile: MODEL3D_ENGINE_POLICY.validationProfile,
  })
  const parsed = await sharedModelResourceCache.acquire(key, () => parseGlbToResource(buffer, localEngine))
  if (token !== requestToken || disposed) {
    sharedModelResourceCache.release(key)
    return
  }
  cachedKey = key

  const { width, height } = readContainerSize()
  const aspect = resolveCameraAspect(width || 1, height || 1)

  const sourceScene = selectScene(parsed, options.sceneIndex, localEngine)
  const renderScene = new localEngine.THREE.Scene()
  renderScene.add(cloneSceneForInstance(sourceScene, localEngine))
  activeScene = renderScene
  applyLighting(renderScene, options.lighting, localEngine)
  activeCamera = resolveCamera({ sourceScene, renderScene, parsed, options, aspect, engineRef: localEngine })

  // 创建独立渲染器与 canvas。
  const canvas = document.createElement('canvas')
  const createdRenderer = new localEngine.THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
    preserveDrawingBuffer: false,
  })
  renderer = createdRenderer
  configureModel3dRenderer(createdRenderer, localEngine)
  applyBackground(createdRenderer, options.background, localEngine)
  createdRenderer.setPixelRatio(resolveModel3dPixelRatio(typeof window !== 'undefined' ? window.devicePixelRatio : 1))
  createdRenderer.setSize(width || 1, height || 1, false)

  const surface = surfaceRef.value
  if (!surface) {
    throw new Error('三维渲染容器未就绪。')
  }
  surface.appendChild(canvas)

  bindCanvasRuntime(options, localEngine)

  await waitForTexturesReady(createdRenderer, renderScene)
  if (token !== requestToken || disposed) {
    return
  }

  renderFrame()
  if (!hasRenderedFrame) {
    throw new Error('三维资源首次绘制失败。')
  }
  await markReady(token)
}

/**
 * 重新加载当前实例。
 */
async function reload(): Promise<void> {
  const token = ++requestToken
  teardownInstance()
  state.value = 'loading'
  stateMessage.value = ''
  await nextTick()
  if (token !== requestToken || disposed) {
    return
  }
  try {
    await startLoad(token)
  } catch (error) {
    fail(toErrorMessage(error), token)
  }
}

watch(
  () => [
    props.name,
    props.src,
    props.sceneIndex,
    props.cameraIndex,
    props.cameraPosition,
    props.cameraTarget,
    props.cameraFov,
    props.background,
    props.lighting,
    props.interactive,
  ],
  () => {
    void reload()
  },
)

onMounted(async () => {
  await nextTick()
  installStaticFrameHandle()
  if (viewerRoot.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => handleResize())
    resizeObserver.observe(viewerRoot.value)
    if (surfaceRef.value) {
      resizeObserver.observe(surfaceRef.value)
    }
  }
  if (viewerRoot.value && typeof IntersectionObserver !== 'undefined') {
    intersectionObserver = new IntersectionObserver((entries) => {
      const visible = entries.some(entry => entry.isIntersecting)
      if (visible) {
        paused = false
        requestRender()
      } else {
        paused = true
      }
    }, { threshold: 0 })
    intersectionObserver.observe(viewerRoot.value)
  }
  if (typeof document !== 'undefined') {
    visibilityHandler = handleVisibilityChange
    document.addEventListener('visibilitychange', visibilityHandler)
  }

  await reload()
})

onBeforeUnmount(() => {
  disposed = true
  requestToken += 1
  uninstallStaticFrameHandle()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (intersectionObserver) {
    intersectionObserver.disconnect()
    intersectionObserver = null
  }
  if (visibilityHandler && typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', visibilityHandler)
    visibilityHandler = null
  }
  teardownInstance()
})

/**
 * 解析静态帧采集上下文；仅在实例真实就绪、已渲染且画布尺寸有效时返回。
 * 约束：取消/错误/上下文丢失与零尺寸画布都必须拒绝采集，避免导出空白帧。
 * @returns 画布与场景/相机；不可采集时返回 null
 */
function resolveStaticFrameContext(): {
  canvas: HTMLCanvasElement
  scene: ThreeNamespace.Scene
  camera: ThreeNamespace.Camera
} | null {
  if (disposed || state.value !== 'ready' || !hasRenderedFrame) {
    return null
  }
  if (!renderer || !activeScene || !activeCamera) {
    return null
  }
  const canvas = renderer.domElement as HTMLCanvasElement | undefined
  if (!canvas || canvas.width <= 1 || canvas.height <= 1) {
    return null
  }
  return { canvas, scene: activeScene, camera: activeCamera }
}

/**
 * 读取当前实例的静态帧身份；未就绪时返回 null。
 * 身份包含资源名/资源地址、视角键与帧像素尺寸，供导出侧缓存分区。
 * @returns 实例身份；不可采集时返回 null
 */
function describeStaticFrame(): ModelStaticFrameIdentity | null {
  const context = resolveStaticFrameContext()
  if (!context) {
    return null
  }
  if (!activeStaticFrameSrc) {
    return null
  }
  return {
    resourceName: String(props.name || '').trim(),
    resourceSrc: activeStaticFrameSrc,
    viewKey: buildModelCameraViewKey(activeStaticFrameViewKey, context.camera),
    frameWidth: context.canvas.width,
    frameHeight: context.canvas.height,
  }
}

/**
 * 采集当前静态帧：同步重绘后立即读回 PNG，不改变视角、不启用交互。
 * 关键约束：renderer 使用 preserveDrawingBuffer: false，必须 render 与 toDataURL 处于同一同步任务。
 * @returns PNG dataURL 与采集时刻身份；尚未就绪或采集失败时返回 null
 */
function captureStaticFrame(): ModelStaticFrameCapture | null {
  const context = resolveStaticFrameContext()
  if (!context) {
    return null
  }
  try {
    renderFrame()
    const dataUrl = context.canvas.toDataURL('image/png')
    if (!dataUrl.startsWith('data:image/png')) {
      return null
    }
    const identity = describeStaticFrame()
    if (!identity) {
      return null
    }
    return { ...identity, dataUrl }
  } catch {
    return null
  }
}

/**
 * 向根元素注册静态帧采集句柄，供 PDF/PPTX 导出在采集前读取当前帧。
 * 卸载时必须按同一引用注销，避免残留悬空句柄。
 */
function installStaticFrameHandle(): void {
  const root = viewerRoot.value
  if (!root) {
    return
  }
  const handle: ModelStaticFrameHandle = {
    describe: describeStaticFrame,
    capture: captureStaticFrame,
  }
  ;(root as unknown as Record<string, unknown>)[MODEL_STATIC_FRAME_HANDLE_KEY] = handle
  registeredStaticFrameHandle = handle
}

/**
 * 注销根元素上的静态帧采集句柄；仅移除本实例注册的引用。
 */
function uninstallStaticFrameHandle(): void {
  const root = viewerRoot.value
  if (root) {
    const record = root as unknown as Record<string, unknown>
    if (record[MODEL_STATIC_FRAME_HANDLE_KEY] === registeredStaticFrameHandle) {
      delete record[MODEL_STATIC_FRAME_HANDLE_KEY]
    }
  }
  registeredStaticFrameHandle = null
}

defineExpose({
  captureStaticFrame,
  reload,
})
</script>

<style scoped>
.model-viewer {
  position: relative;
  box-sizing: border-box;
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.model-viewer--interactive {
  cursor: grab;
}

.model-viewer__surface {
  position: absolute;
  inset: 0;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.model-viewer__surface :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

.model-viewer__surface--hidden {
  visibility: hidden;
}

.model-viewer__loading,
.model-viewer__error {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px;
  text-align: center;
}

.model-viewer__loading {
  background: rgba(248, 250, 252, 0.82);
  color: #64748b;
  font-size: 13px;
}

.model-viewer__error {
  background: #f8fafc;
  color: #64748b;
  font-size: 13px;
}

.model-viewer__error-message {
  color: #475569;
  font-weight: 600;
}

.model-viewer__error-detail {
  max-width: 100%;
  color: #94a3b8;
  font-size: 12px;
  word-break: break-word;
}
</style>
