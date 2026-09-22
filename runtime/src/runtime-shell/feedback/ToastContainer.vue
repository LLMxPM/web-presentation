<!--
  文件用途：全局 Toast 容器（ToastContainer.vue）
  主要功能：
  - 使用 Teleport 将轻量提示消息渲染到 body 顶层，避免受到页面布局影响
  - 支持多条消息堆叠与进入/离开过渡动画
  - 按消息类型展示不同的颜色风格（无渐变、无 !important）
-->
<template>
  <!-- Teleport 到 body，固定布局在右上角 -->
  <teleport to="body">
    <div class="fixed top-4 left-1/2 -translate-x-1/2 z-[var(--z-toast)] w-[420px] space-y-2">
      <transition-group name="toast-fade" tag="div">
        <div
v-for="t in store.list" :key="t.id" class="flex items-start gap-2 rounded-lg border p-3 shadow-sm"
          :class="toastClass(t.type)">
          <div class="flex-1 min-w-0">
            <p class="text-[12px] truncate" :class="textClass(t.type)">{{ t.message }}</p>
          </div>
          <button class="shrink-0 text-gray-500 hover:text-gray-700 transition-colors" @click="removeToast(t.id)">
            <X :size="16" />
          </button>
        </div>
      </transition-group>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { X } from '@lucide/vue'
import { useToast, ToastType } from '@/core/composables/useToast'

/**
 * 容器：渲染全局 toast 列表
 * - 从 useToast 获取 store 与 remove 方法
 */
const { store, removeToast } = useToast()

/**
 * 根据消息类型提供不同的容器样式（边框/背景）
 */
function toastClass(type: ToastType) {
  switch (type) {
    case 'success':
      return 'border-green-200 bg-green-50'
    case 'error':
      return 'border-red-200 bg-red-50'
    case 'warning':
      return 'border-yellow-200 bg-yellow-50'
    default:
      return 'border-blue-200 bg-blue-50'
  }
}

/**
 * 根据消息类型提供不同的文本颜色
 */
function textClass(type: ToastType) {
  switch (type) {
    case 'success':
      return 'text-green-800'
    case 'error':
      return 'text-red-800'
    case 'warning':
      return 'text-yellow-800'
    default:
      return 'text-blue-800'
  }
}
</script>

<style scoped>
/* 无额外复杂样式，仅控制容器宽度与过渡，由模板内 <style> 提供过渡类 */
/* 过渡样式：与 <transition-group name="toast-fade"> 对应的类名 */
.toast-fade-enter-active,
.toast-fade-leave-active {
  transition: all 0.2s ease-in-out;
}

.toast-fade-enter-from,
.toast-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>