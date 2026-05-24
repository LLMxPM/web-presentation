<!-- 文件功能：统一后台各层级页面的标题栏、面包屑、标识信息与右侧操作区布局。 -->
<template>
  <section class="rounded-2xl border border-slate-200 bg-white/95 px-3 py-2 shadow-sm">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div class="min-w-0 flex-1">
        <nav v-if="breadcrumbs.length > 0" class="mb-2 flex flex-wrap items-center gap-2 text-sm font-medium text-slate-500">
          <template v-for="(item, index) in breadcrumbs" :key="`${item.label}-${index}`">
            <router-link v-if="item.to" :to="item.to" class="transition-colors hover:text-slate-800">
              {{ item.label }}
            </router-link>
            <span v-else>{{ item.label }}</span>
            <ChevronRight v-if="index < breadcrumbs.length - 1" class="h-4 w-4 text-slate-300" />
          </template>
        </nav>

        <div class="flex min-w-0 flex-wrap items-center gap-2">
          <slot name="title-leading" />
          <h1 class="truncate text-xl font-bold tracking-tight text-slate-900">{{ title }}</h1>
          <span
            v-if="code"
            class="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-xs font-medium text-slate-500"
          >
            {{ code }}
          </span>
          <slot name="title-actions" />
          <slot name="badges" />
        </div>

        <p v-if="description" class="mt-1 block max-w-full truncate whitespace-nowrap text-xs text-slate-500">
          {{ description }}
        </p>
        <div v-if="metaItems.length > 0" class="mt-1 flex flex-wrap gap-4 text-xs text-slate-500">
          <span v-for="item in metaItems" :key="item">{{ item }}</span>
        </div>
      </div>

      <div v-if="$slots.actions" class="flex shrink-0 flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'

interface BreadcrumbItem {
  label: string
  to?: string
}

withDefaults(
  defineProps<{
    breadcrumbs?: BreadcrumbItem[]
    title: string
    code?: string | null
    description?: string | null
    metaItems?: string[]
  }>(),
  {
    breadcrumbs: () => [],
    code: null,
    description: null,
    metaItems: () => [],
  },
)
</script>
