/**
 * 文件功能：集中维护当前登录用户状态，并提供登录、登出与初始化能力。
 */
import { defineStore } from 'pinia'

import { fetchMe, login, logout } from '@/api/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as Awaited<ReturnType<typeof fetchMe>> | null,
    initialized: false,
  }),
  actions: {
    /**
     * 初始化当前登录态；未登录时静默返回，避免首次打开页面直接报错。
     */
    async ensureLoaded() {
      if (this.initialized) {
        return
      }
      try {
        this.user = await fetchMe()
      } catch {
        this.user = null
      } finally {
        this.initialized = true
      }
    },
    /**
     * 执行登录并刷新当前用户信息。
     */
    async signIn(payload: { username: string; password: string }) {
      const response = await login(payload)
      this.user = response.user
      this.initialized = true
      return response.user
    },
    /**
     * 退出登录并清空本地用户状态。
     */
    async signOut() {
      try {
        await logout()
      } finally {
        this.user = null
        this.initialized = true
      }
    },
  },
})
