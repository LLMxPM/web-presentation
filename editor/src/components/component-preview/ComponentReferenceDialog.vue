<!-- 文件功能：展示工作空间组件的直接引用页面与引用组件，并提供选中项批量升级入口。 -->
<template>
  <UiDialog
    :open="modelValue"
    title="引用关系"
    size="canvas"
    body-preset="split"
    @update:open="emit('update:modelValue', $event)"
  >
    <div class="flex h-full min-h-0 flex-col">
      <section class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-canvas px-4 py-3">
        <div class="min-w-0">
          <p class="truncate text-sm font-bold text-text">{{ component?.name || '未选择组件' }}</p>
          <p class="mt-1 text-xs text-text-muted">
            {{ component ? `${component.code} · 当前发布 v${component.current_version_no}` : '请选择一个已发布组件。' }}
          </p>
        </div>
        <UiButton variant="ghost" size="sm" :disabled="loading || !component" @click="emit('refresh')">
          <RefreshCw class="h-3.5 w-3.5" :class="{ 'animate-spin': loading }" />
          刷新
        </UiButton>
      </section>

      <div v-if="loading" class="mt-4 flex min-h-0 flex-1 items-center justify-center rounded-xl border border-dashed border-border bg-surface px-4 py-10 text-center text-sm font-semibold text-text-disabled">
        正在读取引用关系...
      </div>

      <div v-else-if="!references" class="mt-4 flex min-h-0 flex-1 items-center justify-center rounded-xl border border-dashed border-border bg-surface px-4 py-10 text-center text-sm font-semibold text-text-disabled">
        暂无引用数据。
      </div>

      <div v-else class="mt-4 grid min-h-0 flex-1 gap-4 lg:grid-cols-2">
        <section class="flex min-h-0 min-w-0 flex-col rounded-xl border border-border bg-surface">
          <div class="flex items-center justify-between gap-3 border-b border-border-muted px-4 py-3">
            <div>
              <h3 class="text-sm font-bold text-text">页面引用</h3>
              <p class="mt-1 text-xs text-text-disabled">{{ references.page_references.length }} 个当前页面版本</p>
            </div>
            <span class="rounded-full bg-surface-muted px-2 py-1 text-[11px] font-bold text-text-muted">
              已选 {{ selectedPageIds.length }}
            </span>
          </div>

          <div v-if="references.page_references.length === 0" class="flex min-h-0 flex-1 items-center px-4 py-8 text-sm text-text-disabled">
            当前没有页面直接引用该组件。
          </div>
          <div v-else class="min-h-0 flex-1 divide-y divide-border-muted overflow-y-auto">
            <label
              v-for="item in references.page_references"
              :key="item.page_id"
              class="flex cursor-pointer gap-3 px-4 py-3 transition-colors hover:bg-surface-hover"
              :class="{ 'cursor-not-allowed opacity-70': !item.can_upgrade }"
            >
              <UiCheckbox
                class="mt-1"
                :model-value="selectedPageIds.includes(item.page_id)"
                :disabled="!item.can_upgrade"
                @update:model-value="togglePageSelection(item.page_id, $event === true)"
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-center justify-between gap-2">
                  <p class="truncate text-sm font-semibold text-text">{{ item.page_title }}</p>
                  <ReferenceStatusTag :current="item.is_current_version" />
                </div>
                <p class="mt-1 truncate font-mono text-[11px] text-text-disabled">{{ item.page_code }}</p>
                <p class="mt-1 text-xs text-text-muted">
                  {{ item.project_name || '未归属项目' }} · 页面 v{{ item.current_version_no }} · 引用 v{{ item.referenced_component_version_no }}
                </p>
              </div>
            </label>
          </div>
        </section>

        <section class="flex min-h-0 min-w-0 flex-col rounded-xl border border-border bg-surface">
          <div class="flex items-center justify-between gap-3 border-b border-border-muted px-4 py-3">
            <div>
              <h3 class="text-sm font-bold text-text">组件引用</h3>
              <p class="mt-1 text-xs text-text-disabled">{{ references.component_references.length }} 个当前组件发布版本</p>
            </div>
            <span class="rounded-full bg-surface-muted px-2 py-1 text-[11px] font-bold text-text-muted">
              已选 {{ selectedComponentIds.length }}
            </span>
          </div>

          <div v-if="references.component_references.length === 0" class="flex min-h-0 flex-1 items-center px-4 py-8 text-sm text-text-disabled">
            当前没有组件直接引用该组件。
          </div>
          <div v-else class="min-h-0 flex-1 divide-y divide-border-muted overflow-y-auto">
            <label
              v-for="item in references.component_references"
              :key="item.component_id"
              class="flex cursor-pointer gap-3 px-4 py-3 transition-colors hover:bg-surface-hover"
              :class="{ 'cursor-not-allowed opacity-70': !item.can_upgrade }"
            >
              <UiCheckbox
                class="mt-1"
                :model-value="selectedComponentIds.includes(item.component_id)"
                :disabled="!item.can_upgrade"
                @update:model-value="toggleComponentSelection(item.component_id, $event === true)"
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-center justify-between gap-2">
                  <p class="truncate text-sm font-semibold text-text">{{ item.component_name }}</p>
                  <ReferenceStatusTag :current="item.is_current_version || item.draft_is_current_version" />
                </div>
                <p class="mt-1 truncate font-mono text-[11px] text-text-disabled">{{ item.component_code }}</p>
                <p class="mt-1 text-xs text-text-muted">
                  发布 v{{ item.current_version_no }} 引用 v{{ item.referenced_component_version_no }}
                  <span v-if="item.draft_is_current_version" class="font-semibold text-warning">
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
      <div class="mr-auto text-xs font-semibold text-text-disabled">
        已选 {{ selectedCount }} 项
      </div>
      <UiButton variant="ghost" :disabled="!references || loading || upgrading" @click="selectUpgradeable">
        全选待升级
      </UiButton>
      <UiButton variant="ghost" :disabled="selectedCount === 0 || upgrading" @click="clearSelection">
        清空选择
      </UiButton>
      <UiButton
        variant="primary"
        :disabled="selectedCount === 0 || loading"
        :loading="upgrading"
        @click="emitUpgrade"
      >
        <ArrowUpCircle class="h-3.5 w-3.5" />
        更新选中引用
      </UiButton>
    </template>
  </UiDialog>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch } from 'vue'
