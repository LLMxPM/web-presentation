<!-- 文件功能：展示主题的视觉预览卡片，供主题库管理和选择器复用。 -->
<template>
  <div class="overflow-hidden border bg-white shadow-sm" :style="{
    borderColor: palette.border.default,
    backgroundColor: palette.background.default,
    color: palette.text.primary,
  }">
    <div class="px-3 py-2.5 transition-colors" :class="[
      (!collapsible || isExpanded) ? 'border-b' : '',
      collapsible ? 'cursor-pointer' : ''
    ]" :style="{
      borderColor: (!collapsible || isExpanded) ? palette.border.subtle : 'transparent',
      backgroundColor: collapsible && isHovered ? mixColor(palette.background.default, palette.background.invert, 0.02) : 'transparent'
    }" @click="toggleExpand" @mouseenter="isHovered = true" @mouseleave="isHovered = false">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="truncate text-sm font-bold" :style="headingStyle">{{ name }}</span>
            <code class="shrink-0 rounded-[2px] px-1.5 py-0.5 text-[10px]" :style="keyPillStyle">{{ key }}</code>
            <slot name="title-suffix" />
          </div>
          <p class="mt-1 line-clamp-1 text-[11px] opacity-75" :style="bodyStyle">{{ description }}</p>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <slot name="actions" />
          <div v-if="collapsible"
            class="ml-1 flex items-center justify-center rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
            @click.stop="isExpanded = !isExpanded">
            <component :is="isExpanded ? ChevronDown : ChevronRight" class="h-4 w-4" />
          </div>
        </div>
      </div>
    </div>

    <div v-show="!collapsible || isExpanded" class="space-y-2.5 px-3 py-3">
      <section class="border p-3" :style="surfaceCardStyle">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="text-[10px] font-bold uppercase tracking-[0.18em] opacity-55">页面组件示意</div>
            <div class="mt-1.5 text-[20px] font-bold leading-tight" :style="headingStyle">
              大标题：{{ headingFontLabel }}
            </div>
            <p class="mt-1 text-[11px] leading-5 opacity-90" :style="{ color: palette.text.secondary, ...bodyStyle }">
              正文{{ bodyFontLabel }}，展示字号 {{ baseFontSize }}
            </p>
            <p class="mt-1 text-[10px] leading-5 opacity-75" :style="{ color: palette.text.secondary, ...bodyStyle }">
              图标描边宽度 {{ iconDefaultStrokeWidth }}
            </p>
            <div class="mt-2 flex items-center gap-4">
              <div class="flex items-center gap-2">
                <div class="flex shrink-0 items-center justify-center rounded-lg border transition-all"
                  :style="projectIconFrameStyle">
                  <span v-if="showProjectIconSvg" class="app-preview-icon" :style="projectIconSvgStyle"
                    v-html="projectIconSvgMarkup" />
                  <img v-else-if="projectIconUrl" :src="projectIconUrl" alt="theme-project-icon"
                    class="object-contain transition-all" :style="projectIconImageStyle">
                  <span v-else class="font-semibold uppercase tracking-[0.08em] transition-all"
                    :style="projectIconFallbackStyle">
                    {{ projectIconInitial }}
                  </span>
                </div>
                <div class="min-w-0">
                  <div class="text-[10px] font-bold uppercase tracking-[0.18em] opacity-55">项目图标</div>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border"
                  :style="pageIconFrameStyle">
                  <span class="app-preview-icon" :style="pageDemoIconStyle" v-html="pageDemoIconSvg" />
                </div>
                <div class="min-w-0">
                  <div class="text-[10px] font-bold uppercase tracking-[0.18em] opacity-55">图标示例</div>
                </div>
              </div>

            </div>
          </div>
          <div class="flex h-10 w-24 shrink-0 items-center justify-center border px-2" :style="logoFrameStyle">
            <img v-if="logoUrl" :src="logoUrl" alt="theme-logo-light" class="h-6 max-w-[80px] object-contain">
            <span v-else class="text-[10px] font-semibold uppercase tracking-[0.14em] opacity-60">Logo</span>
          </div>
        </div>

        <div class="mt-3 flex flex-col gap-2.5">
          <article class="border px-3 py-2.5" :style="contentCardStyle">
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <div class="text-[10px] font-bold uppercase tracking-[0.18em] opacity-55">文本与交互</div>
                <p class="mt-1.5 text-[11px] leading-relaxed" :style="{ color: palette.text.primary, ...bodyStyle }">
                  正文提供核心阅读体验。右侧展示了
                  <span :style="{ color: palette.link.default, fontWeight: 600 }">链接</span>、
                  <span :style="{ color: palette.link.hover, fontWeight: 600 }">悬停</span>及
                  <span :style="{ color: palette.link.visited, fontWeight: 600 }">已访问</span>状态的区别。
                </p>
              </div>
              <div class="flex shrink-0 flex-col items-end gap-1.5 text-[10px] font-semibold mt-0.5">
                <button class="rounded-[2px] px-2 py-0.5" :style="primaryActionStyle">操作按钮</button>
                <span class="rounded-[2px] px-2 py-0.5" :style="inverseChipStyle">标签</span>
              </div>
            </div>
            <div class="mt-3 border-t pt-2" :style="{ borderColor: palette.border.subtle }">
              <code class="text-[10px]" :style="inlineCodeStyle">{{ codeFontLabel }} | key: {{ key }}</code>
            </div>
          </article>

          <aside class="flex flex-col justify-center border px-3 py-2.5" :style="inversePanelStyle">
            <div class="flex items-center justify-between gap-2">
              <div class="min-w-0">
                <div class="text-[10px] font-bold uppercase tracking-[0.18em]" :style="inverseMutedStyle">反色</div>
                <div class="mt-1 text-[13px] font-bold leading-snug"
                  :style="{ color: palette.text.invert, ...headingStyle }">
                  反色文字是这个颜色
                </div>
              </div>
              <div class="flex h-6 w-16 shrink-0 items-center justify-center border px-1"
                :style="inverseLogoFrameStyle">
                <img v-if="invertLogoUrl" :src="invertLogoUrl" alt="theme-logo-invert"
                  class="h-4 max-w-[48px] object-contain">
                <span v-else class="scale-[0.85] whitespace-nowrap text-[9px] font-semibold uppercase tracking-[0.1em]"
                  :style="inverseMutedStyle">反色 Logo</span>
              </div>
            </div>
          </aside>
        </div>
      </section>

      <section class="border px-3 py-2.5" :style="summaryCardStyle">
        <div class="text-[10px] font-bold uppercase tracking-[0.18em] opacity-55">主题强调色</div>

        <div class="mt-2 flex gap-1.5">
          <div v-for="(color, index) in palette.accent" :key="`${color}-${index}`"
            class="min-w-0 flex-1 flex flex-col items-center border p-1.5" :style="accentTokenStyle(color)">
            <div class="h-6 w-full rounded-[2px]" :style="{ backgroundColor: color }" />
            <div class="mt-1.5 text-[10px] font-mono font-medium tracking-tight" :style="{ color }">{{ color }}</div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'

