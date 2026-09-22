<!--
  文件用途：为编辑器 iframe 提供通用单页预览壳层，按传入设计尺寸等比缩放页面组件。
-->

<template>
  <main class="standalone-preview-view">
    <ViewPreview
      :file-path="filePath"
      :design-width="designWidth"
      :design-height="designHeight"
      :inert="false"
      @state-change="handlePreviewStateChange"
    />
  </main>
</template>

<script setup lang="ts">
/**
 * 文件用途：承接 runtime 单页预览路由，避免直接渲染页面组件导致 iframe 中只显示局部区域。
 */

import ViewPreview from '@/runtime-shell/preview/ViewPreview.vue'
import {
  PAGE_PREVIEW_ERROR_EVENT,
  PAGE_PREVIEW_READY_EVENT,
  type PagePreviewErrorMessage,
  type PagePreviewReadyMessage,
} from '@/core/shared/page-preview'
import { getRuntimePreviewContext } from '@/core/utils/path'

defineProps<{
  /** 页面逻辑路径，例如 src/views/foo/bar.vue */
  filePath: string
  /** 设计稿宽度，未传时回退到项目配置。 */
  designWidth?: number
  /** 设计稿高度，未传时回退到项目配置。 */
  designHeight?: number
}>()

/**
 * 把单页模块的最终状态回传给 Editor；loading 不作为 iframe 终态发送，empty 归一化为错误。
 * @param payload ViewPreview 回传的状态
 */
function handlePreviewStateChange(payload: {
  state: 'loading' | 'ready' | 'error' | 'empty'
  message: string
}): void {
  const artifactId = getRuntimePreviewContext()?.artifactId
  if (!artifactId || typeof window === 'undefined' || !window.parent) {
    return
  }

  if (payload.state === 'ready') {
    const message: PagePreviewReadyMessage = {
      type: PAGE_PREVIEW_READY_EVENT,
      payload: { version: 1, artifactId },
    }
    window.parent.postMessage(message, resolveParentOrigin() || '*')
    return
  }

  if (payload.state === 'error' || payload.state === 'empty') {
    const message: PagePreviewErrorMessage = {
      type: PAGE_PREVIEW_ERROR_EVENT,
      payload: {
        version: 1,
        artifactId,
        message: payload.message || '页面预览加载失败。',
      },
    }
    window.parent.postMessage(message, resolveParentOrigin() || '*')
  }
}

/**
 * 尝试从 referrer 解析 Editor 来源；跨域 referrer 被裁剪时由父窗口继续做来源校验。
 */
function resolveParentOrigin(): string {
  try {
    return document.referrer ? new URL(document.referrer).origin : ''
  } catch {
    return ''
  }
}
</script>

<style scoped>
.standalone-preview-view {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8fafc;
}
</style>
