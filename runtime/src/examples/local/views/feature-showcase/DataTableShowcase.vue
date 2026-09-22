<!--
  文件用途：本地示例页，展示 Runtime Kit DataTable 的分层样式和 PPTX 原生表格导出能力。
-->
<template>
  <DefaultContentPage title="DataTable 表格" subtitle="CSS Grid 渲染，PPTX 导出为 PowerPoint 原生表格">
    <template #content>
      <div class="grid h-full grid-cols-[minmax(0,1.08fr)_minmax(0,0.92fr)] grid-rows-[360px_auto] gap-5 p-4">
        <section class="flex min-h-0 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <div class="mb-4 flex items-center gap-3">
            <Icon name="slider" class="size-5 text-primary" />
            <h2 class="font-heading text-xl font-semibold text-primary">经营指标表</h2>
          </div>
          <DataTable
            :rows="metricRows"
            :styles="metricStyles"
            width="100%"
            height="100%"
            class="min-h-0 flex-1 rounded-lg border border-border bg-white text-sm overflow-hidden"
          />
        </section>

        <section class="flex min-h-0 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <div>
            <h3 class="font-heading text-lg font-semibold text-primary">项目排期矩阵</h3>
            <p class="mt-2 font-body text-sm leading-6 text-secondary">
              首列通过列样式强调；该表设置为无边框，用于对照 PPTX 导出的 none 边框。
            </p>
          </div>

          <DataTable
            :rows="timelineRows"
            :styles="timelineStyles"
            width="100%"
            height="100%"
            class="mt-5 min-h-0 flex-1 rounded-lg bg-white text-xs overflow-hidden"
          />
        </section>

        <section class="col-span-2 grid grid-cols-3 gap-4">
          <article
            v-for="item in styleNotes"
            :key="item.title"
            class="rounded-lg border border-border bg-default p-4"
          >
            <p class="font-heading text-base font-semibold text-primary">{{ item.title }}</p>
            <p class="mt-2 font-body text-sm leading-6 text-secondary">{{ item.description }}</p>
          </article>
        </section>
      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import DataTable, {
  type RuntimeTableCellInput,
  type RuntimeTableStyleLayers,
} from '@runtime-kit/public/components/data/DataTable.v1.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

/**
 * 经营指标表数据。
 * 输入：无；输出：DataTable rows。
 */
const metricRows: RuntimeTableCellInput[][] = [
  ['指标', 'Q1', 'Q2', 'Q3 目标'],
  ['收入', '96 万', { text: '128 万', class: 'text-accent1 font-bold' }, '156 万'],
  ['增长率', '12%', { text: '18%', class: 'text-accent2 font-bold' }, '22%'],
  ['留存率', '82%', '86%', { text: '90%', class: 'text-primary font-bold' }],
]

/**
 * 经营指标表分层样式。
 * 约束：行高只放在 rows，列宽只放在 columns，单元格视觉通过 cells 精确覆盖。
 */
const metricStyles: RuntimeTableStyleLayers = {
  table: {
    border: {
      outer: { color: '#475569', width: 2, style: 'solid' },
      inner: { color: '#cbd5e1', width: 1, style: 'solid' },
    },
  },
  cell: {
    class: 'bg-white text-secondary',
    style: { textAlign: 'center' },
  },
  rows: {
    0: {
      class: 'bg-slate-100 text-primary font-semibold',
      height: 48,
    },
    3: {
      height: 54,
      border: {
        top: { color: '#334155', width: 2, style: 'solid' },
      },
    },
  },
  columns: {
    0: {
      class: 'bg-slate-50 text-primary font-medium',
      width: 148,
      style: { textAlign: 'left' },
    },
    3: {
      width: 150,
      border: {
        outer: { color: '#2563eb', width: 2, style: 'solid' },
        innerHorizontal: { color: '#93c5fd', width: 1, style: 'dashed' },
      },
    },
  },
  cells: {
    '1,3': {
      class: 'bg-accent1-50 text-accent1-800 font-semibold',
      border: {
        top: { color: '#1d4ed8', width: 2, style: 'solid' },
        right: { color: '#1d4ed8', width: 3, style: 'solid' },
        bottom: { color: '#1d4ed8', width: 2, style: 'dashed' },
        left: 'none',
      },
    },
    '2,3': {
      class: 'bg-accent2-50 text-accent2-800 font-semibold',
      border: {
        outer: { color: '#0f766e', width: 2, style: 'dashed' },
      },
    },
    '3,3': {
      class: 'bg-slate-50 text-primary font-bold',
    },
  },
}

/**
 * 项目排期矩阵数据，首列通过列样式强调。
 */
const timelineRows: RuntimeTableCellInput[][] = [
  ['调研', '需求访谈', '流程梳理', '数据口径'],
  ['设计', '页面结构', '组件拆分', '导出校验'],
  ['开发', 'Runtime Kit', 'PPTX 映射', '测试补齐'],
  ['验收', '预览检查', '导出检查', '文档更新'],
]

/**
 * 项目排期矩阵分层样式。
 */
const timelineStyles: RuntimeTableStyleLayers = {
  table: {
    border: {
      all: 'none',
    },
  },
  cell: {
    class: 'bg-white text-secondary',
    style: { textAlign: 'center' },
  },
  columns: {
    0: {
      class: 'bg-slate-100 text-primary font-semibold',
      width: 96,
    },
    2: {
      width: 130,
    },
  },
  cells: {
    '0,1': { class: 'bg-accent3-50 text-accent3-800 font-medium' },
    '1,2': { class: 'bg-accent4-50 text-accent4-800 font-medium' },
    '2,1': { class: 'bg-accent1-50 text-accent1-800 font-medium' },
    '2,2': { class: 'bg-accent2-50 text-accent2-800 font-medium' },
    '3,3': { class: 'bg-slate-900 text-white font-semibold' },
  },
}

/**
 * 示例页说明卡片。
 */
const styleNotes = [
  {
    title: '显式宽高',
    description: 'width 和 height 负责定义表格可分配空间，未设置尺寸的行列按剩余空间自动均分。',
  },
  {
    title: '分层样式',
    description: 'table、cell、columns、rows、单元格对象、cells 按固定顺序覆盖，接近 PPT 表格编辑方式。',
  },
  {
    title: 'PPTX 原生导出',
    description: '导出器读取最终 DOM 样式，并调用 addTable 生成 PowerPoint 可编辑表格。',
  },
]
</script>