import type { AssetAnalysisMetadata, ThemePalette } from '@/types/api'
import { isStrokeWidthEditable } from '@/utils/assetAnalysis'

const props = withDefaults(defineProps<{
  keyName: string
  name: string
  description: string | null
  palette: ThemePalette
  logoUrl?: string | null
  invertLogoUrl?: string | null
  projectIconUrl?: string | null
  projectIconName?: string | null
  projectIconAnalysis?: AssetAnalysisMetadata | null
  headingFontLabel: string
  bodyFontLabel: string
  codeFontLabel: string
  baseFontSize?: string
  iconDefaultStrokeWidth?: number
  collapsible?: boolean
  defaultExpanded?: boolean
}>(), {
  baseFontSize: '16px',
  iconDefaultStrokeWidth: 2,
  collapsible: false,
  defaultExpanded: true,
})

const isExpanded = ref(props.defaultExpanded)
const isHovered = ref(false)
const projectIconSvgContent = ref('')
const projectIconFetchToken = ref(0)
const PAGE_DEMO_ICON_TEMPLATE = `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14" stroke="#000" stroke-linecap="round"/><path d="M12 5l7 7-7 7" stroke="#000" stroke-linecap="round" stroke-linejoin="round"/></svg>`

watch(() => props.defaultExpanded, (newVal) => {
  isExpanded.value = newVal
})

