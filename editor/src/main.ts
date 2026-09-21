/**
 * 文件功能：挂载后台管理前端应用，并注册路由、状态管理、查询插件和 UI 组件。
 */
import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { setupUnauthorizedRedirect } from './auth/unauthorized'
import { router } from './router'
import { installEditorClientLogger } from './utils/client-logger'
import { initializeAppTimezone } from './utils/setup-timezone'
import './style.css'

const app = createApp(App)

app.use(createPinia())
setupUnauthorizedRedirect(router)
installEditorClientLogger(app, router)
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
/** 等待后端业务时区后再挂载，避免首屏日期和会话分组使用旧时区。 */
async function mountApp(): Promise<void> {
  await initializeAppTimezone()
  app.mount('#app')
}

void mountApp()
