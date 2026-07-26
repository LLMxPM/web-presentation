/**
 * 文件功能：维护全局确认弹窗请求队列，为业务代码提供 Promise 风格的确认接口。
 */
import { shallowRef } from 'vue'

export interface ConfirmOptions {
  dangerous?: boolean
  confirmLabel?: string
  cancelLabel?: string
}

export interface ConfirmRequest {
  id: number
  message: string
  title: string
  dangerous: boolean
  confirmLabel: string
  cancelLabel: string
}

interface PendingConfirmRequest extends ConfirmRequest {
  resolve: (confirmed: boolean) => void
}

export const activeConfirmRequest = shallowRef<ConfirmRequest | null>(null)

const pendingRequests: PendingConfirmRequest[] = []
let activeRequest: PendingConfirmRequest | null = null
let requestId = 0

/**
 * 创建确认请求；请求按触发顺序串行展示，返回值表示用户是否确认。
 */
export function createConfirm(
  message: string,
  title = '操作确认',
  options: ConfirmOptions = {},
): Promise<boolean> {
  return new Promise(resolve => {
    pendingRequests.push({
      id: requestId++,
      message,
      title,
      dangerous: options.dangerous ?? false,
      confirmLabel: options.confirmLabel ?? '确定',
      cancelLabel: options.cancelLabel ?? '取消',
      resolve,
    })
    showNextConfirmRequest()
  })
}

/**
 * 结算当前确认请求，并在当前弹窗卸载后展示队列中的下一项。
 */
export function resolveActiveConfirm(confirmed: boolean): void {
  const request = activeRequest
  if (!request) return

  activeRequest = null
  activeConfirmRequest.value = null
  request.resolve(confirmed)
  queueMicrotask(showNextConfirmRequest)
}

/**
 * 取消全部确认请求，供全局宿主卸载和测试清理使用。
 */
export function cancelAllConfirmRequests(): void {
  const requests = activeRequest ? [activeRequest, ...pendingRequests] : [...pendingRequests]
  activeRequest = null
  pendingRequests.length = 0
  activeConfirmRequest.value = null
  requests.forEach(request => request.resolve(false))
}

/**
 * 在没有活动确认框时取出下一项，保证同一时刻只存在一个模态确认层。
 */
function showNextConfirmRequest(): void {
  if (activeRequest || pendingRequests.length === 0) return
  activeRequest = pendingRequests.shift() ?? null
  activeConfirmRequest.value = activeRequest
}
