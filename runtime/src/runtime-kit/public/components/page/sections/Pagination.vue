<!--
  文件用途：页码展示组件，根据路由顺序计算当前页和总页数。
-->

<template>
  <div
    class="inline-flex items-center gap-1 px-3 py-1 text-sm font-medium rounded-md bg-bg-subtle transition-all duration-300">
    <span v-if="prefix" class="mx-1 text-invert">{{ prefix }}</span>
    <span class="text-secondary">{{ displayCurrentPage }}</span>
    <template v-if="showTotal">
      <span class="mx-1 text-secondary">{{ separator }}</span>
      <span class="text-secondary">{{ displayTotalPages }}</span>
    </template>
    <span v-if="suffix" class="mx-1 text-invert">{{ suffix }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  getPageNumberByPath,
  getMaxPageNumber
} from '@/core/utils/route-generator'

/**
 * 页码组件 Props
 */
interface Props {
  /** 手动模式：当前页码（传入则启用手动模式） */
  currentPage?: number
  /** 手动模式：总页数（传入则启用手动模式） */
  totalPages?: number
  /** 页码分隔符 */
  separator?: string
  /** 是否显示总页数 */
  showTotal?: boolean
  /** 页码前缀文字 */
  prefix?: string
  /** 页码后缀文字 */
  suffix?: string
}

const props = withDefaults(defineProps<Props>(), {
  currentPage: undefined,
  totalPages: undefined,
  separator: '/',
  showTotal: true,
  prefix: '',
  suffix: '',
})

const route = useRoute()

/**
 * 判断是否为手动模式
 * 当传入currentPage或totalPages时启用手动模式
 */
const isManualMode = computed(() => {
  return props.currentPage !== undefined || props.totalPages !== undefined
})



/**
 * 自动模式下的当前页码（直接从路由配置获取）
 */
const autoCurrentPage = computed(() => {
  if (isManualMode.value) return 1

  // 直接使用 route-generator.ts 提供的函数获取当前页码
  const currentPageNumber = getPageNumberByPath(route.path)
  return currentPageNumber || 1
})

/**
 * 自动模式下的总页数（直接从路由配置获取最大页码）
 */
const autoTotalPages = computed(() => {
  if (isManualMode.value) return 1

  // 直接使用 route-generator.ts 提供的函数获取最大页码
  const maxPageNumber = getMaxPageNumber()
  return Math.max(1, maxPageNumber)
})

/**
 * 显示的当前页码（手动模式优先，否则使用自动模式）
 */
const displayCurrentPage = computed(() => {
  if (props.currentPage !== undefined) {
    return Math.max(1, props.currentPage)
  }
  return autoCurrentPage.value
})

/**
 * 显示的总页数（手动模式优先，否则使用自动模式）
 */
const displayTotalPages = computed(() => {
  if (props.totalPages !== undefined) {
    return Math.max(1, props.totalPages)
  }
  return autoTotalPages.value
})
</script>

<style scoped>
/* 所有样式都通过Tailwind类实现 */
</style>
