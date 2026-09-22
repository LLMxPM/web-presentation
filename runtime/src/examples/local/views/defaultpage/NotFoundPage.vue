<template>
  <DefaultContainer>
    <div class="w-full h-full flex items-center justify-center px-4" :style="themeStyles">
      <div class="max-w-md w-full text-center animate-fade-in">
        <div class="mb-8">
          <div class="inline-flex items-center justify-center w-24 h-24 rounded-full mb-4 bg-background-600 border border-border-subtle">
            <svg class="w-12 h-12 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.172 16.172a4 4 0 015.656 0M9 12h6m-6-4h6m2 5.291A7.962 7.962 0 0112 15c-2.34 0-4.467-.881-6.08-2.33.893-.533 1.963-.84 3.08-.84.632 0 1.249.1 1.832.284A7.96 7.96 0 0112 15z"></path>
            </svg>
          </div>
          <h1 class="font-heading text-6xl font-bold leading-tight text-primary">404</h1>
          <h2 class="font-heading text-3xl font-medium leading-relaxed text-secondary">页面未找到</h2>
        </div>

        <div class="mb-8">
          <p class="mb-4 font-body text-primary">
            抱歉，您访问的页面不存在或已被移动。
          </p>
          <p class="text-sm font-body text-secondary">
            请检查URL及路由配置是否正确，或返回首页继续浏览。
          </p>
        </div>

        <div class="space-y-4">
          <button 
            class="w-full font-body font-medium py-3 px-6 rounded-lg transition-opacity duration-200 bg-primary text-invert hover:opacity-90"
            @click="goHome"
          >
            返回首页
          </button>
          
          <button 
            class="w-full font-body font-medium py-3 px-6 rounded-lg transition-colors duration-200 bg-bg-subtle text-primary border border-border-default hover:bg-border-subtle"
            @click="goBack"
          >
            返回上一页
          </button>
        </div>

      </div>
    </div>
  </DefaultContainer>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'
import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'

/**
 * 404页面组件
 * 提供友好的错误提示和导航功能
 */

const router = useRouter()
const { themeStyles } = useTheme()

/**
 * 返回首页
 * 使用路由跳转到首页
 */
const goHome = (): void => {
  router.push('/')
}

/**
 * 返回上一页
 * 如果没有历史记录，则跳转到首页
 */
const goBack = (): void => {
  if (window.history.length > 1) {
    router.go(-1)
  } else {
    router.push('/')
  }
}
</script>

<style scoped>
/* 动画效果 */
.animate-fade-in {
  animation: fadeIn 0.5s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
