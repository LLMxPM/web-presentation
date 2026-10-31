<!--
  文件用途：本地示例页，说明页面真实画布、DefaultContainer 与预览缩放壳层的关系。
-->
<template>
  <ShowcasePage
    title="页面画布与尺寸"
    subtitle="页面在固定设计尺寸内排版，缩放交给预览壳层"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[0.95fr_1.05fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-5">
        <div class="mb-4 flex items-center gap-2">
          <Icon name="缩小" class="size-5 text-primary" />
          <h2 class="font-heading text-lg font-semibold text-primary">当前生效画布</h2>
          <span class="ml-auto font-body text-xs text-secondary">来自 app.config.yaml</span>
        </div>

        <div class="grid grid-cols-3 gap-3">
          <div v-for="metric in metrics" :key="metric.label" class="rounded-md bg-default p-4">
            <p class="font-body text-xs text-secondary">{{ metric.label }}</p>
            <p class="mt-1 font-heading text-xl font-semibold text-primary">{{ metric.value }}</p>
          </div>
        </div>

        <div class="mt-4 flex min-h-0 flex-1 flex-col rounded-md border border-border bg-default p-3">
          <div class="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded border border-border bg-background-subtle">
            <div class="flex h-[14%] shrink-0 items-center gap-2 border-b border-border-subtle bg-primary-50 px-3">
              <span class="size-2 rounded-full bg-accent2" />
              <span class="h-1.5 w-16 rounded-full bg-border" />
              <span class="ml-auto h-1.5 w-10 rounded-full bg-border" />
            </div>
            <div class="grid min-h-0 flex-1 grid-cols-3 gap-2 p-3">
              <span v-for="index in 6" :key="index" class="rounded border border-border bg-default" />
            </div>
            <div class="flex h-[10%] shrink-0 items-center gap-2 border-t border-border-subtle bg-background-subtle px-3">
              <span class="h-1 w-24 rounded-full bg-border" />
              <span class="ml-auto h-1 w-10 rounded-full bg-border" />
            </div>
          </div>
          <div class="mt-2 flex items-center justify-between font-body text-xs text-secondary">
            <span>页面结构示意</span>
            <span class="font-code">{{ width }} × {{ height }} · {{ aspectRatio.toFixed(3) }}</span>
          </div>
        </div>

        <p class="mt-3 font-body text-xs text-secondary">
          页面源码始终按真实像素排版，不感知浏览器窗口尺寸。
        </p>
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">三项能力的职责</h3>
          <div class="mt-3 grid grid-cols-3 gap-3">
            <div v-for="item in responsibilities" :key="item.title" class="rounded-md bg-default p-4">
              <p class="font-heading text-sm font-semibold text-primary">{{ item.title }}</p>
              <p class="mt-1 font-body text-xs leading-6 text-secondary">{{ item.description }}</p>
            </div>
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">标准画布样式</h3>
          <p class="mt-1 font-body text-xs text-secondary">buildPageCanvasStyle 返回的样式对象，可直接绑定到页面根容器</p>
          <dl class="mt-3 grid grid-cols-2 gap-x-6 gap-y-2">
            <template v-for="entry in canvasStyleEntries" :key="entry.name">
              <dt class="font-code text-xs text-secondary">{{ entry.name }}</dt>
              <dd class="font-code text-xs text-primary">{{ entry.value }}</dd>
            </template>
          </dl>
          <pre class="mt-4 overflow-auto rounded-md bg-default p-4 font-code text-xs leading-6 text-primary">{{ snippet }}</pre>

          <ul class="mt-3 space-y-1.5">
            <li v-for="item in boundaries" :key="item" class="flex gap-2 font-body text-xs leading-6 text-secondary">
              <span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent2" />
              <span>{{ item }}</span>
            </li>
          </ul>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import { buildPageCanvasStyle, usePageSize } from '@runtime-kit/public/composables/page/usePageSize.v1'

const { width, height, aspectRatio } = usePageSize()

const capabilities: ShowcaseCapability[] = [
  { name: 'DefaultContainer.v1', path: '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue' },
  { name: 'usePageSize.v1', path: '@runtime-kit/public/composables/page/usePageSize.v1' },
  { name: 'buildPageCanvasStyle.v1', path: '@runtime-kit/public/composables/page/usePageSize.v1' },
]

/** 当前画布的关键指标。 */
const metrics = computed(() => [
  { label: '画布宽度', value: `${width.value}px` },
  { label: '画布高度', value: `${height.value}px` },
  { label: '宽高比', value: aspectRatio.value.toFixed(3) },
])

const responsibilities = [
  { title: 'DefaultContainer', description: '提供真实设计尺寸、定位上下文和裁剪边界。' },
  { title: 'usePageSize', description: '响应式读取宽高、宽高比和标准画布样式。' },
  { title: '预览壳层', description: '把完整画布等比缩放到 iframe 或浏览器视口。' },
]

/** 页面源码不需要自己处理的画布事项。 */
const boundaries = [
  '不处理浏览器窗口缩放：预览与放映壳层负责等比缩放。',
  '不重复声明 width / height：画布尺寸由 DefaultContainer 提供。',
  '不自行适配导出：截图、打印与 PDF 直接面向真实画布取样。',
]

/** 把标准画布样式转成可读列表，验证构造结果。 */
const canvasStyleEntries = computed(() => Object.entries(buildPageCanvasStyle({
  width: width.value,
  height: height.value,
})).map(([name, value]) => ({ name, value: String(value) })))

const snippet = [
  "import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'",
  "import { usePageSize } from '@runtime-kit/public/composables/page/usePageSize.v1'",
  '',
  '// 页面根容器：真实设计尺寸 + 裁剪边界',
  'const { width, height, pageStyle } = usePageSize()',
].join('\n')
</script>
