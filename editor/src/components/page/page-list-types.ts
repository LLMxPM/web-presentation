// 文件功能：声明项目页面列表拆分组件共享的批量操作、卡片尺寸与路由页面条目类型。
import type { Component } from 'vue'

import type { PageItem } from '@/types/api'

export interface RoutedPageEntry {
  key: string
  page: PageItem
  routePath: string
  routeOrderKey: number[]
  duplicateIndex: number
  duplicateTotal: number
  isDuplicate: boolean
}

export type PageBatchScope = 'routed' | 'unrouted'
export type PageBatchAction = 'add-route' | 'remove-route' | 'screenshot' | 'archive' | 'copy'
export type PageCardSize = 'compact' | 'standard' | 'large' | 'huge'

export interface PageCardSizeOption {
  value: PageCardSize
  label: string
  minWidth: number
  icon: Component
}
