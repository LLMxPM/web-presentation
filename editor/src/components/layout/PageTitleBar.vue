<!-- 文件功能：统一后台各层级页面的标题栏、面包屑、标识信息与右侧操作区布局。 -->
<template>
  <section class="rounded-lg border border-slate-200 bg-white/95 px-3.5 py-2 shadow-sm">
    <div class="flex min-w-0 items-center justify-between gap-4">
      <div class="min-w-0 flex-1">
        <!-- 面包屑导航 -->
        <nav v-if="breadcrumbs.length > 0" class="mb-2 flex flex-wrap items-center gap-2 text-sm font-medium text-slate-500">
          <template v-for="(item, index) in breadcrumbs" :key="`${item.label}-${index}`">
            <router-link v-if="item.to" :to="item.to" class="transition-colors hover:text-slate-800">
              {{ item.label }}
            </router-link>
            <span v-else>{{ item.label }}</span>
            <ChevronRight v-if="index < breadcrumbs.length - 1" class="h-4 w-4 text-slate-300" />
          </template>
        </nav>

        <!-- 标题行 -->
        <div class="flex min-w-0 items-center gap-2.5">
          <slot name="title-leading" />
          
          <div class="min-w-0 flex-1">
            <div class="flex min-w-0 items-center gap-2">
              <h1
                class="min-w-0 shrink truncate text-lg font-semibold leading-6 tracking-tight text-slate-900"
                :class="titleClass"
                :title="title"
              >
                {{ title }}
              </h1>
              <span
                v-if="code"
                class="shrink-0 rounded border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-xs font-medium text-slate-600"
                :title="code"
              >
                {{ code }}
              </span>
              <div v-if="$slots['title-actions']" class="flex shrink-0 items-center gap-1">
                <slot name="title-actions" />
              </div>
            </div>
            
            <!-- 描述和元信息 -->
            <div v-if="description || metaItems.length > 0" class="mt-0.5 min-w-0 space-y-0.5">
              <p 
                v-if="description" 
                class="truncate text-xs leading-4 text-slate-600"
                :title="description"
              >
                {{ description }}
              </p>
              <div v-if="metaItems.length > 0" class="flex min-h-4 min-w-0 items-center gap-x-3 text-xs leading-4 text-slate-500">
                <span 
                  v-for="(item, index) in metaItems" 
                  :key="index"
                  class="truncate"
                  :title="item"
                >
                  {{ item }}
                </span>
              </div>
            </div>
          </div>
          
          <slot name="badges" />
        </div>
      </div>

      <!-- 操作按钮区 -->
      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-1">
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
    titleClass?: string
  }>(),
  {
    breadcrumbs: () => [],
    code: null,
    description: null,
    metaItems: () => [],
    titleClass: '',
  },
)
</script>
