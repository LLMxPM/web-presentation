<!-- 文件功能：头部导航条的工作空间下拉选择组件，支持切换启用空间、归档/恢复工作空间以及新建空间。 -->
<template>
  <div class="workspace-switcher relative shrink-0">
    <UiPopover :open="dropdownVisible" side="bottom" align="start" :side-offset="8" content-class="!p-0 w-64 rounded-2xl shadow-xl" @update:open="dropdownVisible = $event">
      <template #trigger>
        <!-- Trigger -->
        <div
          class="flex items-center gap-3 px-4 py-2 rounded-xl bg-surface-muted hover:bg-border transition-all cursor-pointer select-none border border-border/50 shadow-sm"
          :class="triggerClass"
        >
          <div class="flex items-center gap-2">
            <LayoutGrid class="w-4 h-4 text-accent" />
            <div class="flex items-baseline gap-1.5">
              <span class="text-sm font-bold text-text line-clamp-1 max-w-[140px]">{{ currentWorkspace?.name || '请选择空间' }}</span>
            </div>
          </div>
          <ChevronDown class="w-4 h-4 text-text-disabled transition-transform duration-200"
            :class="{ 'rotate-180': dropdownVisible }" />
        </div>
      </template>

      <!-- Dropdown Content -->
      <div class="py-2">
        <div class="px-4 py-2 border-b border-canvas mb-1 flex items-center justify-between gap-3">
          <span class="text-[11px] font-bold text-text-disabled uppercase tracking-widest">所属工作空间</span>
          <UiButton variant="ghost" size="xs" class="text-text-disabled hover:text-text-secondary"
            @click.stop="openArchivedDialog">
            查看已归档
          </UiButton>
        </div>

        <div class="max-h-60 overflow-y-auto px-1.5 py-1">
          <div v-for="ws in activeWorkspaces" :key="ws.id" @click="handleSwitch(ws.id)"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-semibold transition-all mb-0.5 group cursor-pointer"
            :class="ws.id === currentWorkspaceId ? 'bg-surface-selected text-accent-hover' : 'text-text-emphasis hover:bg-surface-hover'">
            <div class="flex items-center gap-3 min-w-0">
              <div class="w-2 h-2 rounded-full shrink-0"
                :class="ws.id === currentWorkspaceId ? 'bg-accent-emphasis' : 'bg-border'"></div>
              <span class="line-clamp-1">{{ ws.name }}</span>
            </div>
            <div class="flex items-center gap-1.5 shrink-0">
              <UiIconButton
                size="xs"
                label="归档工作空间"
                class="bg-surface/0 opacity-0 shadow-none hover:border-border-muted hover:bg-surface hover:text-warning hover:shadow-sm group-hover:opacity-100"
                :disabled="archivingWorkspaceId === ws.id" title="归档工作空间" @click.stop="handleArchiveWorkspace(ws)">
                <Archive class="w-3.5 h-3.5" />
              </UiIconButton>
              <Check v-if="ws.id === currentWorkspaceId" class="w-4 h-4 text-accent-emphasis" />
            </div>
          </div>

          <div v-if="activeWorkspaces.length === 0" class="px-4 py-6 text-center text-text-disabled text-xs italic">
            暂无可用空间
          </div>
        </div>

        <div class="mt-2 pt-1.5 border-t border-border-muted px-1.5">
          <UiButton variant="ghost" size="sm" class="w-full justify-start text-accent hover:bg-surface-selected" @click="openCreate">
            <Plus class="w-4 h-4" />
            新建工作空间
          </UiButton>
        </div>
      </div>
    </UiPopover>

    <!-- Workspace Dialog (Refactored) -->
    <UiDialog :open="dialogVisible" title="创建工作空间" size="compact" @update:open="dialogVisible = $event">
      <div class="space-y-5">
        <UiFormField label="空间名称" required :error="errors.name"><template #default="field"><UiInput v-model="form.name" placeholder="给工作空间起个响亮的名字" required :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" /></template></UiFormField>
        <UiFormField label="详细描述"><template #default="field"><UiInput v-model="form.description" type="textarea" placeholder="（可选）描述此工作空间的用途或归口部门" :rows="4" :input-id="field.inputId" :described-by="field.describedBy" /></template></UiFormField>
      </div>
      <template #footer>
        <UiButton variant="ghost" @click="dialogVisible = false">取消</UiButton>
        <UiButton variant="primary" :loading="saving" @click="handleSubmit">保存空间</UiButton>
      </template>
    </UiDialog>
    <ArchivedWorkspacesDialog v-model="archivedDialogVisible" :current-workspace-id="currentWorkspaceId"
      @restored="handleWorkspaceListUpdated" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Archive, Check, ChevronDown, LayoutGrid, Plus } from '@lucide/vue'

