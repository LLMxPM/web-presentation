<template>
  <DefaultContainer>
    <div class="table-of-contents-page">
      <!-- 左右分栏布局 -->
      <div class="page-layout">
        <!-- 左侧：背景区域 -->
        <div class="left-section" :style="leftSectionStyle">
          <!-- 标题内容 -->
          <div class="title-content">
            <div class="page-header">
              <h1 class="page-title">目&nbsp;&nbsp;&nbsp;录</h1>
              <div class="divider"></div>
              <p class="page-subtitle">Contents</p>
            </div>
          </div>
        </div>
        
        <!-- 右侧：目录区域 -->
        <div class="right-section">
          <div class="toc-container">
            <TableOfContents
              :number-format="'custom'"
              :custom-format="'第{n}部分'"
              :show-dots="true"
              :show-page-numbers="true"
              :clickable="true"
              :two-column="false"
              :column-breakpoint="6"
              :auto-font-size="true"
              :width=900
              :height=700
            />
          </div>
        </div>
      </div>
    </div>
  </DefaultContainer>
</template>

<script setup lang="ts">
import { defaultBackgroundUrl } from '@/assets/runtime-shell'
import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'
import TableOfContents from '@/runtime-kit/public/components/page/sections/TableOfContents.vue'

/**
 * 目录页面
 * 展示TableOfContents组件的使用效果
 */
defineOptions({
  name: 'TableOfContentsPage'
})

const leftSectionStyle = {
  backgroundImage: `url(${defaultBackgroundUrl})`,
}

</script>

<style scoped>
.table-of-contents-page {
  @apply relative w-full h-full overflow-hidden;
}

/* 左右分栏布局 */
.page-layout {
  @apply w-full h-full flex;
}

/* 左侧区域 */
.left-section {
  @apply relative w-2/5 h-full overflow-hidden;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
}



/* 左侧标题内容 */
.title-content {
  @apply relative z-10 h-full flex items-center justify-center;
  padding: 60px 40px;
}

.page-header {
  @apply text-center;
}

.page-title {
  @apply text-6xl font-bold mb-6;
  color: white;
  text-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
  line-height: 1.2;
}

.page-subtitle {
  @apply text-xl font-light opacity-90 mt-4;
  color: white;
  font-style: italic;
  letter-spacing: 2px;
}

.divider {
  @apply w-24 h-1 mx-auto;
  background: linear-gradient(90deg, 
    transparent, 
    rgba(255,255,255,0.8), 
    transparent);
  border-radius: 2px;
}

/* 右侧区域 */
.right-section {
  @apply w-3/5 h-full bg-default;
}

/* 目录容器 */
.toc-container {
  @apply h-full flex items-center justify-center;
  padding: 40px 60px;
}

</style>
