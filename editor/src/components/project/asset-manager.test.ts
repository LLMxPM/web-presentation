/**
 * 文件功能：验证资源类型配置中三维模型（model3d）的扩展名、MIME 与文本创建边界。
 */
import { describe, expect, it } from 'vitest'

import {
  ASSET_ALLOWED_EXTENSIONS,
  ASSET_GROUPS,
  ASSET_UPLOAD_ACCEPT,
  TEXT_CREATABLE_ASSET_TYPES,
  getAcceptedAssetExtensionText,
  isAcceptedAssetFile,
} from './asset-manager'

/** 构造浏览器 File 对象用于扩展名判定。 */
function buildFile(name: string): File {
  return new File([new Uint8Array([0x67, 0x6c, 0x54, 0x46])], name, { type: 'model/gltf-binary' })
}

describe('asset-manager model3d 配置', () => {
  it('内容资源分组应包含三维模型类型', () => {
    const contentGroup = ASSET_GROUPS.find(group => group.key === 'content')
    expect(contentGroup?.types.map(item => item.value)).toContain('model3d')
  })

  it('三维模型只接受 .glb 扩展名与 model/gltf-binary MIME', () => {
    expect(ASSET_ALLOWED_EXTENSIONS.model3d).toEqual(['.glb'])
    expect(ASSET_UPLOAD_ACCEPT.model3d).toContain('.glb')
    expect(ASSET_UPLOAD_ACCEPT.model3d).toContain('model/gltf-binary')
    expect(getAcceptedAssetExtensionText('model3d')).toBe('.glb')
  })

  it('.glb 文件命中扩展名白名单，其他扩展被拒绝', () => {
    expect(isAcceptedAssetFile(buildFile('product.glb'), 'model3d')).toBe(true)
    expect(isAcceptedAssetFile(buildFile('product.gltf'), 'model3d')).toBe(false)
    expect(isAcceptedAssetFile(buildFile('product.png'), 'model3d')).toBe(false)
  })

  it('三维模型不开放文本内容创建入口', () => {
    expect(TEXT_CREATABLE_ASSET_TYPES).not.toContain('model3d')
  })
})
