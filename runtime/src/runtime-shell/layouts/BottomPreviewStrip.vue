<!--
  文件用途：提供独立的底部缩略图导航条，支持整条底栏收起、分组侧边标题和分组折叠。
-->

<template>
  <div class="h-full flex flex-col gap-2 min-h-0 relative" :class="{ 'justify-center items-center': collapsed }">
    <div class="relative h-6 w-full flex items-center justify-center shrink-0 px-14">
      <span
v-if="!collapsed && appTitle" class="absolute left-2 flex max-w-[calc(50%_-_3.5rem)] items-center gap-1.5 overflow-hidden text-xl font-bold text-slate-700"
        :title="appTitle">
        <AppBrandIcon v-if="appIcon" :name="appIcon" :alt="appTitle" :size="28" class="shrink-0" />
        <span class="min-w-0 truncate">{{ appTitle }}</span>
      </span>
      <button
type="button"
        class="self-center w-12 h-6 flex items-center justify-center border border-slate-200 rounded-full bg-slate-50 cursor-pointer shadow-sm transition-all duration-200 hover:bg-slate-100 hover:scale-105 hover:shadow-md z-10"
        :title="collapsed ? '展开底栏' : '收起底栏'" @click="toggleStripCollapsed">
        <ChevronDown
:size="16" class="text-slate-500 transition-transform duration-300"
          :class="{ 'rotate-180': !collapsed }" />
      </button>
    </div>

    <div v-if="!collapsed" class="flex-1 min-h-0 relative flex items-center w-full">
      <transition name="fade">
        <button
v-if="canScrollLeft"
          type="button"
          class="absolute left-0 top-1/2 -translate-y-1/2 z-30 bg-white/90 hover:bg-white backdrop-blur shadow-md rounded-full w-8 h-8 flex items-center justify-center -translate-x-3 transition-opacity"
          aria-label="向左滚动缩略图"
          @click.stop.prevent="scrollBy(-300)">
          <ChevronLeft :size="18" class="text-slate-600" />
        </button>
      </transition>

      <div
ref="scrollContainer"
        class="flex-1 h-full flex items-stretch gap-2.5 overflow-x-auto overflow-y-hidden scrollbar-none p-2"
        :class="hasHorizontalOverflow ? 'justify-start' : 'justify-center'"
        @scroll="handleScroll">
        <template v-for="section in previewSections" :key="section.id">
          <section
v-if="section.kind === 'group'"
            class="flex-none flex items-stretch gap-2 p-1.5 rounded-2xl transition-all duration-300"
            :class="[section.items.some(isActiveRoute) ? 'bg-blue-300/70' : 'bg-slate-200', isGroupCollapsed(section.id) ? '' : '']">
            <div
              class="w-6 py-2 h-full flex flex-col items-center justify-start rounded-xl cursor-pointer transition-colors overflow-hidden"
              :class="section.items.some(isActiveRoute) ? 'bg-blue-200/60 hover:bg-blue-300/70 text-blue-900' : 'bg-slate-200/80 hover:bg-slate-300 text-slate-800'"
              :title="isGroupCollapsed(section.id) ? `展开分组 ${section.title}` : `折叠分组 ${section.title}`"
              @click="toggleGroupCollapse(section.id)">
              <span class="text-xs font-bold tracking-wider vertical-text break-all">{{ section.title }}</span>
            </div>

            <div v-if="!isGroupCollapsed(section.id)" class="flex items-stretch gap-2">
              <PreviewThumbnail
                v-for="item in section.items"
                :key="item.path"
                :item="item"
                :active="isActiveRoute(item)"
                :page-config="resolvedPageConfig"
                fill-height
                class="flex-none h-full"
              />
            </div>
          </section>

          <PreviewThumbnail
            v-else
            :item="section.item"
            :active="isActiveRoute(section.item)"
            :page-config="resolvedPageConfig"
            fill-height
            class="flex-none h-full"
          />
        </template>
      </div>

      <transition name="fade">
        <button
v-if="canScrollRight"
          type="button"
          class="absolute right-0 top-1/2 -translate-y-1/2 z-30 bg-white/90 hover:bg-white backdrop-blur shadow-md rounded-full w-8 h-8 flex items-center justify-center translate-x-3 transition-opacity"
          aria-label="向右滚动缩略图"
          @click.stop.prevent="scrollBy(300)">
          <ChevronRight :size="18" class="text-slate-600" />
        </button>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { ChevronDown, ChevronLeft, ChevronRight } from '@lucide/vue'
import { useRoute } from 'vue-router'

import PreviewThumbnail from '@/runtime-shell/layouts/PreviewThumbnail.vue'
import AppBrandIcon from '@/runtime-shell/layouts/AppBrandIcon.vue'
import type { MenuItem } from '@/core/types/menu'
import { DEFAULT_PAGE_CONFIG } from '@/core/utils/config'
import { createRafResizeObserver } from '@/core/utils/resize-observer'
import { isRouteActive } from '@/core/utils/route-generator'

interface GroupSection {
  kind: 'group'
  id: string
  title: string
  items: MenuItem[]
}

interface ItemSection {
  kind: 'item'
  id: string
  item: MenuItem
}

type PreviewSection = GroupSection | ItemSection

/**
 * 组件属性。
 */
interface Props {
  navigationItems: MenuItem[]
  pageConfig?: {
    width?: number
    height?: number
  }
  appConfig?: {
    icon?: string
    title?: string
  }
  collapsed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  pageConfig: () => ({}),
  appConfig: () => ({}),
  collapsed: false,
})

const emit = defineEmits<{
  (e: 'collapsed-change', collapsed: boolean): void
}>()

