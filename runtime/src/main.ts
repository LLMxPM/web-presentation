/**
 * 文件用途：应用入口，负责初始化只读预览运行时、配置系统、主题系统、图标系统与路由。
 */

import { createApp, nextTick } from 'vue'

import App from './App.vue'
import { loadThemeConfigs } from './core/composables/useTheme'
import { registerPageVisualEditSelectionBridge } from './core/visual-edit/browser/selection-bridge'
import { initializeStaticIcons } from './core/utils/static-icons'
import { initializeConfig } from './core/utils/config'
import { initializeRuntimeFaviconSync } from './core/utils/favicon'
import { initializeRuntimeFontRegistry, waitForRequiredPlatformFonts } from './core/utils/font-registry'
import { getPreviewEntryNavigationPath, shouldNavigateToPreviewEntryPath } from './core/utils/path'
import { notifyParentPagePreviewError } from './core/utils/page-preview-parent'
import { registerEditorVisualAssetProbe } from './core/utils/visual-assets'
import {
  initializeRenderReadyHost,
  markRenderPreviewMounted,
  markRenderReadyFailure,
} from './core/utils/render-ready'
import { installRuntimeClientLogger, reportRuntimeClientError } from './core/utils/client-logger'

import './styles/global.css'

/**
 * 写入编辑器截图使用的运行时就绪标记。
 * @param ready 当前预览是否已稳定可截图
 */
function setEditorRuntimePreviewReady(ready: boolean): void {
  if (typeof window === 'undefined') {
    return
  }
  window.__EDITOR_RUNTIME_PREVIEW_READY__ = ready
}

/**
 * 等待预览页面完成首屏渲染与字体装载，再通过 render-ready.v1 通知 Renderer。
 * 关键约束：
 * 1. 需要在应用挂载完成后调用；
 * 2. 使用双帧等待，尽量覆盖首轮布局和异步组件挂载；
 * 3. 缺少协议或状态无法确认时不得伪报成功。
 */
async function waitForPreviewStabilized(): Promise<void> {
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
 * 初始化并挂载应用。
 */
async function initializeApp(): Promise<void> {
  setEditorRuntimePreviewReady(false)
  initializeRenderReadyHost({
    artifactId: new URLSearchParams(window.location.search).get('artifact'),
    inputDigest: new URLSearchParams(window.location.search).get('input_digest'),
  })
  registerEditorVisualAssetProbe()

  try {
    await initializeConfig()
    initializeRuntimeFontRegistry()
    await loadThemeConfigs()
    initializeStaticIcons()
    initializeRuntimeFaviconSync()

    const { default: routerPromise } = await import('./core/router')
    const router = await routerPromise
    const app = createApp(App)
    installRuntimeClientLogger(app)
    app.use(router)

    const previewEntryPath = getPreviewEntryNavigationPath()
    if (shouldNavigateToPreviewEntryPath(previewEntryPath)) {
      const targetPath = previewEntryPath.startsWith('/') ? previewEntryPath : `/${previewEntryPath}`
      await router.replace(targetPath)
    }

    await router.isReady()
    app.mount('#app')
    const disposeVisualEditSelectionBridge = registerPageVisualEditSelectionBridge()
    if (disposeVisualEditSelectionBridge) {
      window.addEventListener('beforeunload', disposeVisualEditSelectionBridge, { once: true })
    }
    await waitForPreviewStabilized()
    await markRenderPreviewMounted({
      artifactId: new URLSearchParams(window.location.search).get('artifact'),
      inputDigest: new URLSearchParams(window.location.search).get('input_digest'),
    })
    // 以协议状态为准：视觉资源失败时 markRenderPreviewMounted 会写 false，不得无条件覆盖。
    setEditorRuntimePreviewReady(window.__EDITOR_RUNTIME_PREVIEW_READY__ !== false)
  } catch (error) {
    setEditorRuntimePreviewReady(false)
    markRenderReadyFailure(String(error))
    reportRuntimeClientError(error, { message: '应用初始化失败', component: 'runtime-main' })
    notifyParentPagePreviewError(error)
    document.body.innerHTML = `
      <div style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:Segoe UI,PingFang SC,sans-serif;background:#f8fafc;">
        <div style="max-width:720px;padding:32px;text-align:center;color:#dc2626;background:#ffffff;border:1px solid #fecaca;border-radius:16px;box-shadow:0 10px 30px rgba(15,23,42,.08);">
          <h1 style="margin:0 0 12px;font-size:28px;">Runtime 初始化失败</h1>
          <p style="margin:0 0 16px;color:#7f1d1d;">请刷新页面重试；若问题持续，请联系平台侧排查预览上下文、发布产物或内部接口。</p>
          <details style="margin-top:20px;text-align:left;">
            <summary style="cursor:pointer;color:#991b1b;">错误详情</summary>
            <pre style="margin-top:12px;padding:12px;border-radius:12px;background:#fef2f2;overflow:auto;white-space:pre-wrap;">${String(error)}</pre>
          </details>
        </div>
      </div>
    `
  }
}

initializeApp()
