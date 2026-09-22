/**
 * 本地存储工具函数
 * 提供类型安全的本地存储操作
 */

/**
 * 本地存储的键名常量
 */
export const STORAGE_KEYS = {
    CONTAINER_THEMES: 'app_container_themes',
    CONTENT_PAGE_CONTAINER: 'app_content_page_container',
    USER_PREFERENCES: 'app_user_preferences',
    THEME_PREFERENCE: 'app-theme-preference'
} as const

/**
 * 从本地存储获取数据
 * @param key 存储键名
 * @param defaultValue 默认值
 * @returns 解析后的数据或默认值
 */
export function getFromStorage<T>(key: string, defaultValue: T): T {
    try {
        const item = localStorage.getItem(key)
        if (item === null) {
            return defaultValue
        }
        return JSON.parse(item) as T
    } catch (error) {
        console.warn(`Failed to get item from localStorage with key "${key}":`, error)
        return defaultValue
    }
}

/**
 * 保存数据到本地存储
 * @param key 存储键名
 * @param value 要保存的数据
 * @returns 是否保存成功
 */
export function saveToStorage<T>(key: string, value: T): boolean {
    try {
        localStorage.setItem(key, JSON.stringify(value))
        return true
    } catch (error) {
        console.warn(`Failed to save item to localStorage with key "${key}":`, error)
        return false
    }
}

/**
 * 从本地存储删除数据
 * @param key 存储键名
 * @returns 是否删除成功
 */
export function removeFromStorage(key: string): boolean {
    try {
        localStorage.removeItem(key)
        return true
    } catch (error) {
        console.warn(`Failed to remove item from localStorage with key "${key}":`, error)
        return false
    }
}

/**
 * 清空所有应用相关的本地存储
 */
export function clearAppStorage(): void {
    Object.values(STORAGE_KEYS).forEach(key => {
        removeFromStorage(key)
    })
}

/**
 * 检查本地存储是否可用
 * @returns 是否支持本地存储
 */
export function isStorageAvailable(): boolean {
    try {
        const testKey = '__storage_test__'
        localStorage.setItem(testKey, 'test')
        localStorage.removeItem(testKey)
        return true
    } catch {
        return false
    }
}



