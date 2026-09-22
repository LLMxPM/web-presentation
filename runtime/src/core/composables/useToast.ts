/**
 * 文件用途：全局 Toast 消息系统（useToast.ts）
 * 主要功能：
 * - 在应用任意位置以编程方式显示轻量级提示消息（Toast）
 * - 支持消息类型（success、error、info、warning）与自动关闭时长
 * - 提供可在根组件渲染的 ToastContainer 进行统一展示
 */

import { reactive } from 'vue'

/**
 * Toast 项类型定义
 */
export type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface ToastItem {
  id: number
  type: ToastType
  message: string
  duration: number
}

/**
 * 全局 Toast 存储：使用 reactive 以便在任意组件中响应式展示
 */
const toastStore = reactive<{ list: ToastItem[] }>({ list: [] })

/**
 * 生成唯一 ID（基于时间戳与随机数）
 */
function genId(): number {
  return Date.now() + Math.floor(Math.random() * 1000)
}

/**
 * 显示一条 Toast 消息
 * @param options 消息选项：type、message、duration（毫秒）
 * 说明：默认持续 2000ms 后自动移除
 */
function showToast(options: { type?: ToastType; message: string; duration?: number }): number {
  const id = genId()
  const item: ToastItem = {
    id,
    type: options.type || 'info',
    message: options.message,
    duration: options.duration ?? 2000
  }
  toastStore.list.push(item)
  // 自动移除
  window.setTimeout(() => removeToast(id), item.duration)
  return id
}

/**
 * 主动移除一条 Toast
 * @param id Toast 唯一标识
 */
function removeToast(id: number): void {
  const idx = toastStore.list.findIndex(t => t.id === id)
  if (idx > -1) {
    toastStore.list.splice(idx, 1)
  }
}

/**
 * 获取 Toast 存储（用于容器组件渲染）
 */
function getToastStore() {
  return toastStore
}

/**
 * 组合式函数：在组件中调用以显示 toast
 * 返回：showToast、removeToast、store
 */
export function useToast() {
  return {
    showToast,
    removeToast,
    store: getToastStore()
  }
}

/**
 * 工具函数：快捷显示不同类型消息
 */
export const toast = {
  success(message: string, duration?: number) {
    return showToast({ type: 'success', message, duration })
  },
  error(message: string, duration?: number) {
    return showToast({ type: 'error', message, duration })
  },
  info(message: string, duration?: number) {
    return showToast({ type: 'info', message, duration })
  },
  warning(message: string, duration?: number) {
    return showToast({ type: 'warning', message, duration })
  }
}