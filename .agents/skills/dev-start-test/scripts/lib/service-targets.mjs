/** 文件功能：区分开发环境与 E2E 的探测目标，确保 E2E 校验和真实启动使用同一地址规则。 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { resolveServiceEnvironments } from '../../../../../scripts/dev/env-files.mjs'
import { resolveServiceUrls } from '../../../../../scripts/testing/service-env.mjs'
import { DEFAULT_E2E_REDIS_URL, resolveE2eDatabaseUrl } from '../../../../../scripts/testing/e2e-database-env.mjs'

export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../..')

/** 开发模式读取根/模块 .env；E2E 模式只按真实测试入口的进程环境与隔离默认值解析。 */
export function resolveStatusTargets({ e2e = false, systemEnv = process.env } = {}) {
  if (e2e) {
    return {
      urls: resolveServiceUrls(systemEnv),
      databaseUrl: resolveE2eDatabaseUrl(systemEnv),
      redisUrl: systemEnv.E2E_REDIS_URL || DEFAULT_E2E_REDIS_URL,
    }
  }
  const envs = resolveServiceEnvironments(REPO_ROOT, systemEnv)
  return {
    urls: {
      backend: pickUrl(envs.backend, ['BACKEND_BASE_URL', 'BACKEND_PUBLIC_BASE_URL'], `http://127.0.0.1:${envs.backend.APP_PORT || 8000}`),
      editor: pickUrl(envs.editor, ['EDITOR_BASE_URL'], 'http://127.0.0.1:5173'),
      runtime: pickUrl(envs.runtime, ['RUNTIME_BASE_URL'], `http://127.0.0.1:${envs.runtime.RUNTIME_SERVER_PORT || 7373}`),
      renderer: pickUrl(envs.renderer, ['RENDERER_BASE_URL'], `http://127.0.0.1:${envs.renderer.RENDER_PORT || 7400}`),
    },
    databaseUrl: envs.backend.DATABASE_URL,
    redisUrl: envs.backend.REDIS_URL,
  }
}

/** 选取首个非空地址，并移除末尾斜杠以便安全拼接探针路径。 */
function pickUrl(env, keys, fallback) {
  return String(keys.map((key) => env[key]).find((value) => String(value || '').trim()) || fallback).trim().replace(/\/+$/, '')
}
