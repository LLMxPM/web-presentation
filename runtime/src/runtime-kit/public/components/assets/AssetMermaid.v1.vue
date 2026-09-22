<!--
  文件用途：AssetMermaid — 基于 manifest 资源名称渲染 Backend 托管的 Mermaid 图表。
  传入 name（asset.name）即可，workspaceId 和路径解析由内部自动完成。
-->
<template>
  <MermaidViewer v-if="canRender" :src="content ? '' : src" :content="content" v-bind="$attrs" />
  <div v-else class="asset-mermaid__fallback" v-bind="$attrs">{{ fallbackMessage }}</div>
</template>

<script setup lang="ts">
/**
 * AssetMermaid
 *
 * 使用示例：
 *   <AssetMermaid name="sequence" />
 *
 * Props:
 *   name     — 资源的逻辑名 `asset.name`；与 content 二选一
 *   content  — 可直接渲染的 Mermaid 源码；与 name 二选一
 *   fallback — 无法渲染时展示的兜底文案；URL 值仍可作为兼容资源地址
 */
import { computed } from 'vue'
import { useAssetSrc } from '@runtime-kit/public/composables/assets/useAssetSrc.v1'
import MermaidViewer from '@runtime-kit/internal/renderers/MermaidViewer.vue'
import {
  DEFAULT_ASSET_FALLBACK_MESSAGE,
  resolveAssetFallbackMessage,
  resolveAssetFallbackUrl,
} from '@runtime-kit/internal/utils/asset-fallback'

interface Props {
  /** 资源的逻辑名 `asset.name` */
  name?: string
  /** 可直接渲染的 Mermaid 源码 */
  content?: string
  /** 无法渲染时展示的兜底文案；URL 值仍可作为兼容资源地址 */
  fallback?: string
}

const props = withDefaults(defineProps<Props>(), {
  name: '',
  content: '',
  fallback: DEFAULT_ASSET_FALLBACK_MESSAGE,
})

const content = computed(() => props.content.trim())
const fallbackUrl = computed(() => resolveAssetFallbackUrl(props.fallback))
const fallbackMessage = computed(() => resolveAssetFallbackMessage(props.fallback, 'Mermaid 资源无法渲染，请检查资源名称或图表源码。'))
const src = useAssetSrc(() => content.value ? '' : props.name, () => fallbackUrl.value)
const canRender = computed(() => Boolean(content.value || src.value))
</script>

<style scoped>
.asset-mermaid__fallback {
  box-sizing: border-box;
  display: flex;
  width: 100%;
  min-height: 120px;
  align-items: center;
  justify-content: center;
  padding: 12px;
  color: #64748b;
  font-size: 13px;
  text-align: center;
  background: #f8fafc;
}
</style>
