/**
 * 文件用途：统一校验 Backend 与 Runtime 内部接口使用的短期服务令牌。
 */

import { createRemoteJWKSet, jwtVerify, type JWTPayload } from 'jose'

export interface RuntimeServiceClaims extends JWTPayload {
  sub?: string
  scope?: string
}

export interface RuntimeServiceTokenVerificationOptions {
  jwksUrl: string
  audience: string
  requiredScope?: string
}

/**
 * 校验 Runtime 服务令牌的签名、audience、subject 和 scope。
 * @param token x-runtime-service-token 请求头
 * @param options JWKS、audience 与所需 scope
 * @returns 已校验声明
 */
export async function verifyRuntimeServiceToken(
  token: string,
  options: RuntimeServiceTokenVerificationOptions,
): Promise<RuntimeServiceClaims> {
  if (!token) {
    throw new RuntimeServiceAuthError(401, 'RUNTIME_SERVICE_TOKEN_REQUIRED', '缺少 Runtime 服务令牌。')
  }
  if (!options.jwksUrl) {
    throw new RuntimeServiceAuthError(503, 'JWKS_URL_MISSING', 'Runtime 未配置 JWKS 地址。')
  }

  let jwksUrl: URL
  try {
    jwksUrl = new URL(options.jwksUrl)
  } catch (error) {
    throw new RuntimeServiceAuthError(503, 'JWKS_URL_INVALID', 'Runtime JWKS 地址无效。', error)
  }

  let payload: JWTPayload
  try {
    const jwks = createRemoteJWKSet(jwksUrl)
    const verified = await jwtVerify(token, jwks, { audience: options.audience })
    payload = verified.payload
  } catch (error) {
    throw new RuntimeServiceAuthError(401, 'RUNTIME_SERVICE_TOKEN_INVALID', 'Runtime 服务令牌校验失败。', error)
  }

  const claims = payload as RuntimeServiceClaims
  const requiredScope = options.requiredScope || 'runtime-artifact-read'
  if (claims.sub !== 'runtime-service' || claims.scope !== requiredScope) {
    throw new RuntimeServiceAuthError(401, 'RUNTIME_SERVICE_TOKEN_INVALID', 'Runtime 服务令牌缺少必需声明。')
  }
  return claims
}

/**
 * Runtime 内部服务鉴权错误，供各插件稳定映射 HTTP 状态和业务错误码。
 */
export class RuntimeServiceAuthError extends Error {
  statusCode: number
  code: string

  constructor(statusCode: number, code: string, message: string, cause?: unknown) {
    super(message, { cause })
    this.name = 'RuntimeServiceAuthError'
    this.statusCode = statusCode
    this.code = code
  }
}
