/**
 * 文件功能：集中管理平台级测试使用的服务地址、默认端口与环境变量回退逻辑。
 */
export const DEFAULT_SERVICE_URLS = {
  backend: 'http://127.0.0.1:8000',
  editor: 'http://127.0.0.1:5173',
  runtime: 'http://127.0.0.1:7373',
  renderer: 'http://127.0.0.1:7400',
}

/** 按 E2E 覆盖、通用覆盖和默认值解析服务地址；允许传入隔离环境用于预检与测试。 */
export function resolveServiceUrls(env = process.env) {
  return {
    backend: env.E2E_API_BASE_URL || env.BACKEND_BASE_URL || DEFAULT_SERVICE_URLS.backend,
    editor: env.E2E_BASE_URL || env.EDITOR_BASE_URL || DEFAULT_SERVICE_URLS.editor,
    runtime: env.E2E_RUNTIME_BASE_URL || env.RUNTIME_BASE_URL || DEFAULT_SERVICE_URLS.runtime,
    renderer: env.E2E_RENDERER_BASE_URL || DEFAULT_SERVICE_URLS.renderer,
  }
}

export function parseOrigin(url) {
  return new URL(url).origin
}
