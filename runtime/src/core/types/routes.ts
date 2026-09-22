/**
 * 路由相关类型定义
 */
import type { RouteRecordRaw } from 'vue-router'
import type { PageTransitionConfig } from './page-transition'

// 基础路由配置接口（用于YAML配置）
export interface BaseRouteConfig {
  path: string
  title: string
  component?: () => Promise<unknown> // Vue 3 异步组件
  children?: BaseRouteConfig[]
  pageNumber?: number
  hidden?: boolean
  order?: number
  meta?: BaseRouteMeta
}

// 基础路由元信息接口
export interface BaseRouteMeta {
  transition?: PageTransitionConfig | null
  title?: string
  requiresAuth?: boolean
  hidden?: boolean
  parent?: string
  order?: number
  pageNumber?: number // 页码，表示在所有显示页面中的顺序
  speakerNotes?: string | null
  isIndex?: boolean
  hiddenInMenu?: boolean
  disabled?: boolean
}

// 扩展的路由记录类型
export type ExtendedRouteRecordRaw = RouteRecordRaw & {
  meta?: BaseRouteMeta
  children?: ExtendedRouteRecordRaw[]
}



