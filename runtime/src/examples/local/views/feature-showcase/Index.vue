<!--
  文件用途：本地功能展示入口页，汇总 Runtime Kit 公开能力与本地调试页面。
-->
<script setup lang="ts">
import DefaultCoverPage from '@/runtime-kit/public/components/page/templates/DefaultCoverPage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

/**
 * 功能入口卡片配置。
 * 约束：这里只维护演示入口信息，实际能力边界以 Runtime Kit manifest 和文档为准。
 */
interface ShowcaseCard {
  title: string
  description: string
  icon: string
  tag: string
  to: string
  headerClass: string
  iconClass: string
  titleClass: string
  descriptionClass: string
  tagClass: string
}

const cards: ShowcaseCard[] = [
  {
    title: '主题系统',
    description: '展示主题变量、Logo、字体和颜色在页面中的使用方式。',
    icon: 'star',
    tag: '主题能力',
    to: '/feature-showcase/theme-showcase',
    headerClass: 'bg-accent1-100',
    iconClass: 'text-accent1-700',
    titleClass: 'text-accent1-800',
    descriptionClass: 'text-accent1-700',
    tagClass: 'bg-accent1-200 text-accent1-800',
  },
  {
    title: 'Mermaid 图表',
    description: '展示 Mermaid 文本图表由 Runtime 浏览器端渲染的效果。',
    icon: '路由-copy',
    tag: '资源渲染',
    to: '/feature-showcase/mermaid-showcase',
    headerClass: 'bg-accent2-100',
    iconClass: 'text-accent2-700',
    titleClass: 'text-accent2-800',
    descriptionClass: 'text-accent2-700',
    tagClass: 'bg-accent2-200 text-accent2-800',
  },
  {
    title: 'Draw.io 图表',
    description: '展示 Draw.io XML 资源加载、解析和图表区域渲染。',
    icon: '扫描',
    tag: '资源渲染',
    to: '/feature-showcase/drawio-chart-showcase',
    headerClass: 'bg-accent3-100',
    iconClass: 'text-accent3-700',
    titleClass: 'text-accent3-800',
    descriptionClass: 'text-accent3-700',
    tagClass: 'bg-accent3-200 text-accent3-800',
  },
  {
    title: 'ECharts 图表',
    description: '展示 ECharts option 资源在统一渲染区域中的表现。',
    icon: 'slider',
    tag: '资源渲染',
    to: '/feature-showcase/echarts-showcase',
    headerClass: 'bg-accent4-100',
    iconClass: 'text-accent4-700',
    titleClass: 'text-accent4-800',
    descriptionClass: 'text-accent4-700',
    tagClass: 'bg-accent4-200 text-accent4-800',
  },
  {
    title: 'LaTeX 公式',
    description: '展示公式文本资源的块级和行内排版能力。',
    icon: 'star',
    tag: '资源渲染',
    to: '/feature-showcase/latex-showcase',
    headerClass: 'bg-accent5-100',
    iconClass: 'text-accent5-700',
    titleClass: 'text-accent5-800',
    descriptionClass: 'text-accent5-700',
    tagClass: 'bg-accent5-200 text-accent5-800',
  },
  {
    title: 'Video 视频',
    description: '展示视频资源播放、封面、循环和填充策略。',
    icon: '全屏',
    tag: '资源渲染',
    to: '/feature-showcase/video-showcase',
    headerClass: 'bg-accent6-100',
    iconClass: 'text-accent6-700',
    titleClass: 'text-accent6-800',
    descriptionClass: 'text-accent6-700',
    tagClass: 'bg-accent6-200 text-accent6-800',
  },
  {
    title: 'DOM 连线',
    description: '展示基于真实 DOM 位置绘制连接线的高级运行时能力。',
    icon: '路由-copy',
    tag: '运行时能力',
    to: '/feature-showcase/connector-demo',
    headerClass: 'bg-accent2-100',
    iconClass: 'text-accent2-700',
    titleClass: 'text-accent2-800',
    descriptionClass: 'text-accent2-700',
    tagClass: 'bg-accent2-200 text-accent2-800',
  },
  {
    title: 'DataTable 表格',
    description: '展示 CSS Grid 表格的分层样式，以及 PPTX 原生表格导出入口。',
    icon: 'slider',
    tag: '运行时能力',
    to: '/feature-showcase/data-table-showcase',
    headerClass: 'bg-accent4-100',
    iconClass: 'text-accent4-700',
    titleClass: 'text-accent4-800',
    descriptionClass: 'text-accent4-700',
    tagClass: 'bg-accent4-200 text-accent4-800',
  },
]
</script>

<template>
  <DefaultCoverPage
    title="功能展示模块"
    subtitle="展示主题系统、资源渲染和运行时 DOM 组件"
  >
    <template #content>
      <div class="p-6">
        <div class="grid grid-cols-4 gap-5">
          <article
            v-for="card in cards"
            :key="card.to"
            class="overflow-hidden rounded-lg border border-border bg-background-subtle transition-all duration-300 hover:border-primary-300 hover:shadow-lg"
          >
            <div class="p-5" :class="card.headerClass">
              <div class="mb-3 flex items-center">
                <Icon :name="card.icon" class="mr-2 size-5" :class="card.iconClass" />
                <h3 class="font-heading text-lg font-semibold" :class="card.titleClass">
                  {{ card.title }}
                </h3>
              </div>
              <p class="font-body text-sm leading-relaxed" :class="card.descriptionClass">
                {{ card.description }}
              </p>
            </div>
            <div class="p-4">
              <div class="flex items-center justify-between gap-3">
                <span class="rounded-full px-3 py-1 text-xs font-medium" :class="card.tagClass">
                  {{ card.tag }}
                </span>
                <router-link
                  :to="card.to"
                  class="whitespace-nowrap text-sm font-medium text-link transition-colors hover:text-link-hover"
                >
                  查看展示 →
                </router-link>
              </div>
            </div>
          </article>
        </div>
      </div>
    </template>
  </DefaultCoverPage>
</template>
