/** 文件功能：验证应用启动的后端时区同步与网络失败回退。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { fetchSettings, warn } = vi.hoisted(() => ({ fetchSettings: vi.fn(), warn: vi.fn() }))
vi.mock('@/api/system', () => ({ fetchSystemSettings: fetchSettings }))
vi.mock('@/utils/client-logger', () => ({ logClientWarning: warn }))

import { initializeAppTimezone } from '@/utils/setup-timezone'
import { APP_TIMEZONE, setAppTimezone } from '@/utils/timezone'

const initialTimezone = APP_TIMEZONE

beforeEach(() => {
  vi.clearAllMocks()
  setAppTimezone('Asia/Shanghai')
})
afterEach(() => setAppTimezone(initialTimezone))

describe('initializeAppTimezone', () => {
  it('应在初始化完成时使用后端时区', async () => {
    fetchSettings.mockResolvedValue({ app_timezone: 'Asia/Tokyo' })
    await initializeAppTimezone()
    expect(APP_TIMEZONE).toBe('Asia/Tokyo')
    expect(warn).not.toHaveBeenCalled()
  })

  it('配置请求失败时应保留默认时区并允许应用继续挂载', async () => {
    fetchSettings.mockRejectedValue(new Error('network unavailable'))
    await expect(initializeAppTimezone()).resolves.toBeUndefined()
    expect(APP_TIMEZONE).toBe('Asia/Shanghai')
    expect(warn).toHaveBeenCalledOnce()
  })
})
