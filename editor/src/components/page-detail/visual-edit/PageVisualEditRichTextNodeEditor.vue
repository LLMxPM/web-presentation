<!-- 文件功能：递归展示结构化富文本节点，并发出文本、选区和结构编辑事件。 -->
<template>
  <div class="space-y-2">
    <template v-for="node in props.nodes" :key="node.id">
      <textarea
        v-if="node.kind === 'text'"
        :aria-label="`文本片段 ${node.id}`"
        :disabled="props.disabled"
        :rows="textRows(node.text)"
        :value="node.text"
        class="w-full resize-y rounded-md border border-slate-200 bg-white px-2.5 py-2 text-sm leading-5 text-slate-700 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-500"
        @focus="emitSelection($event, node.id)"
        @input="emitTextChange($event, node.id)"
        @keyup="emitSelection($event, node.id)"
        @mouseup="emitSelection($event, node.id)"
        @select="emitSelection($event, node.id)"
      />

      <article
        v-else
        class="rounded-lg border p-2.5"
        :class="node.locked ? 'border-amber-200 bg-amber-50/50' : 'border-slate-200 bg-slate-50/60'"
      >
        <header class="mb-2 flex items-center gap-2">
          <span class="rounded bg-white px-1.5 py-0.5 text-[11px] font-bold text-slate-600 shadow-sm">
            {{ tagLabel(node.tag) }}
          </span>
          <button
            v-if="node.locked"
            type="button"
            class="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 hover:bg-amber-200"
            :aria-expanded="expandedNodeIds.has(node.id)"
            :aria-label="`${expandedNodeIds.has(node.id) ? '隐藏' : '查看'}样式锁定详情 ${node.tag}`"
            @click="toggleDetails(node.id)"
          >
            样式锁定
          </button>
          <button
            v-if="node.locked && !props.disabled"
            type="button"
            class="ml-auto shrink-0 rounded px-2 py-1 text-[11px] font-semibold text-rose-600 hover:bg-rose-50"
            :aria-label="`删除锁定样式 ${node.tag}`"
            @click="emit('remove-lock', node.id)"
          >
            删除锁定样式
          </button>
          <button
            v-else-if="node.tag !== 'span' && !props.disabled"
            type="button"
            class="ml-auto shrink-0 rounded px-2 py-1 text-[11px] font-semibold text-slate-500 hover:bg-white hover:text-indigo-700"
            :aria-label="`取消${tagLabel(node.tag)}`"
            @click="emit('unwrap-node', node.id)"
          >
            取消标签
          </button>
        </header>

        <code
          v-if="node.locked && expandedNodeIds.has(node.id)"
          class="mb-2 block overflow-x-auto whitespace-pre-wrap break-all rounded-md border border-amber-200 bg-white px-2 py-1.5 text-[10px] leading-4 text-amber-900"
        >{{ node.openingTag }}</code>

        <PageVisualEditRichTextNodeEditor
          :nodes="node.children"
          :disabled="props.disabled"
          :semantic-tags="childSemanticTags(node.tag)"
          @remove-lock="emit('remove-lock', $event)"
          @selection-change="emit('selection-change', $event)"
          @text-change="emit('text-change', $event)"
          @unwrap-node="emit('unwrap-node', $event)"
        />
      </article>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import type { PageVisualEditRichTextNode } from '@/utils/page-visual-edit-rich-text'

interface PageVisualEditRichTextSelection {
  nodeId: string
  start: number
  end: number
  semanticTags: Array<'strong' | 'em'>
}

const props = withDefaults(defineProps<{
  nodes: PageVisualEditRichTextNode[]
  disabled?: boolean
  semanticTags?: Array<'strong' | 'em'>
}>(), {
  disabled: false,
  semanticTags: () => [],
})

const emit = defineEmits<{
  'remove-lock': [nodeId: string]
  'selection-change': [selection: PageVisualEditRichTextSelection]
  'text-change': [payload: { nodeId: string; text: string }]
  'unwrap-node': [nodeId: string]
}>()

const expandedNodeIds = ref(new Set<string>())

/** 发出文本变化，输入框天然只接受纯文本粘贴。 */
function emitTextChange(event: Event, nodeId: string): void {
  const textarea = event.target as HTMLTextAreaElement
  emit('text-change', { nodeId, text: textarea.value })
  emitSelection(event, nodeId)
}

/** 记录单个文本框内的选区，供顶层工具栏添加语义标签。 */
function emitSelection(event: Event, nodeId: string): void {
  const textarea = event.target as HTMLTextAreaElement
  emit('selection-change', {
    nodeId,
    start: textarea.selectionStart ?? 0,
    end: textarea.selectionEnd ?? 0,
    semanticTags: props.semanticTags,
  })
}

/** 计算嵌套节点传递给后代的现有语义标签。 */
function childSemanticTags(tag: string): Array<'strong' | 'em'> {
  const semanticTag = tag.toLowerCase()
  if ((semanticTag !== 'strong' && semanticTag !== 'em') || props.semanticTags.includes(semanticTag)) {
    return props.semanticTags
  }
  return [...props.semanticTags, semanticTag]
}

/** 提供面向用户的语义标签名称。 */
function tagLabel(tag: string): string {
  if (tag.toLowerCase() === 'strong') return '加粗 strong'
  if (tag.toLowerCase() === 'em') return '强调 em'
  if (tag.toLowerCase() === 'a') return '链接 a'
  return `标签 ${tag}`
}

/** 展开或收起锁定标签的具体 opening tag 与属性。 */
function toggleDetails(nodeId: string): void {
  const next = new Set(expandedNodeIds.value)
  if (next.has(nodeId)) next.delete(nodeId)
  else next.add(nodeId)
  expandedNodeIds.value = next
}

/** 根据换行数量为文本片段提供有限的初始高度。 */
function textRows(text: string): number {
  return Math.min(6, Math.max(2, text.split('\n').length))
}
</script>
