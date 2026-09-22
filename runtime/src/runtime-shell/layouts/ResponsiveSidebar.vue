<!-- 文件用途：响应式侧边导航栏，负责应用标题、目录折叠与悬浮菜单（纯文本导航模式）。 -->
<template>
  <div class="relative z-[100]">
    <aside
      class="relative h-screen bg-white border-r border-gray-200 flex flex-col transition-all duration-300 ease-in-out z-[999] shadow-md"
      :class="isCollapsed ? 'w-16' : 'w-[280px]'">
      <div class="p-6 px-4 border-b border-gray-200 flex items-center justify-between h-[60px] bg-gray-50">
        <div class="flex-1 min-w-0 flex items-center justify-center">
          <transition name="logo-fade" mode="out-in">
            <div v-if="!isCollapsed" key="title" class="flex min-w-0 max-w-full items-center justify-center gap-3">
              <AppBrandIcon v-if="appConfig.icon" :name="appConfig.icon" :alt="appConfig.title" class="flex-shrink-0 transition-all duration-200" :size="24" />
              <h1 class="min-w-0 max-w-full truncate text-[22px] font-bold leading-tight text-gray-900 m-0 text-center" :title="appConfig.title">{{ appConfig.title }}</h1>
            </div>
            <div
v-else key="icon"
              class="w-10 h-10 bg-slate-50 rounded-xl flex items-center justify-center font-bold text-[20px] cursor-pointer transition-all duration-200 shadow-sm border border-slate-200 hover:scale-105 hover:bg-slate-100 hover:shadow-md hover:border-slate-300"
              :class="appConfig.icon ? '' : 'text-blue-500 hover:text-blue-600'" :title="appConfig.title">
              <AppBrandIcon v-if="appConfig.icon" :name="appConfig.icon" :alt="appConfig.title" :size="20" />
              <span v-else>{{ appConfig.title.charAt(0).toUpperCase() }}</span>
            </div>
          </transition>
        </div>
        <button
          class="bg-transparent border-none cursor-pointer p-2 rounded-lg text-gray-500 transition-all duration-200 flex items-center justify-center hover:text-gray-700 hover:scale-110"
          :title="isCollapsed ? '展开侧边栏' : '收起侧边栏'" @click="toggleCollapse">
          <ChevronLeft :size="20" :class="isCollapsed ? 'rotate-180' : ''" class="transition-transform duration-300" />
        </button>
      </div>

      <nav class="flex-1 overflow-hidden">
        <div class="h-full overflow-y-auto overflow-x-hidden p-4 py-2 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent" :class="isCollapsed ? 'scrollbar-none' : ''">
          <ul class="list-none m-0 p-0">
            <li v-for="item in navigationItems" :key="item.path" class="mb-1">
              <div v-if="item.children && item.children.length > 0" class="relative transition-all duration-300">
                <div class="relative" @mouseenter="isCollapsed ? showHoverMenu(item.path, $event) : null" @mouseleave="isCollapsed ? hideHoverMenu() : null">
                  <div
                    class="flex items-center text-gray-500 no-underline rounded-xl transition-all duration-200 relative cursor-pointer py-3 px-4 font-medium"
                    :class="[
                      isCollapsed ? 'justify-center mx-2' : 'mx-1',
                      isActiveRoute(item.path)
                        ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/50 hover:bg-blue-600 hover:text-white' + (isCollapsed ? '' : ' hover:translate-x-1')
                        : hasActiveChildRoute(item)
                          ? 'bg-blue-50 text-blue-700 border border-blue-200 shadow-sm hover:bg-blue-50 hover:text-blue-800' + (isCollapsed ? '' : ' hover:translate-x-1')
                          : 'hover:bg-gray-100 hover:text-gray-700' + (isCollapsed ? ' hover:scale-110' : ' hover:translate-x-1')
                    ]" @click="handleNavClick(item)">
                    <div v-if="isCollapsed" class="flex items-center justify-center font-bold text-[16px] w-5 h-5">{{ item.title.charAt(0).toUpperCase() }}</div>
                    <span v-if="!isCollapsed" class="flex-1 whitespace-nowrap overflow-hidden text-ellipsis">{{ item.title }}</span>
                    <ChevronDown v-if="!isCollapsed && item.children.length > 0" class="ml-auto transition-transform duration-300 flex-shrink-0" :class="isMenuExpanded(item.path) ? 'rotate-180' : ''" :size="16" />
                  </div>

                  <Teleport to="body">
                    <div v-if="isCollapsed && hoverMenuVisible === item.path" class="pointer-events-auto animate-[hoverMenuFadeIn_0.2s_ease-out]" :style="{ position: 'fixed', top: hoverMenuPosition.top + 'px', left: hoverMenuPosition.left + 'px', zIndex: 9999 }" @mouseenter="keepHoverMenu" @mouseleave="hideHoverMenu">
                      <div class="bg-white border border-gray-200 rounded-xl shadow-xl p-4 min-w-[200px] max-w-[280px]">
                        <div class="font-semibold text-gray-900 mb-3 pb-2 border-b border-gray-200">{{ item.title }}</div>
                        <ul class="list-none m-0 p-0">
                          <li v-for="child in item.children" :key="child.path">
                            <router-link :to="child.path" class="flex items-center py-2 px-3 text-gray-500 no-underline rounded-lg transition-all duration-200 text-[14px] hover:bg-gray-100 hover:text-gray-700" :class="isActiveRoute(child.path) ? 'bg-blue-500 text-white hover:bg-blue-600 hover:text-white' : ''">{{ child.title }}</router-link>
                          </li>
                        </ul>
                      </div>
                    </div>
                  </Teleport>
                </div>

                <transition name="submenu-slide">
                  <ul v-if="isMenuExpanded(item.path) && !isCollapsed" class="list-none mt-2 mb-0 mx-0 py-0 rounded-xl overflow-hidden bg-gray-50 p-1">
                    <li v-for="child in item.children" :key="child.path" class="m-0">
                      <router-link :to="child.path" class="flex items-center py-2 px-4 pl-8 mx-2 my-0.5 text-gray-500 no-underline rounded-lg text-[14px] transition-all duration-200 hover:bg-gray-200 hover:translate-x-1 hover:shadow-sm" :class="isActiveRoute(child.path) ? 'bg-blue-500 text-white shadow-md shadow-blue-500/30 hover:bg-blue-600 hover:text-white hover:translate-x-1' : ''">
                        <span class="flex-1 whitespace-nowrap overflow-hidden text-ellipsis">{{ child.title }}</span>
                      </router-link>
                    </li>
                  </ul>
                </transition>
              </div>

              <div v-else @mouseenter="isCollapsed ? showSimpleTooltip(item.title, $event) : null" @mouseleave="isCollapsed ? hideSimpleTooltip() : null">
                <router-link :to="item.path" class="flex items-center text-gray-500 no-underline rounded-xl transition-all duration-200 relative mx-1 font-medium py-3 px-4" :class="[isCollapsed ? 'justify-center mx-2' : '', isActiveRoute(item.path) ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/50 hover:bg-blue-600 hover:text-white' + (isCollapsed ? '' : ' hover:translate-x-1') : 'hover:bg-gray-100 hover:text-gray-700' + (isCollapsed ? ' hover:scale-110' : ' hover:translate-x-1')]">
                  <div v-if="isCollapsed" class="flex items-center justify-center font-bold text-[16px] w-5 h-5" :class="isActiveRoute(item.path) ? 'text-white' : 'text-gray-500'">{{ item.title.charAt(0).toUpperCase() }}</div>
                  <span v-if="!isCollapsed" class="flex-1 whitespace-nowrap overflow-hidden text-ellipsis">{{ item.title }}</span>
                </router-link>
              </div>
            </li>
          </ul>
        </div>
      </nav>
    </aside>

    <Teleport to="body">
      <div v-if="simpleTooltipVisible && simpleTooltipText" class="pointer-events-none animate-[tooltipFadeIn_0.2s_cubic-bezier(0.4,0,0.2,1)]" :style="{ position: 'fixed', top: simpleTooltipPosition.top + 'px', left: simpleTooltipPosition.left + 'px', zIndex: 9999 }">
        <div class="bg-gray-800 text-white py-2 px-3 rounded-lg text-[14px] whitespace-nowrap shadow-lg border border-white/10 -translate-y-1/2 relative before:content-[''] before:absolute before:top-1/2 before:left-[-5px] before:-translate-y-1/2 before:w-0 before:h-0 before:border-[5px] before:border-solid before:border-transparent before:border-r-gray-800">{{ simpleTooltipText }}</div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronLeft, ChevronDown } from '@lucide/vue'
