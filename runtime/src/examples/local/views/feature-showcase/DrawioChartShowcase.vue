<template>
  <DefaultContentPage 
    title="Draw.io 图表演示"
    subtitle="可以直接渲染drawio文件"
  >
    <template #content>
      <div class="p-4">
        <div class="bg-white border border-border rounded-lg p-4 flex flex-col items-center">
          <DrawioViewer
            :src="sampleDrawioUrl"
            width="700px"
            height="700px"
          />
        </div>
        <h1 class="text-center text-6xl font-bold text-primary py-0">drawio图表渲染</h1>
      </div>
    </template>
  </DefaultContentPage>
  
</template>

<script setup lang="ts">
import { sampleDrawioUrl } from '@/assets/runtime-shell'
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import DrawioViewer from '@runtime-kit/internal/renderers/DrawioViewer.vue'

</script>

<style scoped>
</style>
