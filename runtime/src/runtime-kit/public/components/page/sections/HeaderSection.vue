<!--
  文件用途：默认页头区块，展示标题、副标题和右侧扩展内容。
-->

<template>
  <div class="flex items-center w-full text-primary" :class="[alignClass, { 'border-b border-border-subtle': showBottomBorder }]" :style="headerStyle">
    <!-- 标题内容区域 -->
    <div class="flex-1 flex flex-col gap-2" :class="contentAlignClass">
      <slot name="header">
        <!-- 主标题 -->
        <h1 v-if="title" class="font-heading font-bold leading-tight text-primary m-0" :style="titleStyle">{{ title }}</h1>
        <!-- 副标题 -->
        <h2 v-if="subtitle" class="font-heading font-medium leading-tight text-secondary m-0" :style="subtitleStyle">{{ subtitle }}</h2>
      </slot>
    </div>
    
    <!-- Logo区域 -->
    <div v-if="shouldShowLogo" class="flex items-center justify-center" :class="logoPositionClass">
      <ThemeLogo v-if="isThemeLogo" alt="Logo" :size="logoSize" />
      <img v-else :src="props.customLogoSrc" alt="Logo" class="object-contain" :style="customLogoStyle" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'
import ThemeLogo from '@runtime-kit/public/components/primitives/ThemeLogo.v1.vue'


/**
 * 标题区域组件
 * 提供可配置的标题、副标题、logo和对齐方式
 */
defineOptions({
  name: 'HeaderSection'
})

/**
 * 文字大小类型定义（字号，单位：px）
 */
type FontSize = number

/**
 * 对齐方式类型定义
 */
type AlignType = 'left' | 'center' | 'right'

/**
 * Logo配置类型定义
 */
type LogoConfig = 'theme' | 'custom' | 'none'

/**
 * Padding配置类型定义
 */
type PaddingConfig = number | {
  top?: number
  right?: number
  bottom?: number
  left?: number
}

/**
 * 组件属性定义
 */
interface Props {
  /** 主标题文字内容 */
  title?: string
  /** 副标题内容（可选） */
  subtitle?: string
  /** 主标题文字大小（字号，单位：px） */
  titleSize?: FontSize
  /** 副标题文字大小（字号，单位：px） */
  subtitleSize?: FontSize
  /** padding值（支持单独设置四边或统一设置） */
  padding?: PaddingConfig
  /** 是否显示底部横线 */
  showBottomBorder?: boolean
  /** logo配置选项 */
  logoConfig?: LogoConfig
  /** 自定义logo图片路径（当logoConfig为'custom'时使用） */
  customLogoSrc?: string
  /** 对齐方式 */
  align?: AlignType
  /** 标题区域高度 */
  height?: number
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  subtitle: '',
  titleSize: 40,
  subtitleSize: 24,
  padding: 20,
  showBottomBorder: true,
  logoConfig: 'theme',
  customLogoSrc: '',
  align: 'left',
  height: 100
})


// 使用主题系统
const { themeLogo } = useTheme()

/**
 * 计算是否应该显示logo
 */
const shouldShowLogo = computed(() => {
  if (props.logoConfig === 'none') {
    return false
  }
  if (props.logoConfig === 'custom') {
    return Boolean(props.customLogoSrc)
  }
  return Boolean(themeLogo.value)
})

/**
 * 判断是否使用主题 Logo 组件渲染。
 */
const isThemeLogo = computed(() => props.logoConfig === 'theme')

/**
 * 计算对齐样式类
 */
const alignClass = computed(() => {
  switch (props.align) {
    case 'center':
      return 'justify-center'
    case 'right':
      return 'justify-end'
    default:
      return 'justify-start'
  }
})

/**
 * 计算内容对齐样式类
 */
const contentAlignClass = computed(() => {
  switch (props.align) {
    case 'center':
      return 'text-center'
    case 'right':
      return 'text-right'
    default:
      return 'text-left'
  }
})

/**
 * 计算logo位置样式类
 * 右对齐时logo显示在左侧
 */
const logoPositionClass = computed(() => {
  return props.align === 'right' ? 'order-first mr-4' : 'ml-4'
})

/**
 * 转换字体大小为CSS值
 */
const convertFontSize = (size: FontSize): string => {
  return `${size}px`
}

/**
 * 转换padding配置为CSS值
 */
const convertPadding = (padding: PaddingConfig): string => {
  if (typeof padding === 'number') {
    return `${padding}px`
  }
  
  const { top = 0, right = 0, bottom = 0, left = 0 } = padding
  return `${top}px ${right}px ${bottom}px ${left}px`
}

/**
 * 计算标题样式
 */
const titleStyle = computed(() => ({
  fontSize: convertFontSize(props.titleSize)
}))

/**
 * 计算副标题样式
 */
const subtitleStyle = computed(() => ({
  fontSize: convertFontSize(props.subtitleSize)
}))

/**
 * 计算容器样式
 */
const headerStyle = computed(() => ({
  padding: convertPadding(props.padding),
  height: `${props.height}px`
}))

/**
 * 计算 Logo 高度。
 */
const logoSize = computed(() => {
  const logoHeight = Math.max(24, Math.min(120, props.height * 0.6))
  return `${logoHeight}px`
})

/**
 * 计算自定义 Logo 图片样式。
 */
const customLogoStyle = computed(() => {
  return {
    height: logoSize.value,
    width: 'auto'
  }
})
</script>

<style scoped>
/* 组件特定样式 */
</style>
