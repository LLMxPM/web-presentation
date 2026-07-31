<!-- 文件功能：展示已归档工作空间列表，支持按名称搜索并将工作空间恢复为启用状态。 -->
<template>
  <UiDialog :open="modelValue" title="已归档工作空间" size="standard" @update:open="handleDialogVisibleChange">
    <div class="flex flex-col gap-4">
      <SimpleSearchBar v-model="keyword" placeholder="按工作空间名称或编码搜索" />

      <div class="rounded-2xl border border-border bg-canvas/50 overflow-hidden">
        <div class="flex items-center justify-between px-4 py-3 border-b border-border text-xs font-semibold text-text-muted">
          <span>共 {{ archivedWorkspaces.length }} 个归档工作空间</span>
          <span>按最近更新时间从近到远排序</span>
        </div>

        <div v-if="loading" class="flex items-center justify-center py-12 text-sm text-text-muted">
          正在加载归档工作空间...
        </div>

        <div v-else-if="archivedWorkspaces.length === 0" class="flex flex-col items-center justify-center py-12 gap-2 text-text-muted">
          <p class="text-sm font-semibold">{{ keyword.trim() ? '没有匹配的归档工作空间。' : '当前没有已归档工作空间。' }}</p>
          <p class="text-xs text-text-disabled">恢复后的工作空间会重新出现在顶部切换列表中。</p>
        </div>

        <div v-else class="divide-y divide-border">
          <div
            v-for="workspace in archivedWorkspaces"
            :key="workspace.id"
            class="flex items-center justify-between gap-4 px-4 py-4 bg-surface"
          >
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-3">
                <h4 class="text-sm font-semibold text-text-strong truncate">{{ workspace.name }}</h4>
                <span class="text-[10px] font-bold text-text-disabled uppercase tracking-widest font-mono">{{ workspace.code }}</span>
                <span
                  v-if="workspace.id === currentWorkspaceId"
                  class="inline-flex items-center rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-semibold text-text-muted"
                >
                  当前空间
                </span>
              </div>
              <p class="mt-1 text-xs text-text-muted line-clamp-2">
                {{ workspace.description || '此工作空间尚未添加具体说明。' }}
              </p>
              <div class="mt-2 flex items-center gap-4 text-xs text-text-disabled">
                <span>状态：已归档</span>
                <span>更新于 {{ formatDateTime(workspace.updated_at) }}</span>
              </div>
            </div>

            <UiButton
              variant="secondary"
              :loading="restoringWorkspaceId === workspace.id"
              @click="handleRestoreWorkspace(workspace.id)"
            >
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

import { listWorkspaces, updateWorkspace } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import type { WorkspaceItem } from '@/types/api'
import { formatDateTime } from '@/utils/format'
import { Message } from '@/utils/message'
import { UiButton, UiDialog } from '@/components/ui'

const props = withDefaults(defineProps<{
  modelValue: boolean
  currentWorkspaceId?: number | null
}>(), {
  currentWorkspaceId: null,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  restored: []
}>()

const keyword = ref('')
const loading = ref(false)
const restoringWorkspaceId = ref<number | null>(null)
const archivedWorkspaces = ref<WorkspaceItem[]>([])

/**
 * 加载归档工作空间列表，并按关键字与更新时间排序。
 */
async function fetchArchivedWorkspaces(): Promise<void> {
  loading.value = true
  try {
    const response = await listWorkspaces({
      page: 1,
      page_size: 100,
      status: 'archived',
      keyword: keyword.value.trim(),
      sort_by: 'updated_at',
      sort_order: 'desc',
    })
    archivedWorkspaces.value = response.items
  } catch (error) {
    archivedWorkspaces.value = []
    Message.error(getErrorMessage(error, '加载归档工作空间失败。'))
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
 * 将指定归档工作空间恢复为启用状态，并通知父组件刷新工作空间列表。
 * @param workspaceId 工作空间主键
 */
async function handleRestoreWorkspace(workspaceId: number): Promise<void> {
  restoringWorkspaceId.value = workspaceId
  try {
    await updateWorkspace(workspaceId, { status: 'active' })
    Message.success('工作空间已恢复。')
    emit('restored')
    await fetchArchivedWorkspaces()
  } catch (error) {
    Message.error(getErrorMessage(error, '恢复工作空间失败。'))
  } finally {
    restoringWorkspaceId.value = null
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      void fetchArchivedWorkspaces()
      return
    }
    keyword.value = ''
    archivedWorkspaces.value = []
    restoringWorkspaceId.value = null
  },
)

watch(
  () => keyword.value.trim(),
  () => {
    if (props.modelValue) {
      void fetchArchivedWorkspaces()
    }
  },
)
</script>

