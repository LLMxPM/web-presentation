/**
 * 文件功能：声明前端环境变量类型，约束 API 地址等构建时配置。
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_API_PROXY_TARGET?: string
  readonly VITE_APP_TIMEZONE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
