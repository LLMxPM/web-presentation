<template>
  <DefaultContainer>
    <div class="relative h-full w-full overflow-hidden">
      <!-- 背景图片 -->
      <div class="background-image absolute inset-0 h-full w-full" :style="backgroundImageStyle"></div>
      <!-- 反色背景渐变蒙版：从左到右逐渐变浅（透明） -->
      <div class="gradient-overlay absolute inset-0"></div>

      <!-- 主要内容区域 -->
      <div class="relative z-10 flex h-full w-full px-20">
        <!-- 左侧内容区域 -->
        <div class="flex flex-col justify-between h-full w-1/2">
          <!-- 上半部分：主标题和副标题居中 -->
          <div class="flex flex-col justify-center flex-1">
            <!-- 主标题 -->
            <h1 class="main-title text-invert font-bold mb-4 text-8xl text-left">
              感谢聆听
            </h1>
            <!-- 副标题 -->
            <p class="subtitle text-invert font-light text-left text-4xl">
              了解AI，用好AI
            </p>
          </div>

          <!-- 底部联系信息 -->
          <div class="contact-info mb-16">
            <div class="contact-item mb-4">
              <Icon name="Github" color="#ffffff" class="mr-3 inline-block size-6" />
              <span class="text-invert text-2xl">web-runtime-vue</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </DefaultContainer>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { defaultBackgroundUrl } from '@/assets/runtime-shell'
import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'

/**
 * 结束页
 */
defineOptions({
  name: 'EndPage'
})



const currentDate = ref('')
const backgroundImageStyle = {
  backgroundImage: `url(${defaultBackgroundUrl})`,
}

onMounted(() => {
  const today = new Date()
  const year = today.getFullYear()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  currentDate.value = `${year}${month}${day}`
})
</script>

<style scoped>
/* 背景图片样式说明:
 * @apply absolute inset-0: 绝对定位并占满父容器(top:0, right:0, bottom:0, left:0)
 * w-full h-full: 宽度和高度设置为100%
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

/* 主题背景色渐变蒙版样式
 * 从左到右：主题背景色(不透明) -> 透明
 * 使用CSS变量获取当前主题的背景色，并通过透明度实现渐变效果
 */
.gradient-overlay {
  background: linear-gradient(to right,
      rgb(from var(--tw-color-bg-invert) r g b / 1) 0%,
      rgb(from var(--tw-color-bg-invert) r g b / 0.9) 35%,
      rgb(from var(--tw-color-bg-invert) r g b / 0.7) 70%,
      rgb(from var(--tw-color-bg-invert) r g b / 0.5) 100%);
  pointer-events: none;
  /* 确保蒙版不影响鼠标事件 */
}
</style>
