<!-- 文件功能：作为后台应用根组件，承载路由视图出口与全局确认弹窗宿主。 -->
<template>
  <RouterView />
  <UiConfirmHost />
</template>

<script setup lang="ts">
import { RouterView } from 'vue-router'

import UiConfirmHost from '@/components/ui/dialog/UiConfirmHost.vue'
</script>
