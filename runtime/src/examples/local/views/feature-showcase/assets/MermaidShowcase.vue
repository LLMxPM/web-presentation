<!--
  文件用途：本地示例页，展示 AssetMermaid 渲染文本图表资源与主题切换。
-->
<template>
  <ShowcasePage
    title="Mermaid 图表"
    subtitle="文本图表由 Runtime 在浏览器端渲染，页面只提供源码"
    :capabilities="capabilities"
  >
    <div class="grid h-full min-h-0 grid-cols-[1.6fr_0.9fr] gap-5">
      <section class="flex min-h-0 flex-col rounded-lg border border-border-subtle bg-background-subtle p-4">
        <div class="mb-3 flex items-center gap-2">
          <Icon name="路由-copy" class="size-4 text-primary" />
          <h2 class="font-heading text-base font-semibold text-primary">{{ currentDiagram.label }}</h2>
          <span class="font-body text-xs text-secondary">{{ currentDiagram.description }}</span>
          <select v-model="selectedTheme" class="showcase-input ml-auto w-32">
            <option value="default">default</option>
            <option value="dark">dark</option>
            <option value="forest">forest</option>
            <option value="neutral">neutral</option>
          </select>
        </div>
        <AssetMermaid
          :content="currentDiagram.content"
          :theme="selectedTheme"
          width="100%"
          height="100%"
          class="min-h-0 flex-1 rounded-md bg-default p-3"
        />
      </section>

      <section class="flex min-h-0 flex-col gap-4">
        <div class="rounded-lg border border-border bg-background-subtle p-5">
          <h3 class="mb-3 font-heading text-base font-semibold text-primary">图表类型</h3>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="diagram in MERMAID_DIAGRAMS"
              :key="diagram.key"
              type="button"
              class="rounded-md border px-3 py-2 font-body text-xs font-medium transition-colors"
              :class="diagram.key === selectedDiagram
                ? 'border-primary bg-primary-50 text-primary'
                : 'border-border text-secondary hover:border-primary-300'"
              @click="selectedDiagram = diagram.key"
            >
              {{ diagram.label }}
            </button>
          </div>
        </div>

        <div class="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-background-subtle p-5">
          <div class="mb-2 flex items-center justify-between">
            <h3 class="font-heading text-base font-semibold text-primary">图表源码</h3>
            <span class="font-code text-xs text-secondary">{{ currentDiagram.content.length }} 字符</span>
          </div>
          <pre class="min-h-0 flex-1 overflow-auto rounded-md bg-default p-3 font-code text-xs leading-6 text-primary">{{ currentDiagram.content }}</pre>
          <p class="mt-2 font-body text-xs leading-6 text-secondary">
            资源形式使用 name 引用 Mermaid 资源；主题、宽高与内边距通过属性透传。
          </p>
        </div>
      </section>
    </div>
  </ShowcasePage>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ShowcasePage, { type ShowcaseCapability } from '@/examples/local/components/ShowcasePage.vue'
import AssetMermaid from '@runtime-kit/public/components/assets/AssetMermaid.v1.vue'
import Icon from '@runtime-kit/public/components/primitives/Icon.v1.vue'
import { MERMAID_DIAGRAMS, type MermaidDiagramKey } from './mermaid-diagrams'

const capabilities: ShowcaseCapability[] = [
  { name: 'AssetMermaid.v1', path: '@runtime-kit/public/components/assets/AssetMermaid.v1.vue' },
]

const selectedDiagram = ref<MermaidDiagramKey>('flowchart')
const selectedTheme = ref<'default' | 'dark' | 'forest' | 'neutral'>('default')

const currentDiagram = computed(
  () => MERMAID_DIAGRAMS.find((diagram) => diagram.key === selectedDiagram.value) || MERMAID_DIAGRAMS[0],
)
</script>

<style scoped>
.showcase-input {
  border-radius: 8px;
  border: 1px solid var(--tw-color-border-default);
  background: var(--tw-color-bg-default);
  padding: 6px 10px;
  color: var(--tw-color-text-primary);
  font-size: 12px;
  outline: none;
}
</style>
