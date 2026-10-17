<!-- 文件功能：隔离截图窗口的无导航画布，禁止整页过渡和演讲同步。 -->
<template>
  <main
    class="runtime-capture-layout" v-bind="executionAttrs"
    :style="{ width: `${appPageConfig.width}px`, height: `${appPageConfig.height}px` }">
    <RuntimePageStage disabled />
  </main>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { appPageConfig } from '@/core/utils/config'
import { executionAttributes, useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import RuntimePageStage from './RuntimePageStage.vue'

// 捕获/导出宿主使用 main.ts 初始化出的静态策略，不再从页面组件推导。
const execution = useRuntimeExecutionPolicy()
const executionAttrs = computed(() => executionAttributes(execution.value))
</script>
<style scoped>
.runtime-capture-layout { position: relative; overflow: hidden; }
</style>
