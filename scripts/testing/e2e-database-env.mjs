/**
 * 文件功能：集中生成平台 E2E 测试数据库环境变量，避免本地测试误用开发库。
 */

export const E2E_DATABASE_MARKER = '_e2e'
export const DEFAULT_E2E_DATABASE_URL =
  'postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/web_presentation_e2e'
export const DEFAULT_E2E_REDIS_URL = 'redis://127.0.0.1:6379/15'
export const DEFAULT_E2E_REDIS_KEY_PREFIX = 'web_presentation_e2e'

export function buildE2eBackendEnv(extraEnv = {}) {
  const databaseUrl = resolveE2eDatabaseUrl()
  return {
    ...process.env,
    ...extraEnv,
    DATABASE_URL: databaseUrl,
    AI_DB_URL: process.env.E2E_AI_DB_URL || '',
    REDIS_URL: process.env.E2E_REDIS_URL || DEFAULT_E2E_REDIS_URL,
    REDIS_KEY_PREFIX: process.env.E2E_REDIS_KEY_PREFIX || DEFAULT_E2E_REDIS_KEY_PREFIX,
  }
}

export function resolveE2eDatabaseUrl() {
  const explicitDatabaseUrl = normalizeEnvValue(process.env.E2E_DATABASE_URL)
  if (explicitDatabaseUrl) {
    return requireE2eDatabaseUrl(explicitDatabaseUrl, 'E2E_DATABASE_URL')
  }

  const inheritedDatabaseUrl = normalizeEnvValue(process.env.DATABASE_URL)
  if (inheritedDatabaseUrl && databaseNameContainsE2eMarker(inheritedDatabaseUrl)) {
    return inheritedDatabaseUrl
  }

  return DEFAULT_E2E_DATABASE_URL
}

function requireE2eDatabaseUrl(databaseUrl, sourceName) {
  if (!databaseNameContainsE2eMarker(databaseUrl)) {
    throw new Error(`${sourceName} 指向的数据库名必须包含 ${E2E_DATABASE_MARKER}。`)
  }
  return databaseUrl
}

function databaseNameContainsE2eMarker(databaseUrl) {
  return extractDatabaseName(databaseUrl).includes(E2E_DATABASE_MARKER)
}

function extractDatabaseName(databaseUrl) {
  try {
    const parsedUrl = new URL(databaseUrl)
    const pathParts = parsedUrl.pathname.split('/').filter(Boolean)
    return decodeURIComponent(pathParts.at(-1) || '')
  } catch {
    const match = databaseUrl.match(/\/([^/?#]+)(?:[?#]|$)/)
    return match ? decodeURIComponent(match[1]) : ''
  }
}

function normalizeEnvValue(value) {
  return String(value || '').trim()
}
