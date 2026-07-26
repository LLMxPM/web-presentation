<!-- 文件功能：共享的样式规范 Markdown 预览组件，统一详情弹窗与编辑弹窗的规范排版样式。 -->
<template>
  <div class="style-spec-markdown">
    <MarkdownRender :nodes="specNodes" />
  </div>
</template>

<script setup lang="ts">
import 'markstream-vue/index.css'

import { computed } from 'vue'
import MarkdownRender, { getMarkdown, parseMarkdownToStructure } from 'markstream-vue'

const props = defineProps<{
  /** 待渲染的 Markdown 样式规范文本。 */
  markdown: string
}>()

const markdownParser = getMarkdown()

/** 把 Markdown 文本解析为一次性渲染的结构化节点。 */
const specNodes = computed(() => parseMarkdownToStructure(props.markdown, markdownParser, {
  final: true,
}))
</script>

<style scoped>
.style-spec-markdown :deep(.markstream-vue) {
  background: transparent;
  color: rgb(var(--ui-text-emphasis));
  font-size: 0.875rem;
  line-height: 1.75;
}

.style-spec-markdown :deep(.markstream-vue > :first-child) {
  margin-top: 0;
}

.style-spec-markdown :deep(.markstream-vue > :last-child) {
  margin-bottom: 0;
}

.style-spec-markdown :deep(.markstream-vue > * + *) {
  margin-top: 0.75rem;
}

.style-spec-markdown :deep(h1),
.style-spec-markdown :deep(h2),
.style-spec-markdown :deep(h3) {
  color: rgb(var(--ui-text-strong));
  font-weight: 800;
  line-height: 1.3;
}

.style-spec-markdown :deep(h1) {
  font-size: 1.25rem;
}

.style-spec-markdown :deep(h2) {
  font-size: 1.125rem;
}

.style-spec-markdown :deep(h3) {
  font-size: 1rem;
}

.style-spec-markdown :deep(ul),
.style-spec-markdown :deep(ol) {
  padding-left: 1.25rem;
}

.style-spec-markdown :deep(code:not(pre code)) {
  border-radius: 0.375rem;
  background: rgb(var(--ui-surface-muted));
  padding: 0.125rem 0.375rem;
  color: rgb(var(--ui-text));
  font-size: 0.8125rem;
}

/* 代码块使用固定深色面 Token，两种主题下保持深底浅字，不随夜间模式翻转。 */
.style-spec-markdown :deep(pre) {
  overflow-x: auto;
  border-radius: 0.75rem;
  background: rgb(var(--ui-surface-inverse-raised));
  padding: 1rem;
  color: rgb(var(--ui-text-on-inverse));
}
</style>
