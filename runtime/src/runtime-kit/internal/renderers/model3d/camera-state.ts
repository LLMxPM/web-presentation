/** 文件功能：维护三维相机的原位尺寸更新和实际姿态身份，保证交互与静态帧缓存一致。 */
import type { Camera, PerspectiveCamera } from 'three'
import { computeAutoFitCamera, type BoundingSphere } from './camera-fit'

/**
 * 原位适配自动取景相机；交互中保留用户姿态，其余场景按新宽高比重新取景。
 * 保持相机对象不变，避免 OrbitControls 继续操作已被替换的旧相机。
 */
export function resizeAutoFitCamera(
  camera: PerspectiveCamera,
  sphere: BoundingSphere,
  fovDeg: number,
  aspect: number,
  preservePose: boolean,
): void {
  camera.aspect = aspect
  if (!preservePose) {
    const view = computeAutoFitCamera({ sphere, fovDeg, aspect })
    camera.fov = fovDeg
    camera.near = view.near
    camera.far = view.far
    camera.position.set(view.position.x, view.position.y, view.position.z)
    camera.lookAt(view.target.x, view.target.y, view.target.z)
  }
  camera.updateProjectionMatrix()
  camera.updateMatrixWorld(true)
}

/** 以声明参数、实际世界姿态和投影构建帧身份；旋转、平移、缩放与尺寸变化都会失效旧帧。 */
export function buildModelCameraViewKey(optionsKey: string, camera: Camera): string {
  camera.updateWorldMatrix(true, false)
  return JSON.stringify([optionsKey, camera.matrixWorld.elements, camera.projectionMatrix.elements])
}
