<!--
  文件用途：本地示例页，说明 Runtime 页面真实画布、DefaultContainer 与预览缩放壳层的关系。
-->
<template>
  <DefaultContentPage title="页面画布与缩放" subtitle="真实页面尺寸由内容容器承载，预览缩放由 Runtime 壳层处理">
    <template #content>
      <div class="grid h-full grid-cols-[0.95fr_1.05fr] gap-8 p-6">
        <section class="rounded-lg border border-border bg-background-subtle p-6">
          <div class="mb-5 flex items-center gap-3">
            <Icon name="缩小" class="size-6 text-primary" />
            <h2 class="font-heading text-2xl font-semibold text-primary">当前页面尺寸</h2>
          </div>
          <div class="grid grid-cols-3 gap-4">
            <div v-for="metric in metrics" :key="metric.label" class="rounded-md bg-default p-4">
              <p class="font-body text-sm text-secondary">{{ metric.label }}</p>
              <p class="mt-2 font-heading text-2xl font-semibold text-primary">{{ metric.value }}</p>
            </div>
          </div>
          <div class="mt-6 rounded-md bg-default p-5">
            <p class="font-mono text-sm leading-7 text-primary">
              import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'
            </p>
            <p class="mt-3 font-mono text-sm leading-7 text-primary">
              import { usePageSize } from '@runtime-kit/public/composables/page/usePageSize.v1'
            </p>
          </div>
        </section>

        <section class="space-y-5">
          <div class="rounded-lg border border-border-default bg-default p-6 shadow-theme-sm">
            <h3 class="font-heading text-xl font-semibold text-primary">职责拆分</h3>
            <div class="mt-4 grid grid-cols-3 gap-4">
              <div v-for="item in shellResponsibilities" :key="item.title" class="rounded-md bg-background-muted p-4">
                <p class="font-heading text-lg font-semibold text-primary">{{ item.title }}</p>
                <p class="mt-2 font-body text-sm leading-6 text-secondary">{{ item.description }}</p>
              </div>
            </div>
          </div>

          <div class="rounded-lg border border-border-default bg-default p-6 shadow-theme-sm">
            <h3 class="font-heading text-xl font-semibold text-primary">标准画布样式</h3>
            <dl class="mt-4 grid grid-cols-2 gap-x-6 gap-y-3">
              <template v-for="item in canvasStyleEntries" :key="item.name">
                <dt class="font-body text-sm text-secondary">{{ item.name }}</dt>
                <dd class="font-mono text-sm text-primary">{{ item.value }}</dd>
              </template>
            </dl>
          </div>
        </section>
      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import { usePageSize } from '@runtime-kit/public/composables/page/usePageSize.v1'

const { width, height, aspectRatio, pageStyle } = usePageSize()

/**
 * 当前页面尺寸指标。
 * 输出：展示页面宽高和宽高比，便于验证配置是否已注入。
 */
const metrics = computed(() => [
  { label: '画布宽度', value: `${width.value}px` },
  { label: '画布高度', value: `${height.value}px` },
  { label: '宽高比', value: aspectRatio.value.toFixed(3) },
])

/**
 * 页面容器与缩放壳层的职责说明。
 */
const shellResponsibilities = [
  {
    title: '内容画布',
    description: 'DefaultContainer 负责提供真实设计尺寸，页面内部仍按固定画布排版。',
  },
  {
    title: '预览缩放',
    description: 'Standalone 预览壳层负责把完整画布等比缩放到 iframe 或浏览器视口。',
  },
  {
    title: '导出一致性',
    description: '截图、打印和 PDF 导出面向真实画布取样，避免页面源码重复处理缩放。',
  },
]

/**
 * 将 pageStyle 对象转换成可读列表。
 */
const canvasStyleEntries = computed(() => Object.entries(pageStyle.value).map(([name, value]) => ({
  name,
  value: String(value),
})))
</script>
