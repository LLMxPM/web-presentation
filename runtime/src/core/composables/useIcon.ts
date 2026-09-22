/**
 * 文件用途：提供图标使用相关的 Vue Composable，包括图标获取、批量处理与注册功能。
 *           当前运行时仅支持静态图标，并为静态 SVG 图标提供内联渲染与颜色配置能力。
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { getIcon, hasIcon, getIconConfig } from '@/core/utils/icon-registry'
import type { IconConfig } from '@/core/utils/icon-registry'
import type { Component } from 'vue'
import { resolveResourcePath } from '@/core/utils/path'

/**
 * 判断图标配置是否应按内联 SVG 方式处理。
 * 关键约束：
 * 1. 预览模式下 backend 下发的 `src` 可能只是逻辑资源名（例如 `github`），不能再依赖 `.svg` 后缀判断；
 * 2. 优先以结构化分析元数据为准，确保 dev / preview 两条链路行为一致；
 * 3. 为兼容旧配置，当缺少 format 元数据时仍允许回退到 `.svg` 后缀识别。
 * @param config 图标配置
 * @returns 是否应以内联 SVG 方式加载
 */
function shouldUseInlineSvg(config?: IconConfig): boolean {
  if (config?.type !== 'static') {
    return false
  }

  const renderMode = config.analysis?.icon.render_mode
  if (renderMode !== 'inline_svg') {
    return false
  }

  const format = config.analysis?.icon.format
  if (format === 'svg') {
    return true
  }

  const src = String(config.src || '').trim().toLowerCase()
  return src.endsWith('.svg')
}

/**
 * 图标使用的 Composable
 * @param iconName 图标名称（可以是响应式的）
 */
export function useIcon(iconName: string | ComputedRef<string | undefined> | ComputedRef<string>) {
  /**
   * 计算属性：当前图标名称
   */
  const currentIconName = computed(() => {
    return typeof iconName === 'string' ? iconName : iconName.value
  })
  
  // 响应式状态
  const iconComponent: Ref<Component | null> = ref(null)
  const iconConfig: Ref<IconConfig | undefined> = ref(undefined)
  const iconExists: Ref<boolean> = ref(false)
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)

  // 新增：静态 SVG 内容（当为静态 SVG 图标时存储获取到的文本）
  const staticSvgContent: Ref<string | null> = ref(null)
  
  /**
   * 加载图标数据
   * 完整职责：
   * 1) 根据图标名称获取组件、配置与是否存在
   * 2) 当图标为静态且为 SVG 资源时，拉取并缓存 SVG 文本
   */
  const loadIconData = async () => {
    const name = currentIconName.value
    if (!name) {
      iconComponent.value = null
      iconConfig.value = undefined
      iconExists.value = false
      staticSvgContent.value = null
      return
    }

    loading.value = true
    error.value = null

    try {
      const [component, config, exists] = await Promise.all([
        getIcon(name),
        getIconConfig(name),
        hasIcon(name)
      ])

      iconComponent.value = component
      iconConfig.value = config
      iconExists.value = exists

      // 若是静态 SVG 图标，尝试加载其内容
      if (shouldUseInlineSvg(config) && config?.src) {
        const src = resolveResourcePath(config.src)
        try {
          const res = await fetch(src)
          if (!res.ok) throw new Error(`Failed to fetch svg: ${res.status}`)
          const svgText = await res.text()
          staticSvgContent.value = svgText
        } catch (e) {
          // 如果获取失败，记录错误并清空内容，但不影响其他图标逻辑
          const msg = e instanceof Error ? e.message : 'Failed to load SVG content'
          error.value = msg
          staticSvgContent.value = null
        }
      } else {
        staticSvgContent.value = null
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load icon'
      iconComponent.value = null
      iconConfig.value = undefined
      iconExists.value = false
      staticSvgContent.value = null
    } finally {
      loading.value = false
    }
  }

  // 监听图标名称变化
  watch(currentIconName, loadIconData, { immediate: true })
  
  /**
   * 计算属性：图标类型
   */
  const iconType = computed((): 'static' | undefined => {
    return iconConfig.value?.type
  })

  /**
   * 计算属性：图标结构化分析元数据。
   */
  const iconAnalysis = computed(() => iconConfig.value?.analysis ?? null)

  /**
   * 计算属性：静态图标实际渲染模式。
   */
  const staticRenderMode = computed((): 'inline_svg' | 'image' => {
    return iconAnalysis.value?.icon.render_mode === 'inline_svg' ? 'inline_svg' : 'image'
  })

  /**
   * 计算属性：是否为静态图标
   */
  const isStaticIcon = computed((): boolean => {
    return iconType.value === 'static'
  })

  /**
   * 计算属性：是否为静态 SVG 图标
   */
  const isStaticSvg = computed((): boolean => {
    return isStaticIcon.value && shouldUseInlineSvg(iconConfig.value)
  })

  /**
   * 计算属性：当前静态 SVG 是否允许调整描边宽度。
   */
  const supportsStrokeWidth = computed((): boolean => {
    return Boolean(
      iconAnalysis.value?.icon.stroke_width_editable &&
      staticRenderMode.value === 'inline_svg' &&
      isStaticSvg.value,
    )
  })
  
  /**
   * 计算属性：静态图标源路径
   * 使用 resolveResourcePath 处理 baseUrl
   */
  const staticIconSrc = computed((): string | undefined => {
    if (isStaticIcon.value && iconConfig.value?.src) {
      return resolveResourcePath(iconConfig.value.src)
    }
    return undefined
  })
  
  /**
   * 计算属性：图标描述
   */
  const iconDescription = computed((): string | undefined => {
    return iconConfig.value?.description
  })
  
  return {
    // 基础信息
    iconName: currentIconName,
    iconComponent,
    iconConfig,
    iconExists,
    
    // 状态信息
    loading,
    error,
    
    // 类型判断
    iconType,
    iconAnalysis,
    isStaticIcon,
    isStaticSvg,
    staticRenderMode,
    supportsStrokeWidth,
    
    // 静态图标相关
    staticIconSrc,
    staticSvgContent,
    
    // 其他信息
    iconDescription,
    
    // 方法
    reload: loadIconData
  }
}

