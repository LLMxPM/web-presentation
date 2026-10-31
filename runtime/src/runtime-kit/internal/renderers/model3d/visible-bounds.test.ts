/** 文件功能：验证模型取景覆盖真实蒙皮顶点、克隆后的绑定矩阵、点线和实例变换。 */
import * as THREE from 'three'
import { clone } from 'three/addons/utils/SkeletonUtils.js'
import { describe, expect, it } from 'vitest'

import { computeVisibleBoundingSphere } from './visible-bounds'

/** 为全部顶点绑定第一个骨骼，构造有效的单骨骼蒙皮几何。 */
function createSkinnedBox(size: number): THREE.BoxGeometry {
  const geometry = new THREE.BoxGeometry(size, size, size)
  const count = geometry.getAttribute('position').count
  geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(new Uint16Array(count * 4), 4))
  const weights = new THREE.Float32BufferAttribute(new Float32Array(count * 4), 4)
  for (let index = 0; index < count; index += 1) weights.setXYZW(index, 1, 0, 0, 0)
  geometry.setAttribute('skinWeight', weights)
  return geometry
}

/** 构造 GLTFLoader 风格的单位绑定矩阵与有效逆绑定矩阵，供真实 SkeletonUtils 克隆。 */
function createScaledSkinnedScene(): THREE.Group {
  const root = new THREE.Group()
  const armature = new THREE.Group()
  armature.scale.setScalar(100)
  root.add(armature)
  const boneRoot = new THREE.Bone()
  const boneTip = new THREE.Bone()
  boneTip.position.y = 0.02
  boneRoot.add(boneTip)
  armature.add(boneRoot)
  root.updateMatrixWorld(true)

  const skeleton = new THREE.Skeleton([boneRoot, boneTip])
  const mesh = new THREE.SkinnedMesh(createSkinnedBox(1), new THREE.MeshBasicMaterial())
  mesh.position.y = 0.02
  mesh.scale.setScalar(100)
  root.add(mesh)
  mesh.bind(skeleton, new THREE.Matrix4())
  root.updateMatrixWorld(true)
  return root
}

describe('computeVisibleBoundingSphere', () => {
  it('普通网格保留几何边界与世界变换', () => {
    const scene = new THREE.Group()
    const left = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial())
    const right = left.clone()
    left.position.set(-1, 0.5, 0)
    right.position.set(1, 0.5, 0)
    scene.add(left, right)
    const sphere = computeVisibleBoundingSphere(THREE, scene)
    expect(sphere.center).toEqual({ x: 0, y: 0.5, z: 0 })
    expect(sphere.radius).toBeCloseTo(Math.sqrt(11) / 2, 5)
  })

  it('真实克隆后刷新绑定逆矩阵，重算先前被放大的蒙皮缓存边界', () => {
    const source = createScaledSkinnedScene()
    const instance = clone(source)
    const stale = new THREE.Box3().setFromObject(instance).getBoundingSphere(new THREE.Sphere())
    const sphere = computeVisibleBoundingSphere(THREE, instance)

    // 克隆会以 bindMatrix 重新绑定；更新完整世界矩阵后，实际顶点仍是单位盒体。
    expect(stale.radius).toBeGreaterThan(sphere.radius * 20)
    expect(sphere.radius).toBeCloseTo(Math.sqrt(3) / 2, 5)
    expect(sphere.center.x).toBeCloseTo(0, 5)
    expect(sphere.center.y).toBeCloseTo(0, 5)
  })

  it('单骨骼盒体保留骨骼之外的完整网格尺寸', () => {
    const scene = new THREE.Group()
    const mesh = new THREE.SkinnedMesh(createSkinnedBox(10), new THREE.MeshBasicMaterial())
    const bone = new THREE.Bone()
    mesh.add(bone)
    mesh.bind(new THREE.Skeleton([bone]))
    scene.add(mesh)

    expect(computeVisibleBoundingSphere(THREE, scene).radius).toBeCloseTo(5 * Math.sqrt(3), 5)
  })

  it('重算当前骨骼姿态，不沿用上次的蒙皮边界缓存', () => {
    const scene = new THREE.Group()
    const mesh = new THREE.SkinnedMesh(createSkinnedBox(2), new THREE.MeshBasicMaterial())
    const bone = new THREE.Bone()
    mesh.add(bone)
    mesh.bind(new THREE.Skeleton([bone]))
    scene.add(mesh)
    computeVisibleBoundingSphere(THREE, scene)
    bone.position.x = 7

    const sphere = computeVisibleBoundingSphere(THREE, scene)
    expect(sphere.center.x).toBeCloseTo(7, 5)
    expect(sphere.radius).toBeCloseTo(Math.sqrt(3), 5)
  })

  it('蒙皮网格缺少骨骼时退回几何包围盒', () => {
    const mesh = new THREE.SkinnedMesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial())
    mesh.scale.setScalar(3)
    expect(computeVisibleBoundingSphere(THREE, mesh).radius).toBeCloseTo(3 * Math.sqrt(3), 5)
  })

  it('混合网格、点和线时，合并全部可见图元的范围', () => {
    const scene = new THREE.Group()
    scene.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial()))
    const points = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute([20, 0, 0], 3))
    const line = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute([-10, 0, 0, -5, 0, 0], 3))
    scene.add(new THREE.Points(points), new THREE.Line(line))

    const sphere = computeVisibleBoundingSphere(THREE, scene)
    expect(sphere.center).toEqual({ x: 5, y: 0, z: 0 })
    expect(sphere.radius).toBeCloseTo(Math.sqrt(30 ** 2 + 2) / 2, 5)
  })

  it('实例矩阵及其后续变化均计入对象边界', () => {
    const mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial(), 2)
    mesh.setMatrixAt(0, new THREE.Matrix4().makeTranslation(-10, 0, 0))
    mesh.setMatrixAt(1, new THREE.Matrix4().makeTranslation(10, 0, 0))
    expect(computeVisibleBoundingSphere(THREE, mesh).radius).toBeCloseTo(Math.sqrt(21 ** 2 + 2) / 2, 5)

    mesh.setMatrixAt(1, new THREE.Matrix4().makeTranslation(20, 0, 0))
    mesh.position.y = 3
    const sphere = computeVisibleBoundingSphere(THREE, mesh)
    expect(sphere.center).toEqual({ x: 5, y: 3, z: 0 })
    expect(sphere.radius).toBeCloseTo(Math.sqrt(31 ** 2 + 2) / 2, 5)
  })

  it('不可见父节点下的几何不参与取景，全部隐藏时保持空范围', () => {
    const scene = new THREE.Group()
    const hidden = new THREE.Group()
    hidden.visible = false
    hidden.add(new THREE.Mesh(new THREE.BoxGeometry(100, 100, 100), new THREE.MeshBasicMaterial()))
    scene.add(hidden)
    expect(computeVisibleBoundingSphere(THREE, scene).radius).toBe(0)

    scene.add(new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial()))
    expect(computeVisibleBoundingSphere(THREE, scene).radius).toBeCloseTo(Math.sqrt(3) / 2, 5)
  })

  it('空场景返回零半径', () => {
    expect(computeVisibleBoundingSphere(THREE, new THREE.Group()).radius).toBe(0)
  })
})
