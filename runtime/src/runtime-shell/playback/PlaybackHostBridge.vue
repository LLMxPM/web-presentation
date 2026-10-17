<!-- 文件功能：在放映主画布宿主中接入调度链路，并显示自动放映的可见错误。 -->
<template>
  <div v-if="errorMessage" class="runtime-playback-error" role="alert">{{ errorMessage }}</div>
</template>
<script setup lang="ts">
import { usePlaybackHost } from './usePlaybackHost'

// 控制条与开始/暂停入口由 WP16 接入，这里只建立调度并暴露错误状态。
const { errorMessage } = usePlaybackHost()
</script>
<style scoped>
.runtime-playback-error {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10000;
  padding: 12px 20px;
  background: #fff;
  color: #b91c1c;
  border: 1px solid #fecaca;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgb(15 23 42 / 12%);
  font-size: 14px;
}
</style>
