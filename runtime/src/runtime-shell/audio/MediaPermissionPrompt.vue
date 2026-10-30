<!-- 文件功能：在当前 Runtime frame 提供媒体许可的本地用户手势，演讲者或 Editor 父窗口不能代点解锁。 -->
<script setup lang="ts">
import { computed } from 'vue'
import { runtimeAudioBus } from '@/core/audio/runtime-audio-bus'
import { useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
const execution = useRuntimeExecutionPolicy()
const visible = computed(() => execution.value.allowMediaPlayback && runtimeAudioBus.state.value.blocked > 0)
/** 用户点击在当前 frame 同步发起原生 play；成功与否仍以浏览器 Promise 为准。 */
function retry(): void { void runtimeAudioBus.retryBlocked() }
</script>
<template><aside v-if="visible" class="media-permission" role="alert"><span>媒体播放受阻，请在此窗口允许播放。</span><button type="button" @click="retry">允许播放</button></aside></template>
<style scoped>
.media-permission { position:fixed; z-index:9999; bottom:24px; left:50%; transform:translateX(-50%); display:flex; align-items:center; gap:16px; padding:12px 16px; border-radius:8px; background:#172554; color:#fff; font-size:14px; }
button { padding:6px 12px; border:1px solid #c7d2fe; border-radius:4px; background:#fff; color:#172554; cursor:pointer; white-space:nowrap; }
</style>
