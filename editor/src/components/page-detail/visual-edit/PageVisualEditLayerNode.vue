<!-- 文件功能：递归展示页面可视化编辑 Manifest 中的 Vue 容器、组件和循环层级。 -->
<template>
  <li class="space-y-1">
    <div class="flex items-center gap-1" :style="{ paddingLeft: `${props.depth * 12}px` }">
      <button
        v-if="props.node.children.length"
        type="button"
        class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700"
        :aria-label="expanded ? '收起子节点' : '展开子节点'"
        @click="expanded = !expanded"
      >
        <ChevronDown v-if="expanded" class="h-3.5 w-3.5" />
        <ChevronRight v-else class="h-3.5 w-3.5" />
      </button>
      <span v-else class="h-6 w-6 shrink-0" />

      <button
        type="button"
        class="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition"
        :class="props.selectedNodeId === props.node.node_id
          ? 'bg-indigo-50 font-semibold text-indigo-700 ring-1 ring-indigo-200'
          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'"
        :aria-current="props.selectedNodeId === props.node.node_id ? 'true' : undefined"
        @click="emit('select', props.node)"
      >
        <Component v-if="props.node.kind === 'component'" class="h-3.5 w-3.5 shrink-0 text-violet-500" />
        <Box v-else class="h-3.5 w-3.5 shrink-0 text-slate-400" />
        <span class="truncate">{{ nodeLabel }}</span>
        <span v-if="props.node.loop_context" class="shrink-0 rounded bg-sky-50 px-1.5 py-0.5 text-[10px] text-sky-700">
          v-for
        </span>
        <LockKeyhole
          v-if="props.node.loop_context && !props.node.loop_context.editable"
          class="h-3 w-3 shrink-0 text-amber-500"
          aria-label="循环只读"
        />
      </button>
    </div>

    <ul v-if="expanded && props.node.children.length" class="space-y-1">
      <PageVisualEditLayerNode
        v-for="child in props.node.children"
        :key="child.node_id"
        :node="child"
        :depth="props.depth + 1"
        :selected-node-id="props.selectedNodeId"
        @select="emit('select', $event)"
      />
    </ul>
  </li>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Box, ChevronDown, ChevronRight, Component, LockKeyhole } from '@lucide/vue'

import type { PageVisualEditNode } from '@/types/page-visual-edit'

const props = withDefaults(defineProps<{
  node: PageVisualEditNode
  selectedNodeId: string
  depth?: number
}>(), {
  depth: 0,
})

const emit = defineEmits<{
  select: [node: PageVisualEditNode]
}>()

const expanded = ref(true)
const nodeLabel = computed(() => (
  props.node.kind === 'root' ? 'Page' : props.node.tag
))

watch(
  () => props.selectedNodeId,
  (selectedNodeId) => {
    if (selectedNodeId && containsNode(props.node, selectedNodeId)) expanded.value = true
  },
  { immediate: true },
)

/** 判断当前子树是否包含画布选中的节点，用于自动展开祖先。 */
function containsNode(node: PageVisualEditNode, nodeId: string): boolean {
  return node.node_id === nodeId || node.children.some(child => containsNode(child, nodeId))
}
</script>