watch(
  () => [props.projectIconUrl, props.projectIconName, props.projectIconAnalysis] as const,
  async ([nextProjectIconUrl, , nextProjectIconAnalysis]) => {
    projectIconSvgContent.value = ''
    const iconFormat = nextProjectIconAnalysis?.icon.format
    if (!nextProjectIconUrl || iconFormat !== 'svg') {
      return
    }

    const currentToken = projectIconFetchToken.value + 1
    projectIconFetchToken.value = currentToken
    try {
      const response = await fetch(nextProjectIconUrl)
      if (!response.ok) {
        return
      }
      const svgText = await response.text()
      if (projectIconFetchToken.value === currentToken) {
        projectIconSvgContent.value = svgText
      }
    } catch {
      if (projectIconFetchToken.value === currentToken) {
        projectIconSvgContent.value = ''
      }
    }
  },
  { immediate: true },
)

function toggleExpand() {
  if (props.collapsible) {
    isExpanded.value = !isExpanded.value
  }
}

const key = computed(() => props.keyName)
const palette = computed(() => props.palette)
const description = computed(() => props.description || '未填写主题说明')
const name = computed(() => props.name || '未命名主题')
const logoUrl = computed(() => props.logoUrl || '')
const invertLogoUrl = computed(() => props.invertLogoUrl || '')
const projectIconUrl = computed(() => props.projectIconUrl || '')
const projectIconName = computed(() => props.projectIconName || '未设置项目图标')
const projectIconInitial = computed(() => projectIconName.value.charAt(0).toUpperCase() || '?')
const projectIconSupportsStrokeWidth = computed(() => isStrokeWidthEditable(props.projectIconAnalysis))
const projectIconIsSvg = computed(() => props.projectIconAnalysis?.icon.format === 'svg')
const projectIconPreviewSize = computed(() => 24)
const projectIconFrameSize = computed(() => 42)
const normalizedPreviewStrokeWidth = computed(() => Math.max(1, Number(props.iconDefaultStrokeWidth) || 2))
const runtimeAlignedPageIconSize = computed(() => normalizeBaseFontPixelSize(props.baseFontSize, 16))
const pageIconFrameSize = computed(() => Math.max(40, runtimeAlignedPageIconSize.value + 16))
const projectIconSvgMarkup = computed(() => {
  if (!projectIconSvgContent.value) {
    return ''
  }
  return buildPreviewSvgMarkup(
    projectIconSvgContent.value,
    projectIconColor.value,
    projectIconSupportsStrokeWidth.value ? 2 : undefined,
  )
})
const showProjectIconSvg = computed(() => projectIconIsSvg.value && Boolean(projectIconSvgMarkup.value))
const pageDemoIconSvg = computed(() => buildPreviewSvgMarkup(
  PAGE_DEMO_ICON_TEMPLATE,
  undefined,
  normalizedPreviewStrokeWidth.value,
))
const projectIconColor = computed(() => '#2563eb')

const headingStyle = computed(() => ({
  fontFamily: props.headingFontLabel,
  fontSize: `calc(${props.baseFontSize} * 1.08)`,
}))

const bodyStyle = computed(() => ({
  fontFamily: props.bodyFontLabel,
  fontSize: props.baseFontSize,
}))

const codeStyle = computed(() => ({
  fontFamily: props.codeFontLabel,
}))



const keyPillStyle = computed(() => ({
  color: palette.value.text.invert,
  backgroundColor: mixColor(palette.value.background.default, palette.value.background.invert, 0.92),
  ...codeStyle.value,
}))

const surfaceCardStyle = computed(() => ({
  borderColor: palette.value.border.default,
  backgroundColor: palette.value.background.default,
}))

const contentCardStyle = computed(() => ({
  borderColor: palette.value.border.subtle,
  backgroundColor: mixColor(palette.value.background.default, palette.value.background.invert, 0.03),
}))

