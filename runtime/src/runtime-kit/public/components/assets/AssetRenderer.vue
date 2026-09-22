<!--
  文件用途：按 manifest 资源元数据统一分发内容资源渲染组件。
-->
<template>
  <component
    :is="rendererComponent"
    v-if="rendererComponent && canRender"
    v-bind="{ ...rendererProps, ...$attrs }"
  />
  <slot v-else name="fallback">
    <div class="asset-renderer__fallback" :style="fallbackStyle">
      {{ fallbackMessage }}
    </div>
  </slot>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAssetMetadata } from '@/core/composables/useAsset'
import AssetChart from '@runtime-kit/public/components/assets/AssetChart.v1.vue'
import AssetDrawio from '@runtime-kit/public/components/assets/AssetDrawio.v1.vue'
import AssetFormula from '@runtime-kit/public/components/assets/AssetFormula.v1.vue'
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'
import AssetMermaid from '@runtime-kit/public/components/assets/AssetMermaid.v1.vue'
import AssetVideo from '@runtime-kit/public/components/assets/AssetVideo.v1.vue'
import { buildViewerSurfaceStyle, type ViewerSurfaceProps } from '@runtime-kit/internal/utils/viewer-style'

type AssetRenderType = 'image' | 'drawio' | 'mermaid' | 'chart' | 'formula' | 'video'

interface Props extends ViewerSurfaceProps {
  /** 资源逻辑名 `asset.name` */
  name: string
  /** 显式期望渲染类型；传入后会和 manifest 元数据进行校验 */
  type?: AssetRenderType
  /** 未命中 manifest 时的兜底 URL */
  fallback?: string
}

const props = defineProps<Props>()
const metadata = useAssetMetadata(() => props.name)

const renderType = computed(() => metadata.value?.render_type)
const rendererComponent = computed(() => {
  switch (renderType.value) {
    case 'image':
      return AssetImage
    case 'drawio':
      return AssetDrawio
    case 'mermaid':
      return AssetMermaid
    case 'chart':
      return AssetChart
    case 'formula':
      return AssetFormula
    case 'video':
      return AssetVideo
    default:
      return null
  }
})

const rendererProps = computed(() => ({
  name: props.name,
  fallback: props.fallback,
  width: props.width,
  height: props.height,
  minHeight: props.minHeight,
  backgroundColor: props.backgroundColor,
  showBorder: props.showBorder,
  borderColor: props.borderColor,
  borderWidth: props.borderWidth,
  borderStyle: props.borderStyle,
  borderRadius: props.borderRadius,
  padding: props.padding,
}))

const canRender = computed(() => {
  if (!metadata.value) return false
  if (!props.type) return true
  return renderType.value === props.type
})

const fallbackMessage = computed(() => {
  if (!metadata.value) {
    return `资源未找到：${props.name}`
  }
  if (props.type && renderType.value !== props.type) {
    return `资源类型不匹配：期望 ${props.type}，实际 ${renderType.value || 'unknown'}`
  }
  return `暂不支持的资源类型：${renderType.value || 'unknown'}`
})

const fallbackStyle = computed(() => buildViewerSurfaceStyle({
  width: props.width || '100%',
  height: props.height,
  minHeight: props.minHeight || '80px',
  backgroundColor: props.backgroundColor || '#f8fafc',
  showBorder: props.showBorder ?? true,
  borderColor: props.borderColor || '#cbd5e1',
  borderWidth: props.borderWidth ?? '1px',
  borderStyle: props.borderStyle || 'dashed',
  borderRadius: props.borderRadius ?? '8px',
  padding: props.padding ?? '12px',
}))
</script>

<style scoped>
.asset-renderer__fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 13px;
}
</style>
