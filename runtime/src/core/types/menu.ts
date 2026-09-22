/**
 * 菜单相关类型定义
 */

/**
 * 菜单项接口
 */
export interface MenuItem {
  id: string
  title: string
  path: string
  order: number
  hidden: boolean
  disabled: boolean
  children?: MenuItem[]
  meta?: Record<string, unknown>
}



/**
 * 菜单组接口
 */
export interface MenuGroup {
  id: string
  title: string
  order: number
  items: MenuItem[]
  collapsed?: boolean
}

/**
 * 菜单配置接口
 */
export interface MenuConfig {
  groups?: MenuGroup[]
  items: MenuItem[]
  searchable?: boolean
  collapsible?: boolean
}


/**
 * 菜单状态接口
 */
export interface MenuState {
  activeItem: string | null
  expandedItems: Set<string>
  searchKeyword?: string
  searchResults?: MenuSearchResult[]
}

/**
 * 菜单搜索结果接口
 */
export interface MenuSearchResult {
  item: MenuItem
  matched: string[]
  score: number
}

/**
 * 菜单操作接口
 */
export interface MenuActions {
  setActiveItem: (itemId: string) => void
  toggleExpanded: (itemId: string) => void
  expandItem: (itemId: string) => void
  collapseItem: (itemId: string) => void
}

/**
 * 菜单事件类型
 */
export interface MenuEvents {
  itemClick: (item: MenuItem) => void
  itemExpand: (item: MenuItem) => void
  itemCollapse: (item: MenuItem) => void
}

/**
 * 菜单渲染选项
 */
export interface MenuRenderOptions {
  showBadge?: boolean
  maxDepth?: number
  itemHeight?: number
  virtualized?: boolean
}



