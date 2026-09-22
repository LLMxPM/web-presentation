/**
 * 文件用途：统一加载应用配置、路由配置与图标配置，并为整项目预览提供组件解析能力。
 */

import { reactive, computed } from 'vue'
import { resolvePageTransition } from './page-transition'
import type { PageTransitionConfig } from '../types/page-transition'
import { parse } from 'yaml'
import type { RouteRecordRaw } from 'vue-router'

import type { RouteConfig } from '@/core/types/navigation'
import { getRuntimePreloadedConfig, getRuntimePreviewContext } from '@/core/utils/path'
import { buildConfigUrl, hasExternalConfigSource } from './path'
import { createViewModuleLoader } from './view-module'

/**
 * 应用配置接口。
 */
export interface RuntimePageConfig {
  width: number
  height: number
  baseFontSize: string
  iconDefaultStrokeWidth: number
}

export type RuntimeMenuMode = 'text' | 'preview' | 'bottom-preview'

export interface AppConfig {
  app: {
    icon: string
    title: string
    description: string
    page?: Partial<RuntimePageConfig>
    features?: {
      showPdfExportButton?: boolean
      menuMode?: RuntimeMenuMode
    }
  }
}

export const DEFAULT_PAGE_CONFIG: RuntimePageConfig = {
  width: 1920,
  height: 1080,
  baseFontSize: '24px',
  iconDefaultStrokeWidth: 2,
}

/**
 * 路由配置结构。
 */
export interface RouteConfigYaml {
  transitionDefaults?: PageTransitionConfig | null
  routes: Array<{
    route: string
    component?: string
    meta: {
      title: string
      icon?: string
      order: number
      pageNumber?: number
      hidden?: boolean
      speakerNotes?: string | null
      transition?: PageTransitionConfig | null
    }
    children?: Array<{
      route: string
      component: string
      meta: {
        title: string
        order: number
        pageNumber?: number
        hidden?: boolean
        speakerNotes?: string | null
      transition?: PageTransitionConfig | null
      }
    }>
  }>
}

/**
 * 图标配置结构。
 */
export interface IconAnalysisConfig {
  schema_version: number
  kind: 'icon'
  icon: {
    format: 'svg' | 'image' | 'unknown'
    render_mode: 'inline_svg' | 'image'
    style: 'stroke' | 'fill' | 'mixed' | 'complex' | 'unknown'
    inline_safe: boolean
    stroke_width_editable: boolean
    analysis_status: 'analyzed' | 'unsupported' | 'error'
    reasons: string[]
  }
}

export interface StaticIconConfigItem {
  name: string
  src: string
  analysis?: IconAnalysisConfig | null
}

export interface IconConfigYaml {
  static_icons: StaticIconConfigItem[]
}

/**
 * 配置变化监听器类型。
 */
export type ConfigChangeListener = (configType: 'app' | 'routes' | 'icons') => void

/**
 * 默认应用配置。
 */
const defaultAppConfig: AppConfig = {
  app: {
    icon: 'slider',
    title: 'web-runtime-vue',
    description: '只读预览运行时',
    page: { ...DEFAULT_PAGE_CONFIG },
    features: {
      showPdfExportButton: true,
      menuMode: 'text'
    }
  }
}

/**
 * 默认图标配置。
 */
const defaultIconConfig: IconConfigYaml = {
  static_icons: [],
}

/**
 * 配置缓存。
 */
const configCache = new Map<string, unknown>()

/**
 * 配置状态。
 */
const configState = reactive({
  appConfig: null as AppConfig | null,
  routeConfig: null as RouteConfigYaml | null,
  iconConfig: null as IconConfigYaml | null,
  isLoading: false,
  error: null as string | null
})

/**
 * 配置变化监听器列表。
 */
const listeners: ConfigChangeListener[] = []

/**
 * 读取预加载配置中的指定分段。
 * @param configType 配置分段名称
 * @returns 预加载配置值
 */
function getPreloadedConfigSection<T>(configType: 'app' | 'routes' | 'icons'): T | undefined {
  const preloadedConfig = getRuntimePreloadedConfig()
  const value = preloadedConfig?.[configType]
  if (!value) {
    return undefined
  }
  return value as T
}

/**
 * 判断当前是否处于 SaaS 预览模式。
 * @returns 是否为预览模式
 */
function isPreviewMode(): boolean {
  return Boolean(getRuntimePreviewContext())
}

/**
 * 读取 YAML 配置文件，可选使用内存缓存。
 * @param url 配置 URL
 * @param useCache 是否使用缓存
 * @returns 解析后的配置对象
 */
