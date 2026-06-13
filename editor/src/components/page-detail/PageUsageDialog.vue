<!-- 文件功能：展示当前页面使用的组件与资源索引，避免资源信息占用主编辑画布空间。 -->
<template>
  <BaseDialog :model-value="props.modelValue" title="组件与资源" size="wide" body-preset="auto"
    @update:model-value="emit('update:modelValue', $event)">
    <div class="grid gap-4 lg:grid-cols-[0.86fr_1.14fr]">
      <article class="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
        <div class="flex items-center justify-between gap-3">
          <p class="text-sm font-semibold text-slate-900">使用组件</p>
          <span class="text-xs text-slate-400">{{ props.usedComponentNames.length }} 个</span>
        </div>
        <p v-if="props.componentIndexLoading" class="mt-3 text-sm text-slate-400">正在读取当前版本组件索引...</p>
        <div v-else-if="props.usedComponentNames.length" class="mt-3 flex flex-wrap gap-1.5">
          <span
            v-for="componentName in props.usedComponentNames"
            :key="componentName"
            class="rounded-full border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] font-semibold text-sky-700"
          >
            {{ componentName }}
          </span>
        </div>
        <p v-else class="mt-3 text-sm text-slate-400">当前版本未记录组件索引。</p>
      </article>

      <article class="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
        <div class="flex items-center justify-between gap-3">
          <p class="text-sm font-semibold text-slate-900">资源引用</p>
          <span class="text-xs text-slate-400">{{ groupedResourceItems.length }} 组</span>
        </div>

        <p v-if="props.componentIndexLoading" class="mt-3 text-sm text-slate-400">正在读取当前版本资源索引...</p>
        <div v-else-if="groupedResourceItems.length" class="mt-3 space-y-3">
          <article
            v-for="group in groupedResourceItems"
            :key="group.componentName"
            class="rounded-2xl border border-slate-200 bg-white px-3 py-3"
          >
            <div class="flex items-center justify-between gap-3">
              <h3 class="min-w-0 truncate text-sm font-semibold text-slate-800">{{ group.componentName }}</h3>
              <span class="text-[11px] text-slate-400">{{ group.resources.length }} 个资源</span>
            </div>
            <div class="mt-2 flex flex-wrap gap-1.5">
              <span
                v-for="resource in group.resources"
                :key="`${group.componentName}-${resource.resourceName}`"
                class="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] font-semibold text-emerald-700"
              >
                {{ resource.resourceName }}
              </span>
            </div>
          </article>
        </div>
        <p v-else class="mt-3 text-sm text-slate-400">当前版本未记录资源索引。</p>
      </article>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { PageComponentResourceItem } from '@/types/api'

interface GroupedResourceItem {
  componentName: string
  resources: Array<{
    resourceName: string
  }>
}

interface Props {
  modelValue: boolean
  componentIndexLoading: boolean
  usedComponentNames: string[]
  usedResourceItems: PageComponentResourceItem[]
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const groupedResourceItems = computed<GroupedResourceItem[]>(() => {
  const groupedMap = new Map<string, Set<string>>()

  props.usedResourceItems.forEach((item) => {
    const componentName = item.component_name.trim() || '未命名组件'
    const resourceName = item.resource_name.trim() || '未命名资源'

    if (!groupedMap.has(componentName)) {
      groupedMap.set(componentName, new Set<string>())
    }
    groupedMap.get(componentName)!.add(resourceName)
  })

  return Array.from(groupedMap.entries())
    .sort(([left], [right]) => left.localeCompare(right, 'zh-CN'))
    .map(([componentName, resourceNames]) => ({
      componentName,
      resources: Array.from(resourceNames)
        .sort((left, right) => left.localeCompare(right, 'zh-CN'))
        .map(resourceName => ({ resourceName })),
    }))
})
</script>

