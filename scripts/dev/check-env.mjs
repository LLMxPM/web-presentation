/** 文件功能：检查各服务的有效环境、地址、Audience 与渲染凭据是否一致。 */
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { readRenderCredential, resolveServiceEnvironments } from './env-files.mjs'

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const AUDIENCES = {
  RUNTIME_SERVICE_TOKEN_AUDIENCE: 'runtime-backend',
  RUNTIME_PREVIEW_TOKEN_AUDIENCE: 'runtime-preview',
  RUNTIME_BUILD_TOKEN_AUDIENCE: 'runtime-build',
  RUNTIME_DIAGNOSTICS_TOKEN_AUDIENCE: 'runtime-diagnostics',
}

/** 校验本地 HTTP 地址；远程地址只检查合法性，不与本机监听端口比较。 */
function checkAddress(issues, label, rawUrl, expectedPort) {
  try {
    const url = new URL(rawUrl)
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('协议不支持')
    const port = Number(url.port || (url.protocol === 'https:' ? 443 : 80))
    if (['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) && port !== expectedPort) {
      issues.push(`${label} 端口 ${port} 与目标服务监听端口 ${expectedPort} 不一致。`)
    }
  } catch {
    issues.push(`${label} 必须为合法 HTTP(S) URL。`)
  }
}

/** 返回诊断；不启动服务、不输出凭据，允许注入临时目录验证配置覆盖行为。 */
export function checkEnvironment(repoRoot = REPO_ROOT, systemEnv = process.env) {
  const { backend, runtime, renderer, editor } = resolveServiceEnvironments(repoRoot, systemEnv)
  const issues = []
  const ports = {
    Backend: Number(backend.APP_PORT || 8000),
    Runtime: Number(runtime.RUNTIME_SERVER_PORT || 7373),
    Renderer: Number(renderer.RENDER_PORT || 7400),
    Editor: 5173,
  }
  for (const [name, port] of Object.entries(ports)) {
    if (!Number.isInteger(port) || port < 1 || port > 65535) issues.push(`${name} 监听端口非法。`)
    const conflicts = Object.keys(ports).filter(other => other !== name && ports[other] === port)
    if (conflicts.length) issues.push(`${name} 与 ${conflicts.join('、')} 的监听端口重复。`)
  }
  checkAddress(issues, 'Editor VITE_API_PROXY_TARGET', editor.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000', ports.Backend)
  checkAddress(issues, 'Backend RUNTIME_BASE_URL', backend.RUNTIME_BASE_URL || 'http://127.0.0.1:7373', ports.Runtime)
  checkAddress(issues, 'Runtime RUNTIME_BACKEND_API_BASE_URL', runtime.RUNTIME_BACKEND_API_BASE_URL || 'http://127.0.0.1:8000', ports.Backend)
  checkAddress(issues, 'Runtime RUNTIME_PREVIEW_JWKS_URL', runtime.RUNTIME_PREVIEW_JWKS_URL || 'http://127.0.0.1:8000/.well-known/jwks.json', ports.Backend)
  try {
    const workers = JSON.parse(backend.RENDER_WORKERS_CONFIG || '[{"worker_id":"renderer-local","base_url":"http://127.0.0.1:7400"}]')
    if (!Array.isArray(workers) || !workers.length) throw new Error('Worker 列表为空')
    for (const worker of workers) {
      if (!worker || !worker.worker_id || !worker.base_url) throw new Error('Worker 缺少 ID 或地址')
      checkAddress(issues, `Backend Worker ${worker.worker_id}`, worker.base_url, ports.Renderer)
    }
  } catch {
    issues.push('Backend RENDER_WORKERS_CONFIG 必须为包含 worker_id、base_url 的非空 JSON 数组。')
  }
  const credentials = {}
  for (const [name, env] of Object.entries({ backend, renderer })) {
    try {
      credentials[name] = readRenderCredential(env, path.join(repoRoot, name))
    } catch (error) {
      issues.push(`${name}: ${error.message}`)
    }
  }
  if (credentials.backend && credentials.renderer && credentials.backend !== credentials.renderer) {
    issues.push('Backend 与 Renderer 的渲染共享凭据不一致。')
  }
  if ((backend.RENDER_PROFILE_DIGEST || 'profile.v1') !== (renderer.RENDER_PROFILE_DIGEST || 'profile.v1')) {
    issues.push('Backend 与 Renderer 的 RENDER_PROFILE_DIGEST 不一致。')
  }
  for (const [key, fallback] of Object.entries(AUDIENCES)) {
    if ((backend[key] || fallback) !== (runtime[key] || fallback)) issues.push(`Backend 与 Runtime 的 ${key} 不一致。`)
  }
  return { issues, ports }
}

/** CLI 入口：任一不一致以非零退出码阻断，只汇报完成的静态校验。 */
function main() {
  const { issues, ports } = checkEnvironment()
  if (issues.length) {
    for (const issue of issues) console.error(`[env] ${issue}`)
    process.exitCode = 1
  } else {
    console.log(`[env] 服务环境一致性检查通过：${Object.entries(ports).map(([name, port]) => `${name}(${port})`).join('、')}`)
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main()
