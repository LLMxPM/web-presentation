<!-- 文件功能：承载 Runtime Kit doc-only 能力说明弹窗，展示用法、返回值、约束与面向对象。 -->
<template>
  <UiDialog
    :open="modelValue"
    title="能力说明"
    size="wide"
    body-preset="auto"
    @update:open="emit('update:modelValue', $event)"
  >
    <div v-if="item" class="space-y-5">
        <header class="space-y-2">
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="truncate text-lg font-bold text-text">{{ item.display_name }}</h3>
            <span class="rounded bg-surface-muted px-2 py-0.5 text-[10px] font-black uppercase text-text-secondary">
              {{ item.kind }}
            </span>
            <span class="rounded bg-warning-muted px-2 py-0.5 text-[10px] font-black uppercase text-warning">doc-only</span>
          </div>
          <p class="truncate text-xs text-text-disabled">{{ item.import_path }}</p>
        </header>

        <section class="rounded-xl border border-border bg-canvas p-4">
          <p class="text-sm leading-7 text-text-secondary">{{ item.summary || item.description }}</p>
        </section>

        <section v-if="item.tags.length" class="flex flex-wrap gap-2">
          <span
            v-for="tag in item.tags"
            :key="`${item.name}-${tag}`"
            class="rounded-full bg-canvas px-2 py-1 text-[11px] font-semibold text-text-muted"
          >
            {{ tag }}
          </span>
        </section>

        <section v-if="item.usage.length" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-text-muted">调用示例</h4>
          <pre
            v-for="(usageLine, index) in item.usage"
            :key="`${item.name}-usage-${index}`"
            class="overflow-x-auto rounded-xl border border-border bg-canvas p-3 text-xs text-text-emphasis"
          ><code>{{ usageLine }}</code></pre>
        </section>

        <section v-if="item.returns" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-text-muted">返回值</h4>
          <p class="rounded-xl border border-border bg-canvas p-3 text-sm text-text-emphasis">{{ item.returns }}</p>
        </section>

        <section v-if="item.return_example.length" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-text-muted">返回示例</h4>
          <pre class="overflow-x-auto rounded-xl border border-border bg-canvas p-3 text-xs text-text-emphasis"><code>{{ item.return_example.join('\n') }}</code></pre>
        </section>

        <section v-if="item.constraints.length" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-text-muted">约束</h4>
          <ul class="space-y-2">
            <li
              v-for="(constraint, index) in item.constraints"
              :key="`${item.name}-constraint-${index}`"
              class="rounded-xl border border-border bg-canvas p-3 text-sm text-text-emphasis"
            >
              {{ constraint }}
            </li>
          </ul>
        </section>

        <section v-if="item.audiences.length" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-text-muted">面向对象</h4>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="audience in item.audiences"
              :key="`${item.name}-audience-${audience}`"
              class="rounded-full bg-surface-selected px-2 py-1 text-[11px] font-bold text-accent"
            >
              {{ audience }}
            </span>
          </div>
        </section>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { UiDialog } from '@/components/ui'
import type { RuntimeKitComponentCapabilityItem } from '@/types/api'

defineProps<{
  modelValue: boolean
  item: RuntimeKitComponentCapabilityItem | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()
</script>

