/**
 * 文件用途：验证 Runtime 浏览器端错误 logger 会携带预览上下文并上报 Backend。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { buildRuntimeClientErrorPayload, reportRuntimeClientError } from './client-logger'

describe('runtime client logger', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    window.__RUNTIME_PREVIEW_CONTEXT__ = undefined
  })

  it('should include runtime preview context in payload', () => {
    window.__RUNTIME_PREVIEW_CONTEXT__ = {
      artifactId: 'artifact-1',
      tenantId: 'tenant-1',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: '2',
      projectId: '3',
      entryDescriptor: { entry_type: 'route', route: '/' },
      assetBaseUrl: '/assets',
      traceId: 'trace-1',
    }

    const payload = buildRuntimeClientErrorPayload(new Error('runtime failed?token=secret'), {
      component: 'test',
    })

    expect(payload.artifact_id).toBe('artifact-1')
    expect(payload.trace_id).toBe('trace-1')
    expect(payload.context?.scopeType).toBe('project')
    expect(JSON.stringify(payload)).not.toContain('secret')
  })

  it('should report runtime browser errors to backend', async () => {
    window.__RUNTIME_PREVIEW_CONTEXT__ = {
      artifactId: 'artifact-1',
      tenantId: 'tenant-1',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: '2',
      projectId: '3',
      entryDescriptor: { entry_type: 'route', route: '/' },
      assetBaseUrl: '/assets',
      traceId: 'trace-1',
    }
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(console, 'error').mockImplementation(() => {})

    reportRuntimeClientError(new Error('runtime-report-error'), { component: 'test' })
    await Promise.resolve()
    await Promise.resolve()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/client-logs/errors',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      }),
    )
  })

  it('should ignore browser ResizeObserver loop noise', async () => {
    window.__RUNTIME_PREVIEW_CONTEXT__ = {
      artifactId: 'artifact-1',
      tenantId: 'tenant-1',
      previewKind: 'project',
      scopeType: 'project',
      workspaceId: '2',
      projectId: '3',
      entryDescriptor: { entry_type: 'route', route: '/' },
      assetBaseUrl: '/assets',
      traceId: 'trace-resize',
    }
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }))
    const consoleErrorMock = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', fetchMock)

    reportRuntimeClientError('ResizeObserver loop completed with undelivered notifications.', {
      component: 'window.error',
    })
    await Promise.resolve()

    expect(consoleErrorMock).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
