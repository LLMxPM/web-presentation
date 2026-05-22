/**
 * 文件功能：注册编辑器全局未授权处理逻辑，统一清理登录态并跳转登录页。
 */
import type { Router } from 'vue-router'

import { registerUnauthorizedHandler } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

let isRedirecting = false

/**
 * 为请求层注册 401 处理逻辑。
 * @param router 当前应用路由实例
 */
export function setupUnauthorizedRedirect(router: Router) {
  registerUnauthorizedHandler(async () => {
    const authStore = useAuthStore()
    authStore.user = null
    authStore.initialized = true

    const currentRoute = router.currentRoute.value
    if (currentRoute.name === 'login' || isRedirecting) {
      return
    }

    isRedirecting = true
    try {
      await router.push({
        name: 'login',
        query: { redirect: currentRoute.fullPath },
      })
    } finally {
      isRedirecting = false
    }
  })
}
