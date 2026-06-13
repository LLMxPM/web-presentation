<!-- 文件功能：展示工作空间组件的直接引用页面与引用组件，并提供选中项批量升级入口。 -->
<template>
  <BaseDialog
    :model-value="modelValue"
    title="引用关系"
    size="canvas"
    body-preset="split"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="flex h-full min-h-0 flex-col">
      <section class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
        <div class="min-w-0">
          <p class="truncate text-sm font-bold text-slate-800">{{ component?.name || '未选择组件' }}</p>
          <p class="mt-1 text-xs text-slate-500">
            {{ component ? `${component.code} · 当前发布 v${component.current_version_no}` : '请选择一个已发布组件。' }}
          </p>
        </div>
        <BaseButton variant="ghost" size="sm" :disabled="loading || !component" @click="emit('refresh')">
          <RefreshCw class="h-3.5 w-3.5" :class="{ 'animate-spin': loading }" />
          刷新
        </BaseButton>
      </section>

      <div v-if="loading" class="mt-4 flex min-h-0 flex-1 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm font-semibold text-slate-400">
        正在读取引用关系...
      </div>

      <div v-else-if="!references" class="mt-4 flex min-h-0 flex-1 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white px-4 py-10 text-center text-sm font-semibold text-slate-400">
        暂无引用数据。
      </div>

      <div v-else class="mt-4 grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <section class="flex min-h-0 min-w-0 flex-col rounded-xl border border-slate-200 bg-white">
          <div class="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h3 class="text-sm font-bold text-slate-800">页面引用</h3>
              <p class="mt-1 text-xs text-slate-400">{{ references.page_references.length }} 个当前页面版本</p>
            </div>
            <span class="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-500">
              已选 {{ selectedPageIds.length }}
            </span>
          </div>

          <div v-if="references.page_references.length === 0" class="flex min-h-0 flex-1 items-center px-4 py-8 text-sm text-slate-400">
            当前没有页面直接引用该组件。
          </div>
          <div v-else class="min-h-0 flex-1 divide-y divide-slate-100 overflow-y-auto">
            <label
              v-for="item in references.page_references"
              :key="item.page_id"
              class="flex cursor-pointer gap-3 px-4 py-3 transition-colors hover:bg-slate-50"
              :class="{ 'cursor-not-allowed opacity-70': !item.can_upgrade }"
            >
              <input
                v-model="selectedPageIds"
                type="checkbox"
                class="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                :value="item.page_id"
                :disabled="!item.can_upgrade"
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-center justify-between gap-2">
                  <p class="truncate text-sm font-semibold text-slate-800">{{ item.page_title }}</p>
                  <ReferenceStatusTag :current="item.is_current_version" />
                </div>
                <p class="mt-1 truncate font-mono text-[11px] text-slate-400">{{ item.page_code }}</p>
                <p class="mt-1 text-xs text-slate-500">
                  {{ item.project_name || '未归属项目' }} · 页面 v{{ item.current_version_no }} · 引用 v{{ item.referenced_component_version_no }}
                </p>
              </div>
            </label>
          </div>
        </section>

        <section class="flex min-h-0 min-w-0 flex-col rounded-xl border border-slate-200 bg-white">
          <div class="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
            <div>
              <h3 class="text-sm font-bold text-slate-800">组件引用</h3>
              <p class="mt-1 text-xs text-slate-400">{{ references.component_references.length }} 个当前组件发布版本</p>
            </div>
            <span class="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-500">
              已选 {{ selectedComponentIds.length }}
            </span>
          </div>

          <div v-if="references.component_references.length === 0" class="flex min-h-0 flex-1 items-center px-4 py-8 text-sm text-slate-400">
            当前没有组件直接引用该组件。
          </div>
          <div v-else class="min-h-0 flex-1 divide-y divide-slate-100 overflow-y-auto">
            <label
              v-for="item in references.component_references"
              :key="item.component_id"
              class="flex cursor-pointer gap-3 px-4 py-3 transition-colors hover:bg-slate-50"
              :class="{ 'cursor-not-allowed opacity-70': !item.can_upgrade }"
            >
              <input
                v-model="selectedComponentIds"
                type="checkbox"
                class="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                :value="item.component_id"
                :disabled="!item.can_upgrade"
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-center justify-between gap-2">
                  <p class="truncate text-sm font-semibold text-slate-800">{{ item.component_name }}</p>
                  <ReferenceStatusTag :current="item.is_current_version || item.draft_is_current_version" />
                </div>
                <p class="mt-1 truncate font-mono text-[11px] text-slate-400">{{ item.component_code }}</p>
                <p class="mt-1 text-xs text-slate-500">
                  发布 v{{ item.current_version_no }} 引用 v{{ item.referenced_component_version_no }}
                  <span v-if="item.draft_is_current_version" class="font-semibold text-amber-600">
                    · 草稿已升级，待发布
                  </span>
                </p>
              </div>
            </label>
          </div>
        </section>
      </div>
    </div>

    <template #footer>
      <div class="mr-auto text-xs font-semibold text-slate-400">
        已选 {{ selectedCount }} 项
      </div>
      <BaseButton variant="ghost" :disabled="!references || loading || upgrading" @click="selectUpgradeable">
        全选待升级
      </BaseButton>
      <BaseButton variant="ghost" :disabled="selectedCount === 0 || upgrading" @click="clearSelection">
        清空选择
      </BaseButton>
      <BaseButton
        variant="primary"
        :disabled="selectedCount === 0 || loading"
        :loading="upgrading"
        @click="emitUpgrade"
      >
        <ArrowUpCircle class="h-3.5 w-3.5" />
        更新选中引用
      </BaseButton>
    </template>
  </BaseDialog>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch } from 'vue'