const inversePanelStyle = computed(() => ({
  borderColor: mixColor(palette.value.background.invert, '#ffffff', 0.18),
  backgroundColor: palette.value.background.invert,
}))

const logoFrameStyle = computed(() => ({
  borderColor: palette.value.border.subtle,
  backgroundColor: mixColor(palette.value.background.default, palette.value.background.invert, 0.04),
}))

const projectIconFrameStyle = computed(() => ({
  borderColor: palette.value.border.subtle,
  backgroundColor: '#ffffff',
  width: `${projectIconFrameSize.value}px`,
  height: `${projectIconFrameSize.value}px`,
  borderWidth: '1px',
}))

const projectIconImageStyle = computed(() => ({
  width: `${projectIconPreviewSize.value}px`,
  height: `${projectIconPreviewSize.value}px`,
}))

const projectIconSvgStyle = computed(() => ({
  width: `${projectIconPreviewSize.value}px`,
  height: `${projectIconPreviewSize.value}px`,
  color: projectIconColor.value,
}))

const projectIconFallbackStyle = computed(() => ({
  color: projectIconColor.value,
  fontSize: `${Math.max(9, Math.round(projectIconPreviewSize.value * 0.45))}px`,
}))

const pageIconFrameStyle = computed(() => ({
  borderColor: palette.value.border.subtle,
  backgroundColor: '#ffffff',
  width: `${pageIconFrameSize.value}px`,
  height: `${pageIconFrameSize.value}px`,
}))

const pageDemoIconStyle = computed(() => ({
  width: `${runtimeAlignedPageIconSize.value}px`,
  height: `${runtimeAlignedPageIconSize.value}px`,
}))

const inverseLogoFrameStyle = computed(() => ({
  borderColor: mixColor(palette.value.text.invert, palette.value.background.invert, 0.72),
  backgroundColor: mixColor(palette.value.background.invert, palette.value.background.default, 0.08),
}))

const inlineCodeStyle = computed(() => ({
  color: palette.value.text.primary,
  backgroundColor: mixColor(palette.value.background.default, palette.value.background.invert, 0.06),
  ...codeStyle.value,
}))


const inverseMutedStyle = computed(() => ({
  color: mixColor(palette.value.text.invert, palette.value.background.invert, 0.28),
}))

const inverseChipStyle = computed(() => ({
  color: palette.value.text.invert,
  backgroundColor: palette.value.accent[0] || palette.value.link.default,
}))

const primaryActionStyle = computed(() => ({
  color: palette.value.text.invert,
  backgroundColor: palette.value.link.default,
  fontFamily: props.bodyFontLabel,
}))

const summaryCardStyle = computed(() => ({
  borderColor: palette.value.border.subtle,
  backgroundColor: mixColor(palette.value.background.default, palette.value.background.invert, 0.02),
}))


/**
 * 生成强调色 token 的边框和背景样式，保持色板区轻量可读。
 * @param color 当前强调色
 */
function accentTokenStyle(color: string) {
  return {
    borderColor: mixColor(color, '#ffffff', 0.72),
    backgroundColor: mixColor(color, '#ffffff', 0.93),
  }
}

/**
 * 按比例混合两种 HEX 颜色，生成过渡色。
 * @param from 起始颜色
 * @param to 目标颜色
 * @param ratio 混合比例，0 表示保持起始色，1 表示完全目标色
 */
function mixColor(from: string, to: string, ratio: number): string {
  const fromRgb = parseHexColor(from)
  const toRgb = parseHexColor(to)
  if (!fromRgb || !toRgb) {
    return from
  }

  const clampRatio = Math.min(1, Math.max(0, ratio))
  const mixed = fromRgb.map((channel, index) => Math.round(channel + (toRgb[index] - channel) * clampRatio))
  return `#${mixed.map(channel => channel.toString(16).padStart(2, '0')).join('')}`
}

/**
 * 将 3/6 位 HEX 颜色解析为 RGB 数组，非法输入时返回 null。
 * @param value HEX 颜色文本
 */
