<!--
  文件用途：捕获子组件渲染错误，防止整个应用崩溃，并提供错误提示UI
-->
<template>
    <div
v-if="hasError"
        class="error-boundary p-8 w-full h-full flex flex-col items-center justify-center bg-red-50 text-red-900 rounded-lg shadow-sm border border-red-200">
        <div class="mb-4 text-red-500">
            <AlertCircle :size="48" />
        </div>
        <h2 class="text-xl font-bold mb-2">页面渲染出错</h2>
        <p
            class="text-red-700 mb-4 whitespace-pre-wrap text-center max-w-2xl font-mono text-sm bg-red-100 p-4 rounded text-left overflow-auto max-h-60">
            {{ errorMessage }}</p>
        <button
class="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors shadow-sm font-medium"
            @click="resetError">
            重试渲染
        </button>
    </div>
    <slot v-else></slot>
</template>

<script setup lang="ts">
/**
 * ErrorBoundary 错误边界组件
 * 捕获子树中未处理的异常，展示回退UI，并支持路由切换时自动恢复
 */
import { ref, onErrorCaptured, watch } from 'vue'
import { AlertCircle } from '@lucide/vue'
import { useRoute } from 'vue-router'
import { reportRuntimeClientError } from '@/core/utils/client-logger'

const hasError = ref(false)
const errorMessage = ref('')
const route = useRoute()

// 捕获后代组件的错误
onErrorCaptured((err: unknown, instance, info) => {
    hasError.value = true
    errorMessage.value = err instanceof Error ? `${err.name}: ${err.message}\n${err.stack}` : String(err)
    reportRuntimeClientError(err, { message: 'ErrorBoundary捕获到错误。', component: 'ErrorBoundary', context: { info } })

    // 返回 false 阻止错误继续向上传递（避免引发全局崩溃）
    return false
})

/**
 * 手动重置错误状态
 */
const resetError = () => {
    hasError.value = false
    errorMessage.value = ''
}

// 监听路由改变。如果切换到了其他页面，自动重置错误状态以便尝试正常渲染
watch(
    () => route.path,
    () => {
        if (hasError.value) {
            resetError()
        }
    }
)
</script>

<style scoped>
.error-boundary {
    animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }
}
</style>
