<!--
  文件用途：Runtime Kit 通用图标组件，仅支持静态资源图标展示，并支持静态 SVG 颜色配置。
-->
<template>
  <span
    v-bind="rootAttrs"
    class="app-icon inline-flex items-center justify-center"
    :class="[
      defaultSizeClass,
      externalClass,
      {
        'app-icon--static': isStaticIcon,
        'app-icon--disabled': props.disabled
      }
    ]"
    :style="rootStyle"
  >
    <!-- 静态 SVG 图标（内联渲染以支持颜色配置） -->
    <!-- eslint-disable vue/no-v-html -- SVG 来源于静态图标注册表，需内联渲染以支持颜色替换。 -->
    <span
      v-if="showStaticSvg"
      class="app-icon__static-svg"
      role="img"
      :aria-label="iconDescription || props.name || 'Icon'"
      v-html="coloredSvgContent"
    />
    <!-- eslint-enable vue/no-v-html -->

    <!-- 静态图标 -->
    <img
      v-else-if="showStaticImage"
      :src="staticIconSrc"
      :alt="iconDescription || props.name || 'Icon'"
      class="app-icon__static"
    />

    <!-- 回退显示 -->
    <span
      v-else-if="showFallback && props.fallback"
      class="app-icon-fallback text-xs"
    >
      {{ props.fallback }}
    </span>

    <!-- 默认回退（显示图标名称首字母） -->
    <span
      v-else-if="showFallback"
      class="app-icon-fallback text-xs"
    >
      {{ fallbackContent }}
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import { useIcon } from '@/core/composables/useIcon'
import { appConfig, appPageConfig } from '@/core/utils/config'
import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'
import { resolveColor } from '@runtime-kit/public/utils/colors.v1'

interface Props {
  /** 图标名称 */
  name?: string
  /**
   * 图标颜色
   * 支持以下格式：
   * - 直接颜色值：#ff0000, rgb(255,0,0), rgba(255,0,0,0.5)
   * - 主题颜色类：primary, secondary, accent1, accent2-500 等
   * - CSS 变量：var(--custom-color)
   */
  color?: string
  /** 是否禁用 */
  disabled?: boolean
  /** 自定义类名 */
  class?: string | string[] | Record<string, boolean>
  /** 线条宽度，仅对支持能力标记的内联静态 SVG 生效 */
  strokeWidth?: number
  /** 回退显示内容（当图标不存在时） */
  fallback?: string
}

defineOptions({
  inheritAttrs: false,
})

const props = withDefaults(defineProps<Props>(), {
  name: '',
  color: '',
  disabled: false,
  class: '',
  strokeWidth: undefined,
  fallback: '',
})
const attrs = useAttrs()

// 使用图标 composable
const {
  iconExists,
  isStaticIcon,
  isStaticSvg,
  staticIconSrc,
  iconDescription,
  staticSvgContent,
  supportsStrokeWidth,
} = useIcon(computed(() => props.name))

const { themeConfig } = useTheme()

const effectiveStrokeWidth = computed(() => {
  return props.strokeWidth ?? resolveDefaultIconStrokeWidth()
})

const externalClass = computed(() => [props.class, attrs.class])
const defaultSizeClass = computed(() => hasUnprefixedSizeClass(externalClass.value) ? '' : 'size-4')
const rootAttrs = computed(() => {
  const restAttrs = { ...attrs }
  delete restAttrs.class
  delete restAttrs.style
  delete restAttrs.size
  return restAttrs
})

// 计算解析后的颜色值
const resolvedColor = computed(() => {
  if (!props.color) return undefined

  // 使用颜色解析工具解析颜色
  return resolveColor(props.color)
})

// 计算图标样式
const iconStyle = computed(() => ({
  color: resolvedColor.value,
  opacity: props.disabled ? 0.5 : 1
}))
const rootStyle = computed(() => [iconStyle.value, attrs.style])

const showStaticSvg = computed(() => {
  return iconExists.value && isStaticSvg.value && Boolean(coloredSvgContent.value)
})

const showStaticImage = computed(() => {
  return iconExists.value && isStaticIcon.value && Boolean(staticIconSrc.value) && !showStaticSvg.value
})

const showFallback = computed(() => {
  return Boolean(props.name) && !showStaticSvg.value && !showStaticImage.value
})

const fallbackContent = computed(() => props.fallback || '?')

/**
 * 为静态 SVG 文本注入颜色与尺寸
 * 实现要点：
 * - 保留 fill="none" 与 fill/stroke="url(#...)"（渐变或引用）不做替换
 * - 将其它 fill/stroke 替换为 currentColor，并在根 svg 注入 style="color: <resolvedColor>"
 * - 去除根 svg 的 width/height，使其通过容器样式控制大小，或统一设置为 100%
 * @param svg 原始 SVG 文本
 * @param color 解析后的颜色值（可为 undefined）
 * @returns 处理后的 SVG 文本
 */
