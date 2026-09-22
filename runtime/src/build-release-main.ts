/**
 * 文件用途：Backend build release 专用入口，启动项目演示外壳并排除开发/预览宿主能力。
 */

import { createApp, nextTick } from 'vue'

import BuildReleaseApp from './BuildReleaseApp.vue'
import { loadThemeConfigs } from './core/composables/useTheme'
import { initializeStaticIcons } from './core/utils/static-icons'
import { initializeConfig } from './core/utils/config'
import { initializeRuntimeFaviconSync } from './core/utils/favicon'
import { initializeRuntimeFontRegistry, waitForRequiredPlatformFonts } from './core/utils/font-registry'
import { createProjectRouter } from './core/router/project-router'

import './styles/global.css'

/**
 * 写入运行时就绪标记，便于外部截图或探测流程识别首屏稳定状态。
 * @param ready 当前构建产物是否已完成首屏稳定等待
 */
function setBuildReleaseRuntimeReady(ready: boolean): void {
  if (typeof window === 'undefined') {
    return
  }
  window.__EDITOR_RUNTIME_PREVIEW_READY__ = ready
}

/**
 * 等待构建产物完成首屏渲染与字体装载。
 */
async function waitForBuildReleaseStabilized(): Promise<void> {
  await nextTick()
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve())
    })
  })

  await waitForRequiredPlatformFonts()
  if (document.fonts?.ready) {
    await document.fonts.ready
  }
}

/**
 * 初始化并挂载 build release 应用。
 */
async function initializeBuildReleaseApp(): Promise<void> {
  setBuildReleaseRuntimeReady(false)

  try {
    await initializeConfig()
    initializeRuntimeFontRegistry()
    await loadThemeConfigs()
    initializeStaticIcons()
    initializeRuntimeFaviconSync()

    const router = await createProjectRouter()
    const app = createApp(BuildReleaseApp)
    app.use(router)

    await router.isReady()
    app.mount('#app')
    await waitForBuildReleaseStabilized()
    setBuildReleaseRuntimeReady(true)
  } catch (error) {
    setBuildReleaseRuntimeReady(false)
    console.error('Runtime 构建产物初始化失败', error)
    document.body.innerHTML = `
      <div style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:Segoe UI,PingFang SC,sans-serif;background:#f8fafc;">
        <div style="max-width:720px;padding:32px;text-align:center;color:#dc2626;background:#ffffff;border:1px solid #fecaca;border-radius:16px;box-shadow:0 10px 30px rgba(15,23,42,.08);">
          <h1 style="margin:0 0 12px;font-size:28px;">Runtime 构建产物初始化失败</h1>
          <p style="margin:0 0 16px;color:#7f1d1d;">请联系平台侧排查构建快照、入口路由或静态资源是否完整。</p>
          <details style="margin-top:20px;text-align:left;">
            <summary style="cursor:pointer;color:#991b1b;">错误详情</summary>
            <pre style="margin-top:12px;padding:12px;border-radius:12px;background:#fef2f2;overflow:auto;white-space:pre-wrap;">${String(error)}</pre>
          </details>
        </div>
      </div>
    `
  }
}

void initializeBuildReleaseApp()
