<!--
  文件用途：提供侧栏与底栏共用的页面缩略图导航项，统一预览画框、占位态、选中态和悬停动效。
-->

<template>
  <RouterLink
    :to="item.path"
    class="preview-thumbnail group block no-underline outline-none cursor-pointer rounded-xl text-gray-500"
    :class="{ 'preview-thumbnail--active text-blue-700': active }"
    :style="fillHeight ? previewFrameStyle : undefined"
    :title="item.title"
    :aria-current="active ? 'page' : undefined"
    :data-preview-thumbnail-path="item.path"
  >
    <div
      class="preview-thumbnail__frame rounded-lg overflow-hidden relative bg-white shadow-sm"
      :class="[fillHeight ? 'h-full' : 'w-full', active ? 'preview-thumbnail__frame--active ring-2 ring-blue-500 shadow-md -translate-y-0.5' : 'ring-1 ring-slate-200/80']"
      :style="previewFrameStyle"
    >
      <template v-if="componentPath">
        <ViewPreview :file-path="componentPath" />
      </template>
      <div
        v-else
        class="absolute inset-0 flex items-center justify-center p-2 text-center text-slate-400 text-xs text-wrap whitespace-normal bg-slate-50"
      >
        <span>{{ item.title }}</span>
      </div>
      <div
        class="absolute inset-0 z-20 bg-transparent"
        aria-hidden="true"
      ></div>
      <div
        class="absolute inset-0 z-10 bg-gradient-to-b from-transparent to-slate-900/5 pointer-events-none transition-colors group-hover:bg-black/5"
      ></div>
    </div>
  </RouterLink>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import ViewPreview from '@/runtime-shell/preview/ViewPreview.vue'
import type { MenuItem } from '@/core/types/menu'
import { DEFAULT_PAGE_CONFIG } from '@/core/utils/config'

interface Props {
  /** 缩略图对应的菜单项。 */
  item: MenuItem
  /** 是否匹配当前路由。 */
  active: boolean
  /** 页面画布尺寸，用于保持缩略图宽高比。 */
  pageConfig?: {
    width?: number
    height?: number
  }
  /** 是否以父容器高度作为缩略图主尺寸，底栏模式使用。 */
  fillHeight?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  pageConfig: () => ({}),
  fillHeight: false,
})

/**
 * 当前缩略图使用的画布尺寸。
 * @returns 合法的宽高配置；缺失时回退到默认页面尺寸
 */
const resolvedPageConfig = computed(() => {
  const width = Number(props.pageConfig?.width)
  const height = Number(props.pageConfig?.height)

  return {
    width: Number.isFinite(width) && width > 0 ? width : DEFAULT_PAGE_CONFIG.width,
    height: Number.isFinite(height) && height > 0 ? height : DEFAULT_PAGE_CONFIG.height,
  }
})

/**
 * 缩略图外框比例。
 * @returns 与页面设计稿一致的宽高比
 */
const previewFrameStyle = computed(() => ({
  aspectRatio: `${resolvedPageConfig.value.width} / ${resolvedPageConfig.value.height}`,
}))

/**
 * 解析菜单元数据中的页面组件路径。
 * @returns 可用于缩略预览的组件路径；缺失或类型不匹配时返回空字符串
 */
const componentPath = computed(() => {
  const value = props.item.meta?.componentPath
  return typeof value === 'string' ? value : ''
})
</script>

<style scoped>
.preview-thumbnail {
  transition:
    transform 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    background-color 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    box-shadow 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.preview-thumbnail__frame {
  transition:
    transform 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    box-shadow 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    border-color 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    background-color 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.preview-thumbnail:hover .preview-thumbnail__frame {
  transform: translateY(-0.125rem);
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
}

.preview-thumbnail:hover .preview-thumbnail__frame--active {
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.22);
}
</style>
