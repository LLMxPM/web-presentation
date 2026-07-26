<!-- 文件功能：提供高级页面结构树，并把语义化节点选择转发给可视化编辑面板。 -->
<template>
  <aside class="flex min-h-0 flex-col border-r border-[rgb(var(--ui-border))] bg-[rgb(var(--ui-surface))]">
    <header class="flex items-start justify-between gap-3 border-b border-[rgb(var(--ui-border))] px-4 py-3">
      <div class="min-w-0">
        <h3 class="text-sm font-bold text-[rgb(var(--ui-text))]">页面结构（高级）</h3>
        <p class="mt-1 text-xs text-[rgb(var(--ui-text-muted))]">按内容理解页面层级</p>
      </div>
      <UiIconButton
        label="收起页面结构"
        size="sm"
        class="shrink-0"
        @click="emit('close')"
      >
        <PanelLeftClose class="h-4 w-4" />
      </UiIconButton>
    </header>
    <div ref="treeScroller" class="min-h-0 flex-1 overflow-auto p-2">
      <ul v-if="props.root" class="space-y-1" role="tree" aria-label="页面结构">
        <PageVisualEditLayerNode
          :node="props.root"
          :component-schemas="props.componentSchemas"
          :selected-node-id="props.selectedNodeId"
          @select="emit('select', $event)"
        />
      </ul>
      <p v-else class="px-3 py-6 text-center text-xs text-text-disabled">等待页面分析结果。</p>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { PanelLeftClose } from '@lucide/vue'

import PageVisualEditLayerNode from '@/components/page-detail/visual-edit/PageVisualEditLayerNode.vue'
import { UiIconButton } from '@/components/ui'
import type { PageVisualEditComponentSchema, PageVisualEditNode } from '@/types/page-visual-edit'

const props = defineProps<{
  root: PageVisualEditNode | null
  selectedNodeId: string
  componentSchemas: Record<string, PageVisualEditComponentSchema>
}>()

const emit = defineEmits<{
  select: [node: PageVisualEditNode]
  close: []
}>()

const treeScroller = ref<HTMLElement | null>(null)

watch(
  () => props.selectedNodeId,
  async () => {
    await nextTick()
    treeScroller.value?.querySelector<HTMLElement>('[aria-current="true"]')
      ?.scrollIntoView?.({ block: 'nearest' })
  },
)
</script>