import { createWorkspace, listWorkspaces, touchWorkspace, updateWorkspace } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import type { WorkspaceItem } from '@/types/api'
import { createConfirm, Message } from '@/utils/message'
import { reportClientError } from '@/utils/client-logger'
import ArchivedWorkspacesDialog from '@/components/nav/ArchivedWorkspacesDialog.vue'
import { UiButton, UiDialog, UiFormField, UiIconButton, UiInput, UiPopover } from '@/components/ui'
import { buildWorkspaceHomePath } from '@/utils/workspace-routes'

const route = useRoute()
const router = useRouter()

const props = withDefaults(defineProps<{
  prominent?: boolean
}>(), {
  prominent: false,
})

const workspaces = ref<WorkspaceItem[]>([])
const dropdownVisible = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const archivedDialogVisible = ref(false)
const archivingWorkspaceId = ref<number | null>(null)

const form = reactive({
  name: '',
  description: '',
})

const errors = reactive({
  name: '',
})

const currentWorkspaceId = computed(() => {
  const idStr = route.params.workspaceId as string
  return idStr ? parseInt(idStr, 10) : null
})

const activeWorkspaces = computed(() => workspaces.value.filter(item => item.status === 'active'))

const currentWorkspace = computed(() => {
  if (!currentWorkspaceId.value) return null
  return workspaces.value.find(w => w.id === currentWorkspaceId.value) || null
})

const triggerClass = computed(() => ({
  'bg-border': dropdownVisible.value && !props.prominent,
  'border-accent-border bg-surface ring-2 ring-accent-muted hover:bg-surface-selected': props.prominent,
  'border-accent-border bg-surface-selected ring-2 ring-accent-ring': props.prominent && dropdownVisible.value,
}))

/**
 * 加载所有工作空间列表
 */
async function fetchWorkspaces() {
  try {
    const res = await listWorkspaces({ page: 1, page_size: 100, sort_by: 'last_opened_at', sort_order: 'desc' })
    workspaces.value = res.items
  } catch (error) {
    reportClientError(error, { message: 'Failed to load workspaces', component: 'WorkspaceSwitcher' })
  }
}

onMounted(() => {
  fetchWorkspaces()
  window.addEventListener('workspace-list-updated', fetchWorkspaces)
})

onUnmounted(() => {
  window.removeEventListener('workspace-list-updated', fetchWorkspaces)
})

/**
 * 关闭下拉菜单
 */
function closeDropdown() {
  dropdownVisible.value = false
}

/**
 * 切换当前选中的工作空间
 * @param id 工作空间 ID
 */
function handleSwitch(id: number) {
  closeDropdown()
  if (id !== currentWorkspaceId.value) {
    touchWorkspace(id).then(() => fetchWorkspaces())
    router.push({ path: buildWorkspaceHomePath(id) })
  }
}

/**
 * 打开创建工作空间的对话框
 */
function openCreate() {
  closeDropdown()
  form.name = ''
  form.description = ''
  errors.name = ''
  dialogVisible.value = true
}

/**
 * 打开归档工作空间列表弹窗。
 */
function openArchivedDialog() {
  closeDropdown()
  archivedDialogVisible.value = true
}

/**
 * 提交保存新建工作空间表单。
 */
async function handleSubmit() {
  if (!form.name) {
    errors.name = '请输入空间名称'
    return
  }
  errors.name = ''

  saving.value = true
  try {
    const workspace = await createWorkspace({ name: form.name, description: form.description || null, status: 'active' })
    Message.success('工作空间创建成功。')
    dialogVisible.value = false
    await fetchWorkspaces()
    void router.push({ path: buildWorkspaceHomePath(workspace.id) })
  } catch (error) {
    Message.error(getErrorMessage(error, '保存失败。'))
  } finally {
    saving.value = false
  }
}

/**
 * 归档指定工作空间，并在成功后刷新当前可见列表。
 * @param workspace 目标工作空间
 */
async function handleArchiveWorkspace(workspace: WorkspaceItem) {
  const confirmed = await createConfirm(
    `归档后工作空间将从当前切换列表中隐藏，可在“查看已归档”中恢复，确定归档「${workspace.name}」吗？`,
    '归档工作空间',
  )
  if (!confirmed) {
    return
  }

  archivingWorkspaceId.value = workspace.id
  try {
    await updateWorkspace(workspace.id, { status: 'archived' })
    Message.success('工作空间已归档。')
    await fetchWorkspaces()
  } catch (error) {
    Message.error(getErrorMessage(error, '归档工作空间失败。'))
  } finally {
    archivingWorkspaceId.value = null
  }
}

/**
 * 归档工作空间列表发生变化后，刷新下拉中的工作空间状态。
 */
async function handleWorkspaceListUpdated() {
  await fetchWorkspaces()
}

</script>