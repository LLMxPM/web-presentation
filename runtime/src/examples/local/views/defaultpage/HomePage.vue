<template>
  <DefaultContainer >
    <div class="relative h-full w-full overflow-hidden">
      <!-- 背景图片 -->
      <div class="background-image absolute inset-0 h-full w-full" :style="backgroundImageStyle"></div>
      <!-- 反色背景渐变蒙版：从左到右逐渐变浅（透明） -->
      <div class="gradient-overlay absolute inset-0"></div>
      <!-- 主题背景色渐变蒙版 -->
      <!-- 主要内容区域 -->
      <div class="relative z-10 flex h-full w-full flex-col justify-between px-20 py-[60px]">
        <!-- 顶部Logo和标题区域 -->
        <div class="mt-8 flex items-center justify-left">
          <div class="flex items-center">
            <img :src="logoSrc" alt="Logo" class="logo mr-4 h-16" />
            <h1 class="main-title font-medium text-white text-5xl">| web-runtime-vue</h1>
          </div>
        </div>

        <!-- 中心标题区域 -->
        <div class="flex flex-col items-start justify-start">
          <h2 class="center-title font-bold text-white text-9xl">web-runtime-vue</h2>
          <h3 class="mt-4 font-semibold text-white text-5xl">AI创作PPT的基础框架</h3>
        </div>

        <!-- 底部信息区域 -->
        <div class="flex flex-col items-start">
          <div class="info-line mb-2 flex items-center text-xl text-white">
            <span class="inline-block w-20 text-left">演示时间</span><span>：</span>
            <span class="ml-2">{{ currentDate }}</span>
          </div>
        </div>
      </div>
    </div>
  </DefaultContainer>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { defaultBackgroundUrl } from '@/assets/runtime-shell'
import { useTheme } from '@runtime-kit/public/composables/theme/useTheme.v1'

import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'

/**
 * 首页组件
 * 使用 DefaultContainer 提供固定尺寸容器，指定深色商务主题
 * 展示AI-MIS市场情报分析报告的标题和基本信息
 */


// 使用主题系统获取反色Logo
const { themeInvertLogo } = useTheme()

const logoSrc = computed(() => {
  return themeInvertLogo.value
})
const backgroundImageStyle = computed(() => ({
  backgroundImage: `url(${defaultBackgroundUrl})`,
}))

const currentDate = ref('')

onMounted(() => {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  currentDate.value = `${year}年${month}月${day}日`
})
</script>

<style scoped>
/* 背景图片样式说明:
 * @apply absolute inset-0: 绝对定位并占满父容器(top:0, right:0, bottom:0, left:0)
 * background-image: 设置背景图片路径
 * background-size: cover 确保背景图片覆盖整个容器
 * background-position: center 背景图片居中显示
 * background-repeat: no-repeat 背景图片不重复
 */
.background-image {
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
}

/* 反色背景色渐变蒙版
 * 使用主题反色背景变量 --tw-color-bg-invert
 * 从左到右逐步降低透明度，实现“变浅”的效果
 */
.gradient-overlay {
  background: linear-gradient(
    to right,
    rgb(from var(--tw-color-bg-invert) r g b / 1) 0%,
    rgb(from var(--tw-color-bg-invert) r g b / 0.9) 35%,
    rgb(from var(--tw-color-bg-invert) r g b / 0.7) 70%,
    rgb(from var(--tw-color-bg-invert) r g b / 0.5) 100%
  );
  pointer-events: none; /* 不影响交互 */
}


.logo {
  /* 保持图片原始比例 */
  width: auto;
  aspect-ratio: auto;
}

</style>
