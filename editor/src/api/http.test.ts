/**
 * 文件功能：验证后台 API 基础地址解析和全局未授权拦截逻辑。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getErrorMessage, http, registerUnauthorizedHandler, resolveApiBaseUrl } from '@/api/http'

describe('http api base url', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('未配置 VITE_API_BASE_URL 时应默认使用同源代理地址', () => {
    vi.stubEnv('VITE_API_BASE_URL', '')

    expect(resolveApiBaseUrl()).toBe('/api')
  })

  it('配置 VITE_API_BASE_URL 时应优先使用显式地址', () => {
    vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000/api')

    expect(resolveApiBaseUrl()).toBe('http://127.0.0.1:8000/api')
  })

  it('接口返回 401 时应触发全局未授权处理器', async () => {
    const handler = vi.fn()
    registerUnauthorizedHandler(handler)

    await expect(http.get('/private', {
      adapter: () => Promise.reject({
        isAxiosError: true,
        response: { status: 401 },
      }),
    })).rejects.toMatchObject({ response: { status: 401 } })

    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('/auth/me 返回 401 时应交由路由守卫处理', async () => {
    const handler = vi.fn()
    registerUnauthorizedHandler(handler)

    await expect(http.get('/auth/me', {
      adapter: () => Promise.reject({
        isAxiosError: true,
        config: { url: '/auth/me' },
        response: { status: 401 },
      }),
    })).rejects.toMatchObject({ response: { status: 401 } })

    expect(handler).not.toHaveBeenCalled()
  })

  it('Axios 错误缺少业务错误体时应按状态码返回中文兜底提示', () => {
    expect(getErrorMessage({
      isAxiosError: true,
      message: 'Request failed with status code 500',
      response: { status: 500 },
    })).toBe('服务端处理失败，请稍后重试；如反复出现，请联系管理员查看后台日志。')

    expect(getErrorMessage({
      isAxiosError: true,
      message: 'Request failed with status code 422',
      response: { status: 422 },
    })).toBe('请求参数不符合要求，请检查后再提交。')
  })
})
