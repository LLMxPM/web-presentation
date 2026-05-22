/**
 * 文件功能：验证全局未授权处理会清理登录态并引导用户回到登录页。
 */
import { createPinia, setActivePinia } from 'pinia'
import type { Router } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { notifyUnauthorized } from '@/api/http'
import { setupUnauthorizedRedirect } from '@/auth/unauthorized'
import { useAuthStore } from '@/stores/auth'

/**
 * 构造只包含当前测试所需字段的路由替身。
 */
function createRouterStub(route: { name: string; fullPath: string }) {
  return {
    currentRoute: {
      value: route,
    },
    push: vi.fn().mockResolvedValue(undefined),
  } as unknown as Router & { push: ReturnType<typeof vi.fn> }
}

describe('unauthorized redirect', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('收到 401 后应清空登录态并跳转登录页', async () => {
    const router = createRouterStub({ name: 'workspaceHome', fullPath: '/workspaces/1/home' })
    const authStore = useAuthStore()
    authStore.user = {
      id: 1,
      username: 'admin',
      display_name: '平台系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    setupUnauthorizedRedirect(router)
    notifyUnauthorized()
    await vi.waitFor(() => expect(router.push).toHaveBeenCalled())

    expect(authStore.user).toBeNull()
    expect(authStore.initialized).toBe(true)
    expect(router.push).toHaveBeenCalledWith({
      name: 'login',
      query: { redirect: '/workspaces/1/home' },
    })
  })

  it('当前已经在登录页时不应重复跳转', async () => {
    const router = createRouterStub({ name: 'login', fullPath: '/login' })

    setupUnauthorizedRedirect(router)
    notifyUnauthorized()
    await Promise.resolve()

    expect(router.push).not.toHaveBeenCalled()
  })
})
