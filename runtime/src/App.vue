<template>
  <div 
    id="app" 
    :class="themeClass"
  >
    <router-view />
    <!-- 全局 Toast 容器 -->
    <ToastContainer />
  </div>
</template>

<script setup lang="ts">
/**
 * 文件用途：应用根组件，应用主题样式并提供路由视图容器。
 * 本版本移除全局主题依赖，直接根据配置文件默认主题应用样式。
 */
import { watch, onMounted } from 'vue'
import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'
import ToastContainer from '@/runtime-shell/feedback/ToastContainer.vue'

/**
 * 主应用组件
 * 提供路由视图容器并应用全局主题样式
 */

// 应用主题样式到根元素（默认使用配置中的主题）
const { themeClass, themeStyles } = useTheme()

/**
 * 将主题样式应用到document.documentElement（:root）
 * 确保CSS变量在全局范围内生效
 */
const applyThemeToRoot = () => {
  const styles = themeStyles.value
  if (styles && document.documentElement) {
    // 将所有主题CSS变量应用到:root
    Object.entries(styles).forEach(([key, value]) => {
      if (key.startsWith('--theme-')) {
        document.documentElement.style.setProperty(key, value as string)
      }
    })
    // console.log('主题样式已应用到:root', styles)
  }
}

// 监听主题变化，实时更新CSS变量
watch(
  () => themeStyles.value,
  () => {
    applyThemeToRoot()
  },
  { immediate: true, deep: true }
)

// 组件挂载时确保主题样式已应用
onMounted(() => {
  applyThemeToRoot()
})
</script>

<style>
#app {
  height: 100vh;
  overflow: hidden;
}
</style>
