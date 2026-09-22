<!--
  文件用途：AssetChart — 基于 manifest 资源名称加载并渲染 ECharts option 配置。
-->
<template>
  <EchartsViewer v-if="canRender" :content="resolvedContent" v-bind="$attrs" />
  <div v-else class="asset-chart__fallback" v-bind="$attrs">{{ fallbackMessage }}</div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAssetSrc } from '@runtime-kit/public/composables/assets/useAssetSrc.v1'
import EchartsViewer from '@runtime-kit/internal/renderers/EchartsViewer.vue'
import {
  DEFAULT_ASSET_FALLBACK_MESSAGE,
  resolveAssetFallbackMessage,
  resolveAssetFallbackUrl,
} from '@runtime-kit/internal/utils/asset-fallback'

interface Props {
  /** 资源的逻辑名 `asset.name` */
  name?: string
  /** 可直接渲染的 ECharts option JSON 或 JS 对象表达式 */
  content?: string
  /** 无法渲染时展示的兜底文案；URL 值仍可作为兼容资源地址 */
  fallback?: string
}

const props = withDefaults(defineProps<Props>(), {
  name: '',
  content: '',
  fallback: DEFAULT_ASSET_FALLBACK_MESSAGE,
})

const directContent = computed(() => props.content.trim())
const fallbackUrl = computed(() => resolveAssetFallbackUrl(props.fallback))
const fallbackMessage = computed(() => resolveAssetFallbackMessage(props.fallback, 'Chart 资源无法渲染，请检查资源名称或 ECharts option 内容。'))
const src = useAssetSrc(() => directContent.value ? '' : props.name, () => fallbackUrl.value)
const fetchedContent = ref('')
const resolvedContent = computed(() => directContent.value || fetchedContent.value)
const canRender = computed(() => Boolean(resolvedContent.value || src.value))

watch(src, async (nextSrc) => {
  fetchedContent.value = ''
  if (directContent.value) return
  if (!nextSrc) return
  try {
    const response = await fetch(nextSrc)
    if (!response.ok) {
      fetchedContent.value = ''
      return
    }
    fetchedContent.value = await response.text()
  } catch {
    fetchedContent.value = ''
  }
}, { immediate: true })
</script>

<style scoped>
.asset-chart__fallback {
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
