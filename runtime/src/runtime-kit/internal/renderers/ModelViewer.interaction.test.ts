/** 文件功能：用真实 Three.js 相机和模拟 WebGL 回归 Viewer 尺寸更新、双实例及交互后的静态帧导出。 */
import * as THREE from 'three'
import type { Camera } from 'three'
import { createApp, type App } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearDefaultModelStaticFrameCache, prepareModelStaticFrames } from '@/core/services/export/model-static-frames'
import { findModelStaticFrameImage } from '@/core/shared/model-static-frame-contract'
import ModelViewer from './ModelViewer.vue'

const probes = vi.hoisted(() => ({
  renderers: [] as Array<{ camera: Camera | null }>,
  controls: [] as Array<{ object: Camera; target?: { x: number; y: number; z: number } }>,
  resizes: [] as Array<() => void>,
  clearColors: [] as Array<{ color: { getHexString: () => string }; alpha: number }>,
  useOrthoCamera: false,
  useSourceCamera: false,
  sourceCameraRoll: false,
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
    setClearColor(color: unknown, alpha: number) {
      probes.clearColors.push({ color: color as { getHexString: () => string }, alpha })
    }
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

  /** 保留真实控制器语义：构造时立即 update 到默认 target，之后 update 按当前 target 修正朝向。 */
  class Controls {
    target = new THREE.Vector3()
    constructor(public object: Camera) {
      probes.controls.push(this)
      this.update()
    }
    update() { this.object.lookAt(this.target) }
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
      const cameras: import('three').Camera[] = []
      if (probes.useOrthoCamera) {
        const orthoCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 100)
        scene.add(orthoCamera)
        cameras.push(orthoCamera)
      }
      if (probes.useSourceCamera) {
        const sourceCamera = new THREE.PerspectiveCamera(45, 1, 0.1, 100)
        sourceCamera.position.set(4, 5, 6)
        sourceCamera.lookAt(1, 2, 3)
        if (probes.sourceCameraRoll) {
          sourceCamera.rotateZ(Math.PI / 2)
        }
        sourceCamera.updateMatrixWorld(true)
        scene.add(sourceCamera)
        cameras.push(sourceCamera)
      }
      return { gltf: { scene }, scenes: [scene], cameras, animations: [], dispose() {} }
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
  probes.clearColors.length = 0
  probes.useOrthoCamera = false
  probes.useSourceCamera = false
  probes.sourceCameraRoll = false
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
async function mountViewer(extraProps: Record<string, unknown> = {}): Promise<HTMLElement> {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const viewerProps = { name: 'product', src: './interaction.glb', interactive: true, ...extraProps }
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

  it('启用交互时以显式相机目标为轨道中心，不得回落到原点', async () => {
    await mountViewer({ cameraPosition: [4, 5, 6], cameraTarget: [1, 2, 3] })
    const camera = probes.controls[0].object
    const expected = new THREE.PerspectiveCamera()
    expected.position.set(4, 5, 6)
    expected.lookAt(1, 2, 3)
    expect(camera.quaternion.angleTo(expected.quaternion)).toBeLessThan(1e-6)
    expect(probes.controls[0].target).toMatchObject({ x: 1, y: 2, z: 3 })
  })

  it('源相机开启交互后保持原始朝向，不因控制器构造期默认 target 偏转', async () => {
    probes.useSourceCamera = true
    await mountViewer({ src: './source-camera.glb' })
    const camera = probes.controls[0].object
    const expected = new THREE.PerspectiveCamera()
    expected.position.set(4, 5, 6)
    expected.lookAt(1, 2, 3)
    expect(camera.quaternion.angleTo(expected.quaternion)).toBeLessThan(1e-6)
  })

  it('带滚转的源相机开启交互后保留滚转角，不被默认上方向扶正', async () => {
    probes.useSourceCamera = true
    probes.sourceCameraRoll = true
    await mountViewer({ src: './rolled-source-camera.glb' })
    const camera = probes.controls[0].object
    const expected = new THREE.PerspectiveCamera()
    expected.position.set(4, 5, 6)
    expected.lookAt(1, 2, 3)
    expected.rotateZ(Math.PI / 2)
    expected.updateMatrixWorld(true)
    expect(camera.quaternion.angleTo(expected.quaternion)).toBeLessThan(1e-6)
  })

  it('正交源相机多次改变容器比例后按源视锥重算，不累计放大', async () => {
    probes.useOrthoCamera = true
    width = 640
    // 使用独立地址避开共享模型缓存，确保命中带正交相机的解析结果。
    await mountViewer({ src: './ortho.glb' })
    const camera = probes.controls[0].object as THREE.OrthographicCamera
    expect(camera.type).toBe('OrthographicCamera')
    expect(camera.right - camera.left).toBeCloseTo(6.4)
    expect(camera.top - camera.bottom).toBeCloseTo(2)

    width = 320
    probes.resizes.forEach(resize => resize())
    expect(camera.right - camera.left).toBeCloseTo(3.2)
    expect(camera.top - camera.bottom).toBeCloseTo(2)

    width = 640
    probes.resizes.forEach(resize => resize())
    expect(camera.right - camera.left).toBeCloseTo(6.4)
    expect(camera.top - camera.bottom).toBeCloseTo(2)
  })

  it('背景色按 sRGB 声明转换清屏色，不得按线性工作空间解释', async () => {
    await mountViewer({ background: '#0f0f10' })
    const clear = probes.clearColors.at(-1)
    expect(clear?.alpha).toBe(1)
    expect(clear?.color.getHexString()).toBe('0f0f10')
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
