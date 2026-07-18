<!-- 文件功能：提供页面 Vue 语义图层树容器，并把节点选择转发给可视化编辑面板。 -->
<template>
  <aside class="flex min-h-0 flex-col border-r border-slate-200 bg-white">
    <header class="border-b border-slate-200 px-4 py-3">
      <h3 class="text-sm font-bold text-slate-800">页面层级</h3>
      <p class="mt-1 text-xs text-slate-500">代码解析结果，不是实际 DOM</p>
    </header>
    <div class="min-h-0 flex-1 overflow-auto p-2">
      <ul v-if="props.root" class="space-y-1" role="tree" aria-label="页面容器层级">
        <PageVisualEditLayerNode
          :node="props.root"
          :selected-node-id="props.selectedNodeId"
          @select="emit('select', $event)"
        />
      </ul>
      <p v-else class="px-3 py-6 text-center text-xs text-slate-400">等待页面分析结果。</p>
    </div>
  </aside>
</template>

<script setup lang="ts">
import PageVisualEditLayerNode from '@/components/page-detail/visual-edit/PageVisualEditLayerNode.vue'
import type { PageVisualEditNode } from '@/types/page-visual-edit'

const props = defineProps<{
  root: PageVisualEditNode | null
  selectedNodeId: string
}>()

const emit = defineEmits<{
  select: [node: PageVisualEditNode]
}>()
</script>

