/**
 * 文件功能：封装 Axios 实例，统一处理后台 API 前缀、Cookie 和错误提取逻辑。
 */
import axios from 'axios'

type UnauthorizedHandler = () => void | Promise<void>

let unauthorizedHandler: UnauthorizedHandler | null = null

/**
 * 解析后台 API 基础地址。
 * 默认使用同源 `/api`，以便开发环境通过 Vite 代理转发请求并复用同站 Cookie；
 * 如确实需要直连其它地址，可通过 `VITE_API_BASE_URL` 显式覆盖。
 */
export function resolveApiBaseUrl(): string {
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim()
  return configuredBaseUrl && configuredBaseUrl.length > 0 ? configuredBaseUrl : '/api'
}

export const http = axios.create({
  baseURL: resolveApiBaseUrl(),
  withCredentials: true,
  timeout: 10000,
})

/**
 * 注册全局未授权处理器，由应用入口注入路由跳转和登录态清理逻辑。
 */
export function registerUnauthorizedHandler(handler: UnauthorizedHandler) {
  unauthorizedHandler = handler
}

/**
 * 触发全局未授权处理，供 Axios 和 fetch 场景共用。
 */
export function notifyUnauthorized() {
  void unauthorizedHandler?.()
}

/**
 * 首次登录态探测由路由守卫自行处理，避免初始化导航时产生重复跳转。
 */
function shouldNotifyUnauthorized(requestUrl?: string) {
  return requestUrl !== '/auth/me'
}

http.interceptors.response.use(
  response => response,
  (error) => {
    if (
      axios.isAxiosError(error)
      && error.response?.status === 401
      && shouldNotifyUnauthorized(error.config?.url)
    ) {
      notifyUnauthorized()
    }
    return Promise.reject(error)
  },
)

/**
 * 提取接口错误信息，优先返回后端 message 字段，避免页面层重复判断。
 */
export function getErrorMessage(error: unknown, fallback = '请求失败，请稍后重试。'): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as {
      message?: string
      detail?: string | { msg?: string }[] | { message?: string }
      code?: string
    } | undefined

    if (typeof data?.message === 'string' && data.message.trim()) {
      return data.message
    }

    if (typeof data?.detail === 'string' && data.detail.trim()) {
      return data.detail
    }

    if (Array.isArray(data?.detail) && data.detail.length > 0) {
      const firstDetail = data.detail[0]
      if (typeof firstDetail?.msg === 'string' && firstDetail.msg.trim()) {
        return firstDetail.msg
      }
    }

    if (
      data?.detail
      && typeof data.detail === 'object'
      && !Array.isArray(data.detail)
      && typeof data.detail.message === 'string'
      && data.detail.message.trim()
    ) {
      return data.detail.message
    }

    if (typeof data?.code === 'string' && data.code.trim()) {
      return `${fallback}（${data.code}）`
    }
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return fallback
}

/**
 * 提取后端业务错误码，供页面层按错误语义做二次交互。
 */
export function getErrorCode(error: unknown): string | null {
  if (!axios.isAxiosError(error)) return null
  const data = error.response?.data as { code?: string } | undefined
  return typeof data?.code === 'string' && data.code.trim() ? data.code : null
}

/**
 * 提取后端业务错误附带的结构化数据，供页面层展示可操作修复入口。
 */
export function getErrorData<T = unknown>(error: unknown): T | null {
  if (!axios.isAxiosError(error)) return null
  const data = error.response?.data as { data?: T } | undefined
  return data?.data ?? null
}
