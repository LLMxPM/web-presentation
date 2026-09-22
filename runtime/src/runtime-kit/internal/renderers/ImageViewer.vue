<!--
  文件用途：图片资源基础渲染器，负责统一图片展示、渲染区域样式与解析失败兜底。
-->
<template>
  <figure class="image-viewer" :style="surfaceStyle" v-bind="$attrs">
    <img v-if="src" :src="src" :alt="alt" class="image-viewer__image" :style="imageStyle" />
    <slot v-else name="fallback">
      <span v-if="showFallbackPlaceholder" class="image-viewer__placeholder" aria-hidden="true" />
    </slot>
  </figure>
</template>

<script setup lang="ts">
import { computed, type CSSProperties } from 'vue'
import { useViewerSurfaceStyle, type ViewerSurfaceProps } from '@runtime-kit/internal/utils/viewer-style'

interface Props extends ViewerSurfaceProps {
  /** 图片可访问地址 */
  src?: string
  /** 图片 alt 属性 */
  alt?: string
  /** 图片填充方式 */
  fit?: CSSProperties['objectFit']
  /** 图片定位方式 */
  position?: CSSProperties['objectPosition']
  /** 缺少 src 时是否展示占位 */
  showFallbackPlaceholder?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  src: '',
  alt: '',
  fit: 'contain',
  position: 'center',
  showFallbackPlaceholder: true,
})

const surfaceStyle = useViewerSurfaceStyle(props)
const imageStyle = computed<CSSProperties>(() => ({
  width: '100%',
  height: '100%',
  objectFit: props.fit,
  objectPosition: props.position,
}))
</script>

<style scoped>
.image-viewer {
  box-sizing: border-box;
  display: block;
  max-width: 100%;
  margin: 0;
  overflow: hidden;
}

.image-viewer__image {
  display: block;
  max-width: 100%;
}

.image-viewer__placeholder {
  display: block;
  width: 100%;
  min-height: 120px;
  background-color: #f1f5f9;
  border-radius: 4px;
}
</style>
