/** 文件功能：用独立 dotenv 夹具验证服务覆盖、凭据文件和跨服务一致性诊断。 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { checkEnvironment } from '../../../scripts/dev/check-env.mjs'

let root: string

/** 在本用例的临时仓库写入配置，不接触开发者环境文件。 */
function write(relativePath: string, text: string) {
  const target = path.join(root, relativePath)
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, text)
}

beforeEach(() => {
  root = fs.mkdtempSync(path.join(os.tmpdir(), 'wp-env-test-'))
  write('.env', 'RENDER_SERVICE_CREDENTIAL=fixture-root-secret\nRENDER_PROFILE_DIGEST=profile.v1\n')
})
afterEach(() => fs.rmSync(root, { recursive: true, force: true }))

describe('服务环境边界', () => {
  it('根配置可被所有服务继承', () => {
    expect(checkEnvironment(root, {}).issues).toEqual([])
  })

  it('发现模块覆盖造成的密钥、profile 与 audience 分歧且不打印密钥', () => {
    write('backend/.env', 'RENDER_SERVICE_CREDENTIAL=backend-secret\nRENDER_PROFILE_DIGEST=profile.backend\nRUNTIME_SERVICE_TOKEN_AUDIENCE=backend-audience')
    write('renderer/.env', 'RENDER_SERVICE_CREDENTIAL=renderer-secret\nRENDER_PROFILE_DIGEST=profile.renderer')
    const issues = checkEnvironment(root, {}).issues.join('\n')
    expect(issues).toContain('渲染共享凭据不一致')
    expect(issues).toContain('RENDER_PROFILE_DIGEST 不一致')
    expect(issues).toContain('RUNTIME_SERVICE_TOKEN_AUDIENCE 不一致')
    expect(issues).not.toContain('backend-secret')
    expect(issues).not.toContain('renderer-secret')
  })

  it('系统环境优先于模块文件', () => {
    write('renderer/.env', 'RENDER_SERVICE_CREDENTIAL=module-secret')
    expect(checkEnvironment(root, { RENDER_SERVICE_CREDENTIAL: 'process-secret' }).issues).toEqual([])
  })

  it('文件凭据优先于内联值并按各服务目录解析', () => {
    write('backend/.env', 'RENDER_SERVICE_CREDENTIAL_FILE=./secret')
    write('renderer/.env', 'RENDER_SERVICE_CREDENTIAL_FILE=./secret')
    write('backend/secret', 'file-secret\n')
    write('renderer/secret', 'file-secret')
    expect(checkEnvironment(root, {}).issues).toEqual([])
    write('renderer/secret', '')
    expect(checkEnvironment(root, {}).issues.join()).toContain('渲染共享凭据为空')
    fs.unlinkSync(path.join(root, 'renderer/secret'))
    expect(checkEnvironment(root, {}).issues.join()).toContain('不可读取')
  })

  it('其它服务的覆盖不会遮蔽 Backend 的错误回源地址', () => {
    write('backend/.env', 'RUNTIME_BASE_URL=http://127.0.0.1:7999')
    write('runtime/.env', 'RUNTIME_BASE_URL=http://127.0.0.1:7373')
    expect(checkEnvironment(root, {}).issues.join()).toContain('Backend RUNTIME_BASE_URL 端口 7999')
  })
})
