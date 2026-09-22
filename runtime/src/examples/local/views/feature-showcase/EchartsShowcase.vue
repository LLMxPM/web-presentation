<!--
  文件用途：本地示例页，用于展示 EchartsViewer 的图表渲染与统一渲染区域参数。
-->
<template>
  <DefaultContentPage title="ECharts 图表展示" subtitle="展示 EchartsViewer 的真实图表渲染能力">
    <template #content>
      <div class="space-y-6">
        <section class="grid grid-cols-4 gap-4">
          <label class="space-y-2">
            <span class="text-sm font-medium text-secondary">图表类型</span>
            <select v-model="chartType" class="showcase-select">
              <option value="bar">柱状图</option>
              <option value="line">折线图</option>
              <option value="pie">环形图</option>
              <option value="scatter">散点图</option>
            </select>
          </label>

          <label class="space-y-2">
            <span class="text-sm font-medium text-secondary">主题</span>
            <select v-model="chartTheme" class="showcase-select">
              <option value="">默认</option>
              <option value="dark">深色</option>
            </select>
          </label>

          <label class="space-y-2">
            <span class="text-sm font-medium text-secondary">渲染器</span>
            <select v-model="renderer" class="showcase-select">
              <option value="canvas">Canvas</option>
              <option value="svg">SVG</option>
            </select>
          </label>

          <label class="flex items-end gap-3 rounded-lg border border-border-subtle bg-background-subtle px-4 py-3">
            <input v-model="showBorder" type="checkbox" class="h-4 w-4 accent-primary" />
            <span class="text-sm font-medium text-primary">显示边框</span>
          </label>
        </section>

        <section class="grid grid-cols-[2fr_1fr] gap-6">
          <div class="rounded-lg border border-border bg-background p-4">
            <EchartsViewer
              :option="currentOption"
              :theme="chartTheme"
              :renderer="renderer"
              :show-border="showBorder"
              width="100%"
              height="520px"
              min-height="360px"
              :background-color="viewerBackground"
              border-color="#cbd5e1"
              border-radius="14px"
              padding="12px"
            />
          </div>

          <aside class="rounded-lg border border-border bg-background-subtle p-5">
            <div class="mb-5 flex items-center gap-3">
              <Icon name="slider" class="size-5" color="primary" />
              <h2 class="font-heading text-xl font-semibold text-primary">区域参数</h2>
            </div>
            <dl class="space-y-4 text-sm">
              <div v-for="item in surfaceItems" :key="item.label">
                <dt class="text-secondary">{{ item.label }}</dt>
                <dd class="mt-1 font-code text-primary">{{ item.value }}</dd>
              </div>
            </dl>
          </aside>
        </section>
      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EChartsOption } from 'echarts'
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import EchartsViewer from '@runtime-kit/internal/renderers/EchartsViewer.vue'

type ChartType = 'bar' | 'line' | 'pie' | 'scatter'
type EchartsRenderer = 'canvas' | 'svg'

defineOptions({
  name: 'EchartsShowcase',
})

const chartType = ref<ChartType>('bar')
const chartTheme = ref('')
const renderer = ref<EchartsRenderer>('canvas')
const showBorder = ref(true)

const months = ['1月', '2月', '3月', '4月', '5月', '6月']

const chartOptions: Record<ChartType, EChartsOption> = {
  bar: {
    tooltip: { trigger: 'axis' },
    legend: { top: 8 },
    grid: { left: 42, right: 24, top: 64, bottom: 36 },
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'value' },
    series: [
      { name: '演示访问量', type: 'bar', data: [120, 182, 191, 234, 290, 330], itemStyle: { color: '#2563eb' } },
      { name: '图表渲染量', type: 'bar', data: [86, 142, 165, 210, 246, 305], itemStyle: { color: '#14b8a6' } },
    ],
  },
  line: {
    tooltip: { trigger: 'axis' },
    legend: { top: 8 },
    grid: { left: 42, right: 24, top: 64, bottom: 36 },
    xAxis: { type: 'category', boundaryGap: false, data: months },
    yAxis: { type: 'value' },
    series: [
      { name: '响应速度', type: 'line', smooth: true, data: [80, 76, 71, 68, 61, 55], areaStyle: {} },
      { name: '稳定性', type: 'line', smooth: true, data: [92, 94, 95, 96, 97, 98] },
    ],
  },
  pie: {
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', left: 18, top: 18 },
    series: [
      {
        name: '资源类型',
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['58%', '54%'],
        data: [
          { value: 36, name: '图片' },
          { value: 24, name: '图表' },
          { value: 18, name: '公式' },
          { value: 22, name: '视频' },
        ],
      },
    ],
  },
  scatter: {
    tooltip: { trigger: 'item' },
    grid: { left: 42, right: 24, top: 36, bottom: 42 },
    xAxis: { type: 'value', name: '复杂度' },
    yAxis: { type: 'value', name: '渲染收益' },
    series: [
      {
        name: '组件样本',
        type: 'scatter',
        symbolSize: (value: unknown) => {
          const point = value as number[]
          return Math.max(12, point[2] || 16)
        },
        data: [
          [12, 42, 16],
          [24, 58, 22],
          [35, 68, 28],
          [46, 74, 18],
          [58, 88, 34],
          [72, 92, 26],
        ],
      },
    ],
  },
}

/**
 * 当前示例图表 option。
 * @returns 传给 EchartsViewer 的 option 对象
 */
const currentOption = computed(() => chartOptions[chartType.value] as Record<string, unknown>)

/**
 * 根据当前主题推导容器背景色。
 */
const viewerBackground = computed(() => (chartTheme.value === 'dark' ? '#0f172a' : '#ffffff'))

const surfaceItems = computed(() => [
  { label: '宽度', value: '100%' },
  { label: '高度', value: '520px' },
  { label: '最小高度', value: '360px' },
  { label: '背景色', value: viewerBackground.value },
  { label: '边框', value: showBorder.value ? '1px solid #cbd5e1' : 'none' },
  { label: '圆角', value: '14px' },
  { label: '内边距', value: '12px' },
])
</script>

<style scoped>
.showcase-select {
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--tw-color-border-default);
  background: var(--tw-color-bg-default);
  padding: 10px 12px;
  color: var(--tw-color-text-primary);
  outline: none;
}

.showcase-select:focus {
  border-color: var(--tw-color-text-primary);
}
</style>
