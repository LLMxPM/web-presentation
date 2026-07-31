<!-- 文件功能：以“常用、更多、技术详情”的渐进结构编辑受限 Tailwind 样式。 -->
<template>
  <article class="space-y-3" @click="emit('select')" @focusin="emit('select')">
    <p
      v-if="props.templateLiteralWarning"
      class="rounded-ui-md bg-warning-muted px-3 py-2 text-xs text-warning"
    >
      此项来自模板字面量，保存后会修改全部重复项。
    </p>

    <div
      v-if="props.editable"
      class="overflow-hidden rounded-ui-lg border border-border bg-surface"
    >
      <UiTabs
        v-model="activeStyleTab"
        :items="styleTabs"
        list-class="px-2"
      >
        <template #common>
          <div class="p-3">
            <PageVisualEditTailwindGroupFields
              v-if="commonGroups.length"
              :binding-id="props.bindingId"
              :groups="commonGroups"
              @change="emit('change', $event)"
            />
            <p v-else class="py-5 text-center text-xs text-text-muted">
              当前元素没有可用的常用样式。
            </p>
          </div>
        </template>

        <template #more>
          <div v-if="moreSections.length" class="space-y-4 p-3">
            <section
              v-for="section in moreSections"
              :key="section.key"
              class="space-y-2"
            >
              <h4 class="text-xs font-semibold text-text-secondary">{{ section.label }}</h4>
              <PageVisualEditTailwindGroupFields
                :binding-id="props.bindingId"
                :groups="section.groups"
                @change="emit('change', $event)"
              />
            </section>
          </div>
          <p v-else class="p-5 text-center text-xs text-text-muted">
            当前元素没有更多可编辑样式。
          </p>
        </template>
      </UiTabs>
    </div>
    <p v-else class="rounded-ui-md bg-surface-muted px-3 py-2 text-xs text-text-secondary">
      {{ props.readonlyMessage }}
    </p>

    <details
      v-if="technicalKnownTokens.length || props.unknownTokens.length"
      class="rounded-ui-md border border-border bg-surface"
    >
      <summary
        class="flex min-h-control-sm cursor-pointer select-none items-center px-3 text-xs font-medium text-text-muted outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-border-focus"
      >
        技术详情
      </summary>
      <div class="space-y-3 border-t border-border p-3">
        <div v-if="technicalKnownTokens.length">
          <p class="mb-1.5 text-[11px] font-semibold text-text-secondary">当前 Tailwind 类名</p>
          <div class="flex flex-wrap gap-1.5">
            <code
              v-for="token in technicalKnownTokens"
              :key="token"
              class="rounded-ui-sm bg-surface-muted px-2 py-1 text-[10px] text-text-secondary"
            >
              {{ token }}
            </code>
          </div>
        </div>
        <div v-if="props.unknownTokens.length">
          <p class="mb-1.5 text-[11px] font-semibold text-warning">
            保留的复杂或未识别类（只读）
          </p>
          <div class="flex flex-wrap gap-1.5">
            <code
              v-for="token in props.unknownTokens"
              :key="token"
              class="rounded-ui-sm border border-warning/20 bg-warning-muted px-2 py-1 text-[10px] text-warning"
            >
              {{ token }}
            </code>
          </div>
        </div>
      </div>
    </details>

    <p v-if="props.pending" class="text-[11px] font-semibold text-info">
      此项有待保存修改；保存后画布刷新。
    </p>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import PageVisualEditTailwindGroupFields from '@/components/page-detail/visual-edit/PageVisualEditTailwindGroupFields.vue'
import {
  sectionTailwindGroups,
  type PageVisualEditTailwindGroupView,
} from '@/components/page-detail/visual-edit/page-visual-edit-tailwind-view'
import { UiTabs } from '@/components/ui'

const props = defineProps<{
  bindingId: string
  editable: boolean
  groups: PageVisualEditTailwindGroupView[]
  pending: boolean
  readonlyMessage: string
  templateLiteralWarning: boolean
  unknownTokens: string[]
  commonGroupKeys?: string[]
  allowedGroupKeys?: string[]
}>()

const emit = defineEmits<{
  change: [payload: { group: string; className: string }]
  select: []
}>()

const activeStyleTab = ref('common')
const styleTabs = [
  { value: 'common', label: '常用样式' },
  { value: 'more', label: '更多样式' },
]

const visibleGroups = computed(() => {
  if (props.allowedGroupKeys === undefined) return props.groups
  const allowedKeys = new Set(props.allowedGroupKeys)
  return props.groups.filter(group => allowedKeys.has(group.key))
})

const commonGroups = computed(() => {
  const groupByKey = new Map(visibleGroups.value.map(group => [group.key, group]))
  return (props.commonGroupKeys ?? [])
    .map(key => groupByKey.get(key))
    .filter((group): group is PageVisualEditTailwindGroupView => Boolean(group))
})

const moreSections = computed(() => {
  const commonKeys = new Set(commonGroups.value.map(group => group.key))
  return sectionTailwindGroups(visibleGroups.value.filter(group => !commonKeys.has(group.key)))
})

const technicalKnownTokens = computed(() => (
  [...new Set(props.groups.map(group => group.selectedClass).filter(Boolean))]
))
</script>