export async function loadYamlFromUrl<T>(url: string, useCache = true): Promise<T> {
  if (useCache && configCache.has(url)) {
    return configCache.get(url) as T
  }

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`加载配置失败：${url} -> ${response.status} ${response.statusText}`)
  }

  const yamlText = await response.text()
  const config = parse(yamlText) as T
  if (useCache) {
    configCache.set(url, config)
  }
  return config
}

/**
 * 清理配置缓存。
 * @param url 指定 URL；不传时清空全部缓存
 */
export function clearConfigCache(url?: string): void {
  if (url) {
    configCache.delete(url)
    return
  }
  configCache.clear()
}

/**
 * 在预览模式下校验预加载配置是否存在。
 * @param configType 配置分段名称
 */
function assertPreviewConfigExists(configType: 'app' | 'routes' | 'icons' | 'themes'): never {
  throw new Error(`预览模式缺少必需的预加载配置：${configType}`)
}

/**
 * 加载应用配置。
 * @param force 是否强制刷新
 * @returns 应用配置对象
 */
export async function loadAppConfig(force = false): Promise<AppConfig> {
  if (configState.appConfig && !force) {
    return configState.appConfig
  }

  try {
    configState.isLoading = true
    configState.error = null

    const preloadedAppConfig = getPreloadedConfigSection<AppConfig>('app')
    if (preloadedAppConfig) {
      configState.appConfig = preloadedAppConfig
      notifyListeners('app')
      return preloadedAppConfig
    }

    if (isPreviewMode()) {
      return assertPreviewConfigExists('app')
    }

    const configUrl = buildConfigUrl('app')
    configState.appConfig = await loadYamlFromUrl<AppConfig>(configUrl, !force)
    notifyListeners('app')
  } catch (error) {
    if (hasExternalConfigSource() || isPreviewMode()) {
      configState.error = error instanceof Error ? error.message : 'Unknown error'
      throw error
    }

    console.warn('加载应用配置失败，回退到默认配置：', error)
    configState.appConfig = { ...defaultAppConfig }
    configState.error = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    configState.isLoading = false
  }

  return configState.appConfig || defaultAppConfig
}

/**
 * 解析应用配置中的页面画布尺寸。
 * @param config 当前应用配置
 * @returns 已完成默认值兜底的页面尺寸
 */
export function resolveAppPageConfig(config?: AppConfig | null): RuntimePageConfig {
  const pageConfig = config?.app?.page
  const width = Number(pageConfig?.width)
  const height = Number(pageConfig?.height)
  const iconDefaultStrokeWidth = Number(pageConfig?.iconDefaultStrokeWidth)

  return {
    width: Number.isFinite(width) && width > 0 ? width : DEFAULT_PAGE_CONFIG.width,
    height: Number.isFinite(height) && height > 0 ? height : DEFAULT_PAGE_CONFIG.height,
    baseFontSize: normalizeBaseFontSize(pageConfig?.baseFontSize, DEFAULT_PAGE_CONFIG.baseFontSize),
    iconDefaultStrokeWidth: Number.isFinite(iconDefaultStrokeWidth) && iconDefaultStrokeWidth > 0
      ? iconDefaultStrokeWidth
      : DEFAULT_PAGE_CONFIG.iconDefaultStrokeWidth,
  }
}

/**
 * 将页面基础字号归一为 px 字符串。
 * @param value 原始字号
 * @param fallback 默认字号
 * @returns 可写入 CSS 变量的字号
 */
function normalizeBaseFontSize(value: unknown, fallback: string): string {
  const normalized = String(value || '').trim().toLowerCase()
  if (!normalized) {
    return fallback
  }
  const match = normalized.match(/^(\d+)(px)?$/)
  if (!match) {
    return fallback
  }
  const numericValue = Number.parseInt(match[1], 10)
  if (!Number.isFinite(numericValue) || numericValue < 1 || numericValue > 200) {
    return fallback
  }
  return `${numericValue}px`
}

/**
 * 加载路由配置。
 * @param force 是否强制刷新
 * @returns 路由配置对象
 */