import { ArrowUpCircle, RefreshCw } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import type {
  WorkspaceComponentItem,
  WorkspaceComponentReferenceUpgradePayload,
  WorkspaceComponentReferences,
} from '@/types/api'

const props = defineProps<{
  modelValue: boolean
  component: WorkspaceComponentItem | null
  references: WorkspaceComponentReferences | null
  loading: boolean
  upgrading: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  refresh: []
  upgrade: [payload: WorkspaceComponentReferenceUpgradePayload]
}>()

const selectedPageIds = ref<number[]>([])
const selectedComponentIds = ref<number[]>([])
const selectedCount = computed(() => selectedPageIds.value.length + selectedComponentIds.value.length)

watch(
  () => [props.modelValue, props.references?.component_id, props.references?.current_version_no],
  () => {
    if (props.modelValue && props.references) {
      selectUpgradeable()
    }
  },
  { immediate: true },
)

/**
 * 默认勾选全部仍引用旧版本且可以自动升级的页面和组件草稿。
 */
function selectUpgradeable(): void {
  selectedPageIds.value = props.references?.page_references
    .filter(item => item.can_upgrade)
    .map(item => item.page_id) ?? []
  selectedComponentIds.value = props.references?.component_references
    .filter(item => item.can_upgrade)
    .map(item => item.component_id) ?? []
}

/**
 * 清空当前批量升级选择。
 */
function clearSelection(): void {
  selectedPageIds.value = []
  selectedComponentIds.value = []
}

/**
 * 提交当前勾选项给父级执行升级。
 */
function emitUpgrade(): void {
  if (selectedCount.value === 0) {
    return
  }
  emit('upgrade', {
    page_ids: [...selectedPageIds.value],
    component_ids: [...selectedComponentIds.value],
  })
}

const ReferenceStatusTag = defineComponent({
  name: 'ReferenceStatusTag',
  props: {
    current: {
      type: Boolean,
      required: true,
    },
  },
  setup(tagProps) {
    return () => h(
      'span',
      {
        class: tagProps.current
          ? 'shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-600'
          : 'shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-bold text-amber-600',
      },
      tagProps.current ? '已是最新' : '可升级',
    )
  },
})
</script>

