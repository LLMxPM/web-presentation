/** 文件功能：为 E2E 的 Backend 与 Renderer 注入同一套隔离身份和回源地址。 */
import { resolveServiceUrls } from './service-env.mjs'

/** 测试凭据只用于 E2E，显式清空文件配置，避免继承开发或生产 secret 文件。 */
export function buildE2eRenderEnv() {
  const urls = resolveServiceUrls()
  const workerId = process.env.E2E_RENDER_WORKER_ID || 'renderer-e2e'
  return {
    RENDER_WORKER_ID: workerId,
    RENDER_WORKERS_CONFIG: JSON.stringify([{ worker_id: workerId, base_url: urls.renderer }]),
    RENDER_SERVICE_CREDENTIAL: process.env.E2E_RENDER_SERVICE_CREDENTIAL || 'e2e-render-only-no-production-credential',
    RENDER_SERVICE_CREDENTIAL_FILE: '',
    RENDER_PROFILE_DIGEST: process.env.E2E_RENDER_PROFILE_DIGEST || 'profile.v1',
    RENDER_PROFILE_MANIFEST: '',
    RENDER_PORT: new URL(urls.renderer).port || '7400',
    RENDER_RUNTIME_NAVIGATION_BASE_URL: urls.runtime,
    RENDER_RUNTIME_ASSET_BASE_URL: urls.runtime,
    RENDER_PLATFORM_ASSET_BASE_URL: urls.backend,
  }
}