export async function loadRouteConfig(force = false): Promise<RouteConfigYaml> {
  if (configState.routeConfig && !force) {
    return configState.routeConfig
  }

  try {
    configState.isLoading = true
    configState.error = null

    const preloadedRouteConfig = getPreloadedConfigSection<RouteConfigYaml>('routes')
    if (preloadedRouteConfig) {
      configState.routeConfig = preloadedRouteConfig
      notifyListeners('routes')
      return preloadedRouteConfig
    }

    if (isPreviewMode()) {
      return assertPreviewConfigExists('routes')
    }

    const configUrl = buildConfigUrl('routes')
    configState.routeConfig = await loadYamlFromUrl<RouteConfigYaml>(configUrl, !force)
    notifyListeners('routes')
  } catch (error) {
    if (hasExternalConfigSource() || isPreviewMode()) {
      configState.error = error instanceof Error ? error.message : 'Unknown error'
      throw error
    }

    console.warn('加载路由配置失败，回退到空路由：', error)
    configState.routeConfig = { routes: [] }
    configState.error = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    configState.isLoading = false
  }

  return configState.routeConfig || { routes: [] }
}

/**
 * 加载图标配置。
 * @param force 是否强制刷新
 * @returns 图标配置对象
 */
export async function loadIconConfig(force = false): Promise<IconConfigYaml> {
  if (configState.iconConfig && !force) {
    return configState.iconConfig
  }

  try {
    configState.isLoading = true
    configState.error = null

    const preloadedIconConfig = getPreloadedConfigSection<IconConfigYaml>('icons')
    if (preloadedIconConfig) {
      configState.iconConfig = preloadedIconConfig
      notifyListeners('icons')
      return preloadedIconConfig
    }

    if (isPreviewMode()) {
      return assertPreviewConfigExists('icons')
    }

    const configUrl = buildConfigUrl('icons')
    configState.iconConfig = await loadYamlFromUrl<IconConfigYaml>(configUrl, !force)
    notifyListeners('icons')
  } catch (error) {
    if (hasExternalConfigSource() || isPreviewMode()) {
      configState.error = error instanceof Error ? error.message : 'Unknown error'
      throw error
    }

    console.warn('加载图标配置失败，回退到默认图标配置：', error)
    configState.iconConfig = { ...defaultIconConfig }
    configState.error = error instanceof Error ? error.message : 'Unknown error'
  } finally {
    configState.isLoading = false
  }

  return configState.iconConfig || defaultIconConfig
}

/**
 * 计算默认重定向路径。
 * @returns 默认首页路由；无可用路由时返回空串
 */
function getDefaultRedirectPath(): string {
  if (!configState.routeConfig?.routes) {
    return ''
  }

  const sortedRoutes = [...configState.routeConfig.routes]
    .filter(route => !route.meta.hidden)
    .sort((a, b) => a.meta.order - b.meta.order)

  return String(sortedRoutes[0]?.route || '').trim()
}

/**
 * 生成默认路由记录。
 * @returns 默认路由列表
 */
function getDefaultRouteRecords(): RouteRecordRaw[] {
  const defaultRedirectPath = getDefaultRedirectPath()
  const routeRecords: RouteRecordRaw[] = []

  // 仅在存在可见业务路由时生成首页重定向，避免构建态误跳到本地 demo 路径。
  if (defaultRedirectPath) {
    routeRecords.push({
      path: '',
      redirect: defaultRedirectPath,
    } as RouteRecordRaw)
  }

  routeRecords.push({
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: createViewModuleLoader('@/runtime-shell/fallback/NotFoundPage.vue'),
      meta: {
        title: '页面未找到',
        hidden: true
      }
    } as RouteRecordRaw)

  return routeRecords
}

/**
 * 计算并分配页码。
 * @param yamlRoutes YAML 路由配置
 * @returns 带页码的路由配置副本
 */
function calculatePageNumbers(yamlRoutes: RouteConfigYaml['routes']): RouteConfigYaml['routes'] {
  const routes = JSON.parse(JSON.stringify(yamlRoutes)) as RouteConfigYaml['routes']
  routes.sort(sortRoutesByOrder)

  let currentPageNumber = 1
  routes.forEach((route) => {
    const hasChildren = Array.isArray(route.children) && route.children.length > 0

    if (!hasChildren && !route.meta?.hidden) {
      route.meta.pageNumber = currentPageNumber
      currentPageNumber += 1
    }

    if (hasChildren && route.children) {
      route.children.sort(sortRoutesByOrder)
      route.children.forEach((child) => {
        if (!child.meta?.hidden) {
          child.meta.pageNumber = currentPageNumber
          currentPageNumber += 1
        }
      })
    }
  })

  return routes
}

/**
 * 按路由 meta.order 升序排列，未配置时按 0 处理。
 * @param left 左侧路由配置
 * @param right 右侧路由配置
 * @returns 排序结果
 */
function sortRoutesByOrder<T extends { meta: { order: number } }>(left: T, right: T): number {
  return (left.meta.order || 0) - (right.meta.order || 0)
}

