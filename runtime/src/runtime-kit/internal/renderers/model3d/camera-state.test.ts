/** 文件功能：验证相机原位尺寸更新与实际姿态缓存身份，不依赖 WebGL。 */
import { PerspectiveCamera } from 'three'
import { describe, expect, it } from 'vitest'
import { computeAutoFitCamera } from './camera-fit'
import { buildModelCameraViewKey, resizeAutoFitCamera } from './camera-state'

const sphere = { center: { x: 10, y: 2, z: 0 }, radius: 2 }

describe('模型相机状态', () => {
  it('自动取景尺寸变化在原相机上完成，控制器引用继续生效', () => {
    const camera = new PerspectiveCamera(45, 1)
    const controls = { object: camera }
    resizeAutoFitCamera(camera, sphere, 45, 0.5, false)
    const fit = computeAutoFitCamera({ sphere, fovDeg: 45, aspect: 0.5 })
    expect(controls.object).toBe(camera)
    expect(controls.object.position.toArray()).toEqual([fit.position.x, fit.position.y, fit.position.z])
    expect(camera.aspect).toBe(0.5)
  })

  it('交互后的旋转和平移在尺寸变化时保留，投影随宽高比更新', () => {
    const camera = new PerspectiveCamera(45, 1)
    camera.position.set(3, 4, 5)
    camera.lookAt(1, 2, 3)
    const position = camera.position.clone()
    const rotation = camera.quaternion.clone()
    const projection = camera.projectionMatrix.clone()
    resizeAutoFitCamera(camera, sphere, 45, 2, true)
    expect(camera.position.equals(position)).toBe(true)
    expect(camera.quaternion.equals(rotation)).toBe(true)
    expect(camera.aspect).toBe(2)
    expect(camera.projectionMatrix.equals(projection)).toBe(false)
  })

  it('相同声明参数的两个实例按实际相机姿态区分静态帧', () => {
    const left = new PerspectiveCamera(45, 1)
    const right = new PerspectiveCamera(45, 1)
    left.position.set(-3, 1, 4)
    right.position.set(3, 1, 4)
    left.lookAt(0, 0, 0)
    right.lookAt(0, 0, 0)
    expect(buildModelCameraViewKey('same-props', left)).not.toBe(buildModelCameraViewKey('same-props', right))
  })

  it('同一实例交互或投影变化后不得复用旧帧身份', () => {
    const camera = new PerspectiveCamera(45, 1)
    const initial = buildModelCameraViewKey('props', camera)
    camera.rotation.y = 0.4
    const rotated = buildModelCameraViewKey('props', camera)
    expect(rotated).not.toBe(initial)
    camera.fov = 60
    camera.updateProjectionMatrix()
    expect(buildModelCameraViewKey('props', camera)).not.toBe(rotated)
  })
})