function colorizeSvg(svg: string, color?: string, strokeWidth?: number): string {
  if (!svg) return svg

  let s = svg

  // 1) 去除根 svg width/height 以便容器控制尺寸
  s = s.replace(/<svg([^>]*)>/i, (match, attrs) => {
    let newAttrs = attrs
      .replace(/\swidth=(["'])(.*?)\1/gi, '')
      .replace(/\sheight=(["'])(.*?)\1/gi, '')

    // 注入 width/height="100%" 保持自适应容器
    newAttrs = `${newAttrs} width="100%" height="100%"`

    if (color) {
      if (/style=(["'])(.*?)\1/i.test(newAttrs)) {
        newAttrs = newAttrs.replace(/style=(["'])(.*?)\1/i, (m, quote, val) => `style=${quote}${val};color:${color}${quote}`)
      } else {
        newAttrs = `${newAttrs} style="color:${color}"`
      }
    }
    return `<svg${newAttrs}>`
  })

  // 2) 将非 none/非 url(#...) 的 fill/stroke 替换为 currentColor
  s = s.replace(/fill=(["'])(.*?)\1/gi, (m, quote, val) => {
    const normalizedValue = String(val || '').trim().toLowerCase()
    if (normalizedValue === 'none' || /^url\(#/.test(normalizedValue)) return m
    return `fill=${quote}currentColor${quote}`
  })
  s = s.replace(/stroke=(["'])(.*?)\1/gi, (m, quote, val) => {
    const normalizedValue = String(val || '').trim().toLowerCase()
    if (normalizedValue === 'none' || /^url\(#/.test(normalizedValue)) return m
    return `stroke=${quote}currentColor${quote}`
  })

  if (typeof strokeWidth === 'number' && Number.isFinite(strokeWidth) && strokeWidth > 0) {
    s = injectStrokeWidth(s, strokeWidth)
  }

  return s
}

/**
 * 仅对显式声明了 stroke 的标签写入描边宽度，避免误改填充型或复杂 SVG。
 * @param svg 已完成着色处理的 SVG 文本
 * @param strokeWidth 目标描边宽度
 * @returns 注入描边宽度后的 SVG 文本
 */
function injectStrokeWidth(svg: string, strokeWidth: number): string {
  return svg.replace(/<([a-zA-Z][\w:-]*)([^<>]*?)(\s*\/?)>/g, (match, tagName, attrs, closingMark) => {
    if (tagName.startsWith('/')) {
      return match
    }
    if (!/\sstroke=(["'])(.*?)\1/i.test(attrs)) {
      return match
    }
    const strokeMatch = attrs.match(/\sstroke=(["'])(.*?)\1/i)
    const strokeValue = strokeMatch?.[2]?.trim().toLowerCase() || ''
    if (!strokeValue || strokeValue === 'none' || strokeValue.startsWith('url(#')) {
      return match
    }
    if (/\sstroke-width=(["'])(.*?)\1/i.test(attrs)) {
      return `<${tagName}${attrs.replace(/\sstroke-width=(["'])(.*?)\1/i, (_matched, quote) => ` stroke-width=${quote}${strokeWidth}${quote}`)}${closingMark}>`
    }
    return `<${tagName}${attrs} stroke-width="${strokeWidth}"${closingMark}>`
  })
}

// 计算：着色后的 SVG 文本
const coloredSvgContent = computed(() => {
  const svg = staticSvgContent.value || ''
  const strokeWidth = supportsStrokeWidth.value && typeof effectiveStrokeWidth.value === 'number'
    ? effectiveStrokeWidth.value
    : undefined
  return colorizeSvg(svg, resolvedColor.value, strokeWidth)
})

/**
 * 判断外部 class 是否已声明非响应式尺寸，避免默认 size-4 与调用方尺寸并存。
 * @param value Vue class 绑定值
 * @returns 是否存在 size-* 或 h-* / w-* 尺寸工具类
 */
function hasUnprefixedSizeClass(value: unknown): boolean {
  if (typeof value === 'string') {
    return value.split(/\s+/).some(isUnprefixedSizeClass)
  }
  if (Array.isArray(value)) {
    return value.some(hasUnprefixedSizeClass)
  }
  if (value && typeof value === 'object') {
    return Object.entries(value).some(([className, enabled]) => Boolean(enabled) && isUnprefixedSizeClass(className))
  }
  return false
}

/**
 * 判断单个 class token 是否为未带变体前缀的尺寸工具类。
 * @param className class 名称
 * @returns 是否为尺寸类
 */
function isUnprefixedSizeClass(className: string): boolean {
  return /^(size|h|w)-(\d+(?:\.\d+)?|\[[^\]]+\]|px|full|screen|fit|min|max|auto)$/.test(className)
}

/**
 * 解析项目级默认图标描边宽度，兼容旧主题配置中的图标规格。
 */
function resolveDefaultIconStrokeWidth(): number {
  const rawProjectValue = Number(appConfig.value.app.page?.iconDefaultStrokeWidth)
  if (Number.isFinite(rawProjectValue) && rawProjectValue > 0) {
    return appPageConfig.value.iconDefaultStrokeWidth
  }
  const legacyThemeValue = Number(themeConfig.value?.icon?.default_stroke_width)
  return Number.isFinite(legacyThemeValue) && legacyThemeValue > 0 ? legacyThemeValue : 2
}

</script>

<style scoped>
.app-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s ease;
}

.app-icon--static {
  /* 静态图标特定样式 */
}

.app-icon--disabled {
  /* 禁用状态样式 */
  cursor: not-allowed;
}

.app-icon__static {
  width: 100%;
  height: 100%;
  object-fit: contain;
  max-width: 100%;
  max-height: 100%;
}

.app-icon__static-svg {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}
.app-icon__static-svg :deep(svg) {
  width: 100%;
  height: 100%;
}

.app-icon-fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background-color: #e5e7eb;
  color: #6b7280;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
  flex-shrink: 0;
  min-width: 1em;
  min-height: 1em;
}
</style>
