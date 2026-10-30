/** 文件功能：装配实例灯光与背景并预热共享纹理，保持几何和材质只读。 */
import type * as ThreeNamespace from 'three'
import type { Model3dEngine } from './engine'
import { isTransparentBackground, parseBackgroundColor } from './view-options'
/**
 * 按光照策略补默认光照：仅 auto 且场景无任何光源时添加。
 * @param scene 实例场景
 * @param lighting 光照策略
 * @param engineRef 已加载引擎
 */
export function applyLighting(scene: ThreeNamespace.Scene, lighting: 'auto' | 'source', engineRef: Model3dEngine): void {
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
export async function waitForTexturesReady(
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
export function applyBackground(
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
