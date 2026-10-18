<!--
  文件用途：PPTX 导出报告面板，展示可编辑对象统计与降级/跳过明细；非 PPTX 导出时不渲染。
-->

<template>
  <div
    v-if="report"
    class="mt-4 rounded-lg border border-slate-200 bg-white text-left text-xs leading-6 text-slate-600">
    <div class="border-b border-slate-100 px-4 py-3">
      <p class="text-sm font-semibold text-slate-900">
        PPTX 导出报告
      </p>
      <p class="mt-1 text-xs text-slate-500">
        可编辑对象与降级对象统计
      </p>
    </div>
    <div class="grid grid-cols-2 gap-2 px-4 py-3 sm:grid-cols-3">
      <div
        v-for="item in summaryItems"
        :key="item.label"
        class="rounded-md bg-slate-50 px-3 py-2">
        <p class="text-[11px] text-slate-500">
          {{ item.label }}
        </p>
        <p class="mt-1 text-base font-semibold text-slate-900">
          {{ item.value }}
        </p>
      </div>
    </div>
    <div v-if="detailItems.length" class="border-t border-slate-100 px-4 py-3">
      <p class="mb-2 text-xs font-semibold text-slate-800">
        降级 / 跳过明细
      </p>
      <div class="max-h-40 space-y-2 overflow-y-auto pr-1">
        <p
          v-for="(item, index) in detailItems"
          :key="`${item.pageRoute}-${index}-${item.label}`"
          class="rounded-md bg-amber-50 px-3 py-2 text-amber-800">
          <span class="block w-full truncate" :title="buildDetailText(item)">
            {{ buildDetailText(item) }}
          </span>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type {
  PptxExportReport,
  PptxExportReportItem,
  PptxReportItemResult,
  PptxReportSourceType,
} from '@/core/types/pptx-export'

interface Props {
  /** PPTX 导出报告；非 PPTX 方式或尚未产出时为 null */
  report: PptxExportReport | null
}

const props = defineProps<Props>()

/** 报告源类型的展示文案。 */
const SOURCE_LABELS: Record<PptxReportSourceType, string> = {
  title: '标题',
  body: '正文',
  number: '关键数字',
  shape: '形状',
  table: '表格',
  image: '图片',
  svg: 'SVG',
  mermaid: 'Mermaid',
  drawio: 'Draw.io',
  formula: '公式',
  chart: '图表',
  canvas: 'Canvas',
  video: '视频',
  audio: '音频',
  model3d: '三维模型',
  'complex-css': '复杂容器',
  unknown: '未知对象',
}

/** 报告结果类型的展示文案。 */
const RESULT_LABELS: Record<PptxReportItemResult, string> = {
  'editable-text': '可编辑文本',
  'editable-shape': '可编辑形状',
  'editable-table': '可编辑表格',
  image: '图片块',
  svg: 'SVG块',
  screenshot: '截图块',
  skipped: '跳过',
}

/** 概览统计项，数组顺序即展示顺序。 */
const summaryItems = computed(() => {
  const summary = props.report?.summary
  if (!summary) {
    return []
  }

  return [
    { label: '可编辑文本', value: summary.editableText },
    { label: '可编辑形状', value: summary.editableShape },
    { label: '可编辑表格', value: summary.editableTable },
    { label: '图片块', value: summary.imageBlock },
    { label: 'SVG块', value: summary.svgBlock },
    { label: '截图降级', value: summary.screenshotBlock },
    { label: '跳过对象', value: summary.skipped },
  ]
})

/** 降级与跳过明细：可编辑对象只在结果为截图或跳过时才需要提示用户。 */
const detailItems = computed<PptxExportReportItem[]>(() => {
  if (!props.report) {
    return []
  }

  return props.report.pages
    .flatMap(page => page.items)
    .filter(item => !item.editable || item.result === 'screenshot' || item.result === 'skipped')
})

/**
 * 组装单条明细的完整文案，列表与 tooltip 共用同一份文本。
 * @param item 降级对象明细
 * @returns 页面 · 源类型 → 结果：原因
 */
function buildDetailText(item: PptxExportReportItem): string {
  const reason = item.reason || '已按降级规则处理'
  return `${item.pageTitle} · ${SOURCE_LABELS[item.sourceType]} → ${RESULT_LABELS[item.result]}：${reason}`
}
</script>
