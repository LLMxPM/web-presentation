<!--
  文件用途说明：
  TableOfContents.vue 使用 Tailwind CSS 构建 PPT 风格目录组件，
  从路由配置自动生成目录列表，支持两列布局、页码显示以及点击跳转。
-->
<template>
  <div class="w-full h-full flex flex-col text-primary bg-transparent p-8 box-border" :style="containerStyles">
    <!-- 目录列表 -->
    <div class="min-h-0 h-full flex-1" :class="listLayoutClass">
      <div
v-for="(item, index) in displayItems" :key="item.id" class="relative m-0 flex items-center flex-1"
        :class="[itemPaddingClass, clickable ? 'group cursor-pointer transition-all duration-300 ease-in-out hover:translate-x-1' : '']"
        @click="handleItemClick(item)">
        <div
class="flex items-center transition-all duration-300 font-body w-full"
          :class="[contentGapClass, clickable ? 'group-hover:text-primary' : '']" :style="contentFontStyle">
          <!-- 序号 -->
          <span class="inline-flex items-center justify-end font-bold shrink-0 text-right" :style="numberStyle">{{
            formatNumber(index + 1) }}</span>

          <!-- 标题 -->
          <span class="break-words">{{ item.title }}</span>

          <!-- 连接线（虚线） -->
          <div v-if="showDots" class="flex-1 mx-2 h-px border-t border-dotted border-zinc-500 opacity-80"></div>

          <!-- 页码 -->
          <span
