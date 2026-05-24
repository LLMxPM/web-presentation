<!-- 文件功能：基础弹窗组件，承载表单或确认信息。 -->
<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="modelValue" class="fixed inset-0 z-[1000] flex items-center justify-center p-4">
        <!-- Overlay -->
        <div class="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" @click="close"></div>
        
        <!-- Modal Content -->
        <Transition name="scale">
          <div 
            v-if="modelValue" 
            class="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden"
            :style="{ maxWidth: width }"
            @click.stop
          >
            <!-- Header -->
            <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/50">
              <h3 class="text-lg font-bold text-slate-900 line-clamp-1">{{ title }}</h3>
              <BaseCloseButton :label="title ? `关闭${title}` : '关闭弹窗'" @click="close" />
            </div>
            
            <!-- Body -->
            <div :class="props.bodyClass || 'px-6 py-5 max-h-[80vh] overflow-y-auto'">
              <slot></slot>
            </div>
            
            <!-- Footer -->
            <div v-if="$slots.footer" class="px-6 py-4 border-t border-slate-100 flex items-center justify-end gap-3 bg-slate-50/20">
              <slot name="footer"></slot>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

import BaseCloseButton from '@/components/ui/BaseCloseButton.vue'

/**
 * 基础弹窗组件
 */
const props = defineProps<{
  modelValue: boolean
  title?: string
  width?: string
  bodyClass?: string
}>()

const emit = defineEmits(['update:modelValue'])

function close() {
  emit('update:modelValue', false)
}

// 禁止滚动条
function handleEsc(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.modelValue) {
    close()
  }
}

onMounted(() => window.addEventListener('keydown', handleEsc))
onUnmounted(() => window.removeEventListener('keydown', handleEsc))
</script>

<style scoped>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.25s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

.scale-enter-active, .scale-leave-active {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.scale-enter-from, .scale-leave-to {
  transform: scale(0.9) translateY(10px);
  opacity: 0;
}
</style>
