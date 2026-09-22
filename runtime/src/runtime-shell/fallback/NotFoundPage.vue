<!-- 文件用途：提供 Runtime 壳层私有的路由兜底页面，避免依赖本地示例页面。 -->
<template>
  <section class="not-found-page">
    <div class="not-found-page__panel">
      <p class="not-found-page__code">404</p>
      <h1 class="not-found-page__title">页面未找到</h1>
      <p class="not-found-page__description">
        当前路由没有匹配的页面组件，请检查路由配置或预览产物清单。
      </p>
      <button class="not-found-page__button" type="button" @click="goHome">
        返回首页
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

/**
 * 返回 Runtime 根路由。
 * @returns 无返回值
 */
function goHome(): void {
  router.push('/')
}
</script>

<style scoped>
.not-found-page {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  background: #f8fafc;
  color: #0f172a;
}

.not-found-page__panel {
  width: min(520px, calc(100% - 48px));
  text-align: center;
}

.not-found-page__code {
  margin: 0;
  font-size: 72px;
  font-weight: 800;
  line-height: 1;
  color: #2563eb;
}

.not-found-page__title {
  margin: 20px 0 12px;
  font-size: 32px;
  line-height: 1.25;
}

.not-found-page__description {
  margin: 0 auto 28px;
  max-width: 420px;
  font-size: 16px;
  line-height: 1.7;
  color: #475569;
}

.not-found-page__button {
  min-width: 140px;
  height: 44px;
  border: 0;
  border-radius: 8px;
  background: #0f172a;
  color: #ffffff;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
}

.not-found-page__button:hover {
  background: #1e293b;
}
</style>
