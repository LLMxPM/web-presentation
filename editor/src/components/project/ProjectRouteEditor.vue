<!-- 文件功能：提供项目路由的可视化编排界面，支持页面池、分组管理与结构化路由树编辑。 -->
<template>
  <div class="grid items-stretch gap-3 xl:grid-cols-[300px_minmax(0,1fr)]">
    <section class="flex flex-col rounded-2xl border border-slate-200 bg-slate-50/70 p-3.5 xl:h-[620px] xl:min-h-0">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h5 class="text-sm font-bold text-slate-900">页面池</h5>
        </div>
        <span class="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-500">
          {{ props.pages.length }} 个页面
        </span>
      </div>

      <div class="mt-4">
        <input
          v-model="pageKeyword"
          type="text"
          class="h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-indigo-400"
          placeholder="搜索页面标题或编码"
        >
      </div>

      <div v-if="props.loading" class="mt-4 flex items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-400 xl:flex-1">
        正在加载项目页面和路由数据...
      </div>

      <div v-else class="mt-4 space-y-2.5 pr-1 xl:flex-1 xl:min-h-0 xl:overflow-y-auto">
        <article
          v-for="page in filteredPages"
          :key="page.id"
          class="rounded-2xl border border-slate-200 bg-white p-3"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="truncate text-sm font-semibold text-slate-900">{{ page.title }}</div>
              <div class="mt-1 text-[11px] font-mono text-slate-400">{{ page.code }}</div>
            </div>
            <span
              class="rounded-full px-2 py-1 text-[11px] font-semibold"
              :class="getPageUsageCount(page.id) > 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
            >
              {{ getPageUsageCount(page.id) > 0 ? `已加入路由 × ${getPageUsageCount(page.id)}` : '未加入路由' }}
            </span>
          </div>

          <p v-if="getPageUsageCount(page.id) > 0" class="mt-2 text-[11px] leading-5 text-slate-500">
            {{ getPageUsageText(page.id) }}
          </p>

          <div class="mt-3 flex items-center gap-2">
            <button
              type="button"
              class="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-500"
              @click="handleAddRootPage(page.id)"
            >
              添加为顶层页
            </button>
          </div>
        </article>

        <div v-if="filteredPages.length === 0" class="rounded-xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-400">
          没有匹配的页面。
        </div>
      </div>
    </section>

    <ProjectRouteTreeTable v-model="routesDraft" :pages="props.pages" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import ProjectRouteTreeTable from '@/components/project/ProjectRouteTreeTable.vue'
import type { PageItem, ProjectRouteItemWrite } from '@/types/api'
import { appendRootPageRoute } from '@/utils/project-route'

const props = withDefaults(defineProps<{
  modelValue: ProjectRouteItemWrite[]
  pages: PageItem[]
  loading?: boolean
}>(), {
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: ProjectRouteItemWrite[]]
}>()

const pageKeyword = ref('')
const routesDraft = computed({
  get: () => props.modelValue ?? [],
  set: (value: ProjectRouteItemWrite[]) => emit('update:modelValue', value),
})
const pageMap = computed(() => new Map(props.pages.map(page => [page.id, page])))

const filteredPages = computed(() => {
  const keyword = pageKeyword.value.trim().toLowerCase()
  const orderedPages = [...props.pages].sort((left, right) => left.title.localeCompare(right.title, 'zh-CN'))
  if (!keyword) {
    return orderedPages
  }
  return orderedPages.filter(page => {
    return [page.title, page.code, page.summary ?? '']
      .some(item => item.toLowerCase().includes(keyword))
  })
})

const pageBindingMap = computed(() => {
  const nextMap = new Map<number, string[]>()
  for (const routeItem of routesDraft.value) {
    if (routeItem.route_type === 'page' && routeItem.page_id != null) {
      appendPageBinding(nextMap, routeItem.page_id, buildFullPath(null, routeItem.route))
      continue
    }
    for (const childRoute of routeItem.children ?? []) {
      appendPageBinding(nextMap, childRoute.page_id, buildFullPath(routeItem.route, childRoute.route))
    }
  }
  return nextMap
})

function emitRoutes(nextRoutes: ProjectRouteItemWrite[]): void {
  emit('update:modelValue', nextRoutes)
}

function handleAddRootPage(pageId: number): void {
  const page = pageMap.value.get(pageId)
  if (!page) {
    return
  }
  emitRoutes(appendRootPageRoute(routesDraft.value, page))
}

function getPageUsageCount(pageId: number): number {
  return pageBindingMap.value.get(pageId)?.length ?? 0
}

function getPageUsageText(pageId: number): string {
  const bindings = pageBindingMap.value.get(pageId) ?? []
  if (bindings.length === 0) {
    return ''
  }
  return bindings.join('，')
}

function appendPageBinding(bindingMap: Map<number, string[]>, pageId: number, fullPath: string): void {
  const currentPaths = bindingMap.get(pageId) ?? []
  currentPaths.push(fullPath)
  bindingMap.set(pageId, currentPaths)
}

function buildFullPath(parentRoute: string | null, route: string): string {
  if (parentRoute) {
    return `/${parentRoute}/${route}`.replace(/\/+/g, '/')
  }
  return `/${route}`.replace(/\/+/g, '/')
}
</script>
