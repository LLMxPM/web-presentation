/**
 * 文件用途：验证 Icon composable 在预览模式下可根据结构化分析元数据以内联 SVG 方式加载逻辑资源名。
 */
// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/core/utils/icon-registry', () => ({
  getIcon: vi.fn(async () => null),
  hasIcon: vi.fn(async () => true),
  getIconConfig: vi.fn(async () => ({
    component: {},
    type: 'static',
    src: 'github',
    description: 'github icon',
    analysis: {
      schema_version: 1,
      kind: 'icon',
      icon: {
        format: 'svg',
        render_mode: 'inline_svg',
        style: 'stroke',
        inline_safe: true,
        stroke_width_editable: true,
        analysis_status: 'analyzed',
        reasons: ['test'],
      },
    },
  })),
}))

import { useIcon } from './useIcon'
import { setRuntimePreloadedConfig, setRuntimePreviewContext } from '@/core/utils/path'

async function flushAsyncTasks(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  await new Promise(resolve => setTimeout(resolve, 0))
}

describe('runtime useIcon', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        text: async () => '<svg><path stroke="currentColor" d="M0 0" /></svg>',
      })),
    )

    setRuntimePreviewContext({
      artifactId: 'artifact-1',
      tenantId: 'tenant-1',
      previewKind: 'component',
      scopeType: 'workspace_component',
      workspaceId: '1',
      assetBaseUrl: 'http://127.0.0.1:8000/public/assets/1',
      traceId: 'trace-1',
      entryDescriptor: { entry_type: 'component_host' },
      componentPreviewMode: 'draft',
      componentCode: 'CMP001',
      componentVersionNo: 1,
    })
    setRuntimePreloadedConfig({
      manifest: {
        artifact_id: 'artifact-1',
        artifact_kind: 'preview_artifact',
        tenant_id: 'tenant-1',
        preview_kind: 'component',
        asset_base_url: 'http://127.0.0.1:8000/public/assets/1',
        owner_scope: {
          scope_type: 'workspace_component',
          workspace_id: '1',
          component_code: 'CMP001',
          component_version_no: 1,
          preview_mode: 'draft',
        },
        entry_descriptor: { entry_type: 'component_host' },
        modules: {},
        assets: {
          github: 'github',
        },
      },
    })
  })

  it('在预览模式下使用逻辑资源名也会按 inline svg 加载', async () => {
    const icon = useIcon('github')
    await flushAsyncTasks()

    expect(icon.isStaticSvg.value).toBe(true)
    expect(icon.staticSvgContent.value).toContain('<svg>')
    expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/public/assets/1/github')
  })
})
