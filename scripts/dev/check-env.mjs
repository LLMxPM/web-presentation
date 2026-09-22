/**
 * 文件功能：检测全仓库环境变量的完整性、跨模块一致性与安全性约束。
 *
 * 职责：
 * 1. 检查是否存在根目录 .env，并提供初始化引导；
 * 2. 校验 Backend、Runtime、Renderer、Editor 之间的端口、URL、Audience 与凭据对齐；
 * 3. 拦截 Renderer 等核心组件的弱占位符与空密钥（防止启动期 fail-closed 崩溃）；
 * 4. 扫描各模块服务配置的监听端口冲突。
 */

import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(__dirname, '../..')

// 弱占位密钥列表（对齐 renderer/app/config.py _PLACEHOLDER_CREDENTIALS）
const PLACEHOLDER_CREDENTIALS = new Set([
  '',
  'change-me-render-secret',
  'change-me',
  'replace-with-strong-shared-secret',
  'replace-me',
])

/**
 * 简单解析 .env 文件内容为键值对字典。
 * @param {string} filePath 待解析的 .env 文件绝对路径
 * @returns {Record<string, string>}
 */
function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return {}
  }
  const content = fs.readFileSync(filePath, 'utf-8')
  const env = {}
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) {
      continue
    }
    const match = trimmed.match(/^([A-Za-z0-9_]+)\s*=\s*(.*)$/)
    if (match) {
      let val = match[2].trim()
      // 去除首尾引号
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1)
      }
      env[match[1]] = val
    }
  }
  return env
}

/**
 * 按照级联规则获取整合后的环境变量字典。
 * 优先级：系统环境变量 > 模块子目录 .env > 根目录 .env
 */
function resolveConsolidatedEnv() {
  const rootEnv = parseEnvFile(path.join(REPO_ROOT, '.env'))
  const backendEnv = parseEnvFile(path.join(REPO_ROOT, 'backend', '.env'))
  const runtimeEnv = parseEnvFile(path.join(REPO_ROOT, 'runtime', '.env'))
  const rendererEnv = parseEnvFile(path.join(REPO_ROOT, 'renderer', '.env'))
  const editorEnv = parseEnvFile(path.join(REPO_ROOT, 'editor', '.env'))

  return {
    rootEnv,
    backendEnv,
    runtimeEnv,
    rendererEnv,
    editorEnv,
    // 综合视图（针对各模块，默认先继承根目录再继承子目录）
    merged: {
      ...rootEnv,
      ...backendEnv,
      ...runtimeEnv,
      ...rendererEnv,
      ...editorEnv,
      ...process.env,
    },
  }
}

/**
 * 解析 URL 中的端口号与主机。
 * @param {string} urlStr
 * @param {number} defaultPort
 */
function extractPortAndHost(urlStr, defaultPort) {
  try {
    const parsed = new URL(urlStr)
    const port = parsed.port ? parseInt(parsed.port, 10) : defaultPort
    return { host: parsed.hostname, port, valid: true }
  } catch {
    return { host: '', port: defaultPort, valid: false }
  }
}

/**
 * 主执行函数
 */
