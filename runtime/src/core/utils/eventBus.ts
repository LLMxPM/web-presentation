/**
 * 全局事件总线
 * 用于组件间通信和配置更新通知
 */

import { ref } from 'vue'

/**
 * 事件类型定义
 */
export interface AppEvents {
  'config:updated': {
    type: 'containerThemes' | 'contentPageContainer' | 'app'
    data: unknown
  }
  'theme:changed': {
    theme: string
  }
  'settings:applied': void
}

/**
 * 事件监听器类
 */
type EventListener<T = unknown> = (data: T) => void

/**
 * 事件总线
 */
class EventBus {
  private listeners: Map<string, EventListener[]> = new Map()

  /**
   * 监听事件
   */
  on<K extends keyof AppEvents>(event: K, listener: EventListener<AppEvents[K]>): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, [])
    }
    this.listeners.get(event)!.push(listener)
  }

  /**
   * 移除事件监听
   */
  off<K extends keyof AppEvents>(event: K, listener: EventListener<AppEvents[K]>): void {
    const eventListeners = this.listeners.get(event)
    if (eventListeners) {
      const index = eventListeners.indexOf(listener)
      if (index > -1) {
        eventListeners.splice(index, 1)
      }
    }
  }

  /**
   * 触发事件
   */
  emit<K extends keyof AppEvents>(event: K, data: AppEvents[K]): void {
    const eventListeners = this.listeners.get(event)
    if (eventListeners) {
      eventListeners.forEach(listener => {
        try {
          listener(data)
        } catch (error) {
          console.error(`Error in event listener for "${event}":`, error)
        }
      })
    }
  }

  /**
   * 只监听一次事件
   */
  once<K extends keyof AppEvents>(event: K, listener: EventListener<AppEvents[K]>): void {
    const onceListener = (data: AppEvents[K]) => {
      listener(data)
      this.off(event, onceListener)
    }
    this.on(event, onceListener)
  }

  /**
   * 清除所有监听器
   */
  clear(): void {
    this.listeners.clear()
  }

  /**
   * 获取事件监听器数量
   */
  getListenerCount(event: keyof AppEvents): number {
    return this.listeners.get(event)?.length || 0
  }
}

/**
 * 全局事件总线实例
 */
export const eventBus = new EventBus()

/**
 * 响应式的配置更新状态
 */
export const configUpdateState = ref({
  lastUpdate: Date.now(),
  updateCount: 0
})

/**
 * 触发配置更新事件
 */
export function notifyConfigUpdate(type: 'containerThemes' | 'contentPageContainer' | 'app', data: unknown): void {
  configUpdateState.value.lastUpdate = Date.now()
  configUpdateState.value.updateCount++
  
  eventBus.emit('config:updated', { type, data })
}

/**
 * 监听配置更新
 */
export function onConfigUpdate(callback: (event: AppEvents['config:updated']) => void): void {
  eventBus.on('config:updated', callback)
}

/**
 * 移除配置更新监听
 */
export function offConfigUpdate(callback: (event: AppEvents['config:updated']) => void): void {
  eventBus.off('config:updated', callback)
}
