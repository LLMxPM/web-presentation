/** 文件用途：提供 Runtime 发布构建身份与版本路径，副本身份不参与发布指纹。 */
import { readFileSync } from 'node:fs'
import runtimeKitManifest from '../../runtime-kit/manifest/runtime-kit.manifest.json'

export const RUNTIME_VERSION_PATH = '/__runtime_version/'
let imageBuildId: string | undefined

/** 读取镜像构建时生成的身份；本地开发可用 dev，交付镜像缺身份必须失败。 */
export function resolveRuntimeBuildId(): string {
  const configured = String(process.env.RUNTIME_BUILD_ID || '').trim()
  if (configured) return configured
  if (imageBuildId === undefined) {
    try {
      imageBuildId = readFileSync(new URL('../../../.runtime-build-id', import.meta.url), 'utf8').trim()
    } catch {
      imageBuildId = ''
    }
  }
  if (!imageBuildId && process.env.RUNTIME_RELEASE_ID_REQUIRED === 'true') {
    throw new Error('交付 Runtime 缺少构建身份，必须重新构建镜像。')
  }
  return imageBuildId || 'dev'
}

/** 返回稳定的公开版本信息，RUNTIME_INSTANCE_ID 只用于另行观测。 */
export function buildRuntimeVersionFingerprint(): { runtime_kit_version: string; build_id: string } {
  return { runtime_kit_version: String(runtimeKitManifest.version || ''), build_id: resolveRuntimeBuildId() }
}

/** 格式化单次预览绑定的 Runtime Kit/发布构建身份。 */
export function formatRuntimeVersionFingerprint(): string {
  const identity = buildRuntimeVersionFingerprint()
  return `${identity.runtime_kit_version || 'unknown'}+${identity.build_id}`
}

/** 比较服务端绑定的期望指纹；历史未绑定票据保留兼容，版本路径仍受检查。 */
export function assertRuntimeVersion(expected: string | undefined, local: string): void {
  if (!expected || expected === local) return
  throw Object.assign(new Error(`预览版本不匹配：期望 ${expected}，当前 ${local}。`), {
    statusCode: 409, code: 'PREVIEW_VERSION_SKEW',
  })
}

/** 保留原请求头检查入口；正常浏览器由签名票据与版本路径自动传播。 */
export function assertExpectedRuntimeFingerprint(
  headers: Record<string, string | string[] | undefined> | undefined, local: string,
): void {
  const raw = headers?.['x-expected-runtime-version-fingerprint']
  assertRuntimeVersion(String(Array.isArray(raw) ? raw[0] : raw || '').trim(), local)
}

/** 给公开地址/Vite base 增加版本路径，重复调用保持同一个挂载路径。 */
export function withRuntimeVersionBase(base: string, fingerprint = formatRuntimeVersionFingerprint()): string {
  const normalized = base === './' ? '' : base.replace(/\/+$/, '')
  const suffix = `${RUNTIME_VERSION_PATH}${encodeURIComponent(fingerprint)}`
  if (normalized.endsWith(suffix)) return normalized
  return `${normalized}${suffix}`
}

/** 从挂载路径中读取版本；格式错误也明确拒绝，不进入 Vite 的源码错误处理。 */
export function assertRuntimeVersionPath(url: string, local: string): void {
  const pathname = new URL(url || '/', 'http://runtime.local').pathname
  const marker = pathname.indexOf(RUNTIME_VERSION_PATH)
  if (marker < 0) return
  const encoded = pathname.slice(marker + RUNTIME_VERSION_PATH.length).split('/')[0]
  let expected: string
  try {
    expected = decodeURIComponent(encoded || '')
  } catch {
    expected = 'invalid-version-path'
  }
  assertRuntimeVersion(expected || 'invalid-version-path', local)
}
