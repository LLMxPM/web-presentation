<!-- 文件功能：以保持、继承或覆盖三种原子操作批量设置选中路由，复用 schema 4 放映字段。 -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { UiButton, UiDialog, UiSegmentedControl } from '@/components/ui'
import type { SlideshowCapabilities, SlideshowSettings } from '@/types/api'
import type { SlideshowBatchPatch } from '@/utils/project-route-slideshow'
import ProjectSlideshowFields from './ProjectSlideshowFields.vue'
import { createSlideshowDraft, normalizeSlideshowDraft } from './project-slideshow-values'

type BatchAction = 'keep' | 'inherit' | 'override'
const props = withDefaults(defineProps<{ open: boolean; itemCount: number; pageCount: number; defaults: SlideshowSettings; capabilities?: SlideshowCapabilities | null }>(), { capabilities: null })
const emit = defineEmits<{ 'update:open': [value: boolean]; apply: [value: SlideshowBatchPatch] }>()
const actions = [{ label: '不修改', value: 'keep' }, { label: '恢复继承', value: 'inherit' }, { label: '设置覆盖', value: 'override' }]
const transitionAction = ref<BatchAction>('keep'), advanceAction = ref<BatchAction>('keep'), draft = ref(createSlideshowDraft(props.defaults))
const canApply = computed(() => transitionAction.value !== 'keep' || advanceAction.value !== 'keep')
watch(() => props.open, open => { if (open) { transitionAction.value = 'keep'; advanceAction.value = 'keep'; draft.value = createSlideshowDraft(props.defaults) } }, { immediate: true })

/** 每一组只有选择覆盖或继承时才出现，保持原样不产生字段，父级可整批原子保存。 */
function apply(): void {
  if (!canApply.value) return
  const normalized = normalizeSlideshowDraft(draft.value), patch: SlideshowBatchPatch = {}
  if (transitionAction.value !== 'keep') patch.transition = transitionAction.value === 'inherit' ? null : normalized.transition
  if (advanceAction.value !== 'keep') patch.advance = advanceAction.value === 'inherit' ? null : normalized.advance
  emit('apply', patch); emit('update:open', false)
}
</script>
<template>
  <UiDialog :open="open" title="批量放映设置" size="compact" width="600px" body-preset="dense" :panel-style="{ height: 'auto' }" @update:open="emit('update:open', $event)">
    <div class="grid gap-4">
      <p class="text-sm text-text-muted">将应用到 {{ pageCount }} 个页面<template v-if="itemCount > pageCount">（共 {{ itemCount }} 项）</template>。隐藏页保存设置，但不参与放映。</p>
      <section class="rounded-ui-lg border border-border p-3">
        <h4 class="mb-2 text-sm font-semibold text-text-emphasis">翻页动画</h4>
        <UiSegmentedControl v-model="transitionAction" :options="actions" aria-label="翻页动画处理方式" />
        <p v-if="transitionAction === 'inherit'" class="mt-2 text-xs text-text-muted">清除动画覆盖，恢复项目默认。</p>
        <ProjectSlideshowFields v-if="transitionAction === 'override'" v-model:draft="draft" class="mt-3" section="transition" :show-loop="false" :capabilities="capabilities" />
      </section>
      <section class="rounded-ui-lg border border-border p-3">
        <h4 class="mb-2 text-sm font-semibold text-text-emphasis">翻页方式</h4>
        <UiSegmentedControl v-model="advanceAction" :options="actions" aria-label="翻页方式处理方式" />
        <p v-if="advanceAction === 'inherit'" class="mt-2 text-xs text-text-muted">清除翻页覆盖，恢复项目默认。</p>
        <ProjectSlideshowFields v-if="advanceAction === 'override'" v-model:draft="draft" class="mt-3" section="advance" :show-loop="false" :capabilities="capabilities" />
      </section>
    </div>
    <template #footer><UiButton variant="secondary" @click="emit('update:open', false)">取消</UiButton><UiButton :disabled="!canApply" @click="apply">应用到选中页面</UiButton></template>
  </UiDialog>
</template>
