<!-- 文件功能：在叶子路由按组覆盖 schema 4 放映设置，空值继承项目默认，复用统一字段组件。 -->
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { UiCheckbox } from '@/components/ui'
import type { SlideshowAdvance, SlideshowCapabilities, SlideshowSettings, SlideshowTransition } from '@/types/api'
import ProjectSlideshowFields from './ProjectSlideshowFields.vue'
import { createSlideshowDraft, normalizeSlideshowDraft, formatSlideshowAdvance, TRANSITION_EFFECT_LABELS, formatMillisecondsAsSeconds, type SlideshowDraft } from './project-slideshow-values'

const props = withDefaults(defineProps<{ transition: SlideshowTransition | null; advance: SlideshowAdvance | null; defaults: SlideshowSettings; capabilities?: SlideshowCapabilities | null }>(), { capabilities: null })
const emit = defineEmits<{ 'update:transition': [value: SlideshowTransition | null]; 'update:advance': [value: SlideshowAdvance | null] }>()
const overrideTransition = ref(props.transition != null), overrideAdvance = ref(props.advance != null)
const draft = ref(createSlideshowDraft(props.defaults))
const inheritedTransitionSummary = computed(() => `继承项目默认：${TRANSITION_EFFECT_LABELS[props.defaults.transition.effect]} ${formatMillisecondsAsSeconds(props.defaults.transition.duration_ms)} 秒。`)
const inheritedAdvanceSummary = computed(() => `继承项目默认：${formatSlideshowAdvance(props.defaults.advance)}。`)
watch(() => [props.transition, props.advance, props.defaults] as const, () => {
  overrideTransition.value = props.transition != null; overrideAdvance.value = props.advance != null
  draft.value = createSlideshowDraft({ ...props.defaults, transition: props.transition ?? props.defaults.transition, advance: props.advance ?? props.defaults.advance })
}, { deep: true, immediate: true })

/** 开启覆盖按当前生效值初始化，关闭时只清除这一组。 */
function toggleTransition(value: boolean | 'indeterminate'): void { overrideTransition.value = value === true; emit('update:transition', overrideTransition.value ? normalizeSlideshowDraft(draft.value).transition : null) }
/** 翻页覆盖与动画独立，恢复继承不会覆盖另一组编辑。 */
function toggleAdvance(value: boolean | 'indeterminate'): void { overrideAdvance.value = value === true; emit('update:advance', overrideAdvance.value ? normalizeSlideshowDraft(draft.value).advance : null) }
/** 草稿更新只保存在当前表单，失焦或选项切换时才提交目标组。 */
function updateDraft(value: SlideshowDraft): void { draft.value = value }
/** 每次提交重新收敛字段范围，null 保持明确继承语义。 */
function commitTransition(): void { if (overrideTransition.value) emit('update:transition', normalizeSlideshowDraft(draft.value).transition) }
/** 完成后停留与定时停留各自保留，不再传输旧超时字段。 */
function commitAdvance(): void { if (overrideAdvance.value) emit('update:advance', normalizeSlideshowDraft(draft.value).advance) }
</script>
<template>
  <div class="grid gap-4">
    <fieldset class="min-w-0 rounded-ui-lg border border-border p-3">
      <label class="flex items-center gap-2 text-sm font-semibold text-text-emphasis"><UiCheckbox :model-value="overrideTransition" @update:model-value="toggleTransition" />覆盖翻页动画</label>
      <p v-if="!overrideTransition" class="mt-1 text-xs text-text-muted">{{ inheritedTransitionSummary }}</p>
      <ProjectSlideshowFields v-else class="mt-3" :draft="draft" :capabilities="capabilities" section="transition" :show-loop="false" @update:draft="updateDraft" @commit="commitTransition" />
    </fieldset>
    <fieldset class="min-w-0 rounded-ui-lg border border-border p-3">
      <label class="flex items-center gap-2 text-sm font-semibold text-text-emphasis"><UiCheckbox :model-value="overrideAdvance" @update:model-value="toggleAdvance" />覆盖翻页方式</label>
      <p v-if="!overrideAdvance" class="mt-1 text-xs text-text-muted">{{ inheritedAdvanceSummary }}</p>
      <ProjectSlideshowFields v-else class="mt-3" :draft="draft" :capabilities="capabilities" section="advance" :show-loop="false" @update:draft="updateDraft" @commit="commitAdvance" />
    </fieldset>
  </div>
</template>
