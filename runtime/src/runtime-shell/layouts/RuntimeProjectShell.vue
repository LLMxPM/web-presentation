<!-- 文件功能：稳定的项目宿主，按地址选择展示界面，页面路径独立于模式。 -->
<template>
  <div v-if="navigationError" class="runtime-navigation-error" role="alert">{{ navigationError }}</div>
  <RuntimeCaptureLayout v-if="capture" />
  <PresenterConsoleView v-else-if="mode === 'presenter'" :key="channel" />
  <PresenterDisplayView v-else-if="mode === 'display'" :key="channel" />
  <ResponsiveLayout v-else />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { getRuntimeSession } from '@/core/router/runtime-session'
import RuntimeCaptureLayout from '../transitions/RuntimeCaptureLayout.vue'
import ResponsiveLayout from './ResponsiveLayout.vue'
import PresenterConsoleView from '../presenter/PresenterConsoleView.vue'
import PresenterDisplayView from '../presenter/PresenterDisplayView.vue'

const router = useRouter()
const { mode, navigationError } = getRuntimeSession(router)
const capture = computed(() => router.currentRoute.value.query.runtimeCapture === '1')
const channel = computed(() => String(router.currentRoute.value.query.channel || ''))
</script>

<style scoped>
.runtime-navigation-error { position: fixed; top: 16px; left: 50%; transform: translateX(-50%); z-index: 10000; padding: 12px 20px; background: #fff; color: #b91c1c; border: 1px solid #fecaca; border-radius: 8px; }
</style>
