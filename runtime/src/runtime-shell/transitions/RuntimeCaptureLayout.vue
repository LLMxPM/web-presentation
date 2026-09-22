<!-- 文件功能：隔离截图窗口的无导航画布，禁止整页过渡和演讲同步。 -->
<template>
  <main class="runtime-capture-layout" :style="{ width: `${appPageConfig.width}px`, height: `${appPageConfig.height}px` }">
    <RuntimePageStage disabled />
  </main>
</template>
<script setup lang="ts">
import { appPageConfig } from '@/core/utils/config'
import RuntimePageStage from './RuntimePageStage.vue'
</script>
<style scoped>
.runtime-capture-layout { position: relative; overflow: hidden; }
</style>
