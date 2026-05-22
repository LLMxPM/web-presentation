<!-- 文件功能：封装工作空间资源的 Runtime iframe 预览创建、加载态与错误态展示。 -->
<template>
  <section class="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white">
    <div v-if="loading" class="flex min-h-0 flex-1 items-center justify-center text-sm font-semibold text-slate-400">
      正在创建资源预览...
    </div>
    <div v-else-if="errorMessage" class="flex min-h-0 flex-1 items-center justify-center p-6 text-center">
      <div class="max-w-sm">
        <p class="text-sm font-bold text-rose-600">资源预览打开失败</p>
        <p class="mt-2 text-xs leading-6 text-slate-500">{{ errorMessage }}</p>
      </div>
    </div>
    <RuntimePreviewFrame
      v-else
      :frame-url="previewFrameUrl"
      :title="previewTitle"
      layout="fill"
      container-class="min-h-0 flex-1 overflow-hidden bg-white"
      iframe-class="block h-full w-full bg-white"
      empty-content-class="flex h-full items-center justify-center px-8 text-center"
      empty-title="请选择资源"
      empty-description="资源预览会在这里打开。"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { createAssetPreviewArtifact } from '@/api/preview'
import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import type { AssetResponse } from '@/types/api'
import { getErrorMessage } from '@/api/http'

const props = defineProps<{
  workspaceId: number | null
  asset: AssetResponse | null
}>()

const loading = ref(false)
const errorMessage = ref('')
const previewUrl = ref('')
const previewRefreshToken = ref(0)

const previewTitle = computed(() => props.asset ? `资源预览：${props.asset.name}` : '资源预览')
const previewFrameUrl = computed(() => {
  if (!previewUrl.value) return ''
  try {
    const url = new URL(previewUrl.value)
    url.searchParams.set('t', String(previewRefreshToken.value))
    return url.toString()
  } catch {
    return ''
  }
})

watch(
  () => [
    props.workspaceId,
    props.asset?.id ?? null,
    props.asset?.file_hash ?? '',
  ],
  () => {
    void loadPreview()
  },
  { immediate: true },
)

/**
 * 根据当前资源创建一次 Runtime 预览 artifact，并刷新 iframe 地址。
 */
async function loadPreview(): Promise<void> {
  previewUrl.value = ''
  errorMessage.value = ''
  if (!props.workspaceId || !props.asset) {
    loading.value = false
    return
  }

  loading.value = true
  try {
    const response = await createAssetPreviewArtifact(props.workspaceId, props.asset.id)
    previewUrl.value = response.preview_url
    previewRefreshToken.value = Date.now()
  } catch (error) {
    errorMessage.value = getErrorMessage(error, '创建资源预览失败')
  } finally {
    loading.value = false
  }
}
</script>
