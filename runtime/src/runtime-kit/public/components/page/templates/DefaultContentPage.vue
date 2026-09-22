<!--
  文件用途：默认内容页容器，按当前页面画布尺寸自适应分配头部、正文和页脚区域。
-->

<template>
  <DefaultContainer>
    <!-- 标题区域 -->
    <HeaderSection
      :title="title"
      :subtitle="subtitle"
      :title-size="headerTitleSize"
      :subtitle-size="headerSubtitleSize"
      :padding="sectionPadding"
      :show-bottom-border="true"
      :logo-config="'theme'"
      :align="'left'"
      :height="headerHeight"
    />
    
    <!-- 内容区域 -->
    <div class="flex-1  text-primary " :style="contentStyle">
      <slot name="content">
        <div class="w-full h-full flex items-center justify-center">
          <p class="font-body text-lg text-secondary">这里是默认内容区域，可以通过slot自定义内容</p>
        </div>
      </slot>
    </div>
    
    <!-- 页脚区域 -->
    <FooterSection
      :text-size="'medium'"
      :align="'left'"
      :padding="sectionPadding"
      :show-top-border="true"
      :show-pagination="true"
      :height="footerHeight"
      link="https://github.com/LLMxPM/web-runtime-vue"
      link-text=" web-runtime-vue"
      icon="Github"
    />
  </DefaultContainer>
</template>

<script setup lang="ts">
import { computed, type CSSProperties } from 'vue'
import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'
import HeaderSection from '../sections/HeaderSection.vue'
import FooterSection from '../sections/FooterSection.vue'
import { appPageConfig } from '@/core/utils/config'

const BASE_PAGE_HEIGHT = 1080
const BASE_HEADER_HEIGHT = 100
const BASE_FOOTER_HEIGHT = 50
const BASE_CONTENT_PADDING = 30
const BASE_SECTION_PADDING = 20
const BASE_HEADER_TITLE_SIZE = 40
const BASE_HEADER_SUBTITLE_SIZE = 20

/**
 * 默认内容页面组件。
 * 主要职责：
 * 1. 基于统一页面尺寸生成标准内容页结构；
 * 2. 按旧版 1080 高度基线等比推导头部、正文内边距和页脚尺寸；
 * 3. 避免正文区依赖固定 930px 高度。
 */
defineOptions({
  name: 'DefaultContentPage'
})

/**
 * 组件属性定义
 */
interface Props {
  /** 页面标题文字 */
  title?: string
  /** 页面副标题文字,可选,默认为空 */
  subtitle?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '默认标题',
  subtitle: '',
})
void props

/**
 * 将旧版基线尺寸按当前页面高度等比缩放。
 * @param baseValue 基线像素值
 * @returns 当前画布下的像素值，最小为 1
 */
function scaleByPageHeight(baseValue: number): number {
  return Math.max(1, Math.round((appPageConfig.value.height / BASE_PAGE_HEIGHT) * baseValue))
}

/**
 * 头部区域高度，随页面高度等比变化。
 */
const headerHeight = computed(() => scaleByPageHeight(BASE_HEADER_HEIGHT))

/**
 * 页脚区域高度，随页面高度等比变化。
 */
const footerHeight = computed(() => scaleByPageHeight(BASE_FOOTER_HEIGHT))

/**
 * 正文区域内边距，随页面高度等比变化。
 */
const contentPadding = computed(() => scaleByPageHeight(BASE_CONTENT_PADDING))

/**
 * 头尾区域统一内边距，随页面高度等比变化。
 */
const sectionPadding = computed(() => scaleByPageHeight(BASE_SECTION_PADDING))

/**
 * 标题字号，随页面高度等比变化。
 */
const headerTitleSize = computed(() => scaleByPageHeight(BASE_HEADER_TITLE_SIZE))

/**
 * 副标题字号，随页面高度等比变化。
 */
const headerSubtitleSize = computed(() => scaleByPageHeight(BASE_HEADER_SUBTITLE_SIZE))

/**
 * 计算内容区域样式。
 * 输出：
 * 1. 使用 flex 自动填满头尾之外剩余空间；
 * 2. 内容超出时保留滚动能力；
 * 3. 不再写死高度为 930px。
 */
const contentStyle = computed((): CSSProperties => ({
  minHeight: '0',
  padding: `${contentPadding.value}px`,
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'flex-start',
  alignItems: 'stretch',
  overflow: 'auto'
}))
</script>

<style scoped>
/* 组件特定样式 */
</style>
