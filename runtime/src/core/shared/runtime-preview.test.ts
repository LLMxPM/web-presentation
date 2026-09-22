/**
 * 文件用途：验证 SaaS 预览共享契约中的路径规范化、远程模块 ID 构造与资源 key 处理逻辑。
 */

import { describe, expect, it } from 'vitest'

import {
  buildRemoteModuleId,
  isPreviewEntryModuleRequest,
  isBuiltinLocalViewPath,
  isRuntimeLocalPublicModulePath,
  normalizeAssetKey,
  normalizeRuntimeModulePath,
  normalizeViewModulePath,
  parseRemoteModuleId,
  resolvePreviewEntryModulePath,
  toAliasModulePath,
  toAliasViewPath,
  type RuntimePreviewArtifactManifest,
} from './runtime-preview'

describe('runtime preview shared helpers', () => {
  it('应将多种视图路径规范化为 src/views 形式', () => {
    expect(normalizeViewModulePath('@/views/demo/Page.vue')).toBe('src/views/demo/Page.vue')
    expect(normalizeViewModulePath('/src/views/demo/Page.vue')).toBe('src/views/demo/Page.vue')
    expect(normalizeViewModulePath('views/demo/Page.vue')).toBe('src/views/demo/Page.vue')
  })

  it('应将工作空间组件别名规范化为远程模块路径', () => {
    expect(normalizeRuntimeModulePath('@workspace-components/CMP_DEMO/v/3')).toBe('src/workspace-components/CMP_DEMO/v/3.vue')
    expect(toAliasModulePath('src/workspace-components/CMP_DEMO/v/3.vue')).toBe('@workspace-components/CMP_DEMO/v/3')
  })

  it('应识别本地内建兜底页面路径', () => {
    expect(isBuiltinLocalViewPath('src/runtime-shell/fallback/NotFoundPage.vue')).toBe(true)
    expect(isBuiltinLocalViewPath('src/examples/local/views/defaultpage/NotFoundPage.vue')).toBe(false)
    expect(isBuiltinLocalViewPath('src/views/demo/Page.vue')).toBe(false)
  })

  it('应识别 Runtime 对远程模块开放的本地公共模块路径', () => {
    expect(isRuntimeLocalPublicModulePath('src/runtime-kit/public/components/primitives/Icon.v1.vue')).toBe(true)
    expect(isRuntimeLocalPublicModulePath('src/runtime-kit/public/utils/assets.v1.ts')).toBe(true)
    expect(normalizeRuntimeModulePath('@runtime-kit/public/components/assets/AssetImage.v1.vue')).toBe(
      'src/runtime-kit/public/components/assets/AssetImage.v1.vue',
    )
    expect(toAliasModulePath('src/runtime-kit/public/components/primitives/Icon.v1.vue')).toBe(
      '@runtime-kit/public/components/primitives/Icon.v1.vue',
    )
    expect(isRuntimeLocalPublicModulePath('src/components/common/AppIcon.vue')).toBe(false)
    expect(isRuntimeLocalPublicModulePath('src/core/utils/path.ts')).toBe(false)
    expect(isRuntimeLocalPublicModulePath('src/views/demo/Page.vue')).toBe(false)
  })

  it('应构造并解析稳定的远程模块 ID', () => {
    const remoteId = buildRemoteModuleId('artifact_1', '@/views/demo/Page.vue', 'signed-preview-token')
    const parsed = parseRemoteModuleId(remoteId)

    expect(remoteId).toContain('/@runtime-preview/')
    expect(remoteId).toContain('/src/views/demo/Page.vue?ctx=')
    expect(parsed).toEqual({
      artifactId: 'artifact_1',
      modulePath: 'src/views/demo/Page.vue',
      previewToken: 'signed-preview-token',
    })
    expect(toAliasViewPath(parsed?.modulePath || '')).toBe('@/views/demo/Page.vue')
  })

  it('应按 Runtime 公开基址构造同域 Gateway 远程模块 ID', () => {
    const remoteId = buildRemoteModuleId(
      'artifact_1',
      '@/views/demo/Page.vue',
      'signed-preview-token',
      'http://127.0.0.1:8080/runtime/',
    )
    const parsed = parseRemoteModuleId(remoteId)

    expect(remoteId.startsWith('http://127.0.0.1:8080/runtime/@runtime-preview/artifact_1/')).toBe(true)
    expect(parsed).toEqual({
      artifactId: 'artifact_1',
      modulePath: 'src/views/demo/Page.vue',
      previewToken: 'signed-preview-token',
    })
  })

  it('应在 Vue 子请求丢失 ctx 后仍能从路径解析远程模块逻辑路径', () => {
    const parsed = parseRemoteModuleId('/@runtime-preview/artifact_1/src/workspace-components/CMP_DEMO/v/1.vue?vue&type=style&index=0&lang.css')

    expect(parsed).toEqual({
      artifactId: 'artifact_1',
      modulePath: 'src/workspace-components/CMP_DEMO/v/1.vue',
      previewToken: undefined,
    })
  })

  it('应识别 Vue SFC 子请求中的相对远程模块 importer', () => {
    const parsed = parseRemoteModuleId('../../../@runtime-preview/366/src/views/PG20260328003.vue?ctx=signed-preview-token')

    expect(parsed).toEqual({
      artifactId: '366',
      modulePath: 'src/views/PG20260328003.vue',
      previewToken: 'signed-preview-token',
    })
  })

  it('应仅将单页面预览的页面模块识别为入口模块请求', () => {
    expect(resolvePreviewEntryModulePath({ entry_type: 'module', module_path: 'src/views/demo/Page.vue' })).toBe('src/views/demo/Page.vue')
    expect(resolvePreviewEntryModulePath({ entry_type: 'route', route: '/home' })).toBe('')
    expect(isPreviewEntryModuleRequest('src/views/demo/Page.vue', { entry_type: 'module', module_path: 'src/views/demo/Page.vue' })).toBe(true)
    expect(isPreviewEntryModuleRequest('src/views/demo/Page.vue', { entry_type: 'route', route: '/home' })).toBe(false)
  })

  it('应将资源路径规范化为 manifest key', () => {
    expect(normalizeAssetKey('./img/logo/demo.png')).toBe('img/logo/demo.png')
    expect(normalizeAssetKey('\\fonts\\demo.woff2')).toBe('fonts/demo.woff2')
  })

  it('应接受页面可视化编辑专用 artifact 与版本化元数据', () => {
    const manifest: RuntimePreviewArtifactManifest = {
      artifact_id: 'artifact-visual-edit',
      artifact_kind: 'page_visual_edit_preview',
      tenant_id: 'tenant_1',
      preview_kind: 'page',
      owner_scope: {
        scope_type: 'project',
        workspace_id: '1',
        project_id: '2',
      },
      entry_descriptor: { entry_type: 'module', module_path: 'src/views/PGdemo.vue' },
      modules: {},
      assets: {},
      visual_edit: {
        protocol_version: 1,
        page_id: 12,
        base_version_no: 3,
        source_hash: 'a'.repeat(64),
        module_path: 'src/views/PGdemo.vue',
        manifest: { protocolVersion: 1 },
      },
    }

    expect(manifest.artifact_kind).toBe('page_visual_edit_preview')
    expect(manifest.visual_edit?.protocol_version).toBe(1)
    expect(manifest.visual_edit?.module_path).toBe('src/views/PGdemo.vue')
  })
})
