<!-- 文件功能：观众窗口的画布缩放适配，内容复用普通模式的页面过渡宿主。 -->
<template>
  <div ref="container" class="presenter-page-stage">
    <ScaledCanvasViewport :scale="scale" :design-width="appPageConfig.width" :design-height="appPageConfig.height" :is-fullscreen="false">
      <RuntimePageStage />
    </ScaledCanvasViewport>
  </div>
</template>
<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { appPageConfig } from '@/core/utils/config'
import ScaledCanvasViewport from '@runtime-kit/internal/components/viewport/ScaledCanvasViewport.vue'
import RuntimePageStage from '../transitions/RuntimePageStage.vue'
const container = ref<HTMLElement>()
const scale = ref(1)
let observer: ResizeObserver | undefined
/** 仅调整外层画布缩放，不改变过渡层的位移。 */
function resize(): void {
  if (container.value) scale.value = Math.min(container.value.clientWidth / appPageConfig.value.width, container.value.clientHeight / appPageConfig.value.height)
}
onMounted(() => { resize(); observer = new ResizeObserver(resize); if (container.value) observer.observe(container.value) })
onBeforeUnmount(() => observer?.disconnect())
</script>
<style scoped>
.presenter-page-stage { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; overflow: hidden; }
</style>
