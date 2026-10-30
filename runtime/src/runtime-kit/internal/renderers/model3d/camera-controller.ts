/** 文件功能：按实例维护源相机、自动取景与控制器目标，隔离 resize 基线和源相机姿态。 */
import type * as ThreeNamespace from 'three'
import type { Model3dEngine, ParsedModelResource } from './engine'
import { resizeAutoFitCamera } from './camera-state'
import { adaptOrthographicFrustum, resolveOrthographicSourceFrustum, type BoundingSphere, type OrthoFrustum } from './camera-fit'
import { normalizeModelViewOptions } from './view-options'

/** 每个 Viewer 使用独立相机状态，重载时显式重置基线。 */
export function createModelCameraController() {
let cameraMode: 'auto' | 'source' = 'auto'
let autoFitSphere: BoundingSphere | null = null
let orthoSourceFrustum: OrthoFrustum | null = null
/**
 * 选择要渲染的场景。
 * @param parsed 解析结果
 * @param sceneIndex 源文件场景索引；null 表示缺省
 * @returns 选中的源场景
 */
function selectScene(
  parsed: ParsedModelResource,
  sceneIndex: number | null,
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
  renderScene: ThreeNamespace.Scene | null,
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
  const radius = renderScene ? computeSceneBoundingSphere(renderScene, engineRef).radius : 0
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


/** resize 保持用户交互后的姿态，源正交相机始终从原视锥重算。 */
function resize(camera: ThreeNamespace.Camera, fov: number, aspect: number, interactive: boolean): void {
  if (cameraMode === 'auto' && autoFitSphere) resizeAutoFitCamera(camera as ThreeNamespace.PerspectiveCamera, autoFitSphere, fov, aspect, interactive)
  else adaptSourceCamera(camera, aspect)
}
/** 新资源不得继承上一资源的包围球或正交基线。 */
function reset(): void { cameraMode = 'auto'; autoFitSphere = null; orthoSourceFrustum = null }
return { selectScene, resolveCamera, resize, reset, resolveControlsTarget, alignCameraUpToWorldPose }
}
