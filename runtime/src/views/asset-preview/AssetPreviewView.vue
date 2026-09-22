<!--
  文件用途：提供资源预览宿主页，按 Backend 下发的 asset_preview 配置复用 Runtime 渲染器展示单个资源。
-->
<template>
  <main
    class="asset-preview-view"
    :class="`asset-preview-view--${previewBackground}`"
    :data-preview-background="previewBackground"
  >
    <div v-if="!assetConfig" class="asset-preview-view__state">
      资源预览配置缺失。
    </div>
    <AssetImage
      v-else-if="isImageLike"
      :name="assetConfig.name"
      :fallback="assetConfig.url || ''"
      :alt="assetConfig.original_name"
      width="100%"
      height="100%"
      min-height="0"
      fit="contain"
      :background-color="rendererBackgroundColor"
    />
    <AssetDrawio
      v-else-if="renderType === 'drawio'"
      :name="assetConfig.name"
      :fallback="assetConfig.url || ''"
      width="100%"
      height="100%"
      min-height="0"
      :background-color="rendererBackgroundColor"
      :show-border="false"
    />
    <AssetMermaid
      v-else-if="renderType === 'mermaid'"
      :name="assetConfig.name"
      :fallback="assetConfig.url || ''"
      width="100%"
      height="100%"
      min-height="0"
      :background-color="rendererBackgroundColor"
      :show-border="false"
    />
    <AssetChart
      v-else-if="renderType === 'chart'"
      :name="assetConfig.name"
      :fallback="assetConfig.url || ''"
      width="100%"
      height="100%"
      min-height="0"
      :background-color="rendererBackgroundColor"
      :show-border="false"
    />
    <AssetFormula
      v-else-if="renderType === 'formula'"
      :name="assetConfig.name"
      :fallback="assetConfig.url || ''"
      width="100%"
      height="100%"
      min-height="0"
      :background-color="rendererBackgroundColor"
      :show-border="false"
      :display-mode="true"
    />
    <AssetVideo
      v-else-if="renderType === 'video'"
      :name="assetConfig.name"
      :fallback="assetConfig.url || ''"
      width="100%"
      height="100%"
      min-height="0"
      background-color="#000000"
      :show-border="false"
      controls
    />
    <div v-else class="asset-preview-view__state">
      暂不支持预览该资源类型：{{ renderType || 'unknown' }}
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getRuntimePreloadedConfig } from '@/core/utils/path'
import AssetChart from '@runtime-kit/public/components/assets/AssetChart.v1.vue'
import AssetDrawio from '@runtime-kit/public/components/assets/AssetDrawio.v1.vue'
import AssetFormula from '@runtime-kit/public/components/assets/AssetFormula.v1.vue'
import AssetImage from '@runtime-kit/public/components/assets/AssetImage.v1.vue'
import AssetMermaid from '@runtime-kit/public/components/assets/AssetMermaid.v1.vue'
import AssetVideo from '@runtime-kit/public/components/assets/AssetVideo.v1.vue'
import {
  normalizeAssetPreviewBackground,
  resolveAssetPreviewRendererBackground,
} from './asset-preview-background'

const assetConfig = computed(() => getRuntimePreloadedConfig()?.asset_preview ?? null)
const previewBackground = computed(() => normalizeAssetPreviewBackground(
  new URLSearchParams(window.location.search).get('preview_background'),
))
const rendererBackgroundColor = computed(() => resolveAssetPreviewRendererBackground(previewBackground.value))
const renderType = computed(() => String(assetConfig.value?.render_type || '').trim())
const contentType = computed(() => String(assetConfig.value?.content_type || '').split(';', 1)[0].trim().toLowerCase())
const originalName = computed(() => String(assetConfig.value?.original_name || '').trim().toLowerCase())
const isImageLike = computed(() => (
  renderType.value === 'image'
  || (renderType.value === 'icon' && (contentType.value.startsWith('image/') || /\.(svg|png|jpe?g|webp|gif)$/i.test(originalName.value)))
))
</script>

<style scoped>
.asset-preview-view {
  box-sizing: border-box;
  width: 100vw;
  height: 100vh;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.asset-preview-view--light {
  background: #ffffff;
}

.asset-preview-view--dark {
  background: #0f172a;
}

.asset-preview-view--checker {
  background-color: #ffffff;
  background-image:
    linear-gradient(45deg, #e2e8f0 25%, transparent 25%),
    linear-gradient(-45deg, #e2e8f0 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #e2e8f0 75%),
    linear-gradient(-45deg, transparent 75%, #e2e8f0 75%);
  background-position: 0 0, 0 8px, 8px -8px, -8px 0;
  background-size: 16px 16px;
}

.asset-preview-view__state {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  padding: 24px;
  color: #64748b;
  font-size: 14px;
  text-align: center;
}
</style>
