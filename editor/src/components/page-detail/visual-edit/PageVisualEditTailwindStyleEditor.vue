<!-- 文件功能：渲染可视化编辑属性面板中的 Tailwind 分组样式控件，支持折叠、类名回显和未知类只读展示。 -->
<template>
  <article class="space-y-3" @click="emit('select')" @focusin="emit('select')">
    <p
      v-if="props.templateLiteralWarning"
      class="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800"
    >
      此项来自模板字面量，保存后会修改所有循环实例。
  </p>
    <template v-if="props.editable">
      <section
        v-for="section in groupedSections"
        :key="section.key"
        class="overflow-hidden rounded-lg border border-slate-200 bg-white"
      >
        <button
          type="button"
          class="flex w-full items-center justify-between gap-3 bg-slate-50 px-3 py-2 text-left transition hover:bg-slate-100"
          :aria-expanded="isSectionExpanded(section.key)"
          @click.stop="toggleSection(section.key)"
        >
          <span class="flex min-w-0 flex-1 items-center gap-2">
            <component :is="isSectionExpanded(section.key) ? ChevronDown : ChevronRight" class="h-4 w-4 shrink-0 text-slate-400" />
            <span class="truncate text-xs font-bold text-slate-700">{{ section.label }}</span>
            <span class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-500">
              {{ section.selectedGroupCount }}/{{ section.groups.length }} 项
            </span>
          </span>
          <span class="flex min-w-0 max-w-[55%] shrink-0 justify-end gap-1 overflow-hidden">
            <code
              v-for="className in section.selectedClasses"
              :key="className"
              class="min-w-0 truncate rounded bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-500"
            >
              {{ className }}
            </code>
            <span v-if="!section.selectedClasses.length" class="shrink-0 rounded bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-400">
              不设置
            </span>
          </span>
        </button>
        <div v-show="isSectionExpanded(section.key)" class="space-y-3 border-t border-slate-100 p-3">
          <div
            v-for="group in section.groups"
            :key="group.key"
            class="grid gap-1.5"
          >
            <div class="flex items-center justify-between gap-2">
              <label class="text-xs font-semibold text-slate-700" :for="tailwindSelectId(group.key)">
                {{ group.label }}
              </label>
              <code class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
                {{ group.selectedClass || '不设置' }}
              </code>
            </div>
            <select
              :id="tailwindSelectId(group.key)"
              class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-indigo-400"
              :value="group.selectedClass"
              @change="emit('change', { group: group.key, className: ($event.target as HTMLSelectElement).value })"
            >
              <option value="">不设置</option>
              <option
                v-for="option in group.options"
                :key="option.class_name"
                :value="option.class_name"
                :title="option.class_name"
              >
                {{ option.label }} · {{ option.class_name }}
              </option>
            </select>
          </div>
        </div>
      </section>
    </template>
    <p v-else class="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
      {{ props.readonlyMessage }}
    </p>

    <div v-if="props.unknownTokens.length" class="rounded-lg border border-amber-100 bg-amber-50/60 p-3">
      <p class="mb-2 text-[11px] font-semibold text-amber-800">保留的复杂 / 未识别类（只读）</p>
      <div class="flex flex-wrap gap-1.5">
        <span
          v-for="token in props.unknownTokens"
          :key="token"
          class="rounded-md border border-amber-200 bg-white px-2 py-1 font-mono text-[10px] text-amber-800"
        >
          {{ token }}
        </span>
      </div>
    </div>
    <p v-if="props.pending" class="text-[11px] font-semibold text-indigo-600">
      此项有待保存修改，画布暂未更新。
    </p>
  </article>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, ChevronRight } from '@lucide/vue'

interface TailwindOptionView {
  class_name: string
  label: string
}

interface TailwindGroupView {
  key: string
  label: string
  selectedClass: string
  options: TailwindOptionView[]
}

interface TailwindSectionView {
  key: string
  label: string
  groups: TailwindGroupView[]
  selectedGroupCount: number
  selectedClasses: string[]
}

