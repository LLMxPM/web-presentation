import type { Component } from 'vue'
import { defineAsyncComponent } from 'vue'
import { loadIconConfig, type IconAnalysisConfig, type IconConfigYaml } from './config'

/**
 * 图标类型定义
 */
export interface IconConfig {
  /** 图标组件 */
  component: Component
  /** 图标类型：当前仅支持 static */
  type: 'static'
  /** 静态图标的路径 */
  src?: string
  /** 图标描述 */
  description?: string
  /** 图标分类 */
  category?: string
  /** 结构化分析元数据 */
  analysis?: IconAnalysisConfig | null
}

/**
 * 创建静态图标组件
 * @param src 图标源路径
 * @param description 图标描述
 * @returns 图标组件
 */
function createStaticIconComponent(src: string, description?: string): Component {
  return defineAsyncComponent(() => {
    return Promise.resolve({
      template: `<img :src="src" :alt="alt" v-bind="$attrs" class="static-icon" />`,
      props: {
        src: { type: String, default: src },
        alt: { type: String, default: description || 'Static Icon' }
      },
      style: {
        '.static-icon': {
          'max-width': '100%',
          'height': 'auto',
          'object-fit': 'contain'
        }
      }
    })
  })
}

/**
 * 图标注册表类
 */
class IconRegistry {
  private icons: Map<string, IconConfig> = new Map()
  private initialized = false
  private iconConfig: IconConfigYaml | null = null

  constructor() {
    this.initialize()
  }

  /**
   * 初始化图标注册表
   */
  private async initialize(): Promise<void> {
    if (this.initialized) return

    try {
      // 加载图标配置
      this.iconConfig = await loadIconConfig()

      // 注册静态图标
      this.registerStaticIcons()

      this.initialized = true
    } catch (error) {
      console.error('Failed to initialize icon registry:', error)
      this.initialized = false
    }
  }

  /**
   * 注册静态图标
   */
  private registerStaticIcons(): void {
    if (!this.iconConfig?.static_icons) return

    for (const iconConfig of this.iconConfig.static_icons) {
      const component = createStaticIconComponent(iconConfig.src, iconConfig.name)
      this.icons.set(iconConfig.name, {
        component,
        type: 'static',
        src: iconConfig.src,
        description: iconConfig.name || 'Static icon',
        analysis: iconConfig.analysis ?? null,
      })
    }
  }
  
  /**
   * 确保图标注册表已初始化
   */
  private async ensureInitialized(): Promise<void> {
    if (!this.initialized) {
      await this.initialize()
    }
  }

  /**
   * 注册新图标
   * @param name 图标名称
   * @param config 图标配置
   */
  async register(name: string, config: IconConfig): Promise<void> {
    await this.ensureInitialized()
    this.icons.set(name, config)
  }
  
  /**
   * 批量注册图标
   * @param icons 图标配置对象
   */
  async registerBatch(icons: Record<string, IconConfig>): Promise<void> {
    await this.ensureInitialized()
    Object.entries(icons).forEach(([name, config]) => {
      this.icons.set(name, config)
    })
  }
  
  /**
   * 获取图标组件
   * @param name 图标名称
   * @returns 图标组件或null
   */
  async getIcon(name?: string): Promise<Component | null> {
    if (!name) return null
    
    await this.ensureInitialized()
    const iconConfig = this.icons.get(name)
    return iconConfig?.component || null
  }
  
  /**
   * 获取图标配置
   * @param name 图标名称
   * @returns 图标配置或undefined
   */
  async getIconConfig(name?: string): Promise<IconConfig | undefined> {
    if (!name) return undefined
    
    await this.ensureInitialized()
    return this.icons.get(name)
  }
  
  /**
   * 检查图标是否存在
   * @param name 图标名称
   * @returns 是否存在
   */
  async hasIcon(name?: string): Promise<boolean> {
    if (!name) return false
    
    await this.ensureInitialized()
    return this.icons.has(name)
  }
  
