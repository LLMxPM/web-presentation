<!-- 文件用途：Backend build release 构建态根组件，仅承载项目路由视图与主题样式。 -->
<template>
  <div id="app" :class="themeClass">
    <router-view />
  </div>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'

const { themeClass, themeStyles } = useTheme()

/**
 * 将主题变量同步到文档根节点，供页面内容和演示外壳共享。
 */
function applyThemeToRoot(): void {
  const styles = themeStyles.value
  if (!styles || !document.documentElement) {
    return
  }

  Object.entries(styles).forEach(([key, value]) => {
    if (key.startsWith('--theme-')) {
      document.documentElement.style.setProperty(key, value as string)
    }
  })
}

watch(
  () => themeStyles.value,
  () => {
    applyThemeToRoot()
  },
  { immediate: true, deep: true },
)

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
