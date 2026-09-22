/**
 * 菜单相关的组合式函数
 * 提供菜单状态管理和操作方法
 */

import {  computed, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { MenuItem, MenuConfig, MenuState } from '@/core/types/menu'
import { generateMenuConfig,  isRouteActive, hasActiveChild } from '@/core/utils/route-generator'
import { useTheme } from './useTheme'

/**
 * 菜单状态管理
 */
export function useMenu(config?: Partial<MenuConfig>) {
  const route = useRoute()
  const router = useRouter()
  
  // 获取主题相关的Logo路径
  const { themeLogo, themeInvertLogo } = useTheme()
  
  // 生成菜单配置 - 使用计算属性确保配置加载后自动更新
  const menuConfig = computed(() => {
    try {
      // console.log('useMenu - menuConfig computed 被调用')
      const baseConfig = generateMenuConfig()
      // console.log('useMenu - baseConfig:', baseConfig)
      const result = {
        ...baseConfig,
        ...config
      }
      // console.log('useMenu - menuConfig result:', result)
      return result
    } catch (error) {
      console.error('生成菜单配置时出错:', error)
      return {
        items: [],
        searchable: true,
        collapsible: true
      }
    }
  })
  
  // 菜单状态
  const menuState = reactive<MenuState>({
    activeItem: null,
    expandedItems: new Set<string>(),
    searchKeyword: '',
    searchResults: []
  })
  
  // 当前激活的菜单项
  const activeItem = computed(() => {
    const currentPath = route.path
    return findActiveMenuItem(menuConfig.value.items, currentPath)
  })
  
  
  
  /**
   * 查找激活的菜单�?   */
  function findActiveMenuItem(items: MenuItem[], currentPath: string): MenuItem | null {
    for (const item of items) {
      if (isRouteActive(item.path, currentPath)) {
        return item
      }
      if (item.children) {
        const found = findActiveMenuItem(item.children, currentPath)
        if (found) return found
      }
    }
    return null
  }
  
  /**
   * 设置激活的菜单�?   */
  function setActiveItem(itemId: string) {
    menuState.activeItem = itemId
  }
  
  /**
   * 切换菜单项展开状�?   */
  function toggleExpanded(itemId: string) {
    if (menuState.expandedItems.has(itemId)) {
      menuState.expandedItems.delete(itemId)
    } else {
      menuState.expandedItems.add(itemId)
    }
  }
  
  /**
   * 展开菜单�?   */
  function expandItem(itemId: string) {
    menuState.expandedItems.add(itemId)
  }
  
  /**
   * 收起菜单�?   */
  function collapseItem(itemId: string) {
    menuState.expandedItems.delete(itemId)
  }
  
  /**
   * 展开所有父级菜单项
   */
  function expandParents(itemId: string) {
    const item = findMenuItemById(menuConfig.value.items, itemId)
    if (item) {
      const parents = getMenuItemParents(menuConfig.value.items, itemId)
      parents.forEach(parent => expandItem(parent.id))
    }
  }
  
  /**
   * 根据ID查找菜单�?   */
  function findMenuItemById(items: MenuItem[], id: string): MenuItem | null {
    for (const item of items) {
      if (item.id === id) {
        return item
      }
      if (item.children) {
        const found = findMenuItemById(item.children, id)
        if (found) return found
      }
    }
    return null
  }
  
  /**
   * 获取菜单项的所有父级
   */
  function getMenuItemParents(items: MenuItem[], targetId: string, parents: MenuItem[] = []): MenuItem[] {
    for (const item of items) {
      if (item.id === targetId) {
        return parents
      }
      if (item.children) {
        const found = getMenuItemParents(item.children, targetId, [...parents, item])
        if (found.length > 0) return found
      }
    }
    return []
  }
  
  /**
   * 搜索菜单
   */
  function search(keyword: string) {
    menuState.searchKeyword = keyword
  }
  
  /**
   * 清除搜索
   */
  function clearSearch() {
    menuState.searchKeyword = ''
  }
  
  /**
   * 处理菜单项点�?   */
  function handleItemClick(item: MenuItem) {
    
    if (item.disabled) {
      return
    }
    
    // 如果有子菜单，切换展开状态
    if (item.children && item.children.length > 0) {
      toggleExpanded(item.id)
    } else {
      // 导航到目标路径
      router.push(item.path).then(() => {
        // console.log('路由导航成功，新路径:', router.currentRoute.value.path)
      }).catch((error) => {
        console.error('路由导航失败:', error)
      })
    }
    // console.log('=== useMenu handleItemClick 结束 ===')
  }
  
  /**
   * 检查菜单项是否展开
   */
  function isExpanded(itemId: string): boolean {
    return menuState.expandedItems.has(itemId)
  }
  
  /**
   * 检查菜单项是否激�?   */
  function isActive(item: MenuItem): boolean {
    const currentPath = route.path
    return isRouteActive(item.path, currentPath)
  }
  
  /**
   * 检查菜单项是否有激活的子项
   */
  function hasActiveChildren(item: MenuItem): boolean {
    const currentPath = route.path
    return hasActiveChild(item, currentPath)
  }
  
  /**
   * 获取当前主题的Logo路径
   * @returns 当前主题的Logo路径
   */
  function getCurrentThemeLogo(): string {
    return themeLogo.value
  }
  
  /**
   * 获取当前主题的反色Logo路径
   * @returns 当前主题的反色Logo路径
   */
  function getCurrentThemeInvertLogo(): string {
    return themeInvertLogo.value
  }
  
  // 监听路由变化，自动展开激活项的父路由
  watch(
    () => route.path,
    (newPath) => {
      const activeMenuItem = findActiveMenuItem(menuConfig.value.items, newPath)
      if (activeMenuItem) {
        expandParents(activeMenuItem.id)
      }
    },
    { immediate: true }
  )
  
  const result = {
    // 状态
    menuConfig,
    menuState,
    activeItem,
    
    // 方法
    setActiveItem,
    toggleExpanded,
    expandItem,
    collapseItem,
    expandParents,
    search,
    clearSearch,
    handleItemClick,
    isExpanded,
    isActive,
    hasActiveChildren,
    findMenuItemById,
    getMenuItemParents,
    
    // Logo相关方法
    getCurrentThemeLogo,
    getCurrentThemeInvertLogo
  }
  
  return result
}