import type { MenuItem } from '@/core/types/menu'
import { isRouteActive, hasActiveChild } from '@/core/utils/route-generator'

import AppBrandIcon from '@/runtime-shell/layouts/AppBrandIcon.vue'

interface Props {
  navigationItems: MenuItem[]
  appConfig: {
    icon?: string
    title: string
    description?: string
  }
}

const props = defineProps<Props>()
const emit = defineEmits<{ (e: 'collapseChange', collapsed: boolean): void }>()

const route = useRoute()
const router = useRouter()

const isCollapsed = ref(false)
const expandedMenus = ref<Set<string>>(new Set())

const hoverMenuVisible = ref<string | null>(null)
const hoverMenuPosition = ref({ top: 0, left: 0 })
const hoverMenuTimer = ref<number | null>(null)

const simpleTooltipVisible = ref(false)
const simpleTooltipText = ref('')
const simpleTooltipPosition = ref({ top: 0, left: 0 })
const simpleTooltipTimer = ref<number | null>(null)

const toggleCollapse = (): void => {
  isCollapsed.value = !isCollapsed.value
  emit('collapseChange', isCollapsed.value)
}

const toggleMenuExpansion = (menuPath: string): void => {
  if (expandedMenus.value.has(menuPath)) {
    expandedMenus.value.delete(menuPath)
  } else {
    expandedMenus.value.add(menuPath)
  }
}

