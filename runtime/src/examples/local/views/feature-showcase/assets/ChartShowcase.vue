<!--
  文件用途：本地示例页，展示 AssetChart 渲染 ECharts option 资源的多种图表形态。
-->
<template>
  <ShowcasePage
    title="ECharts 图表"
    subtitle="页面只传 option，图表实例、主题与渲染器由 Runtime 负责"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[1.55fr_0.95fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="slider" class="size-4 text-primary" />
          <h2 class="font-heading text-base font-semibold text-primary">{{ currentChartLabel }}</h2>
          <span class="ml-auto font-code text-xs text-secondary">{{ chartType }} · {{ renderer }}</span>
        </div>
        <AssetChart
          :content="chartContent"
          :theme="chartTheme"
          :renderer="renderer"
          :show-border="true"
          width="100%"
          height="100%"
          class="min-h-0 flex-1 rounded-md"
          background-color="#ffffff"
          border-color="#cbd5e1"
          border-radius="12px"
          padding="8px"
        />
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="mb-3 font-heading text-base font-semibold text-primary">图表参数</h3>

          <label class="block space-y-1.5">
            <span class="font-body text-xs text-secondary">图表类型</span>
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="item in chartTypeOptions"
                :key="item.key"
                type="button"
                class="rounded-md border px-3 py-2 font-body text-xs font-medium transition-colors"
                :class="chartType === item.key ? 'border-primary bg-primary-50 text-primary' : 'border-border text-secondary'"
                @click="chartType = item.key"
              >
                {{ item.label }}
              </button>
            </div>
          </label>

          <div class="mt-3 grid grid-cols-2 gap-3">
            <label class="space-y-1.5">
              <span class="font-body text-xs text-secondary">主题</span>
              <select v-model="chartTheme" class="showcase-input">
                <option value="">默认</option>
                <option value="dark">dark</option>
              </select>
            </label>
            <label class="space-y-1.5">
              <span class="font-body text-xs text-secondary">渲染器</span>
              <select v-model="renderer" class="showcase-input">
                <option value="canvas">canvas</option>
                <option value="svg">svg</option>
              </select>
            </label>
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="font-heading text-base font-semibold text-primary">option 资源</h3>
          <p class="mt-1 font-body text-xs leading-6 text-secondary">
            AssetChart 接受 name（资源名）或 content（option 文本）；本地 fixture 直接用 content 传入。
          </p>
          <pre class="mt-3 min-h-0 flex-1 overflow-auto rounded-md bg-default p-3 font-code text-xs leading-6 text-primary">{{ chartContent }}</pre>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import AssetChart from '@runtime-kit/public/components/assets/AssetChart.v1.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

type ChartType = 'bar' | 'line' | 'pie' | 'scatter'
type EchartsRenderer = 'canvas' | 'svg'

const capabilities: ShowcaseCapability[] = [
  { name: 'AssetChart.v1', path: '@runtime-kit/public/components/assets/AssetChart.v1.vue' },
]

const chartType = ref<ChartType>('bar')
const chartTheme = ref('')
const renderer = ref<EchartsRenderer>('canvas')

const months = ['1月', '2月', '3月', '4月', '5月', '6月']

const chartTypes = [
  { key: 'bar', label: '柱状图' },
  { key: 'line', label: '折线图' },
  { key: 'pie', label: '环形图' },
  { key: 'scatter', label: '散点图' },
] as const
const chartTypeOptions: Array<{ key: ChartType; label: string }> = chartTypes.map((item) => ({ ...item }))

const currentChartLabel = computed(() => chartTypes.find((item) => item.key === chartType.value)?.label || '')

/** 纯 JSON option：不含函数，便于以资源文本形式保存。 */
const chartOptions: Record<ChartType, Record<string, unknown>> = {
  bar: {
    tooltip: { trigger: 'axis' },
    legend: { top: 8 },
    grid: { left: 42, right: 24, top: 56, bottom: 32 },
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'value' },
    series: [
      { name: '访问量', type: 'bar', data: [120, 182, 191, 234, 290, 330], itemStyle: { color: '#2D7BB8' } },
      { name: '渲染量', type: 'bar', data: [86, 142, 165, 210, 246, 305], itemStyle: { color: '#159A8C' } },
    ],
  },
  line: {
    tooltip: { trigger: 'axis' },
    legend: { top: 8 },
    grid: { left: 42, right: 24, top: 56, bottom: 32 },
    xAxis: { type: 'category', boundaryGap: false, data: months },
    yAxis: { type: 'value' },
    series: [
      { name: '响应耗时', type: 'line', smooth: true, data: [80, 76, 71, 68, 61, 55], areaStyle: {} },
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
    grid: { left: 42, right: 24, top: 32, bottom: 36 },
    xAxis: { type: 'value', name: '复杂度' },
    yAxis: { type: 'value', name: '渲染收益' },
    series: [
      {
        name: '组件样本',
        type: 'scatter',
        symbolSize: 18,
        data: [[12, 42], [24, 58], [35, 68], [46, 74], [58, 88], [72, 92]],
      },
    ],
  },
}

const chartContent = computed(() => JSON.stringify(chartOptions[chartType.value], null, 2))
</script>

<style scoped>
.showcase-input {
  width: 100%;
  border-radius: 8px;
  border: 1px solid var(--tw-color-border-default);
  background: var(--tw-color-bg-default);
  padding: 8px 10px;
  color: var(--tw-color-text-primary);
  font-size: 13px;
  outline: none;
}
</style>
