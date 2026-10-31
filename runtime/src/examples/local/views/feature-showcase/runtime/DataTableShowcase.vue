<!--
  文件用途：本地示例页，展示 Runtime Kit DataTable 的分层样式与 PPTX 原生表格导出映射。
-->
<template>
  <ShowcasePage
    title="DataTable 表格"
    subtitle="CSS Grid 渲染，PPTX 导出为 PowerPoint 原生可编辑表格"
    :capabilities="capabilities"
  >
    <div class="flex h-full min-h-0 flex-col gap-4">
      <div class="grid grid-cols-[1.05fr_0.95fr] gap-4">
        <section class="flex flex-col justify-start rounded-lg border border-border-subtle bg-background-subtle p-4">
          <div class="mb-3 flex items-center gap-2">
            <Icon name="slider" class="size-4 text-primary" />
            <h2 class="font-heading text-base font-semibold text-primary">经营指标表</h2>
            <span class="ml-auto font-body text-xs text-secondary">边框 / 行高 / 列宽 / 单元格分层</span>
          </div>
          <DataTable
            :rows="metricRows"
            :styles="metricStyles"
            width="100%"
            height="320px"
            class="overflow-hidden rounded-md border border-border bg-white text-sm"
          />
          <p class="mt-3 font-body text-xs leading-6 text-secondary">
            第 0 行 46px、第 3 行 50px，首列 148px、末列 150px；末列内部横线为虚线。
          </p>
        </section>

        <section class="flex flex-col justify-start rounded-lg border border-border-subtle bg-background-subtle p-4">
          <div class="mb-3 flex items-center gap-2">
            <Icon name="slider" class="size-4 text-primary" />
            <h2 class="font-heading text-base font-semibold text-primary">项目排期矩阵</h2>
            <span class="ml-auto font-body text-xs text-secondary">无边框 + 列样式强调</span>
          </div>
          <DataTable
            :rows="timelineRows"
            :styles="timelineStyles"
            width="100%"
            height="300px"
            class="overflow-hidden rounded-md bg-white text-xs"
          />
          <p class="mt-3 font-body text-xs leading-6 text-secondary">
            整表无边框，仅靠首列底色和 5 个单元格强调区分模块。
          </p>
        </section>
      </div>

      <section class="grid grid-cols-3 gap-3">
        <article v-for="item in styleNotes" :key="item.title" class="rounded-lg border border-border bg-default px-4 py-3">
          <p class="font-heading text-sm font-semibold text-primary">{{ item.title }}</p>
          <p class="mt-1 font-body text-xs leading-6 text-secondary">{{ item.description }}</p>
        </article>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import DataTable, {
  type RuntimeTableCellInput,
  type RuntimeTableStyleLayers,
} from '@runtime-kit/public/components/data/DataTable.v1.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

const capabilities: ShowcaseCapability[] = [
  { name: 'DataTable.v1', path: '@runtime-kit/public/components/data/DataTable.v1.vue' },
]

/** 经营指标表数据。 */
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
  cell: { class: 'bg-white text-secondary', style: { textAlign: 'center' } },
  rows: {
    0: { class: 'bg-slate-100 text-primary font-semibold', height: 46 },
    3: { height: 50, border: { top: { color: '#334155', width: 2, style: 'solid' } } },
  },
  columns: {
    0: { class: 'bg-slate-50 text-primary font-medium', width: 148, style: { textAlign: 'left' } },
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
    '2,3': { class: 'bg-accent2-50 text-accent2-800 font-semibold', border: { outer: { color: '#0f766e', width: 2, style: 'dashed' } } },
    '3,3': { class: 'bg-slate-50 text-primary font-bold' },
  },
}

/** 项目排期矩阵数据，首列通过列样式强调。 */
const timelineRows: RuntimeTableCellInput[][] = [
  ['调研', '需求访谈', '流程梳理', '数据口径'],
  ['设计', '页面结构', '组件拆分', '导出校验'],
  ['开发', 'Runtime Kit', 'PPTX 映射', '测试补齐'],
  ['验收', '预览检查', '导出检查', '文档更新'],
]

/** 项目排期矩阵分层样式。 */
const timelineStyles: RuntimeTableStyleLayers = {
  table: { border: { all: 'none' } },
  cell: { class: 'bg-white text-secondary', style: { textAlign: 'center' } },
  columns: {
    0: { class: 'bg-slate-100 text-primary font-semibold', width: 96 },
    2: { width: 130 },
  },
  cells: {
    '0,1': { class: 'bg-accent3-50 text-accent3-800 font-medium' },
    '1,2': { class: 'bg-accent4-50 text-accent4-800 font-medium' },
    '2,1': { class: 'bg-accent1-50 text-accent1-800 font-medium' },
    '2,2': { class: 'bg-accent2-50 text-accent2-800 font-medium' },
    '3,3': { class: 'bg-slate-900 text-white font-semibold' },
  },
}

const styleNotes = [
  { title: '显式宽高', description: 'width / height 定义可分配空间，未设尺寸的行列按剩余空间均分。' },
  { title: '分层样式', description: 'table、cell、columns、rows、单元格对象、cells 按固定顺序覆盖。' },
  { title: 'PPTX 原生导出', description: '导出器读取最终 DOM 样式，用 addTable 生成可编辑表格。' },
]
</script>
