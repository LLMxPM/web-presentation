/**
 * 文件用途：计算三维模型的可视包围球，供自动取景与交互轨道中心使用。
 *
 * 克隆后的蒙皮绑定逆矩阵必须先随世界矩阵更新，再按真实蒙皮顶点重算实例边界。
 * 点、线和实例化网格沿用各自的几何或对象边界，不能只按普通 Mesh 的几何处理。
 */
import type * as Three from 'three'

import type { BoundingSphere } from './camera-fit'

/** 同时覆盖 Mesh、Points、Line 与具有实例级包围盒的对象。 */
type GeometryObject = Three.Object3D & {
  geometry?: Three.BufferGeometry
  boundingBox?: Three.Box3 | null
  computeBoundingBox?: () => void
}

/**
 * 计算场景可视包围球。
 * @param THREE 已加载的 three 命名空间
 * @param scene 渲染场景（或模型根节点）
 * @returns 可视包围球；场景内没有可见几何时返回零半径
 */
export function computeVisibleBoundingSphere(
  THREE: typeof import('three'),
  scene: Three.Object3D,
): BoundingSphere {
  // updateWorldMatrix 不会调用 SkinnedMesh 的绑定逆矩阵更新，因此还需 updateMatrixWorld。
  scene.updateWorldMatrix(true, false)
  scene.updateMatrixWorld(true)
  const box = new THREE.Box3()
  const worldBox = new THREE.Box3()

  scene.traverseVisible((object) => {
    const renderable = object as GeometryObject
    const geometry = renderable.geometry
    if (!geometry) return

    const mesh = object as Three.SkinnedMesh
    const canComputeObjectBounds = !mesh.isSkinnedMesh || Boolean(mesh.skeleton?.bones.length)
    let localBox: Three.Box3 | null | undefined
    if (canComputeObjectBounds && renderable.computeBoundingBox) {
      // 重算蒙皮姿态和实例矩阵，避免继承源实例或上一姿态的缓存包围盒。
      renderable.computeBoundingBox()
      localBox = renderable.boundingBox
    } else {
      if (!geometry.boundingBox) geometry.computeBoundingBox()
      localBox = geometry.boundingBox
    }
    if (localBox) {
      box.union(worldBox.copy(localBox).applyMatrix4(object.matrixWorld))
    }
  })

  if (box.isEmpty()) {
    return { center: { x: 0, y: 0, z: 0 }, radius: 0 }
  }

  const sphere = box.getBoundingSphere(new THREE.Sphere())
  return {
    center: { x: sphere.center.x, y: sphere.center.y, z: sphere.center.z },
    radius: sphere.radius,
  }
}
