<!-- 文件功能：承载 Runtime Kit doc-only 能力说明弹窗，展示用法、返回值、约束与面向对象。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    title="能力说明"
    size="wide"
    body-preset="auto"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="item" class="space-y-5">
        <header class="space-y-2">
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="truncate text-lg font-bold text-slate-800">{{ item.display_name }}</h3>
            <span class="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-black uppercase text-slate-600">
              {{ item.kind }}
            </span>
            <span class="rounded bg-amber-50 px-2 py-0.5 text-[10px] font-black uppercase text-amber-600">doc-only</span>
          </div>
          <p class="truncate text-xs text-slate-400">{{ item.import_path }}</p>
        </header>

        <section class="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <p class="text-sm leading-7 text-slate-600">{{ item.summary || item.description }}</p>
        </section>

        <section v-if="item.tags.length" class="flex flex-wrap gap-2">
          <span
            v-for="tag in item.tags"
            :key="`${item.name}-${tag}`"
            class="rounded-full bg-slate-50 px-2 py-1 text-[11px] font-semibold text-slate-500"
          >
            {{ tag }}
          </span>
        </section>

        <section v-if="item.usage.length" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-slate-500">调用示例</h4>
          <pre
            v-for="(usageLine, index) in item.usage"
            :key="`${item.name}-usage-${index}`"
            class="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700"
          ><code>{{ usageLine }}</code></pre>
        </section>

        <section v-if="item.returns" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-slate-500">返回值</h4>
          <p class="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">{{ item.returns }}</p>
        </section>

        <section v-if="item.return_example.length" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-slate-500">返回示例</h4>
          <pre class="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700"><code>{{ item.return_example.join('\n') }}</code></pre>
        </section>

        <section v-if="item.constraints.length" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-slate-500">约束</h4>
          <ul class="space-y-2">
            <li
              v-for="(constraint, index) in item.constraints"
              :key="`${item.name}-constraint-${index}`"
              class="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700"
            >
              {{ constraint }}
            </li>
          </ul>
        </section>

        <section v-if="item.audiences.length" class="space-y-2">
          <h4 class="text-xs font-black uppercase tracking-wide text-slate-500">面向对象</h4>
          <div class="flex flex-wrap gap-2">
            <span
              v-for="audience in item.audiences"
              :key="`${item.name}-audience-${audience}`"
              class="rounded-full bg-indigo-50 px-2 py-1 text-[11px] font-bold text-indigo-600"
            >
              {{ audience }}
            </span>
          </div>
        </section>
    </div>
  </BaseDialog>
</template>

<script setup lang="ts">
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type { RuntimeKitComponentCapabilityItem } from '@/types/api'

defineProps<{
  modelValue: boolean
  item: RuntimeKitComponentCapabilityItem | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()
</script>