const props = defineProps<{
  bindingId: string
  editable: boolean
  groups: TailwindGroupView[]
  pending: boolean
  readonlyMessage: string
  templateLiteralWarning: boolean
  unknownTokens: string[]
}>()

const emit = defineEmits<{
  change: [payload: { group: string; className: string }]
  select: []
}>()

const expandedSectionKeys = ref<Set<string>>(new Set())
const sectionDefinitions = [
  {
    key: 'layout',
    label: '布局',
    groups: ['display', 'position', 'flex-direction', 'flex-wrap', 'items', 'justify', 'grid-columns'],
  },
  {
    key: 'spacing',
    label: '间距',
    groups: ['gap', 'gap-x', 'gap-y', 'padding', 'padding-x', 'padding-y', 'margin', 'margin-x', 'margin-y'],
  },
  {
    key: 'sizing',
    label: '尺寸',
    groups: ['width', 'height', 'size'],
  },
  {
    key: 'typography',
    label: '字体',
    groups: ['text-size', 'text-alignment', 'text-align', 'font-weight', 'line-height', 'text-color'],
  },
  {
    key: 'appearance',
    label: '外观',
    groups: ['background-color', 'border-width', 'border-style', 'border-color', 'radius', 'shadow', 'opacity'],
  },
]

const groupedSections = computed<TailwindSectionView[]>(() => {
  const remainingGroups = [...props.groups]
  const sections = sectionDefinitions
    .map((definition) => {
      const groups = takeGroupsByKeys(remainingGroups, definition.groups)
      return createSection(definition.key, definition.label, groups)
    })
    .filter(section => section.groups.length > 0)
  if (remainingGroups.length) {
    sections.push(createSection('other', '其他', remainingGroups))
  }
  return sections
})

watch(
  () => groupedSections.value.map(section => `${section.key}:${section.selectedClasses.join(',')}`).join('|'),
  () => {
    const selectedSectionKeys = groupedSections.value
      .filter(section => section.selectedClasses.length > 0)
      .map(section => section.key)
    expandedSectionKeys.value = new Set(selectedSectionKeys.length > 0
      ? selectedSectionKeys
      : groupedSections.value.slice(0, 1).map(section => section.key))
  },
  { immediate: true },
)

/** 从待分组列表中按 key 取出目标组，同时保留目录顺序。 */
function takeGroupsByKeys(groups: TailwindGroupView[], keys: string[]): TailwindGroupView[] {
  const keySet = new Set(keys)
  const matched = groups.filter(group => keySet.has(group.key))
  for (const group of matched) {
    const index = groups.findIndex(candidate => candidate.key === group.key)
    if (index >= 0) groups.splice(index, 1)
  }
  return matched
}

/** 创建大分区视图，并汇总该分区当前生效的 Tailwind class。 */
function createSection(key: string, label: string, groups: TailwindGroupView[]): TailwindSectionView {
  return {
    key,
    label,
    groups,
    selectedGroupCount: groups.filter(group => group.selectedClass).length,
    selectedClasses: groups.map(group => group.selectedClass).filter(Boolean),
  }
}

/** 展开或折叠一个 Tailwind 样式大分区。 */
function toggleSection(sectionKey: string): void {
  const next = new Set(expandedSectionKeys.value)
  if (next.has(sectionKey)) {
    next.delete(sectionKey)
  } else {
    next.add(sectionKey)
  }
  expandedSectionKeys.value = next
}

/** 判断 Tailwind 样式大分区是否展开。 */
function isSectionExpanded(sectionKey: string): boolean {
  return expandedSectionKeys.value.has(sectionKey)
}

/** 生成 Tailwind 组选择器的稳定 DOM id。 */
function tailwindSelectId(groupKey: string): string {
  return `tailwind-${safeDomId(props.bindingId)}-${safeDomId(groupKey)}`
}

/** DOM id 只保留安全字符，避免绑定 id 中的分隔符影响 label 关联。 */
function safeDomId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '-')
}
</script>