function parseHexColor(value: string): number[] | null {
  const normalized = value.trim().replace('#', '')
  if (!/^[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(normalized)) {
    return null
  }
  const full = normalized.length === 3 ? normalized.split('').map(char => `${char}${char}`).join('') : normalized
  return [0, 1, 2].map(index => Number.parseInt(full.slice(index * 2, index * 2 + 2), 16))
}

/**
 * 将主题预览中的基础字号转换为图标示例尺寸，模拟 Runtime 默认跟随 baseFontSize。
 * @param value 基础字号文本
 * @param fallback 非法时的回退像素
 */
function normalizeBaseFontPixelSize(value: string | undefined, fallback: number): number {
  const match = String(value || '').trim().toLowerCase().match(/^(\d+)(px)?$/)
  if (!match) {
    return fallback
  }
  const parsedValue = Number.parseInt(match[1], 10)
  if (!Number.isFinite(parsedValue) || parsedValue < 1) {
    return fallback
  }
  return Math.round(parsedValue)
}

/**
 * 将预览用 SVG 规范化为可直接内联展示的 markup，并把描边宽度写入显式 stroke 元素。
 * @param svg 原始 SVG 文本
 * @param color 预览图标颜色
 * @param strokeWidth 当前展示描边宽度
 */
function buildPreviewSvgMarkup(svg: string, color?: string, strokeWidth?: number): string {
  if (!svg) {
    return ''
  }

  let normalizedSvg = svg.replace(/<svg([^>]*)>/i, (_matched: string, attrs: string) => {
    let nextAttrs = attrs
      .replace(/\swidth=(["'])(.*?)\1/gi, '')
      .replace(/\sheight=(["'])(.*?)\1/gi, '')
    if (color && /style=(["'])(.*?)\1/i.test(nextAttrs)) {
      nextAttrs = nextAttrs.replace(
        /style=(["'])(.*?)\1/i,
        (_styleMatched: string, quote: string, styleValue: string) => `style=${quote}${styleValue};color:${color}${quote}`,
      )
    } else if (color) {
      nextAttrs = `${nextAttrs} style="color:${color}"`
    }
    return `<svg${nextAttrs} width="100%" height="100%">`
  })

  normalizedSvg = normalizedSvg.replace(/stroke=(["'])(.*?)\1/gi, (match, quote, strokeValue) => {
    const normalizedStrokeValue = String(strokeValue || '').trim().toLowerCase()
    if (!normalizedStrokeValue || normalizedStrokeValue === 'none' || normalizedStrokeValue.startsWith('url(#')) {
      return match
    }
    return `stroke=${quote}currentColor${quote}`
  })

  normalizedSvg = normalizedSvg.replace(/fill=(["'])(.*?)\1/gi, (match, quote, fillValue) => {
    const normalizedFillValue = String(fillValue || '').trim().toLowerCase()
    if (!normalizedFillValue || normalizedFillValue === 'none' || normalizedFillValue.startsWith('url(#')) {
      return match
    }
    return `fill=${quote}currentColor${quote}`
  })

  normalizedSvg = normalizedSvg.replace(/<([a-zA-Z][\w:-]*)([^<>]*?)(\s*\/?)>/g, (match, tagName, attrs, closingMark) => {
    if (!/\sstroke=(["'])(.*?)\1/i.test(attrs)) {
      return match
    }
    const strokeMatch = attrs.match(/\sstroke=(["'])(.*?)\1/i)
    const strokeValue = strokeMatch?.[2]?.trim().toLowerCase() || ''
    if (!strokeValue || strokeValue === 'none' || strokeValue.startsWith('url(#')) {
      return match
    }
    if (/\sstroke-width=(["'])(.*?)\1/i.test(attrs)) {
      return `<${tagName}${attrs.replace(
        /\sstroke-width=(["'])(.*?)\1/i,
        (_strokeMatched: string, quote: string) => ` stroke-width=${quote}${strokeWidth}${quote}`,
      )}${closingMark}>`
    }
    return `<${tagName}${attrs} stroke-width="${strokeWidth}"${closingMark}>`
  })

  return normalizedSvg
}
</script>

<style scoped>
.app-preview-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.app-preview-icon :deep(svg) {
  width: 100%;
  height: 100%;
}
</style>
