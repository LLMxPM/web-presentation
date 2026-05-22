/**
 * 文件功能：验证认证状态仓库的初始化、登录与登出行为。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useAuthStore } from '@/stores/auth'
import type { AuthUser } from '@/types/api'

vi.mock('@/api/auth', () => ({
  fetchMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}))

import { fetchMe, login, logout } from '@/api/auth'

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('ensureLoaded 在未登录时应静默结束并标记已初始化', async () => {
    vi.mocked(fetchMe).mockRejectedValue(new Error('401'))
    const store = useAuthStore()

    await store.ensureLoaded()

    expect(store.user).toBeNull()
    expect(store.initialized).toBe(true)
  })

  it('signIn 与 signOut 应正确维护用户状态', async () => {
    const user: AuthUser = {
      id: 1,
      username: 'admin',
      display_name: '平台系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }
    vi.mocked(login).mockResolvedValue({ user })
    vi.mocked(logout).mockResolvedValue({ message: 'ok' })

    const store = useAuthStore()
    await store.signIn({ username: 'admin', password: 'test-password' })
    expect(store.user).toEqual(user)

    await store.signOut()
    expect(store.user).toBeNull()
    expect(store.initialized).toBe(true)
  })
})
