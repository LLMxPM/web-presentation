<!--
  文件用途：三维模型（GLB）内部渲染器，负责懒加载 Three.js、按实例独立取景、生命周期与状态探针。
  根节点声明 data-runtime-model-state/message 与 data-runtime-kit-media 契约，供首帧探针与 PPTX 导出识别，勿删。
-->

<template>
  <div
    v-bind="$attrs"
    ref="viewerRoot"
    class="model-viewer"
    :class="{
      'model-viewer--loading': state === 'loading',
      'model-viewer--error': state === 'error',
      'model-viewer--interactive': interactive,
    }"
    :data-runtime-model-state="state"
    :data-runtime-model-message="stateMessage"
    data-runtime-kit-media="v1"
    data-runtime-kit-media-kind="model3d"
  >
    <div v-if="state === 'loading'" class="model-viewer__loading">
      <span class="model-viewer__loading-text">正在加载三维模型...</span>
    </div>

    <div v-if="state === 'error'" class="model-viewer__error">
      <span class="model-viewer__error-message">{{ fallbackMessage }}</span>
      <span v-if="stateMessage" class="model-viewer__error-detail">{{ stateMessage }}</span>
    </div>

    <div ref="surfaceRef" class="model-viewer__surface" :class="{ 'model-viewer__surface--hidden': state !== 'ready' }"></div>
  </div>
</template>

<script setup lang="ts">
import type { ModelViewerProps } from './model3d/viewer-types'
import { DEFAULT_MODEL_FALLBACK_MESSAGE } from './model3d/view-options'
import { useModelViewer } from './model3d/viewer-controller'
defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<ModelViewerProps>(), {
  name: '',
  src: '',
  sceneIndex: undefined,
  cameraIndex: undefined,
  cameraPosition: undefined,
  cameraTarget: undefined,
  cameraFov: undefined,
  background: 'transparent',
  lighting: 'auto',
  interactive: false,
  fallback: DEFAULT_MODEL_FALLBACK_MESSAGE,
})

const { viewerRoot, surfaceRef, state, stateMessage, fallbackMessage, captureStaticFrame, reload } = useModelViewer(props)
defineExpose({ captureStaticFrame, reload })
</script>

<style scoped>
.model-viewer {
  position: relative;
  box-sizing: border-box;
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.model-viewer--interactive {
  cursor: grab;
}

.model-viewer__surface {
  position: absolute;
  inset: 0;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.model-viewer__surface :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

.model-viewer__surface--hidden {
  visibility: hidden;
}

.model-viewer__loading,
.model-viewer__error {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px;
  text-align: center;
}

.model-viewer__loading {
  background: rgba(248, 250, 252, 0.82);
  color: #64748b;
  font-size: 13px;
}

.model-viewer__error {
  background: #f8fafc;
  color: #64748b;
  font-size: 13px;
}

.model-viewer__error-message {
  color: #475569;
  font-weight: 600;
}

.model-viewer__error-detail {
  max-width: 100%;
  color: #94a3b8;
  font-size: 12px;
  word-break: break-word;
}
</style>
