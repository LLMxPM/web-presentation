/**
 * 文件用途：补充运行时全局类型定义，尤其是预览上下文与部署环境变量约束。
 */

import type {
  RuntimePreloadedConfigBundle,
  RuntimePreviewContext,
} from '@/core/shared/runtime-preview'
import type { RuntimeConfigContext } from '@/core/utils/path'
import type {
  EditorVisualAssetWaitOptions,
  EditorVisualAssetWaitResult,
} from '@/core/utils/visual-assets'

export interface AppConfig {
  title: string
  description?: string
  logo?: string
}

export interface SidebarConfig {
  width: number
  collapsible: boolean
  defaultCollapsed: boolean
}

export interface BaseResponse<T = unknown> {
  success: boolean
  data: T
  message?: string
  code?: number | string
}

export interface ImportMetaEnv {
  readonly VITE_APP_TITLE?: string
  readonly VITE_APP_VERSION?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_BUILD_TIME?: string
  readonly RUNTIME_SERVER_HOST?: string
  readonly RUNTIME_SERVER_PORT?: string
  readonly RUNTIME_PREVIEW_JWKS_URL?: string
  readonly RUNTIME_PREVIEW_TOKEN_AUDIENCE?: string
  readonly RUNTIME_BACKEND_API_BASE_URL?: string
  readonly RUNTIME_STANDALONE_PREVIEW_ENABLED?: string
  readonly VITE_SNAPDOM_PROXY_URL?: string
}

export interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare global {
  const __RUNTIME_BACKEND_BUILD__: boolean

  interface Window {
    __RUNTIME_CONFIG_CONTEXT__?: RuntimeConfigContext
    __RUNTIME_PREVIEW_CONTEXT__?: RuntimePreviewContext
    __RUNTIME_PREVIEW_TOKEN__?: string
    __RUNTIME_PRELOADED_CONFIG__?: RuntimePreloadedConfigBundle
    __RUNTIME_PUBLIC_BASE_URL__?: string
    __EDITOR_RUNTIME_PREVIEW_READY__?: boolean
    __EDITOR_RUNTIME_WAIT_FOR_VISUAL_ASSETS__?: (
      options?: EditorVisualAssetWaitOptions
    ) => Promise<EditorVisualAssetWaitResult>
  }
}
