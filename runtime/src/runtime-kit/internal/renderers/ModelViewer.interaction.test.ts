/** 文件功能：用真实 Three.js 相机和模拟 WebGL 回归 Viewer 尺寸更新、双实例及交互后的静态帧导出。 */
import type { Camera } from 'three'
import { createApp, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearDefaultModelStaticFrameCache, prepareModelStaticFrames } from '@/core/services/export/model-static-frames'
import { findModelStaticFrameImage } from '@/core/shared/model-static-frame-contract'
import ModelViewer from './ModelViewer.vue'

const probes = vi.hoisted(() => ({
  renderers: [] as Array<{ camera: Camera | null }>,
  controls: [] as Array<{ object: Camera }>,
  resizes: [] as Array<() => void>,
}))

vi.mock('./model3d/engine', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./model3d/engine')>()
  const THREE = await import('three')

  /** 只替换 GPU 执行，保留真实场景、相机和采集入口。 */
  class Renderer {
    domElement: HTMLCanvasElement
    camera: Camera | null = null
    constructor(options: { canvas: HTMLCanvasElement }) {
      this.domElement = options.canvas
      probes.renderers.push(this)
    }
    setPixelRatio() {}
    setClearColor() {}
    setSize(width: number, height: number) {
      this.domElement.width = width
      this.domElement.height = height
    }
    render(_scene: unknown, camera: Camera) {
      this.camera = camera
      this.domElement.dataset.pose = JSON.stringify(camera.position.toArray())
    }
    dispose() {}
    forceContextLoss() {}
  }

  /** 保留控制器绑定相机的语义，测试直接模拟旋转后的相机姿态。 */
  class Controls {
    constructor(public object: Camera) { probes.controls.push(this) }
    update() {}
    dispose() {}
    addEventListener() {}
  }

  return {
    ...actual,
    loadModel3dEngine: async () => ({
      THREE: { ...THREE, WebGLRenderer: Renderer },
      OrbitControls: Controls,
      SkeletonUtils: { clone: (scene: import('three').Group) => scene.clone(true) },
    }),
    parseGlbToResource: async () => {
      const scene = new THREE.Group()
      scene.add(new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial()))
      return { gltf: { scene }, scenes: [scene], cameras: [], animations: [], dispose() {} }
    },
  }
})

const mounted: App[] = []
let width = 320

beforeEach(() => {
  width = 320
  probes.renderers.length = 0
  probes.controls.length = 0
  probes.resizes.length = 0
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(200)
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockImplementation(function () {
    return `data:image/png;base64,${btoa(this.dataset.pose || '')}`
  })
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(0) })))
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { probes.resizes.push(callback) }
    observe() {}
    disconnect() {}
  })
})

afterEach(() => {
  mounted.splice(0).forEach(app => app.unmount())
  clearDefaultModelStaticFrameCache()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

/** 挂载真实 Viewer 并等待首帧就绪，返回模型根以驱动正式静态帧准备流程。 */
async function mountViewer(): Promise<HTMLElement> {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const viewerProps = { name: 'product', src: './interaction.glb', interactive: true }
  const app = createApp(ModelViewer, viewerProps)
  mounted.push(app)
  app.mount(host)
  const root = host.querySelector<HTMLElement>('.model-viewer')!
  await vi.waitFor(() => expect(root.dataset.runtimeModelState).toBe('ready'))
  return root
}

describe('ModelViewer 交互与静态帧', () => {
  it('尺寸变化后继续渲染控制器持有的同一相机，并保留交互姿态', async () => {
    await mountViewer()
    const originalCamera = probes.controls[0].object
    originalCamera.position.set(3, 4, 5)
    width = 640
    probes.resizes.forEach(resize => resize())
    await vi.waitFor(() => expect(probes.renderers[0].camera?.position.x).toBe(3))
    expect(probes.renderers[0].camera).toBe(originalCamera)
    expect((originalCamera as import('three').PerspectiveCamera).aspect).toBe(3.2)
    expect(originalCamera.position.toArray()).toEqual([3, 4, 5])
  })

  it('相同 props 的两个实例旋转后分别采集各自的当前帧', async () => {
    const left = await mountViewer()
    const right = await mountViewer()
    probes.controls[0].object.position.set(-3, 1, 4)
    probes.controls[1].object.position.set(3, 1, 4)
    const prepared = prepareModelStaticFrames(document.body)
    try {
      expect(prepared.preparedCount).toBe(2)
      expect(findModelStaticFrameImage(left)?.src).not.toBe(findModelStaticFrameImage(right)?.src)
    } finally {
      prepared.cleanup()
    }
  })

  it('同一实例旋转后再次导出不会复用旧 PNG', async () => {
    const root = await mountViewer()
    const first = prepareModelStaticFrames(root)
    const originalFrame = findModelStaticFrameImage(root)?.src
    first.cleanup()
    probes.controls[0].object.position.x += 2
    const second = prepareModelStaticFrames(root)
    try {
      expect(findModelStaticFrameImage(root)?.src).not.toBe(originalFrame)
    } finally {
      second.cleanup()
    }
  })
})