  /**
   * 获取所有已注册的图标名称
   * @returns 图标名称数组
   */
  async getAllIconNames(): Promise<string[]> {
    await this.ensureInitialized()
    return Array.from(this.icons.keys())
  }
  
  /**
   * 根据类型获取图标名称
   * @param type 图标类型
   * @returns 图标名称数组
   */
  async getIconNamesByType(type: 'static'): Promise<string[]> {
    await this.ensureInitialized()
    return Array.from(this.icons.entries())
      .filter(([, config]) => config.type === type)
      .map(([name]) => name)
  }
  
  /**
   * 根据分类获取图标名称
   * @param category 图标分类
   * @returns 图标名称数组
   */
  async getIconNamesByCategory(category: string): Promise<string[]> {
    await this.ensureInitialized()
    return Array.from(this.icons.entries())
      .filter(([, config]) => config.category === category)
      .map(([name]) => name)
  }
  
  /**
   * 重新加载图标配置
   */
  async reload(): Promise<void> {
    this.initialized = false
    this.icons.clear()
    await this.initialize()
  }
  
  /**
   * 移除图标
   * @param name 图标名称
   */
  async unregister(name: string): Promise<boolean> {
    await this.ensureInitialized()
    return this.icons.delete(name)
  }
  
  /**
   * 清空所有图标
   */
  async clear(): Promise<void> {
    await this.ensureInitialized()
    this.icons.clear()
  }
}

// 创建全局图标注册表实例
export const iconRegistry = new IconRegistry()

/**
 * 获取图标组件的便捷函数
 * @param name 图标名称
 * @returns 图标组件或null
 */
export const getIcon = async (name?: string): Promise<Component | null> => {
  return await iconRegistry.getIcon(name)
}

/**
 * 检查图标是否存在的便捷函数
 * @param name 图标名称
 * @returns 是否存在
 */
export const hasIcon = async (name?: string): Promise<boolean> => {
  return await iconRegistry.hasIcon(name)
}

/**
 * 注册自定义图标的便捷函数
 * @param name 图标名称
 * @param config 图标配置
 */
export const registerIcon = async (name: string, config: IconConfig): Promise<void> => {
  await iconRegistry.register(name, config)
}

/**
 * 批量注册图标的便捷函数
 * @param icons 图标配置对象
 */
export const registerIcons = async (icons: Record<string, IconConfig>): Promise<void> => {
  await iconRegistry.registerBatch(icons)
}

/**
 * 获取图标配置的便捷函数
 * @param name 图标名称
 * @returns 图标配置或undefined
 */
export const getIconConfig = async (name?: string): Promise<IconConfig | undefined> => {
  return await iconRegistry.getIconConfig(name)
}

/**
 * 获取所有图标名称的便捷函数
 * @returns 图标名称数组
 */
export const getAllIconNames = async (): Promise<string[]> => {
  return await iconRegistry.getAllIconNames()
}

/**
 * 根据类型获取图标名称的便捷函数
 * @param type 图标类型
 * @returns 图标名称数组
 */
export const getIconNamesByType = async (type: 'static'): Promise<string[]> => {
  return await iconRegistry.getIconNamesByType(type)
}

/**
 * 根据分类获取图标名称的便捷函数
 * @param category 图标分类
 * @returns 图标名称数组
 */
export const getIconNamesByCategory = async (category: string): Promise<string[]> => {
  return await iconRegistry.getIconNamesByCategory(category)
}

/**
 * 重新加载图标注册表的便捷函数
 */
export const reloadIconRegistry = async (): Promise<void> => {
  await iconRegistry.reload()
}

/**
 * 移除图标的便捷函数
 * @param name 图标名称
 */
export const unregisterIcon = async (name: string): Promise<boolean> => {
  return await iconRegistry.unregister(name)
}

/**
 * 清空所有图标的便捷函数
 */
export const clearIcons = async (): Promise<void> => {
  await iconRegistry.clear()
}

// 导出类型
export type { Component as IconComponent }
export { IconRegistry }
