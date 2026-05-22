/**
 * 文件功能：挂载后台管理前端应用，并注册路由、状态管理、查询插件和 UI 组件。
 */
import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { setupUnauthorizedRedirect } from './auth/unauthorized'
import { router } from './router'
import './style.css'

const app = createApp(App)

app.use(createPinia())
setupUnauthorizedRedirect(router)
app.use(router)
app.use(VueQueryPlugin, {
  queryClientConfig: {
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
      },
    },
  },
})
app.mount('#app')
