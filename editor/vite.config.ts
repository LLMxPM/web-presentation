/**
 * 文件功能：定义 Editor 前端的 Vite 构建、测试与本地开发代理配置。
 */
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { loadEnv, type Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

/**
 * 修正 markstream-vue 发布包 CSS 中残留的 Vue SFC 深度选择器，避免 Lightning CSS 压缩告警。
 */
function normalizeMarkstreamVueCssDeepSelector(): Plugin {
  return {
    name: 'editor:normalize-markstream-vue-css-deep-selector',
    enforce: 'pre',
    transform(code, id) {
      const normalizedId = id.replace(/\\/g, '/')
      if (!normalizedId.endsWith('/markstream-vue/dist/index.css')) {
        return null
      }

      const normalizedCode = code.replace(/\.icon-slot\s+:deep\(svg\)/g, '.icon-slot svg')
      if (normalizedCode === code) {
        return null
      }

      return {
        code: normalizedCode,
        map: null,
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [normalizeMarkstreamVueCssDeepSelector(), vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    build: {
      // Monaco 编辑器作为按需加载的重型编辑器 chunk 保留独立产物，避免对主入口制造无意义告警。
      chunkSizeWarningLimit: 4500,
      rolldownOptions: {
        checks: {
          pluginTimings: false,
        },
      },
    },
    server: {
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
        '/public': {
          target: proxyTarget,
          changeOrigin: true,
        },
        '/build-artifacts': {
          target: proxyTarget,
          changeOrigin: true,
        },
        '/preview': {
          target: proxyTarget,
          changeOrigin: true,
        },
        '/media': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
    },
  }
})