const route = useRoute()
const collapsedGroupIds = ref<Set<string>>(new Set())

// 滚动相关
const scrollContainer = ref<HTMLElement | null>(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)
const hasHorizontalOverflow = ref(false)
let resizeObserver: ResizeObserver | null = null

const checkScroll = () => {
  if (!scrollContainer.value) return
  const { scrollLeft, scrollWidth, clientWidth } = scrollContainer.value
  hasHorizontalOverflow.value = scrollWidth > clientWidth + 1
  canScrollLeft.value = scrollLeft > 0
  canScrollRight.value = hasHorizontalOverflow.value && Math.ceil(scrollLeft + clientWidth) < scrollWidth
}

const handleScroll = () => {
  checkScroll()
}

const scrollBy = (offset: number) => {
  if (scrollContainer.value) {
    scrollContainer.value.scrollBy({ left: offset, behavior: 'smooth' })
  }
}

/**
 * 将当前激活缩略图滚动到可视区域中部。
 * @param behavior 滚动动画方式，路由切换使用 smooth，初始同步使用 auto
 */
const scrollActiveThumbnailIntoView = (behavior: ScrollBehavior): void => {
  if (!scrollContainer.value || props.collapsed) return

  const thumbnailElements = Array.from(
    scrollContainer.value.querySelectorAll<HTMLElement>('[data-preview-thumbnail-path]'),
  )
  const activeElement = thumbnailElements.find((element) => {
    const thumbnailPath = element.dataset.previewThumbnailPath
    return typeof thumbnailPath === 'string' && isRouteActive(thumbnailPath, route.path)
  })

  activeElement?.scrollIntoView({
    behavior,
    block: 'nearest',
    inline: 'center',
  })
}

/**
 * 等待 DOM 更新后同步滚动状态和当前缩略图位置。
 * @param behavior 当前缩略图居中使用的滚动动画方式
 */
const syncScrollState = (behavior: ScrollBehavior): void => {
  void nextTick(() => {
    checkScroll()
    scrollActiveThumbnailIntoView(behavior)
  })
}

onMounted(() => {
  if (scrollContainer.value) {
    resizeObserver = createRafResizeObserver(() => {
      checkScroll()
    })
    resizeObserver.observe(scrollContainer.value)
    syncScrollState('auto')
  }
})

onUnmounted(() => {
  if (resizeObserver && scrollContainer.value) {
    resizeObserver.unobserve(scrollContainer.value)
  }
})

watch(() => props.collapsed, (collapsed) => {
  if (collapsed) {
    void nextTick(checkScroll)
    return
  }
  syncScrollState('auto')
}, { flush: 'post' })

watch(() => props.navigationItems, () => {
  syncScrollState('auto')
}, { deep: true, flush: 'post' })

watch(() => route.path, () => {
  syncScrollState('smooth')
}, { flush: 'post' })

/**
 * 归一化底部缩略图分段。
 * @returns 有子页的目录渲染为分组；无子页的顶层页面直接渲染为独立缩略图
 */
const previewSections = computed<PreviewSection[]>(() => {
  return props.navigationItems.map((item) => {
    if (item.children && item.children.length > 0) {
      return {
        kind: 'group',
        id: item.id || item.path,
        title: item.title,
        items: item.children,
      } satisfies GroupSection
    }

    return {
      kind: 'item',
      id: item.id || item.path,
      item,
    } satisfies ItemSection
  })
})

/**
 * 底栏中展示的应用标题。
 * @returns 去除空白后的标题，缺失时不占位
 */
const appTitle = computed(() => props.appConfig?.title?.trim() || '')

/**
 * 底栏标题旁展示的项目图标名称。
 * @returns 去除空白后的图标名，缺失时不渲染图标
 */
const appIcon = computed(() => props.appConfig?.icon?.trim() || '')

/**
 * 当前缩略图使用的画布尺寸。
 * @returns 合法的宽高配置；缺失时回退到默认页面尺寸
 */
const resolvedPageConfig = computed(() => {
  const width = Number(props.pageConfig?.width)
  const height = Number(props.pageConfig?.height)

  return {
    width: Number.isFinite(width) && width > 0 ? width : DEFAULT_PAGE_CONFIG.width,
    height: Number.isFinite(height) && height > 0 ? height : DEFAULT_PAGE_CONFIG.height,
  }
})

/**
 * 判断指定分组是否已折叠。
 * @param groupId 分组标识
 * @returns 是否处于折叠态
 */
const isGroupCollapsed = (groupId: string): boolean => {
  return collapsedGroupIds.value.has(groupId)
}

/**
 * 切换整条底栏的展开状态。
 */
const toggleStripCollapsed = (): void => {
  emit('collapsed-change', !props.collapsed)
}

/**
 * 切换分组折叠状态。
 * @param groupId 分组标识
 */
const toggleGroupCollapse = (groupId: string): void => {
  if (collapsedGroupIds.value.has(groupId)) {
    collapsedGroupIds.value.delete(groupId)
  } else {
    collapsedGroupIds.value.add(groupId)
  }
  syncScrollState('auto')
}

/**
 * 判断目标项是否与当前路由匹配。
 * @param item 菜单项
 * @returns 是否处于激活态
 */
const isActiveRoute = (item: MenuItem): boolean => {
  return isRouteActive(item.path, route.path)
}

</script>

<style scoped>
/* 隐藏原生滚动条 */
.scrollbar-none::-webkit-scrollbar {
  display: none;
}

.scrollbar-none {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

/* 垂直排版文字 */
.vertical-text {
  writing-mode: vertical-rl;
  text-orientation: mixed;
}

/* 渐隐动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
