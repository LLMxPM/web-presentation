<!-- 文件功能：展示当前工作空间下的已归档组件列表，支持搜索并将组件恢复为启用状态。 -->
<template>
  <UiDialog :open="modelValue" title="已归档组件" size="standard" @update:open="handleDialogVisibleChange">
    <div class="flex flex-col gap-4">
      <SimpleSearchBar v-model="keyword" placeholder="按组件名称、引用名、编码或类型搜索" />

      <div class="overflow-hidden rounded-2xl border border-border bg-canvas/50">
        <div class="flex items-center justify-between border-b border-border px-4 py-3 text-xs font-semibold text-text-muted">
          <span>共 {{ archivedComponents.length }} 个归档组件</span>
          <span>按最近更新时间从近到远排序</span>
        </div>

        <div v-if="loading" class="flex items-center justify-center py-12 text-sm text-text-muted">
          正在加载归档组件...
        </div>

        <div v-else-if="archivedComponents.length === 0"
          class="flex flex-col items-center justify-center gap-2 py-12 text-text-muted">
          <p class="text-sm font-semibold">{{ keyword.trim() ? '没有匹配的归档组件。' : '当前没有已归档组件。' }}</p>
          <p class="text-xs text-text-disabled">恢复后的组件会重新出现在组件库列表。</p>
        </div>

        <div v-else class="divide-y divide-border">
          <div v-for="component in archivedComponents" :key="component.id"
            class="flex items-center justify-between gap-4 bg-surface px-4 py-4">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-3">
                <h4 class="truncate text-sm font-semibold text-text-strong">{{ component.name }}</h4>
                <span class="font-mono text-[10px] font-bold uppercase tracking-widest text-text-disabled">{{
                  component.code }}</span>
                <span class="rounded bg-surface-muted px-1.5 py-0.5 text-[10px] font-black uppercase tracking-tight text-text-muted">
                  {{ component.component_type }}
                </span>
              </div>
              <div class="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-text-muted">
                <span>状态：已归档</span>
                <span class="font-mono font-bold text-accent-emphasis">{{ component.import_name }}</span>
                <span>更新于 {{ formatDateTime(component.updated_at) }}</span>
              </div>
            </div>

            <UiButton variant="secondary" :loading="restoringComponentId === component.id"
              @click="handleRestoreComponent(component.id)">
              恢复
            </UiButton>
          </div>
        </div>
      </div>
    </div>
  </UiDialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import { listComponents, restoreComponent } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import type { WorkspaceComponentItem } from '@/types/api'
import { formatDateTime } from '@/utils/format'
import { Message } from '@/utils/message'
import { UiButton, UiDialog } from '@/components/ui'

const props = withDefaults(defineProps<{
  modelValue: boolean
  workspaceId: number | null
}>(), {
  workspaceId: null,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  restored: []
}>()

const keyword = ref('')
const loading = ref(false)
const restoringComponentId = ref<number | null>(null)
const archivedComponents = ref<WorkspaceComponentItem[]>([])

/**
 * 加载归档组件列表，并按关键字与更新时间排序。
 */
async function fetchArchivedComponents(): Promise<void> {
  if (!props.workspaceId) {
    archivedComponents.value = []
    return
  }
  loading.value = true
  try {
    const response = await listComponents({
      page: 1,
      page_size: 100,
      workspace_id: props.workspaceId,
      status: 'archived',
      keyword: keyword.value.trim(),
      sort_by: 'updated_at',
      sort_order: 'desc',
    })
    archivedComponents.value = response.items
  } catch (error) {
    archivedComponents.value = []
    Message.error(getErrorMessage(error, '加载归档组件失败。'))
  } finally {
    loading.value = false
  }
}

/**
 * 同步父组件的弹窗显隐状态。
 * @param value 弹窗显隐值
 */
function handleDialogVisibleChange(value: boolean): void {
  emit('update:modelValue', value)
}

/**
 * 将指定归档组件恢复为启用状态，并通知父组件刷新组件库列表。
 * @param componentId 组件主键
 */
async function handleRestoreComponent(componentId: number): Promise<void> {
  restoringComponentId.value = componentId
  try {
    await restoreComponent(componentId)
    Message.success('组件已恢复。')
    emit('restored')
    await fetchArchivedComponents()
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复组件失败。'))
  } finally {
    restoringComponentId.value = null
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      void fetchArchivedComponents()
      return
    }
    keyword.value = ''
    archivedComponents.value = []
    restoringComponentId.value = null
  },
  { immediate: true },
)

watch(
  () => keyword.value.trim(),
  () => {
    if (props.modelValue) {
      void fetchArchivedComponents()
    }
  },
)
</script>
