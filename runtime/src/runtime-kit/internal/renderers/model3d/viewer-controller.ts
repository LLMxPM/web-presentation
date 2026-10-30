/** 文件功能：协调模型资源加载与实例寿命，委托相机、就绪和静态采集模块；不向页面暴露共享对象。 */

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
  MODEL3D_ENGINE_POLICY,
  cloneSceneForInstance,
  configureModel3dRenderer,
  loadModel3dEngine,
  parseGlbToResource,
  resolveModel3dPixelRatio,
  sharedModelResourceCache,
  type Model3dEngine,
  type ParsedModelResource,
} from './engine'
import { buildModelCacheKey } from './model-cache'
import { acquireModelRenderer, releaseModelRenderer } from './renderer-pool'
import { resolveCameraAspect } from './camera-fit'
import { DEFAULT_MODEL_FALLBACK_MESSAGE, buildModelViewIdentityKey, normalizeModelViewOptions } from './view-options'
import { MODEL_SCENE_HANDLE_KEY } from './scene-contract'
import { createModelSceneController } from './scene-controller'
import { createModelWebglLifecycle } from './webgl-lifecycle'
import { getRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { isStaticSceneRoot } from '@/core/scene/scene-scope'
import { isStaticExecution } from '@/core/static-presentation/types'



import type { ModelViewerProps, OrbitControlsLike } from './viewer-types'
import { createModelCameraController } from './camera-controller'
import { applyLighting, applyBackground, waitForTexturesReady } from './instance-assets'
import { createModelFirstFrameReady } from './first-frame-ready'
import { createModelStaticFrameController } from './static-frame-controller'
type ModelRenderState = 'loading' | 'ready' | 'error'

/** 每次 Vue setup 建立独立 Viewer，卸载只释放自己的请求、控制器和缓存引用。 */
export function useModelViewer(props: Readonly<ModelViewerProps>) {
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

  const camera = createModelCameraController()

  let frameHandle: number | null = null
  const waitingFrames = new Map<number, () => void>()
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

  // —— 导出静态帧身份（采集句柄在 describe/capture 时读取最新值） ——
  /** 当前加载使用的资源地址；未加载成功时为空串。 */
  let activeStaticFrameSrc = ''
  /** 当前加载使用的视角身份键；由规范化展示参数派生。 */
  let activeStaticFrameViewKey = ''
  /** 已注册到根元素的采集句柄；卸载时按同一引用注销。 */


  let modelScene: ReturnType<typeof createModelSceneController> | null = null

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
      const handle = scheduleAnimationFrame(() => { waitingFrames.delete(handle); resolve() })
      waitingFrames.set(handle, resolve)
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
   * 释放当前实例：取消在途请求、断开控制器、释放渲染器与缓存引用。
   */
  function teardownInstance(): void {
    cancelScheduledFrame()
    for (const [handle, resolve] of waitingFrames) { cancelAnimationFrameHandle(handle); resolve() }
    waitingFrames.clear()
    const previous = modelScene
    modelScene = null
    if (viewerRoot.value && (viewerRoot.value as unknown as Record<string, unknown>)[MODEL_SCENE_HANDLE_KEY] === previous?.handle) {
      delete (viewerRoot.value as unknown as Record<string, unknown>)[MODEL_SCENE_HANDLE_KEY]
    }
    previous?.dispose()

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
    webgl.unbind()
    if (canvasElement?.parentElement) {
      canvasElement.parentElement.removeChild(canvasElement)
    }
    canvasElement = null
    if (renderer && engine) {
      releaseModelRenderer(renderer, engine)
    }
    renderer = null
    engine = null

    // 共享资源只递减引用计数；仅当缓存引用归零时才真正释放。
    if (cachedKey) {
      sharedModelResourceCache.release(cachedKey)
      cachedKey = null
    }

    activeCamera = null
    activeScene = null
    camera.reset()
    hasRenderedFrame = false
    pendingRenderProof = false
  }

  /**
   * 更新渲染器尺寸与相机长宽比并请求重绘；零尺寸时暂停渲染。
   */
  function applyContainerSize(): void {
    const { width, height } = readContainerSize()
    if (width <= 0 || height <= 0) {
      webgl.setSized(false)
      return
    }
    webgl.setSized(true)
    const aspect = resolveCameraAspect(width, height)

    if (renderer) {
      renderer.setPixelRatio(resolveModel3dPixelRatio(typeof window !== 'undefined' ? window.devicePixelRatio : 1))
      renderer.setSize(width, height, false)
    }

    if (activeCamera && engine) {
      camera.resize(activeCamera, props.cameraFov ?? 45, aspect, controls !== null)
    }

    requestRender()
  }

  /**
   * 处理尺寸变化：零尺寸暂停渲染，恢复后重绘。
   */
  function handleResize(): void {
    applyContainerSize()
  }

  const webgl = createModelWebglLifecycle({
    pause(value) { paused = value; modelScene?.setViewerSuspended(value); if (value) cancelScheduledFrame() },
    requestRender,
    lost() {
      pendingRenderProof = true
      state.value = 'error'; stateMessage.value = boundMessage('WebGL 上下文丢失，正在尝试恢复。')
      modelScene?.setBlocked('WebGL 上下文丢失，等待恢复。')
    },
    restored() {
      const token = requestToken
      void markReadyAfterRenderedFrame(token).then(() => {
        if (token === requestToken && state.value === 'ready') modelScene?.setBlocked(null)
      })
    },
  })

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
    webgl.bind(canvas)

    if (options.interactive && engineRef.OrbitControls && renderer && activeCamera) {
      // OrbitControls 构造函数会立即 update 并把相机转向默认 target（原点），
      // 因此必须在构造前保存原始视线与上方向；构造后再写回 target 并 update 恢复完整姿态。
      const controlsTarget = camera.resolveControlsTarget(activeCamera, options, engineRef, activeScene)
      camera.alignCameraUpToWorldPose(activeCamera, engineRef)
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

    const sourceScene = camera.selectScene(parsed, options.sceneIndex)
    const renderScene = new localEngine.THREE.Scene()
    const instanceRoot = cloneSceneForInstance(sourceScene, localEngine)
    // 整体变换应用在包装节点上，不覆盖片段内部骨骼/节点动画。
    const wrapper = new localEngine.THREE.Group()
    wrapper.name = 'runtime-model-motion-wrapper'
    wrapper.add(instanceRoot)
    renderScene.add(wrapper)
    activeScene = renderScene
    applyLighting(renderScene, options.lighting, localEngine)
    activeCamera = camera.resolveCamera({ sourceScene, renderScene, parsed, options, aspect, engineRef: localEngine })

    modelScene = createModelSceneController({ engine: localEngine, parsed, root: instanceRoot, wrapper, camera: activeCamera,
      target: camera.resolveControlsTarget(activeCamera, options, localEngine, activeScene),
      isReady: () => state.value === 'ready' && !disposed && token === requestToken && !options.interactive,
      isStatic: () => isStaticExecution(getRuntimeExecutionPolicy().kind) || Boolean(viewerRoot.value && isStaticSceneRoot(viewerRoot.value)), render: requestRender,
    })
    if (viewerRoot.value) (viewerRoot.value as unknown as Record<string, unknown>)[MODEL_SCENE_HANDLE_KEY] = modelScene.handle

    // 同时可见实例独占渲染器；页面往返时借用空闲上下文。
    const createdRenderer = acquireModelRenderer(localEngine)
    const canvas = createdRenderer.domElement as HTMLCanvasElement
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
    if (token === requestToken && state.value === 'ready') modelScene?.setBlocked(null)
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


  const { markReady, markReadyAfterRenderedFrame } = createModelFirstFrameReady({
    state, message: stateMessage, isCurrent: token => token === requestToken && !disposed,
    hasRenderProof: () => hasRenderedFrame && !pendingRenderProof, waitForFrame: waitForAnimationFrame, requestRender,
  })
  const { captureStaticFrame, installStaticFrameHandle, uninstallStaticFrameHandle } = createModelStaticFrameController({
    root: () => viewerRoot.value, resolveContext: resolveStaticFrameContext,
    resource: () => ({ name: String(props.name || '').trim(), src: activeStaticFrameSrc, viewKey: activeStaticFrameViewKey }), renderFrame,
  })

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
        webgl.setVisible(visible)
      }, { threshold: 0 })
      intersectionObserver.observe(viewerRoot.value)
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
    webgl.dispose()
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


  return { viewerRoot, surfaceRef, state, stateMessage, fallbackMessage, captureStaticFrame, reload }
}
