/**
 * 文件用途：注册 Runtime 本地演示环境使用的静态图标配置。
 */

import { defineAsyncComponent } from 'vue'
import type { IconConfig } from './icon-registry'
import { registerIcons } from './icon-registry'

/**
 * 静态图标配置
 * 这里可以注册自定义的静态图标
 */
const staticIconConfigs: Record<string, IconConfig> = {
  // 示例：自定义Logo图标
  // 'custom-logo': {
  //   type: 'static',
  //   src: '/img/logo/custom-logo.svg',
  //   description: '自定义Logo图标'
  // },
  
  // 示例：品牌图标
  // 'brand-icon': {
  //   type: 'static',
  //   src: '/img/icons/brand.png',
  //   description: '品牌图标'
  // },
  
  // 示例：特殊功能图标
  // 'special-feature': {
  //   type: 'static',
  //   src: '/img/icons/special-feature.svg',
  //   description: '特殊功能图标'
  // }
}

/**
 * 初始化静态图标
 * 在应用启动时调用此函数来注册所有静态图标
 */
export function initializeStaticIcons(): void {
  registerIcons(staticIconConfigs)
}

/**
 * 动态注册静态图标的辅助函数
 * @param name 图标名称
 * @param src 图标文件路径
 * @param description 图标描述
 */
export function registerStaticIcon(
  name: string, 
  src: string, 
  description?: string
): void {
  const config: IconConfig = {
    component: defineAsyncComponent(() => {
      // 创建一个简单的img组件
      return Promise.resolve({
        template: `<img :src="src" :alt="alt" v-bind="$attrs" />`,
        props: {
          src: { type: String, default: src },
          alt: { type: String, default: description || name }
        }
      })
    }),
    type: 'static',
    src,
    description: description || `Static icon: ${name}`
  }
  
  registerIcons({ [name]: config })
}

/**
 * 批量注册静态图标的辅助函数
 * @param icons 图标配置对象，key为图标名称，value为图标路径或完整配置
 */
export function registerStaticIcons(
  icons: Record<string, string | { src: string; description?: string }>
): void {
  const configs: Record<string, IconConfig> = {}
  
  Object.entries(icons).forEach(([name, config]) => {
    const iconConfig = typeof config === 'string' 
      ? { src: config }
      : config
    
    configs[name] = {
      component: defineAsyncComponent(() => {
        return Promise.resolve({
          template: `<img :src="src" :alt="alt" v-bind="$attrs" />`,
          props: {
            src: { type: String, default: iconConfig.src },
            alt: { type: String, default: iconConfig.description || name }
          }
        })
      }),
      type: 'static',
      src: iconConfig.src,
      description: iconConfig.description || `Static icon: ${name}`
    }
  })
  
  registerIcons(configs)
}

// 导出静态图标配置供其他地方使用
export { staticIconConfigs }
