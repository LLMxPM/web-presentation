<!-- 文件功能：头部导航条的工作空间下拉选择组件，支持切换启用空间、归档/恢复工作空间以及新建空间。 -->
<template>
  <div class="workspace-switcher relative shrink-0" v-click-outside="closeDropdown">
    <!-- Trigger -->
    <div @click="dropdownVisible = !dropdownVisible"
      class="flex items-center gap-3 px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 transition-all cursor-pointer select-none border border-slate-200/50 shadow-sm"
      :class="{ 'bg-slate-200': dropdownVisible }">
      <div class="flex items-center gap-2">
        <LayoutGrid class="w-4 h-4 text-indigo-600" />
        <div class="flex items-baseline gap-1.5">
          <span class="text-sm font-bold text-slate-800 line-clamp-1 max-w-[140px]">{{ currentWorkspace?.name || '请选择空间'
            }}</span>
        </div>
      </div>
      <ChevronDown class="w-4 h-4 text-slate-400 transition-transform duration-200"
        :class="{ 'rotate-180': dropdownVisible }" />
    </div>

    <!-- Dropdown Menu -->
    <Transition name="fade-scale">
      <div v-if="dropdownVisible"
        class="absolute left-1/2 -translate-x-1/2 mt-2 w-64 bg-white border border-slate-200 rounded-2xl shadow-xl z-50 py-2">
        <div class="px-4 py-2 border-b border-slate-50 mb-1 flex items-center justify-between gap-3">
          <span class="text-[11px] font-bold text-slate-400 uppercase tracking-widest">所属工作空间</span>
          <button type="button" class="text-[11px] font-medium text-slate-400 transition-colors hover:text-slate-600"
            @click.stop="openArchivedDialog">
            查看已归档
          </button>
        </div>

        <div class="max-h-60 overflow-y-auto px-1.5 py-1">
          <div v-for="ws in activeWorkspaces" :key="ws.id" @click="handleSwitch(ws.id)"
            class="w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-semibold transition-all mb-0.5 group cursor-pointer"
            :class="ws.id === currentWorkspaceId ? 'bg-indigo-50 text-indigo-700' : 'text-slate-700 hover:bg-slate-50'">
            <div class="flex items-center gap-3 min-w-0">
              <div class="w-2 h-2 rounded-full shrink-0"
                :class="ws.id === currentWorkspaceId ? 'bg-indigo-500' : 'bg-slate-200'"></div>
              <span class="line-clamp-1">{{ ws.name }}</span>
            </div>
            <div class="flex items-center gap-1.5 shrink-0">
              <button type="button"
                class="p-1.5 rounded-lg bg-white/0 hover:bg-white shadow-none hover:shadow-sm opacity-0 group-hover:opacity-100 transition-all text-slate-400 hover:text-amber-600 border border-transparent hover:border-slate-100"
                :disabled="archivingWorkspaceId === ws.id" title="归档工作空间" @click.stop="handleArchiveWorkspace(ws)">
                <Archive class="w-3.5 h-3.5" />
              </button>
              <Check v-if="ws.id === currentWorkspaceId" class="w-4 h-4 text-indigo-500" />
            </div>
          </div>

          <div v-if="activeWorkspaces.length === 0" class="px-4 py-6 text-center text-slate-400 text-xs italic">
            暂无可用空间
          </div>
        </div>

        <div class="mt-2 pt-1.5 border-t border-slate-100 px-1.5">
          <button @click="openCreate"
            class="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-sm font-semibold text-indigo-600 hover:bg-indigo-50 transition-colors">
            <Plus class="w-4 h-4" />
            新建工作空间
          </button>
        </div>
      </div>
    </Transition>

    <!-- Workspace Dialog (Refactored) -->
    <BaseDialog v-model="dialogVisible" title="创建工作空间" width="500px">
      <div class="space-y-5">
        <BaseInput v-model="form.name" label="空间名称" placeholder="给工作空间起个响亮的名字" required :error="errors.name" />

        <BaseInput v-model="form.description" type="textarea" label="详细描述" placeholder="（可选）描述此工作空间的用途或归口部门"
          :rows="4" />
      </div>
      <template #footer>
        <BaseButton variant="ghost" @click="dialogVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :loading="saving" @click="handleSubmit">保存空间</BaseButton>
      </template>
    </BaseDialog>
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
import ArchivedWorkspacesDialog from '@/components/nav/ArchivedWorkspacesDialog.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import { buildWorkspaceHomePath } from '@/utils/workspace-routes'

const route = useRoute()
const router = useRouter()

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

/**
 * 加载所有工作空间列表
 */
async function fetchWorkspaces() {
  try {
    const res = await listWorkspaces({ page: 1, page_size: 100, sort_by: 'last_opened_at', sort_order: 'desc' })
    workspaces.value = res.items
  } catch (error) {
    console.error('Failed to load workspaces', error)
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

// 指令实现：点击外部关闭下拉框
const vClickOutside = {
  mounted(el: any, binding: any) {
    el.clickOutsideEvent = (event: Event) => {
      if (!(el === event.target || el.contains(event.target))) {
        binding.value()
      }
    }
    document.body.addEventListener('click', el.clickOutsideEvent)
  },
  unmounted(el: any) {
    document.body.removeEventListener('click', el.clickOutsideEvent)
  },
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

<style scoped>
.fade-scale-enter-active,
.fade-scale-leave-active {
  transition: all 0.2s ease-out;
}

.fade-scale-enter-from,
.fade-scale-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(-10px);
}
</style>