import { ArrowUpCircle, RefreshCw } from '@lucide/vue'

import UiButton from '@/components/ui/button/UiButton.vue'
import { UiCheckbox, UiDialog } from '@/components/ui'
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

/** 更新页面引用的单项选择，避免业务层直接保留裸 checkbox。 */
function togglePageSelection(pageId: number, checked: boolean): void {
  selectedPageIds.value = toggleId(selectedPageIds.value, pageId, checked)
}

/** 更新组件引用的单项选择，保持两类引用的状态相互独立。 */
function toggleComponentSelection(componentId: number, checked: boolean): void {
  selectedComponentIds.value = toggleId(selectedComponentIds.value, componentId, checked)
}

/** 将单个 ID 加入或移出当前选择，始终返回新的数组供响应式状态更新。 */
function toggleId(currentIds: number[], id: number, checked: boolean): number[] {
  return checked
    ? currentIds.includes(id) ? currentIds : [...currentIds, id]
    : currentIds.filter(currentId => currentId !== id)
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
          ? 'shrink-0 rounded-full bg-success-muted px-2 py-0.5 text-[11px] font-bold text-success'
          : 'shrink-0 rounded-full bg-warning-muted px-2 py-0.5 text-[11px] font-bold text-warning',
      },
      tagProps.current ? '已是最新' : '可升级',
    )
  },
})
</script>

