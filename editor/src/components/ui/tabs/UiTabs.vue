<!-- 文件功能：基于 Reka UI 提供页面和面板级标签切换。 -->
<template>
  <TabsRoot :model-value="modelValue" :orientation="orientation" class="min-w-0" @update:model-value="emit('update:modelValue', $event)">
    <TabsList class="flex items-center gap-1 border-b border-slate-200" :class="listClass"><TabsTrigger v-for="item in items" :key="item.value" :value="item.value" :disabled="item.disabled" class="border-b-2 border-transparent px-3 py-2 text-sm text-slate-500 outline-none transition hover:text-slate-800 focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 data-[state=active]:border-indigo-600 data-[state=active]:font-semibold data-[state=active]:text-indigo-700">{{ item.label }}</TabsTrigger></TabsList>
    <TabsContent v-for="item in items" :key="`${item.value}-content`" :value="item.value" class="outline-none"><slot :name="item.value" /></TabsContent>
  </TabsRoot>
</template>
<script setup lang="ts">
import { TabsContent, TabsList, TabsRoot, TabsTrigger } from 'reka-ui'
defineProps<{ modelValue: string; items: Array<{ label: string; value: string; disabled?: boolean }>; orientation?: 'horizontal' | 'vertical'; listClass?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
