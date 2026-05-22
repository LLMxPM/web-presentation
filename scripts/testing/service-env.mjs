/**
 * 文件功能：集中管理平台级测试使用的服务地址、默认端口与环境变量回退逻辑。
 */
export const DEFAULT_SERVICE_URLS = {
  backend: 'http://127.0.0.1:8000',
  editor: 'http://127.0.0.1:5173',
  runtime: 'http://127.0.0.1:7373',
}

export function resolveServiceUrls() {
  return {
    backend: process.env.E2E_API_BASE_URL || process.env.BACKEND_BASE_URL || DEFAULT_SERVICE_URLS.backend,
    editor: process.env.E2E_BASE_URL || process.env.EDITOR_BASE_URL || DEFAULT_SERVICE_URLS.editor,
    runtime: process.env.E2E_RUNTIME_BASE_URL || process.env.RUNTIME_BASE_URL || DEFAULT_SERVICE_URLS.runtime,
  }
}

export function parseOrigin(url) {
  return new URL(url).origin
}
