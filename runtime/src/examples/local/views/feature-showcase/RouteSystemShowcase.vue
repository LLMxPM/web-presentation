<!--
  文件用途：本地示例页，展示 Runtime 路由目录、当前页上下文与页面导航能力。
-->
<template>
  <DefaultContentPage title="路由系统与导航" subtitle="两级路由配置最终转换为可查询、可导航的页面目录">
    <template #content>
      <div class="grid h-full grid-cols-[0.9fr_1.1fr] gap-8 p-6">
        <section class="rounded-lg border border-border bg-background-subtle p-6">
          <div class="mb-5 flex items-center gap-3">
            <Icon name="路由-copy" class="size-6 text-primary" />
            <h2 class="font-heading text-2xl font-semibold text-primary">当前页上下文</h2>
          </div>
          <dl class="grid grid-cols-2 gap-4">
            <template v-for="item in currentPageRows" :key="item.label">
              <dt class="rounded-md bg-default p-3 font-body text-sm text-secondary">{{ item.label }}</dt>
              <dd class="rounded-md bg-default p-3 font-mono text-sm text-primary">{{ item.value }}</dd>
            </template>
          </dl>
          <div class="mt-6 flex gap-4">
            <button
              class="rounded-md border border-border px-4 py-2 text-sm font-medium text-primary disabled:opacity-40"
              :disabled="!canGoPrevious"
              @click="goToPreviousPage"
            >
              上一页
            </button>
            <button
              class="rounded-md border border-border px-4 py-2 text-sm font-medium text-primary disabled:opacity-40"
              :disabled="!canGoNext"
              @click="goToNextPage"
            >
              下一页
            </button>
          </div>
        </section>

        <section class="rounded-lg border border-border-default bg-default p-6 shadow-theme-sm">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="font-heading text-xl font-semibold text-primary">可见页面目录</h3>
            <span class="rounded-full bg-accent2-100 px-3 py-1 text-sm font-medium text-accent2-800">
              {{ catalogItems.length }} 页
            </span>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <router-link
              v-for="item in catalogItems"
              :key="item.path"
              :to="item.path"
              class="rounded-md border border-border bg-background-muted p-3 transition hover:border-primary-300"
            >
              <div class="flex items-center justify-between gap-3">
                <span class="font-body text-sm font-medium text-primary">{{ item.title }}</span>
                <span class="font-mono text-xs text-secondary">P{{ item.pageNumber }}</span>
              </div>
              <p class="mt-2 truncate font-mono text-xs text-secondary">{{ item.path }}</p>
            </router-link>
          </div>
        </section>
      </div>
    </template>
  </DefaultContentPage>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DefaultContentPage from '@/runtime-kit/public/components/page/templates/DefaultContentPage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import { useCurrentPage } from '@runtime-kit/public/composables/page/useCurrentPage.v1'
import { usePageNavigation } from '@runtime-kit/public/composables/page/usePageNavigation.v1'
import { useRouteCatalog } from '@runtime-kit/public/composables/page/useRouteCatalog.v1'

const page = useCurrentPage()
const { catalogItems } = useRouteCatalog()
const {
  canGoPrevious,
  canGoNext,
  goToPreviousPage,
  goToNextPage,
} = usePageNavigation()

/**
 * 当前路由上下文展示行。
 * 输出：当前路径、标题、页码和总页数。
 */
const currentPageRows = computed(() => [
  { label: '当前路径', value: page.route.path },
  { label: '页面标题', value: page.title.value || '-' },
  { label: '当前页码', value: String(page.currentPage.value) },
  { label: '总页数', value: String(page.totalPages.value) },
])
</script>