const isMenuExpanded = (menuPath: string): boolean => expandedMenus.value.has(menuPath)
const isActiveRoute = (path: string): boolean => isRouteActive(path, route.path)
const hasActiveChildRoute = (item: MenuItem): boolean => hasActiveChild(item, route.path)

const handleNavClick = (item: MenuItem): void => {
  if (item.children && item.children.length > 0) {
    const isExpanded = isMenuExpanded(item.path)
    if (!isCollapsed.value) toggleMenuExpansion(item.path)
    if (!isExpanded || isCollapsed.value) {
      const firstChild = item.children[0]
      if (firstChild) router.push(firstChild.path)
    }
  } else {
    router.push(item.path)
  }
}

const showHoverMenu = (itemPath: string, event: MouseEvent): void => {
  if (hoverMenuTimer.value) clearTimeout(hoverMenuTimer.value)
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const item = props.navigationItems.find(nav => nav.path === itemPath)
  const menuLeft = rect.right + 8
  const menuTop = rect.top
  const menuWidth = 200
  const viewportWidth = window.innerWidth
  let finalLeft = menuLeft
  if (menuLeft + menuWidth > viewportWidth) finalLeft = rect.left - menuWidth - 8
  const menuHeight = item?.children ? item.children.length * 40 + 60 : 100
  const viewportHeight = window.innerHeight
  let finalTop = menuTop
  if (menuTop + menuHeight > viewportHeight) finalTop = viewportHeight - menuHeight - 20
  hoverMenuPosition.value = { top: Math.max(20, finalTop), left: Math.max(20, finalLeft) }
  hoverMenuVisible.value = itemPath
}

const hideHoverMenu = (): void => {
  hoverMenuTimer.value = window.setTimeout(() => { hoverMenuVisible.value = null }, 100)
}

const keepHoverMenu = (): void => {
  if (hoverMenuTimer.value) {
    clearTimeout(hoverMenuTimer.value)
    hoverMenuTimer.value = null
  }
}

const showSimpleTooltip = (text: string, event: MouseEvent): void => {
  if (simpleTooltipTimer.value) clearTimeout(simpleTooltipTimer.value)
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const tooltipLeft = rect.right + 12
  const tooltipTop = rect.top + rect.height / 2
  const tooltipWidth = text.length * 8 + 24
  const viewportWidth = window.innerWidth
  let finalLeft = tooltipLeft
  if (tooltipLeft + tooltipWidth > viewportWidth) finalLeft = rect.left - tooltipWidth - 12
  const viewportHeight = window.innerHeight
  let finalTop = tooltipTop
  if (tooltipTop < 20) finalTop = 20
  else if (tooltipTop > viewportHeight - 40) finalTop = viewportHeight - 40
  simpleTooltipPosition.value = { top: finalTop, left: Math.max(12, finalLeft) }
  simpleTooltipText.value = text
  simpleTooltipVisible.value = true
}

const hideSimpleTooltip = (): void => {
  simpleTooltipTimer.value = window.setTimeout(() => {
    simpleTooltipVisible.value = false
    simpleTooltipText.value = ''
  }, 100)
}

const autoExpandCurrentRoute = (): void => {
  props.navigationItems.forEach(item => {
    if (hasActiveChild(item, route.path)) {
      expandedMenus.value.add(item.path)
    }
  })
}

watch(() => route.path, autoExpandCurrentRoute)
onMounted(autoExpandCurrentRoute)

onUnmounted(() => {
  if (hoverMenuTimer.value) clearTimeout(hoverMenuTimer.value)
  if (simpleTooltipTimer.value) clearTimeout(simpleTooltipTimer.value)
})
</script>

<style scoped>
.logo-fade-enter-active,
.logo-fade-leave-active { transition: all 0.3s ease; }
.logo-fade-enter-from { opacity: 0; transform: scale(0.8); }
.logo-fade-leave-to { opacity: 0; transform: scale(1.2); }

.submenu-slide-enter-active,
.submenu-slide-leave-active { transition: all 0.3s ease; overflow: hidden; }
.submenu-slide-enter-from,
.submenu-slide-leave-to { max-height: 0; opacity: 0; transform: translateY(-10px); }
.submenu-slide-enter-to,
.submenu-slide-leave-from { max-height: 500px; opacity: 1; transform: translateY(0); }

@keyframes hoverMenuFadeIn {
  from { opacity: 0; transform: translateY(-10px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes tooltipFadeIn {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}

.scrollbar-thin::-webkit-scrollbar { width: 4px; }
.scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 2px; }
.scrollbar-thin::-webkit-scrollbar-thumb:hover { background: #9ca3af; }
.scrollbar-none::-webkit-scrollbar { display: none; }
</style>
