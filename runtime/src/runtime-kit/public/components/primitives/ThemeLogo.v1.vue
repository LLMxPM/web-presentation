<!--
  文件用途：Runtime Kit 主题 Logo 渲染组件，按当前主题配置输出等比显示的 logo 或反色 logo 图片。
-->
<template>
  <img
    v-if="logoSrc"
    v-bind="imageAttrs"
    class="theme-logo"
    :class="externalClass"
    :src="logoSrc"
    :alt="resolvedAlt"
    :style="logoStyle"
  />
</template>

<script setup lang="ts">
import { computed, useAttrs, type CSSProperties, type StyleValue } from 'vue'

import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'

type LogoVariant = 'logo' | 'invert'

interface Props {
  /** 主题 Logo 类型：logo 为常规 Logo，invert 为反色 Logo */
  variant?: LogoVariant
  /** 图片替代文本；传入空字符串时按装饰图处理 */
  alt?: string
  /** Logo 高度刻度；数字与纯数字字符串按 Tailwind spacing 刻度解析，4 等于一个页面基础字号 */
  size?: number | string
}

defineOptions({
  name: 'ThemeLogo',
  inheritAttrs: false,
})

const props = withDefaults(defineProps<Props>(), {
  variant: 'logo',
  alt: undefined,
  size: 4,
})

const attrs = useAttrs()
const { themeLogo, themeInvertLogo } = useTheme()

const logoSrc = computed(() => {
  return props.variant === 'invert' ? themeInvertLogo.value : themeLogo.value
})

const resolvedAlt = computed(() => {
  if (props.alt !== undefined) {
    return props.alt
  }
  return props.variant === 'invert' ? '主题反色 Logo' : '主题 Logo'
})

const externalClass = computed(() => attrs.class)
const imageAttrs = computed(() => {
  const restAttrs = { ...attrs }
  delete restAttrs.class
  delete restAttrs.style
  return restAttrs
})

const baseLogoStyle = computed<CSSProperties>(() => ({
  width: 'auto',
  height: normalizeLogoSize(props.size),
  objectFit: 'contain',
}))

const logoStyle = computed<StyleValue>(() => [attrs.style, baseLogoStyle.value] as StyleValue)

/**
 * 将 Logo 尺寸转换成 CSS 高度。
 * @param value 尺寸配置；数字或纯数字字符串按 Tailwind spacing 刻度解析
 * @returns CSS 尺寸字符串
 */
function normalizeLogoSize(value: number | string | undefined): string {
  if (typeof value === 'number') {
    return Number.isFinite(value) && value > 0 ? buildSpacingSize(value) : buildSpacingSize(4)
  }
  const normalized = String(value || '').trim()
  if (!normalized) {
    return buildSpacingSize(4)
  }
  if (/^\d+(?:\.\d+)?$/.test(normalized)) {
    return buildSpacingSize(Number(normalized))
  }
  return normalized
}

/**
 * 按 Runtime Tailwind spacing 语义构造高度，保证跟随页面基础字号变化。
 * @param scale Tailwind spacing 刻度，4 等于一个页面基础字号
 * @returns CSS calc 表达式
 */
function buildSpacingSize(scale: number): string {
  return `calc(var(--tw-spacing-unit, calc(var(--tw-font-size-base, 24px) * 0.25)) * ${scale})`
}
</script>

<style scoped>
.theme-logo {
  display: inline-block;
  max-width: 100%;
  max-height: 100%;
  vertical-align: middle;
}
</style>
