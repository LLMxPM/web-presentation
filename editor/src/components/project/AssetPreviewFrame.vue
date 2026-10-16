<!-- 文件功能：封装工作空间资源的 Runtime iframe 预览、背景切换、加载态与错误态展示。 -->
<template>
  <section class="relative flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-surface">
    <AssetPreviewBackgroundControl
      v-if="asset"
      v-model="previewBackground"
      class="absolute right-3 top-3 z-10 w-[148px] shadow-sm"
    />
    <div v-if="loading" class="flex min-h-0 flex-1 items-center justify-center text-sm font-semibold text-text-disabled">
      正在创建资源预览...
    </div>
    <div v-else-if="errorMessage" class="flex min-h-0 flex-1 items-center justify-center p-6 text-center">
      <div class="max-w-sm">
        <p class="text-sm font-bold text-danger">资源预览打开失败</p>
        <p class="mt-2 text-xs leading-6 text-text-muted">{{ errorMessage }}</p>
        <UiButton class="mt-3" size="sm" @click="loadPreview()">重新生成预览</UiButton>
      </div>
    </div>
    <RuntimePreviewFrame
      v-else
      auto-recover
      :recovery-key="`${workspaceId}:${asset?.id ?? ''}`"
      :artifact-id="previewArtifactId"
      :frame-url="previewFrameUrl"
      :title="previewTitle"
      layout="fill"
      container-class="min-h-0 flex-1 overflow-hidden bg-surface"
      iframe-class="block h-full w-full bg-surface"
      empty-content-class="flex h-full items-center justify-center px-8 text-center"
      empty-title="请选择资源"
      empty-description="资源预览会在这里打开。"
      @retry="loadPreview(true)"
      @renew="handleRenew"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { createAssetPreviewArtifact } from '@/api/preview'
import RuntimePreviewFrame from '@/components/runtime-preview/RuntimePreviewFrame.vue'
import AssetPreviewBackgroundControl from '@/components/ui/AssetPreviewBackgroundControl.vue'
import type { AssetPreviewBackground } from '@/components/ui/asset-preview-background'
import type { AssetResponse } from '@/types/api'
import { getErrorMessage } from '@/api/http'
import { UiButton } from '@/components/ui'

type AssetPreviewTarget = Pick<AssetResponse, 'id' | 'name'> & Partial<Pick<AssetResponse, 'file_hash'>>

const props = defineProps<{
  workspaceId: number | null
  asset: AssetPreviewTarget | null
}>()

const loading = ref(false)
const errorMessage = ref('')
const previewUrl = ref('')
const previewArtifactId = ref('')
let previewRequestSequence = 0
const previewRefreshToken = ref(0)
const previewBackground = ref<AssetPreviewBackground>('checker')

const previewTitle = computed(() => props.asset ? `资源预览：${props.asset.name}` : '资源预览')
const previewFrameUrl = computed(() => {
  if (!previewUrl.value) return ''
  try {
    const url = new URL(previewUrl.value)
    url.searchParams.set('t', String(previewRefreshToken.value))
    url.searchParams.set('preview_background', previewBackground.value)
    return url.toString()
  } catch {
    return ''
  }
})

watch(
  () => [
    props.workspaceId,
    props.asset?.id ?? null,
    props.asset?.file_hash ?? props.asset?.id ?? '',
  ],
  () => {
    void loadPreview()
  },
  { immediate: true },
)

/**
 * 根据当前资源创建一次 Runtime 预览 artifact，并刷新 iframe 地址。
 */
async function loadPreview(recovering = false): Promise<void> {
  const sequence = ++previewRequestSequence
  const workspaceId = props.workspaceId
  const assetId = props.asset?.id
  if (!recovering) previewUrl.value = ''
  errorMessage.value = ''
  if (!workspaceId || !assetId) {
    previewArtifactId.value = ''
    loading.value = false
    return
  }

  loading.value = !recovering
  try {
    const response = await createAssetPreviewArtifact(workspaceId, assetId)
    if (sequence !== previewRequestSequence) return
    previewUrl.value = response.preview_url
    previewArtifactId.value = response.artifact_id
    previewRefreshToken.value = Date.now()
  } catch (error) {
    if (sequence === previewRequestSequence) errorMessage.value = getErrorMessage(error, '创建资源预览失败')
  } finally {
    if (sequence === previewRequestSequence) loading.value = false
  }
}

/** 续签成功后写回 previewUrl，使 previewFrameUrl 计算属性与 iframe 保持一致。 */
function handleRenew(newUrl: string): void {
  previewUrl.value = newUrl
}
</script>
