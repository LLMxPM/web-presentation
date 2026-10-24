/**
 * 文件功能：复用已绘制的 Three.js WebGL 渲染器，限制反复进出模型页时的上下文增长。
 * 同时可见的 Viewer 仍独占各自实例；仅卸载后的空闲实例允许重新分配。
 */
import type * as ThreeNamespace from 'three'
import type { Model3dEngine } from './engine'

interface PooledRenderer {
  renderer: ThreeNamespace.WebGLRenderer
  constructorRef: Model3dEngine['THREE']['WebGLRenderer']
}

const MAX_IDLE_RENDERERS = 4
const idleRenderers: PooledRenderer[] = []

/**
 * 借用同版本渲染器；没有空闲实例时创建新 canvas 与 WebGL 上下文。
 * @param engine 已加载的 Three.js 引擎
 * @returns 本次 Viewer 独占的渲染器
 */
export function acquireModelRenderer(engine: Model3dEngine): ThreeNamespace.WebGLRenderer {
  const constructorRef = engine.THREE.WebGLRenderer
  const index = idleRenderers.findIndex(entry => entry.constructorRef === constructorRef)
  if (index >= 0) {
    return idleRenderers.splice(index, 1)[0].renderer
  }
  return new constructorRef({
    canvas: document.createElement('canvas'),
    alpha: true,
    antialias: true,
    preserveDrawingBuffer: false,
  })
}

/**
 * 归还已卸载 Viewer 的渲染器；清空旧场景引用，超出空闲上限则销毁上下文。
 * @param renderer 当前 Viewer 的独占渲染器
 * @param engine 创建该渲染器所用的引擎
 */
export function releaseModelRenderer(renderer: ThreeNamespace.WebGLRenderer, engine: Model3dEngine): void {
  try {
    renderer.setAnimationLoop?.(null)
    renderer.renderLists?.dispose()
    renderer.resetState?.()
  } catch {
    disposeRenderer(renderer)
    return
  }
  if (idleRenderers.length < MAX_IDLE_RENDERERS) {
    idleRenderers.push({ renderer, constructorRef: engine.THREE.WebGLRenderer })
    return
  }
  disposeRenderer(renderer)
}

/**
 * 主动清空空闲池，供测试隔离及页面宿主显式退出时释放 GPU 资源。
 */
export function drainModelRendererPool(): void {
  for (const entry of idleRenderers.splice(0)) {
    disposeRenderer(entry.renderer)
  }
}

/** 销毁超额或主动排空的渲染器。 */
function disposeRenderer(renderer: ThreeNamespace.WebGLRenderer): void {
  try {
    renderer.dispose()
    renderer.forceContextLoss()
  } catch {
    // WebGL 上下文已丢失时仍须允许页面卸载继续执行。
  }
}
