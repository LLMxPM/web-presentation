/**
 * 文件功能：缓存服务端放映能力声明，确保放映表单只展示已开放执行的模式。
 */
import { ref } from 'vue'

import { fetchSlideshowCapabilities } from '@/api/system'
import type { SlideshowCapabilities } from '@/types/api'

const capabilities = ref<SlideshowCapabilities | null>(null)
const loading = ref(false)
let pending: Promise<void> | null = null

/**
 * 提供共享的放映能力状态；并发调用复用同一请求，失败时保持未开放并允许后续重试。
 */
export function useSlideshowCapabilities() {
  /**
   * 读取一次能力声明；已成功读取或正在读取时不再发起重复请求。
   */
  function load(): Promise<void> {
    if (pending) {
      return pending
    }
    if (capabilities.value) {
      return Promise.resolve()
    }
    loading.value = true
    pending = fetchSlideshowCapabilities()
      .then((value) => {
        capabilities.value = value
      })
      .catch(() => {
        capabilities.value = null
      })
      .finally(() => {
        loading.value = false
        pending = null
      })
    return pending
  }

  return {
    capabilities,
    loading,
    load,
  }
}

/** 仅供测试重置共享能力缓存；生产代码不得调用。 */
export function resetSlideshowCapabilitiesForTests(): void {
  capabilities.value = null
  loading.value = false
  pending = null
}
