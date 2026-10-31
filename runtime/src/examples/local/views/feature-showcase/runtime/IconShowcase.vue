<!--
  文件用途：本地示例页，展示图标配置解析、主题色内联渲染与主题 Logo 读取。
-->
<template>
  <ShowcasePage
    title="图标与 Logo"
    subtitle="图标按运行时配置解析为 inline SVG，Logo 跟随当前主题"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[1.1fr_0.9fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-5">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="star" class="size-5 text-primary" />
          <h2 class="font-heading text-lg font-semibold text-primary">图标库</h2>
          <span class="ml-auto font-body text-xs text-secondary">来自 icons.config.yaml</span>
        </div>

        <div class="grid grid-cols-5 gap-2">
          <div
            v-for="name in iconNames"
            :key="name"
            class="flex flex-col items-center gap-1.5 rounded-md bg-default px-2 py-3"
          >
            <Icon :name="name" class="size-6 text-primary" />
            <span class="w-full truncate text-center font-code text-xs text-secondary">{{ name }}</span>
          </div>
        </div>

        <div class="mt-4 grid grid-cols-2 gap-3">
          <div class="flex flex-col justify-center rounded-md bg-default p-4">
            <p class="font-body text-xs text-secondary">尺寸档位</p>
            <div class="mt-2 flex items-end gap-3">
              <span v-for="size in iconSizes" :key="size" class="flex flex-col items-center gap-1">
                <Icon name="slider" :class="size" class="text-primary" />
                <span class="font-code text-xs text-secondary">{{ size.replace('size-', '') }}</span>
              </span>
            </div>
          </div>

          <div class="flex flex-col justify-center rounded-md bg-default p-4">
            <p class="font-body text-xs text-secondary">主题色与描边</p>
            <div class="mt-2 flex flex-wrap items-center gap-3">
              <Icon name="heart" class="size-7" color="accent1" />
              <Icon name="heart" class="size-7" color="accent2" />
              <Icon name="heart" class="size-7" color="accent3" />
              <Icon name="heart" class="size-7 text-primary" :stroke-width="1" />
              <Icon name="heart" class="size-7 text-primary" :stroke-width="3" />
              <Icon name="heart" class="size-7 text-primary" disabled />
            </div>
          </div>

          <div class="flex flex-col justify-center rounded-md bg-default p-4">
            <p class="font-body text-xs text-secondary">未知图标回退</p>
            <div class="mt-2 flex items-center gap-3">
              <Icon name="不存在的图标" fallback="?" class="size-7 text-primary" />
              <span class="font-code text-xs text-secondary">&lt;Icon name="不存在的图标" fallback="?" /&gt;</span>
            </div>
          </div>

          <div class="flex flex-col justify-center rounded-md bg-default p-4">
            <p class="font-body text-xs text-secondary">静态描边宽度</p>
            <div class="mt-2 flex items-center gap-3">
              <Icon name="扫描" class="size-7 text-primary" :stroke-width="1.5" />
              <Icon name="扫描" class="size-7 text-primary" :stroke-width="2.5" />
              <span class="font-code text-xs text-secondary">stroke-width 只作用于描边型图标</span>
            </div>
          </div>
        </div>

        <div class="mt-3 rounded-md bg-default p-4">
          <p class="font-body text-xs text-secondary">组合示例</p>
          <div class="mt-2 grid grid-cols-3 gap-3">
            <div v-for="item in compositions" :key="item.title" class="flex items-center gap-2.5 rounded border border-border-subtle p-3">
              <span class="flex size-9 shrink-0 items-center justify-center rounded-md" :class="item.iconClass">
                <Icon :name="item.icon" class="size-4" />
              </span>
              <div class="min-w-0">
                <p class="font-heading text-sm font-semibold text-primary">{{ item.title }}</p>
                <p class="truncate font-body text-xs text-secondary">{{ item.description }}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">主题 Logo</h3>
          <p class="mt-1 font-body text-xs text-secondary">ThemeLogo 只按 size 控制高度，宽度等比计算</p>
          <div class="mt-3 grid grid-cols-2 gap-3">
            <div class="flex flex-col items-center gap-2 rounded-md bg-default p-4">
              <ThemeLogo variant="logo" :size="10" />
              <span class="font-code text-xs text-secondary">variant="logo"</span>
            </div>
            <div class="flex flex-col items-center gap-2 rounded-md bg-background-invert p-4">
              <ThemeLogo variant="invert" :size="10" />
              <span class="font-code text-xs text-invert">variant="invert"</span>
            </div>
          </div>
          <div class="mt-3 flex items-center justify-around rounded-md bg-default p-4">
            <ThemeLogo v-for="size in [4, 6, 8]" :key="size" :size="size" />
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">使用边界</h3>
          <ul class="mt-3 space-y-2">
            <li v-for="note in notes" :key="note" class="flex gap-2 font-body text-xs leading-6 text-secondary">
              <span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent2" />
              <span>{{ note }}</span>
            </li>
          </ul>

          <div class="mt-4 rounded-md border border-border-subtle bg-default p-3">
            <p class="font-body text-xs text-secondary">解析链路</p>
            <div class="mt-2 flex flex-wrap items-center gap-1.5">
              <template v-for="(step, index) in flow" :key="step">
                <span class="rounded bg-background-subtle px-2 py-1 font-code text-xs text-primary">{{ step }}</span>
                <span v-if="index < flow.length - 1" class="font-code text-xs text-secondary">→</span>
              </template>
            </div>
          </div>

          <pre class="mt-4 overflow-auto rounded-md bg-default p-3 font-code text-xs leading-6 text-primary">&lt;Icon name="slider" class="size-5" color="accent1" :stroke-width="2" /&gt;
&lt;ThemeLogo variant="invert" :size="8" /&gt;</pre>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import ThemeLogo from '@runtime-kit/public/components/primitives/ThemeLogo.v1.vue'

const capabilities: ShowcaseCapability[] = [
  { name: 'Icon.v1', path: '@runtime-kit/public/components/primitives/Icon.v1.vue' },
  { name: 'ThemeLogo.v1', path: '@runtime-kit/public/components/primitives/ThemeLogo.v1.vue' },
]

const iconNames = ['slider', 'c-search', 'heart', 'star', 'mail', 'home', '全屏', '刷新', '扫描', '路由-copy', 'TOP榜', '外汇', '手电筒', '添加联系人', 'Github']
const iconSizes = ['size-3', 'size-4', 'size-5', 'size-6', 'size-8']

/** 图标从逻辑名到最终渲染结果的解析链路。 */
const flow = ['name', '图标配置', 'inline SVG / img', '主题色']

/** 图标与标题、说明的组合示例。 */
const compositions = [
  { title: '数据概览', description: 'icon + 标题 + 指标', icon: 'slider', iconClass: 'bg-accent1-100 text-accent1-700' },
  { title: '内容制作', description: 'icon + 标题 + 动作', icon: '添加联系人', iconClass: 'bg-accent2-100 text-accent2-700' },
  { title: '全局设置', description: 'icon + 标题 + 入口', icon: '全屏', iconClass: 'bg-accent3-100 text-accent3-700' },
]

const notes = [
  '普通页面只使用 Icon 组件，图标配置读取、SVG 加载和回退由 Runtime 内部处理。',
  'color 接受主题 token、色阶（accent1-300）或合法 CSS 颜色；描边型图标会被替换为 currentColor。',
  'ThemeLogo 没有配置 Logo 时直接空渲染，不提供自定义兜底图片。',
  '自定义 Logo、图标周围布局和按钮样式属于页面源码职责，不进入 Runtime Kit。',
]
</script>
