<!-- 文件功能：递归展示页面可视化编辑 Manifest 中的 Vue 容器、组件和循环层级。 -->
<template>
  <li class="space-y-1">
    <div class="flex items-center" :style="{ paddingLeft: `${props.depth * 12}px` }">
      <UiIconButton
        v-if="props.node.children.length"
        type="button"
        :label="expanded ? '收起子节点' : '展开子节点'"
        size="xs"
        class="h-6 w-6 shrink-0 rounded text-text-disabled hover:bg-surface-muted hover:text-text-emphasis"
        :aria-label="expanded ? '收起子节点' : '展开子节点'"
        @click="expanded = !expanded"
      >
        <ChevronDown v-if="expanded" class="h-3.5 w-3.5" />
        <ChevronRight v-else class="h-3.5 w-3.5" />
      </UiIconButton>
      <span v-else class="h-6 w-6 shrink-0" />

      <UiButton
        type="button"
        variant="ghost"
        size="xs"
        content-align="start"
        class="h-auto flex min-w-0 flex-1 items-center gap-2 rounded-lg py-1.5 pl-1 pr-2 text-left text-xs transition"
        :class="props.selectedNodeId === props.node.node_id
          ? 'bg-surface-selected font-semibold text-accent-hover ring-1 ring-accent-ring'
          : 'text-text-secondary hover:bg-surface-hover hover:text-text-strong'"
        :aria-current="props.selectedNodeId === props.node.node_id ? 'true' : undefined"
        @click="emit('select', props.node)"
      >
        <ImageIcon v-if="isImageNode" class="h-3.5 w-3.5 shrink-0 text-ai" />
        <Component v-else-if="props.node.kind === 'component'" class="h-3.5 w-3.5 shrink-0 text-ai" />
        <Box v-else class="h-3.5 w-3.5 shrink-0 text-text-disabled" />
        <span class="min-w-0 flex-1 truncate" :title="nodeLabel">{{ nodeLabel }}</span>
        <span v-if="props.node.loop_context" class="shrink-0 rounded bg-info-muted px-1.5 py-0.5 text-[10px] text-info-strong">
          v-for
        </span>
        <LockKeyhole
          v-if="props.node.loop_context && !props.node.loop_context.editable"
          class="h-3 w-3 shrink-0 text-warning"
          aria-label="循环只读"
        />
      </UiButton>
    </div>

    <ul v-if="expanded && props.node.children.length" class="space-y-1">
      <PageVisualEditLayerNode
        v-for="child in props.node.children"
        :key="child.node_id"
        :node="child"
        :depth="props.depth + 1"
        :component-schemas="props.componentSchemas"
        :selected-node-id="props.selectedNodeId"
        @select="emit('select', $event)"
      />
    </ul>
  </li>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Box, ChevronDown, ChevronRight, Component, Image as ImageIcon, LockKeyhole } from '@lucide/vue'

import { UiButton, UiIconButton } from '@/components/ui'
import type {
  PageVisualEditBinding,
  PageVisualEditComponentSchema,
  PageVisualEditNode,
} from '@/types/page-visual-edit'

const props = withDefaults(defineProps<{
  node: PageVisualEditNode
  selectedNodeId: string
  depth?: number
  componentSchemas?: Record<string, PageVisualEditComponentSchema>
}>(), {
  depth: 0,
  componentSchemas: () => ({}),
})

const emit = defineEmits<{
  select: [node: PageVisualEditNode]
}>()

const expanded = ref(true)
const componentSchema = computed(() => props.componentSchemas[props.node.tag] ?? null)
const isAssetImage = computed(() => (
  props.node.kind === 'component'
  && (
    componentSchema.value?.component_code === 'AssetImage'
    || normalizeComponentName(props.node.tag) === 'assetimage'
  )
))
const isImageNode = computed(() => isAssetImage.value || props.node.tag.toLowerCase() === 'img')
const nodeLabel = computed(() => buildSemanticLabel(props.node, componentSchema.value, isAssetImage.value))

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

/**
 * 根据节点职责和静态内容生成面向创作者的图层名称。
 * 原始 tag 只保留在技术提示中，不作为普通元素的主标签。
 */
function buildSemanticLabel(
  node: PageVisualEditNode,
  schema: PageVisualEditComponentSchema | null,
  assetImage: boolean,
): string {
  if (node.kind === 'root') return '页面'

  const tag = node.tag.toLowerCase()
  const text = bindingSnippet(node.bindings, binding => binding.kind === 'text' || binding.kind === 'rich_text')
  if (/^h[1-6]$/.test(tag)) return labelWithContent('标题', text)
  if (assetImage) {
    const imageDescription = bindingSnippet(
      node.bindings,
      binding => binding.kind === 'prop' && binding.name === 'alt',
    ) || bindingSnippet(
      node.bindings,
      binding => binding.kind === 'prop' && binding.name === 'name',
    )
    return labelWithContent('图片', imageDescription)
  }
  if (node.kind === 'component') {
    const componentName = schema?.component_code || node.tag || '自定义组件'
    return text ? `组件：${componentName} · ${text}` : `组件：${componentName}`
  }

  if (tag === 'img') return '原生图片'
  if (tag === 'p' || tag === 'span' || tag === 'label' || tag === 'strong' || tag === 'small' || tag === 'blockquote') {
    return labelWithContent('文本', text)
  }
  if (tag === 'a') return labelWithContent('链接', text)
  if (tag === 'button') return labelWithContent('按钮', text)
  if (tag === 'section' || tag === 'article' || tag === 'main' || tag === 'header' || tag === 'footer' || tag === 'nav' || tag === 'aside') {
    return labelWithContent('区块', text)
  }
  if (tag === 'div') return labelWithContent('容器', text)
  if (tag === 'ul' || tag === 'ol') return labelWithContent('列表', text)
  if (tag === 'li') return labelWithContent('列表项', text)
  if (tag === 'table') return '表格'
  if (tag === 'form') return '表单'
  return labelWithContent('元素', text)
}

/** 从可静态读取的绑定中提取适合作为图层说明的短文本。 */
function bindingSnippet(
  bindings: PageVisualEditBinding[],
  predicate: (binding: PageVisualEditBinding) => boolean,
): string {
  for (const binding of bindings) {
    if (!predicate(binding) || typeof binding.value !== 'string') continue
    const normalized = binding.value
      .replace(/<[^>]*>/g, ' ')
      .replace(/&nbsp;/gi, ' ')
      .replace(/\s+/g, ' ')
      .trim()
    if (!normalized) continue
    const characters = Array.from(normalized)
    return characters.length > 18 ? `${characters.slice(0, 18).join('')}…` : normalized
  }
  return ''
}

/** 为语义节点追加短内容；无静态内容时只显示职责名称。 */
function labelWithContent(label: string, content: string): string {
  return content ? `${label}：${content}` : label
}

/** 统一组件标签格式，兼容 PascalCase 与 kebab-case。 */
function normalizeComponentName(value: string): string {
  return value.replace(/[-_]/g, '').toLowerCase()
}
</script>
