/**
 * 文件用途：为组件预览宿主页提供 mock 数据注入与读取能力，供被预览组件按 key 获取静态 mock。
 */

import { computed, inject, type ComputedRef, type Ref } from 'vue'

export const COMPONENT_PREVIEW_MOCKS_KEY = Symbol('component-preview-mocks')

/**
 * 读取组件预览宿主页注入的 mock 数据。
 * @param key mock 键名
 * @param fallback 非预览环境或缺失键名时的默认值
 * @returns 响应式 mock 数据
 */
export function useComponentPreviewMock<T = unknown>(key: string, fallback?: T): ComputedRef<T> {
  const mockStateRef = inject<Ref<Record<string, unknown>> | null>(COMPONENT_PREVIEW_MOCKS_KEY, null)
  return computed(() => {
    if (!mockStateRef) {
      return fallback as T
    }
    return (mockStateRef.value[key] as T | undefined) ?? (fallback as T)
  })
}
