<!-- 文件功能：平台根入口，自动进入近期工作空间，并为无启用工作空间的用户提供创建引导。 -->
<template>
  <div class="flex h-full min-h-[28rem] items-center justify-center px-4">
    <DataState
      class="w-full max-w-xl"
      :state="entryState"
      :title="entryStateTitle"
      :description="entryStateDescription"
      @retry="loadActiveWorkspace"
    >
      <template #empty>
        <UiButton class="mt-2" size="lg" @click="openCreateDialog">
          <template #icon>
            <Plus class="h-5 w-5" />
          </template>
          创建工作空间
        </UiButton>
      </template>
    </DataState>

    <UiDialog
      :open="createDialogVisible"
      title="创建工作空间"
      size="compact"
      body-preset="dense"
      @update:open="createDialogVisible = $event"
    >
      <div class="flex h-full min-h-0 flex-col gap-5">
        <UiFormField label="工作空间名称" required :error="errors.name">
          <template #default="field">
            <UiInput
              v-model="form.name"
              placeholder="例如：产品演示"
              required
              :input-id="field.inputId"
              :described-by="field.describedBy"
              :invalid="field.invalid"
            />
          </template>
        </UiFormField>
        <UiFormField class="min-h-0 flex-1" label="工作空间描述">
          <template #default="field">
            <UiInput
              v-model="form.description"
              type="textarea"
              textarea-mode="fill"
              placeholder="（可选）说明该空间的用途或归属"
              :input-id="field.inputId"
              :described-by="field.describedBy"
            />
          </template>
        </UiFormField>
      </div>
      <template #footer>
        <UiButton variant="ghost" @click="createDialogVisible = false">取消</UiButton>
        <UiButton :loading="saving" @click="handleCreateWorkspace">创建并进入</UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus } from '@lucide/vue'

import { createWorkspace, listWorkspaces } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import DataState from '@/components/patterns/DataState.vue'
import { UiButton, UiDialog, UiFormField, UiInput } from '@/components/ui'
import { reportClientError } from '@/utils/client-logger'
import { Message } from '@/utils/message'
import { buildWorkspaceHomePath } from '@/utils/workspace-routes'

type EntryState = 'loading' | 'empty' | 'error'

const router = useRouter()
const entryState = ref<EntryState>('loading')
const createDialogVisible = ref(false)
const saving = ref(false)
const form = reactive({ name: '', description: '' })
const errors = reactive({ name: '' })

const entryStateTitle = computed(() => {
  if (entryState.value === 'empty') return '创建第一个工作空间'
  if (entryState.value === 'error') return '工作空间加载失败'
  return '正在加载工作空间'
})

const entryStateDescription = computed(() => {
  if (entryState.value === 'empty') return '工作空间用于集中管理项目、页面、组件和资源。创建后即可开始制作演示内容。'
  if (entryState.value === 'error') return '暂时无法获取工作空间，请检查网络后重试。'
  return '正在同步权限并查找最近使用的空间。'
})

/**
 * 查询最近使用的启用工作空间；存在时直接进入，否则展示可操作的创建引导。
 */
async function loadActiveWorkspace(): Promise<void> {
  entryState.value = 'loading'
  try {
    const response = await listWorkspaces({
      page: 1,
      page_size: 1,
      status: 'active',
      sort_by: 'last_opened_at',
      sort_order: 'desc',
    })
    const workspace = response.items[0]
    if (workspace) {
      await router.replace(buildWorkspaceHomePath(workspace.id))
      return
    }
    entryState.value = 'empty'
  } catch (error) {
    entryState.value = 'error'
    reportClientError(error, { message: '获取工作空间失败，请检查网络。', component: 'EntryView' })
  }
}

/** 打开创建表单，并清理上次输入与校验状态。 */
function openCreateDialog(): void {
  form.name = ''
  form.description = ''
  errors.name = ''
  createDialogVisible.value = true
}

/**
 * 创建启用工作空间并直接进入，同时通知顶部切换器刷新列表。
 */
async function handleCreateWorkspace(): Promise<void> {
  const name = form.name.trim()
  if (!name) {
    errors.name = '请输入工作空间名称'
    return
  }

  errors.name = ''
  saving.value = true
  try {
    const workspace = await createWorkspace({
      name,
      description: form.description.trim() || null,
      status: 'active',
    })
    createDialogVisible.value = false
    window.dispatchEvent(new CustomEvent('workspace-list-updated'))
    Message.success('工作空间创建成功。')
    await router.replace(buildWorkspaceHomePath(workspace.id))
  } catch (error) {
    Message.error(getErrorMessage(error, '创建工作空间失败。'))
  } finally {
    saving.value = false
  }
}

onMounted(loadActiveWorkspace)
</script>