/**
 * 批量图标使用的 Composable
 * @param iconNames 图标名称数组
 */
export function useIcons(iconNames: string[]) {
  // 为每个图标创建独立的 useIcon 实例
  const iconInstances = iconNames.map(name => ({
    name,
    ...useIcon(name)
  }))
  
  /**
   * 计算属性：所有图标的加载状态
   */
  const loading = computed(() => {
    return iconInstances.some(icon => icon.loading.value)
  })
  
  /**
   * 计算属性：是否有错误
   */
  const hasErrors = computed(() => {
    return iconInstances.some(icon => icon.error.value !== null)
  })
  
  /**
   * 计算属性：所有错误信息
   */
  const errors = computed(() => {
    return iconInstances
      .filter(icon => icon.error.value !== null)
      .map(icon => ({ name: icon.name, error: icon.error.value }))
  })
  
  /**
   * 计算属性：存在的图标
   */
  const existingIcons = computed(() => {
    return iconInstances.filter(icon => icon.iconExists.value)
  })
  
  /**
   * 计算属性：不存在的图标名称
   */
  const missingIconNames = computed(() => {
    return iconInstances
      .filter(icon => !icon.iconExists.value)
      .map(icon => icon.name)
  })
  
  /**
   * 计算属性：按类型分组的图标
   */
  const iconsByType = computed(() => {
    const staticIcons: string[] = []
    const unknownIcons: string[] = []
    
    iconInstances.forEach(icon => {
      if (icon.isStaticIcon.value) {
        staticIcons.push(icon.name)
      } else {
        unknownIcons.push(icon.name)
      }
    })
    
    return {
      static: staticIcons,
      unknown: unknownIcons
    }
  })
  
  /**
   * 重新加载所有图标
   */
  const reloadAll = async () => {
    await Promise.all(iconInstances.map(icon => icon.reload()))
  }
  
  return {
    icons: iconInstances,
    loading,
    hasErrors,
    errors,
    existingIcons,
    missingIconNames,
    iconsByType,
    reloadAll
  }
}

/**
 * 图标注册的 Composable
 */
export function useIconRegistry() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  
  /**
   * 注册单个图标
   */
  const registerIcon = async (name: string, config: IconConfig) => {
    loading.value = true
    error.value = null
    try {
      await (await import('@/core/utils/icon-registry')).registerIcon(name, config)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to register icon'
      throw err
    } finally {
      loading.value = false
    }
  }
  
  /**
   * 批量注册图标
   */
  const registerIcons = async (icons: Record<string, IconConfig>) => {
    loading.value = true
    error.value = null
    try {
      await (await import('@/core/utils/icon-registry')).registerIcons(icons)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to register icons'
      throw err
    } finally {
      loading.value = false
    }
  }
  
  /**
   * 移除图标
   */
  const unregisterIcon = async (name: string) => {
    loading.value = true
    error.value = null
    try {
      return await (await import('@/core/utils/icon-registry')).unregisterIcon(name)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to unregister icon'
      throw err
    } finally {
      loading.value = false
    }
  }
  
  /**
   * 获取所有图标名称
   */
  const getAllIconNames = async () => {
    try {
      return await (await import('@/core/utils/icon-registry')).getAllIconNames()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to get icon names'
      throw err
    }
  }
  
  /**
   * 根据类型获取图标名称
   */
  const getIconNamesByType = async (type: 'static') => {
    try {
      return await (await import('@/core/utils/icon-registry')).getIconNamesByType(type)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to get icon names by type'
      throw err
    }
  }
  
  /**
   * 根据分类获取图标名称
   */
  const getIconNamesByCategory = async (category: string) => {
    try {
      return await (await import('@/core/utils/icon-registry')).getIconNamesByCategory(category)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to get icon names by category'
      throw err
    }
  }
  
  /**
   * 重新加载图标注册表
   */
  const reloadRegistry = async () => {
    loading.value = true
    error.value = null
    try {
      await (await import('@/core/utils/icon-registry')).reloadIconRegistry()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to reload icon registry'
      throw err
    } finally {
      loading.value = false
    }
  }
  
  return {
    loading,
    error,
    registerIcon,
    registerIcons,
    unregisterIcon,
    getAllIconNames,
    getIconNamesByType,
    getIconNamesByCategory,
    reloadRegistry
  }
}
