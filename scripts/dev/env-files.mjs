/** 文件功能：按服务分别解析根配置、模块覆盖与进程环境，并安全读取服务凭据。 */
import fs from 'node:fs'
import path from 'node:path'
import { parseEnv } from 'node:util'

export const PLACEHOLDER_CREDENTIALS = new Set([
  '', 'change-me-render-secret', 'change-me', 'replace-with-strong-shared-secret', 'replace-me',
])

/** 读取可选 dotenv 文件；缺失返回空对象，语法解析使用 Node 的 dotenv 实现。 */
export function readEnvFile(filePath) {
  return fs.existsSync(filePath) ? parseEnv(fs.readFileSync(filePath, 'utf8')) : {}
}

/** 独立计算每个服务的有效环境，模块覆盖不得串入另一个服务。 */
export function resolveServiceEnvironments(repoRoot, systemEnv = process.env) {
  const root = readEnvFile(path.join(repoRoot, '.env'))
  return Object.fromEntries(['backend', 'runtime', 'renderer', 'editor'].map(name => [
    name, { ...root, ...readEnvFile(path.join(repoRoot, name, '.env')), ...systemEnv },
  ]))
}

/** 文件凭据优先；缺失、空文件与占位符立即报错，错误中不包含密钥。 */
export function readRenderCredential(env, moduleDir) {
  let secret = env.RENDER_SERVICE_CREDENTIAL || ''
  if (env.RENDER_SERVICE_CREDENTIAL_FILE) {
    try {
      secret = fs.readFileSync(path.resolve(moduleDir, env.RENDER_SERVICE_CREDENTIAL_FILE), 'utf8')
    } catch {
      throw new Error('RENDER_SERVICE_CREDENTIAL_FILE 不可读取。')
    }
  }
  secret = secret.trim()
  if (PLACEHOLDER_CREDENTIALS.has(secret)) throw new Error('渲染共享凭据为空或为占位符。')
  return secret
}