/**
 * 将 YAML 路由配置转换为运行时路由配置。
 * @param yamlRoutes YAML 路由配置
 * @returns RouteConfig 数组
 */
function convertYamlRoutesToRouteConfig(yamlRoutes: RouteConfigYaml['routes']): RouteConfig[] {
  const routesWithPageNumbers = calculatePageNumbers(yamlRoutes)
  const defaultTransition = resolvePageTransition(configState.routeConfig?.transitionDefaults)

  return routesWithPageNumbers.map(route => {
    const hasChildren = route.children && route.children.length > 0

    const routeConfig: RouteConfig = {
      path: route.route,
      title: route.meta.title,
      name: route.route,
      order: route.meta.order,
      pageNumber: route.meta.pageNumber,
      component: createViewModuleLoader(route.component || '@/runtime-shell/fallback/NotFoundPage.vue'),
      meta: {
        ...route.meta,
        transition: hasChildren ? undefined : resolvePageTransition(route.meta.transition, defaultTransition),
        componentPath: route.component
      }
    }

    if (hasChildren) {
      routeConfig.children = route.children!.map(child => ({
        path: child.route,
        title: child.meta?.title || child.route,
        name: `${route.route}-${child.route}`,
        order: child.meta.order,
        pageNumber: child.meta.pageNumber,
        component: createViewModuleLoader(child.component || '@/runtime-shell/fallback/NotFoundPage.vue'),
        meta: {
          ...child.meta,
          transition: resolvePageTransition(child.meta.transition, defaultTransition),
          parent: route.route,
          componentPath: child.component
        }
      }))
    }

    return routeConfig
  })
}

/**
 * 获取当前已转换的路由配置。
 * @returns RouteConfig 数组
 */
function getCurrentRouteConfigs(): RouteConfig[] {
  if (!configState.routeConfig?.routes) {
    return []
  }

  return convertYamlRoutesToRouteConfig(configState.routeConfig.routes)
}

/**
 * 响应式应用配置。
 */
export const appConfig = computed(() => configState.appConfig || defaultAppConfig)

/**
 * 响应式页面画布尺寸配置。
 */
export const appPageConfig = computed(() => resolveAppPageConfig(appConfig.value))

/**
 * 响应式路由配置数组。
 */
export const routeConfigs = computed(() => getCurrentRouteConfigs())

/**
 * 响应式默认路由配置。
 */
export const defaultRouteConfig = computed(() => getDefaultRouteRecords())

/**
 * 响应式图标配置。
 */
export const iconConfig = computed(() => configState.iconConfig || defaultIconConfig)

/**
 * 添加配置变化监听器。
 * @param listener 监听器函数
 */
export function addChangeListener(listener: ConfigChangeListener): void {
  listeners.push(listener)
}

/**
 * 移除配置变化监听器。
 * @param listener 监听器函数
 */
export function removeChangeListener(listener: ConfigChangeListener): void {
  const index = listeners.indexOf(listener)
  if (index >= 0) {
    listeners.splice(index, 1)
  }
}

/**
 * 通知配置监听器。
 * @param configType 变更的配置分段
 */
function notifyListeners(configType: 'app' | 'routes' | 'icons'): void {
  listeners.forEach(listener => {
    try {
      listener(configType)
    } catch (error) {
      console.error('配置监听器执行失败：', error)
    }
  })
}

/**
 * 异步获取路由配置数组。
 * @returns RouteConfig 数组
 */
export async function getRouteConfigsAsync(): Promise<RouteConfig[]> {
  await loadRouteConfig()
  return getCurrentRouteConfigs()
}

/**
 * 异步获取默认路由记录。
 * @returns RouteRecordRaw 数组
 */
export async function getDefaultRouteConfigAsync(): Promise<RouteRecordRaw[]> {
  await loadRouteConfig()
  return getDefaultRouteRecords()
}

/**
 * 初始化配置系统。
 */
export async function initializeConfig(): Promise<void> {
  await Promise.all([
    loadAppConfig(),
    loadRouteConfig(),
    loadIconConfig()
  ])
}

/**
 * 重新加载全部配置。
 */
export async function reloadAllConfigs(): Promise<void> {
  clearConfigCache()
  configState.appConfig = null
  configState.routeConfig = null
  configState.iconConfig = null

  await Promise.all([
    loadAppConfig(true),
    loadRouteConfig(true),
    loadIconConfig(true)
  ])
}

/**
 * 异步获取图标配置。
 * @returns 图标配置对象
 */
export async function getIconConfigAsync(): Promise<IconConfigYaml> {
  return loadIconConfig()
}
