<!--
  文件用途：本地示例页，展示主题变量、色板和字体在页面中的读取与使用方式。
-->
<template>
  <ShowcasePage
    title="主题与配色"
    subtitle="主题色板通过 CSS 变量下发，页面只消费语义 token"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[1.15fr_0.85fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-5">
        <div class="mb-4 flex items-center gap-2">
          <Icon name="star" class="size-5 text-primary" />
          <h2 class="font-heading text-lg font-semibold text-primary">{{ themeName }}</h2>
          <span class="rounded-full bg-background px-2 py-0.5 font-code text-xs text-secondary">{{ themeClass }}</span>
          <span class="ml-auto font-body text-xs text-secondary">6 组强调色 · 每组 10 阶</span>
        </div>

        <div class="space-y-2">
          <div v-for="(accent, index) in accentRows" :key="accent.token" class="flex items-center gap-3">
            <span class="w-16 shrink-0 font-code text-xs text-primary">{{ accent.token }}</span>
            <div class="grid flex-1 grid-cols-6 gap-1">
              <div v-for="step in accentSteps" :key="step" class="flex flex-col gap-1">
                <span
                  class="h-7 rounded border border-border-subtle"
                  :style="{ backgroundColor: resolveColor(`${accent.token}-${step}`) }"
                />
                <span class="text-center font-code text-xs text-secondary">{{ step }}</span>
              </div>
            </div>
            <span class="w-20 shrink-0 text-right font-code text-xs text-secondary">{{ accent.hex }}</span>
          </div>
        </div>

        <h3 class="mb-2 mt-5 font-heading text-sm font-semibold text-primary">语义色</h3>
        <div class="grid grid-cols-2 gap-x-4 gap-y-2">
          <div v-for="group in semanticGroups" :key="group.label" class="flex items-center gap-2">
            <span class="w-14 shrink-0 font-body text-xs text-secondary">{{ group.label }}</span>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="token in group.tokens"
                :key="token"
                class="inline-flex items-center gap-1.5 rounded border border-border-subtle bg-default px-2 py-1"
              >
                <span class="size-2.5 rounded-full border border-border-subtle" :style="{ backgroundColor: resolveColor(token) }" />
                <span class="font-code text-xs text-primary">{{ token }}</span>
              </span>
            </div>
          </div>
        </div>

        <h3 class="mb-2 mt-5 font-heading text-sm font-semibold text-primary">字号刻度</h3>
        <div class="space-y-1">
          <div
            v-for="item in fontScale"
            :key="item.token"
            class="flex items-baseline justify-between gap-3 rounded-md bg-default px-3 py-1.5"
          >
            <span class="text-primary" :class="item.className">{{ item.label }}</span>
            <span class="font-code text-xs text-secondary">{{ item.token }}</span>
          </div>
        </div>
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">字体家族</h3>
          <div class="mt-3 space-y-2">
            <div v-for="font in fonts" :key="font.token" class="rounded-md bg-default px-4 py-3">
              <div class="flex items-center justify-between">
                <span class="font-body text-xs text-secondary">{{ font.label }}</span>
                <span class="font-code text-xs text-secondary">{{ font.token }}</span>
              </div>
              <p class="mt-1 text-lg text-primary" :class="font.className">{{ font.sample }}</p>
            </div>
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">resolveColor</h3>
          <p class="mt-1 font-body text-xs leading-6 text-secondary">
            需要把主题色写进 SVG、canvas 或内联样式时，用 resolveColor 解析 token，不要硬编码颜色值。
          </p>
          <div class="mt-3 flex flex-1 items-center justify-center rounded-md bg-default p-4">
            <svg viewBox="0 0 320 96" class="w-full" role="img" aria-label="使用主题强调色描边的折线">
              <path d="M8 88 H312" :stroke="resolveColor('border')" stroke-width="1" />
              <path
                d="M12 76 C60 76 68 30 112 40 S180 64 208 30 S268 20 308 12"
                fill="none"
                :stroke="resolveColor('accent3')"
                stroke-width="4"
                stroke-linecap="round"
              />
              <circle cx="308" cy="12" r="5" :fill="resolveColor('accent3')" />
            </svg>
          </div>
          <pre class="mt-3 overflow-auto rounded-md bg-default p-3 font-code text-xs leading-6 text-primary">const stroke = resolveColor('accent3')</pre>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'
import { resolveColor } from '@runtime-kit/public/utils/colors.v1'

const capabilities: ShowcaseCapability[] = [
  { name: 'useTheme.v1', path: '@runtime-kit/public/composables/theme/useTheme.v1' },
  { name: 'resolveColor.v1', path: '@runtime-kit/public/utils/colors.v1' },
]

const { themeConfig, themeClass } = useTheme()

const themeName = computed(() => themeConfig.value?.name || '当前主题')

/** 强调色色阶展示档位。 */
const accentSteps = [100, 300, 500, 700, 900]

/** 六组强调色的 token 与主题配置中的原始色值。 */
const accentRows = computed(() => (themeConfig.value?.palette.accent ?? []).map((hex, index) => ({
  token: `accent${index + 1}`,
  hex,
})))

/** 语义色分组；token 同时作为 resolveColor 的输入。 */
const semanticGroups = [
  { label: '文本', tokens: ['primary', 'secondary', 'invert'] },
  { label: '背景', tokens: ['background', 'background-invert'] },
  { label: '边框', tokens: ['border', 'border-subtle'] },
  { label: '链接', tokens: ['link', 'link-hover', 'link-visited'] },
]

const fonts = [
  { token: 'font-heading', label: '标题字体', className: 'font-heading font-semibold', sample: '让内容按节奏发生' },
  { token: 'font-body', label: '正文字体', className: 'font-body', sample: '正文承担解释、限定和上下文补充。' },
  { token: 'font-code', label: '等宽字体', className: 'font-code', sample: 'const { width, height } = usePageSize()' },
]

/** 字号刻度；字号与行高都跟随页面基础字号等比变化。 */
const fontScale = [
  { label: '辅助说明', token: 'text-xs', className: 'text-xs' },
  { label: '小字号正文', token: 'text-sm', className: 'text-sm' },
  { label: '基础字号', token: 'text-base', className: 'text-base' },
  { label: '小标题', token: 'text-xl', className: 'text-xl font-heading font-semibold' },
  { label: '页面标题', token: 'text-3xl', className: 'text-3xl font-heading font-semibold' },
]
</script>
