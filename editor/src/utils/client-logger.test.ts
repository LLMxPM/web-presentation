/**
 * 文件功能：验证 Editor 浏览器端 logger 的脱敏、上报和去重行为。
 */
import { describe, expect, it, vi, afterEach } from 'vitest'

import { buildClientErrorPayload, reportClientError } from './client-logger'

describe('client-logger', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    ;(import.meta.env as Record<string, unknown>).VITE_CLIENT_ERROR_REPORTING = undefined
  })

  it('should redact sensitive data from payload', () => {
    const payload = buildClientErrorPayload(
      new Error('failed?token=secret-token'),
      {
        route: '/demo?ctx=secret',
        context: {
          api_key: 'hidden',
          page_content: '<template>source</template>',
          safe: 'ok',
        },
      },
    )

    const serialized = JSON.stringify(payload)
    expect(serialized).not.toContain('secret-token')
    expect(serialized).not.toContain('hidden')
    expect(serialized).not.toContain('<template>source</template>')
    expect(payload.context?.safe).toBe('ok')
  })

  it('should report enabled errors once within dedupe window', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(console, 'error').mockImplementation(() => {})
    ;(import.meta.env as Record<string, unknown>).VITE_CLIENT_ERROR_REPORTING = 'true'

    const error = new Error('dedupe-error')
    reportClientError(error, { component: 'test' })
    reportClientError(error, { component: 'test' })
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
})