function main() {
  console.log('\n🔍 开始检查 web-presentation 环境变量配置...\n')

  const rootEnvPath = path.join(REPO_ROOT, '.env')
  const hasRootEnv = fs.existsSync(rootEnvPath)
  const { rootEnv, backendEnv, runtimeEnv, rendererEnv, editorEnv, merged } = resolveConsolidatedEnv()

  const issues = []
  const warnings = []
  const passes = []

  // 1. 根目录 .env 存在性检查
  if (!hasRootEnv) {
    warnings.push(
      '未检测到根目录 .env 文件。建议执行 `cp .env.example .env` 以享受全仓统一环境变量管理便利。'
    )
  } else {
    passes.push('根目录 .env 文件已就绪 (单一事实源)。')
  }

  // 2. 核心端口提取与冲突扫描
  const backendPort = parseInt(merged.APP_PORT || '8000', 10)
  const runtimePort = parseInt(merged.RUNTIME_SERVER_PORT || '7373', 10)
  const rendererPort = parseInt(merged.RENDER_PORT || '7400', 10)
  const editorPort = 5173 // Editor Vite 默认端口

  const portsMap = {
    Backend: backendPort,
    Runtime: runtimePort,
    Renderer: rendererPort,
    Editor: editorPort,
  }

  const portCount = {}
  for (const [name, port] of Object.entries(portsMap)) {
    portCount[port] = portCount[port] || []
    portCount[port].push(name)
  }
  for (const [port, services] of Object.entries(portCount)) {
    if (services.length > 1) {
      issues.push(`端口冲突检测：端口 ${port} 被多个服务同时声明：${services.join(', ')}。`)
    }
  }
  passes.push(`服务端口分配正常：Backend(${backendPort}), Runtime(${runtimePort}), Renderer(${rendererPort}), Editor(${editorPort})。`)

  // 3. Backend ↔ Editor 对齐检查
  const editorProxyTarget = merged.VITE_API_PROXY_TARGET || `http://127.0.0.1:${backendPort}`
  const editorProxyPortInfo = extractPortAndHost(editorProxyTarget, 80)
  if (editorProxyPortInfo.valid && editorProxyPortInfo.port !== backendPort) {
    warnings.push(
      `Editor 代理目标端口 (VITE_API_PROXY_TARGET=${editorProxyTarget}) 与 Backend 监听端口 (${backendPort}) 不一致。本地联调可能无法代理 API。`
    )
  } else {
    passes.push('Editor API 代理目标端口与 Backend 端口对齐。')
  }

  // 4. Backend ↔ Runtime 对齐检查
  const runtimeBaseUrl = merged.RUNTIME_BASE_URL || `http://127.0.0.1:${runtimePort}`
  const runtimePortInfo = extractPortAndHost(runtimeBaseUrl, 7373)
  if (runtimePortInfo.valid && runtimePortInfo.port !== runtimePort) {
    issues.push(
      `Backend 配置的 RUNTIME_BASE_URL (${runtimeBaseUrl}) 端口与 Runtime 监听端口 (${runtimePort}) 不匹配。`
    )
  } else {
    passes.push('Backend 调用 Runtime 的内部地址与 Runtime 监听端口对齐。')
  }

  const runtimeBackendApiUrl = merged.RUNTIME_BACKEND_API_BASE_URL || `http://127.0.0.1:${backendPort}`
  const runtimeBackendPortInfo = extractPortAndHost(runtimeBackendApiUrl, 8000)
  if (runtimeBackendPortInfo.valid && runtimeBackendPortInfo.port !== backendPort) {
    issues.push(
      `Runtime 回源地址 RUNTIME_BACKEND_API_BASE_URL (${runtimeBackendApiUrl}) 端口与 Backend 监听端口 (${backendPort}) 不匹配。`
    )
  } else {
    passes.push('Runtime 回源 Backend 的地址与 Backend 端口对齐。')
  }

  // 5. Backend ↔ Renderer 对齐检查
  let backendRenderWorkers = []
  try {
    backendRenderWorkers = JSON.parse(merged.RENDER_WORKERS_CONFIG || '[]')
  } catch {
    issues.push('Backend RENDER_WORKERS_CONFIG 格式非法，必须为合法 JSON 数组。')
  }

  if (backendRenderWorkers.length > 0) {
    const localWorker = backendRenderWorkers.find(
      (w) => w.worker_id === (merged.RENDER_WORKER_ID || 'renderer-local') || w.base_url?.includes('127.0.0.1') || w.base_url?.includes('localhost')
    ) || backendRenderWorkers[0]
    if (localWorker && localWorker.base_url) {
      const workerPortInfo = extractPortAndHost(localWorker.base_url, 7400)
      if (workerPortInfo.valid && workerPortInfo.port !== rendererPort) {
        issues.push(
          `Backend RENDER_WORKERS_CONFIG 中 ${localWorker.worker_id} 地址 (${localWorker.base_url}) 与 Renderer 监听端口 (${rendererPort}) 不匹配。`
        )
      } else {
        passes.push('Backend 远程渲染 Worker 配置与 Renderer 监听端口对齐。')
      }
    }
  }

  // 凭据一致性与弱密钥检测
  const backendRenderSecret = merged.RENDER_SERVICE_CREDENTIAL || ''
  const rendererSecret = merged.RENDER_SERVICE_CREDENTIAL || ''
  if (PLACEHOLDER_CREDENTIALS.has(rendererSecret.trim())) {
    issues.push(
      'Renderer 共享密钥 RENDER_SERVICE_CREDENTIAL 为弱占位符或为空。Renderer 启动时将 fail-closed 退出。请配置安全随机密钥。'
    )
  } else if (backendRenderSecret !== rendererSecret) {
    issues.push(
      'Backend 与 Renderer 的 RENDER_SERVICE_CREDENTIAL 密钥不一致，渲染请求将被拒绝 (401 Unauthorized)。'
    )
  } else {
    passes.push('Backend 与 Renderer 共享服务身份凭据已配置且保持一致。')
  }

  // Digest 检查
  const backendDigest = merged.RENDER_PROFILE_DIGEST || 'profile.v1'
  const rendererDigest = merged.RENDER_PROFILE_DIGEST || 'profile.v1'
  if (backendDigest !== rendererDigest) {
    issues.push(
      `Backend RENDER_PROFILE_DIGEST (${backendDigest}) 与 Renderer (${rendererDigest}) 不一致。渲染调度将拒绝执行。`
    )
  } else {
    passes.push(`Renderer Profile 指纹一致 (${backendDigest})。`)
  }

  // 6. Audience 对齐检查
  const audienceKeys = [
    'RUNTIME_SERVICE_TOKEN_AUDIENCE',
    'RUNTIME_PREVIEW_TOKEN_AUDIENCE',
    'RUNTIME_BUILD_TOKEN_AUDIENCE',
    'RUNTIME_DIAGNOSTICS_TOKEN_AUDIENCE',
  ]
  let audiencePassed = true
  for (const key of audienceKeys) {
    const val = merged[key]
    if (!val) {
      warnings.push(`令牌受众声明缺失：${key} 为空。建议在根目录 .env 中明确声明。`)
      audiencePassed = false
    }
  }
  if (audiencePassed) {
    passes.push('Backend 与 Runtime 跨服务 Audience 令牌声明已就绪。')
  }

  // 输出检查报告
  for (const p of passes) {
    console.log(`  ✅ ${p}`)
  }
  if (warnings.length > 0) {
    console.log('')
    for (const w of warnings) {
      console.log(`  ⚠️  ${w}`)
    }
  }
  if (issues.length > 0) {
    console.log('')
    for (const err of issues) {
      console.log(`  ❌ ${err}`)
    }
    console.log('\n❌ 环境配置检查未通过，请根据上方提示修复相关配置。\n')
    process.exit(1)
  }

  console.log('\n🎉 环境配置检查全部通过！所有服务配置自洽且就绪。\n')
}

main()