v-if="showPageNumbers"
            class="inline-flex items-center justify-center px-2 py-1 rounded shrink-0 text-secondary font-medium min-w-[2rem] text-center"
            :style="pageFontStyle">
            {{ getPageNumber(item, index) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, type CSSProperties } from 'vue'
import { useRouter } from 'vue-router'
import {
  getPageNumberByPath
} from '@/core/utils/route-generator'
import { routeConfigs } from '@/core/utils/config'

/**
 * 目录组件
 * 从路由配置中自动获取模块信息，生成目录列表
 */
defineOptions({
  name: 'TableOfContents'
})

/**
 * 目录项接口
 */
export interface TOCItem {
  id: string
  title: string
  path?: string
  pageNumber?: number | string
}

/**
 * 序号格式枚举
 */
export type NumberFormat = 'numeric' | 'chapter' | 'section' | 'custom'

/**
 * 组件属性定义
 */
interface Props {
  /** 序号格式：numeric(1,2,3) | chapter(第1章,第2章) | section(第1节,第2节) | custom */
  numberFormat?: NumberFormat
  /** 自定义序号格式模板，当numberFormat为custom时使用，{n}为序号占位符 */
  customFormat?: string
  /** 是否显示页码 */
  showPageNumbers?: boolean
  /** 手动模式：页码起始值（传入则启用手动页码模式） */
  pageStartNumber?: number
  /** 手动模式：每个目录项的页码映射（传入则启用手动页码模式） */
  pageNumbers?: (number | string)[]
  /** 自动模式：是否使用路由自动页码（默认true） */
  useAutoPageNumbers?: boolean
  /** 是否显示装饰点线 */
  showDots?: boolean
  /** 是否可点击跳转 */
  clickable?: boolean
  /** 是否启用两列布局 */
  twoColumn?: boolean
  /** 两列布局的分割点（当项目数量超过此值时启用两列） */
  columnBreakpoint?: number
  /** 自定义目录项，如果提供则不从路由配置获取 */
  customItems?: TOCItem[]
  /** 排除的路由名称数组 */
  excludeRoutes?: string[]
  /** 容器宽度 */
  width?: string | number
  /** 容器高度 */
  height?: string | number
  /** 内容字体大小 */
  contentFontSize?: string
  /** 是否自动调整字体大小 */
  autoFontSize?: boolean
  /** 序号字体大小 */
  numberFontSize?: string
  /** 页码字体大小 */
  pageFontSize?: string
}

const props = withDefaults(defineProps<Props>(), {
  numberFormat: 'numeric',
  customFormat: '第{n}项',
  showPageNumbers: true,
  useAutoPageNumbers: true,
  showDots: true,
  clickable: true,
  twoColumn: false,
  columnBreakpoint: 6,
  pageStartNumber: 1, // 添加默认值
  pageNumbers: undefined,
  customItems: undefined,
  excludeRoutes: () => ['home', 'contents', 'endpage'], // 默认排除首页、目录和末页
  width: '100%',
  height: '100%',
  contentFontSize: undefined,
  autoFontSize: true,
  numberFontSize: undefined,
  pageFontSize: undefined,
})

// 路由器实例
const router = useRouter()

/**
 * 从路由配置获取目录项（直接使用 route-generator.ts 的函数）
 */
const routeItems = computed((): TOCItem[] => {
  if (props.customItems) {
    return props.customItems
  }

  const items: TOCItem[] = []

  // 从 routeConfigs 中获取0级别路由作为章节
  routeConfigs.value.forEach(route => {
    // 检查是否在排除列表中
    if (props.excludeRoutes.includes(route.path) || props.excludeRoutes.includes(`/${route.path}`) || route.meta?.hidden) {
      return
    }

    // 如果有子路由（即该路由指向一个章节组合）
    const hasChildren = route.children && route.children.length > 0
    if (hasChildren) {
      // 找到第一个非隐藏的子路由页面
      const firstVisibleChild = route.children?.find(child => !child.meta?.hidden)

      if (firstVisibleChild) {
        items.push({
          id: route.name || route.title,
          title: route.title || route.meta?.title || route.name,
          path: `/${route.path}/${firstVisibleChild.path}`, // 完整路径
          pageNumber: firstVisibleChild.pageNumber || firstVisibleChild.meta?.pageNumber
        })
      }
    } else {
      // 没有子路由，直接作为独立页面显示
      items.push({
        id: route.name || route.title,
        title: route.title || route.meta?.title || route.name,
        path: `/${route.path}`,
        pageNumber: route.pageNumber || route.meta?.pageNumber
      })
    }
  })

  return items.sort((a, b) => {
    // 如果有页码，按页码排序；否则按字母顺序排序
    if (a.pageNumber && b.pageNumber) {
      return Number(a.pageNumber) - Number(b.pageNumber)
    }
    return a.title.localeCompare(b.title)
  })
})

/**
 * 显示的目录项
 */
const displayItems = computed(() => routeItems.value)

/**
 * 获取页码 - 简化版本，直接使用 route-generator 的函数
 */
const getPageNumber = (item: TOCItem, index: number): string => {
  // 1. 优先使用手动传入的页码数组
  if (props.pageNumbers && props.pageNumbers[index] !== undefined) {
    return props.pageNumbers[index].toString()
  }

  // 2. 使用目录项自带的页码（从路由配置中获取）
  if (item.pageNumber) {
    return item.pageNumber.toString()
  }

  // 3. 通过路径从 route-generator 获取页码
  if (item.path && props.useAutoPageNumbers) {
    const pageNumber = getPageNumberByPath(item.path)
    if (pageNumber) {
      return pageNumber.toString()
    }
  }

  // 4. 后备方案：使用起始页码递增
  return (props.pageStartNumber + index).toString()
}

/**
 * 计算字体大小（根据目录数量自动调整）
 */
const calculateFontSize = (baseSize: number, itemCount: number): string => {
  if (!props.autoFontSize) {
    return `${baseSize}px`
  }

  // 根据目录数量调整字体大小
  if (itemCount <= 5) {
    return `${baseSize}px`
  } else if (itemCount <= 10) {
    return `${Math.max(baseSize * 0.9, 14)}px`
  } else if (itemCount <= 15) {
    return `${Math.max(baseSize * 0.8, 12)}px`
  } else {
    return `${Math.max(baseSize * 0.7, 10)}px`
  }
}

/**
 * 容器样式
 */
const containerStyles = computed((): CSSProperties => {
  const styles: CSSProperties = {
    width: typeof props.width === 'number' ? `${props.width}px` : props.width,
    height: typeof props.height === 'number' ? `${props.height}px` : props.height,
  }
  return styles
})

/**
 * 计算列表布局的 Tailwind 类（单列/双列）
 * 当 twoColumn 为真且项目数量超过分割点时，使用双列网格布局，否则使用单列 Flex 布局。
 */
const listLayoutClass = computed(() => {
  const useTwoColumn = props.twoColumn && displayItems.value.length > props.columnBreakpoint
  return useTwoColumn ? 'grid grid-cols-2 gap-x-8' : 'flex flex-col justify-between'
})

/**
 * 紧凑模式等级：根据目录项数量动态调整间距
 * 0：默认（<=15） 1：中度紧凑（>=16） 2：高度紧凑（>=21）
 */
const compactLevel = computed(() => {
  const count = displayItems.value.length
  if (count >= 21) return 2
  if (count >= 16) return 1
  return 0
})

/**
 * 目录项的上下内边距类，根据紧凑等级调整
 */
const itemPaddingClass = computed(() => {
  return compactLevel.value === 2 ? 'py-0.5' : compactLevel.value === 1 ? 'py-1' : 'py-2'
})

/**
 * 内容区的左右间距（gap）类，根据紧凑等级调整
 */
const contentGapClass = computed(() => {
  return compactLevel.value === 2 ? 'gap-2' : compactLevel.value === 1 ? 'gap-3' : 'gap-4'
})



/**
 * 内容字体样式
 */
const contentFontStyle = computed((): CSSProperties => {
  const itemCount = displayItems.value.length
  const baseFontSize = props.contentFontSize ? parseInt(props.contentFontSize) : 50

  return {
    fontSize: props.contentFontSize || calculateFontSize(baseFontSize, itemCount)
  }
})

/**
 * 序号样式
 */
const numberStyle = computed((): CSSProperties => {
  const itemCount = displayItems.value.length
  const baseFontSize = props.numberFontSize ? parseInt(props.numberFontSize) : 50

  // 根据序号格式类型确定基础宽度
  let baseWidth: number
  switch (props.numberFormat) {
    case 'numeric':
      baseWidth = 60  // 数字格式：适中宽度
      break
    case 'chapter':
      baseWidth = 180 // 章节格式：较大宽度 (第1章)
      break
    case 'section':
      baseWidth = 180 // 节格式：较大宽度 (第1节)
      break
    case 'custom': {
      // 自定义格式：根据模板长度估算宽度
      const templateLength = props.customFormat.length
      baseWidth = Math.max(120, Math.min(templateLength * 38, 250))
      break
    }
    default:
      baseWidth = 180
  }

  // 根据目录项数量调整宽度（自动字体大小时）
  let finalWidth = baseWidth
  if (props.autoFontSize) {
    if (itemCount <= 5) {
      finalWidth = baseWidth
    } else if (itemCount <= 10) {
      finalWidth = Math.max(baseWidth * 0.9, baseWidth * 0.7)
    } else if (itemCount <= 15) {
      finalWidth = Math.max(baseWidth * 0.8, baseWidth * 0.6)
    } else {
      finalWidth = Math.max(baseWidth * 0.7, baseWidth * 0.5)
    }
  }

  return {
    width: `${finalWidth}px`,
    minWidth: `${Math.min(finalWidth, 40)}px`, // 设置最小宽度
    textAlign: 'right',
    fontSize: props.numberFontSize || calculateFontSize(baseFontSize, itemCount),
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexShrink: 0
  }
})

/**
 * 页码字体样式
 */
const pageFontStyle = computed((): CSSProperties => {
  const itemCount = displayItems.value.length
  const baseFontSize = props.pageFontSize ? parseInt(props.pageFontSize) : 40

  return {
    fontSize: props.pageFontSize || calculateFontSize(baseFontSize, itemCount)
  }
})

/**
 * 格式化序号
 */
const formatNumber = (num: number): string => {
  switch (props.numberFormat) {
    case 'chapter':
      return `第${num}章`
    case 'section':
      return `第${num}节`
    case 'custom':
      return props.customFormat.replace('{n}', num.toString())
    case 'numeric':
    default:
      return num.toString()
  }
}

/**
 * 处理目录项点击
 */
const handleItemClick = (item: TOCItem) => {
  if (!props.clickable || !item.path) {
    return
  }

  // 导航到目标路径
  router.push(item.path).catch(err => {
    console.warn('导航失败:', err)
  })
}

/**
 * 暴露给父组件的方法
 */
defineExpose({
  /**
   * 手动刷新目录项
   */
  refresh: () => {
    // 触发重新计算
    return routeItems.value
  },

  /**
   * 获取当前目录项
   */
  getItems: () => displayItems.value
})
</script>
