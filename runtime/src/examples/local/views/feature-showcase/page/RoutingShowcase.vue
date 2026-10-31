<!--
  文件用途：本地示例页，展示 Runtime 路由目录、当前页上下文与页面导航能力。
-->
<template>
  <ShowcasePage
    title="路由与导航"
    subtitle="两级路由最终转换为可查询、可导航的页面目录"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[0.9fr_1.1fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-5">
        <div class="mb-4 flex items-center gap-2">
          <Icon name="路由-copy" class="size-5 text-primary" />
          <h2 class="font-heading text-lg font-semibold text-primary">当前页上下文</h2>
        </div>

        <dl class="grid grid-cols-[auto_1fr] gap-2">
          <template v-for="item in currentPageRows" :key="item.label">
            <dt class="rounded-md bg-default px-3 py-2 font-body text-xs text-secondary">{{ item.label }}</dt>
            <dd class="truncate rounded-md bg-default px-3 py-2 font-code text-xs text-primary">{{ item.value }}</dd>
          </template>
        </dl>

        <div class="mt-4 flex gap-3">
          <button
            type="button"
            class="rounded-md border border-border px-4 py-2 font-body text-sm font-medium text-primary transition-colors hover:border-primary-300 disabled:opacity-40"
            :disabled="!canGoPrevious"
            @click="goToPreviousPage"
          >
            ← 上一页
          </button>
          <button
            type="button"
            class="rounded-md border border-border px-4 py-2 font-body text-sm font-medium text-primary transition-colors hover:border-primary-300 disabled:opacity-40"
            :disabled="!canGoNext"
            @click="goToNextPage"
          >
            下一页 →
          </button>
        </div>

        <div class="mt-4 rounded-md border border-border bg-default p-4">
          <p class="font-body text-xs text-secondary">相邻页面</p>
          <div class="mt-2 space-y-1.5">
            <p class="truncate font-code text-xs text-primary">
              prev · {{ previousPage ? `${previousPage.name} (P${previousPage.pageNumber})` : 'null' }}
            </p>
            <p class="truncate font-code text-xs text-primary">
              next · {{ nextPage ? `${nextPage.name} (P${nextPage.pageNumber})` : 'null' }}
            </p>
          </div>
        </div>
        <div class="mt-4 rounded-md border border-border bg-default p-4">
          <p class="font-body text-xs text-secondary">两级路由</p>
          <ul class="mt-2 space-y-1.5">
            <li v-for="item in routeRules" :key="item" class="flex gap-2 font-body text-xs leading-6 text-secondary">
              <span class="mt-2 size-1.5 shrink-0 rounded-full bg-accent2" />
              <span>{{ item }}</span>
            </li>
          </ul>
        </div>

      </section>

      <section class="flex min-h-0 flex-col rounded-lg border border-border bg-background-subtle p-5">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="font-heading text-lg font-semibold text-primary">可见页面目录</h2>
          <span class="rounded-full bg-accent2-100 px-3 py-1 font-body text-xs font-medium text-accent2-800">
            {{ catalogItems.length }} 页 · P{{ minPageNumber }}–P{{ maxPageNumber }}
          </span>
        </div>

        <div class="grid min-h-0 flex-1 grid-cols-2 gap-2 overflow-auto pr-1">
          <router-link
            v-for="item in catalogItems"
            :key="item.path"
            :to="item.path"
            class="flex min-w-0 items-center gap-2 rounded-md border border-border-subtle bg-default px-3 py-2 transition-colors hover:border-primary-300"
            :class="item.path === currentPath ? 'border-primary-400 bg-primary-50' : ''"
          >
            <span class="w-8 shrink-0 font-code text-xs text-secondary">P{{ item.pageNumber }}</span>
            <span class="min-w-0 flex-1 truncate font-body text-xs text-primary">{{ item.title }}</span>
          </router-link>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import { useCurrentPage } from '@runtime-kit/public/composables/page/useCurrentPage.v1'
import { usePageNavigation } from '@runtime-kit/public/composables/page/usePageNavigation.v1'
import { useRouteCatalog } from '@runtime-kit/public/composables/page/useRouteCatalog.v1'

const capabilities: ShowcaseCapability[] = [
  { name: 'useCurrentPage.v1', path: '@runtime-kit/public/composables/page/useCurrentPage.v1' },
  { name: 'useRouteCatalog.v1', path: '@runtime-kit/public/composables/page/useRouteCatalog.v1' },
  { name: 'usePageNavigation.v1', path: '@runtime-kit/public/composables/page/usePageNavigation.v1' },
]

const page = useCurrentPage()
const { catalogItems, minPageNumber, maxPageNumber } = useRouteCatalog()
const { canGoPrevious, canGoNext, goToPreviousPage, goToNextPage, previousPage, nextPage } = usePageNavigation()

const currentPath = computed(() => page.route.path)

/** 两级路由的结构约定。 */
const routeRules = [
  '分组路由只承载章节，不允许配置组件，访问时自动跳到第一个可见子页面。',
  '子页面是唯一有真实内容的层级，页码按目录顺序连续编号。',
  '独立页面没有子页面，直接作为一个页面参与编号。',
]

/** 当前路由上下文展示行。 */
const currentPageRows = computed(() => [
  { label: '当前路径', value: page.route.path },
  { label: '页面标题', value: page.title.value || '-' },
  { label: '当前页码', value: String(page.currentPage.value) },
  { label: '总页数', value: String(page.totalPages.value) },
])
</script>
