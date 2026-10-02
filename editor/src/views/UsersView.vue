<!-- 文件功能：平台用户管理现代化视图，支持用户搜索多维筛选、指标统计概览、账号编辑与角色降级/停用防呆机制。 -->
<template>
  <section class="space-y-6 pb-12">
    <SettingsPageHeader
      title="用户管理"
      description="管理平台系统用户账号、分配全局角色权限并监控账户活跃状态。"
    >
      <template #actions>
        <UiButton variant="primary" @click="openCreate">
          <UserPlus class="h-4 w-4" />
          <span>新建用户</span>
        </UiButton>
      </template>
    </SettingsPageHeader>

    <!-- 统计概览卡片 -->
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <div class="rounded-xl border border-border bg-surface p-4 shadow-xs">
        <div class="text-xs font-medium text-text-muted">总用户数</div>
        <div class="mt-1 text-2xl font-bold text-text">{{ stats.total }}</div>
      </div>
      <div class="rounded-xl border border-border bg-surface p-4 shadow-xs">
        <div class="text-xs font-medium text-text-muted">启用中</div>
        <div class="mt-1 text-2xl font-bold text-success-strong">{{ stats.active }}</div>
      </div>
      <div class="rounded-xl border border-border bg-surface p-4 shadow-xs">
        <div class="text-xs font-medium text-text-muted">已停用</div>
        <div class="mt-1 text-2xl font-bold text-text-muted">{{ stats.archived }}</div>
      </div>
      <div class="rounded-xl border border-border bg-surface p-4 shadow-xs">
        <div class="text-xs font-medium text-text-muted">平台管理员</div>
        <div class="mt-1 text-2xl font-bold text-accent">{{ stats.admin }}</div>
      </div>
    </div>

    <!-- 搜索与多维筛选栏 -->
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex flex-1 flex-col gap-2.5 sm:flex-row sm:items-center">
        <div class="w-full sm:w-64">
          <SimpleSearchBar
            v-model="searchKeyword"
            placeholder="搜索用户名或显示名..."
          />
        </div>
        <div class="flex items-center gap-2">
          <UiSelect
            v-model="roleFilter"
            :options="roleFilterOptions"
            class="w-32"
          />
          <UiSelect
            v-model="statusFilter"
            :options="statusFilterOptions"
            class="w-28"
          />
        </div>
      </div>
      <div class="text-xs text-text-muted">
        共找到 <span class="font-semibold text-text">{{ filteredUsers.length }}</span> 位用户
      </div>
    </div>

    <!-- 用户列表数据表格 -->
    <div class="overflow-x-auto rounded-ui-xl border border-border bg-surface shadow-xs">
      <table class="w-full min-w-[880px] table-fixed text-left text-sm">
        <thead class="bg-canvas text-xs font-semibold uppercase text-text-muted">
          <tr>
            <th class="w-48 px-4 py-3">用户名</th>
            <th class="px-4 py-3">显示名</th>
            <th class="w-36 px-4 py-3">角色</th>
            <th class="w-28 px-4 py-3">状态</th>
            <th class="w-56 px-4 py-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border-muted">
          <tr v-for="user in filteredUsers" :key="user.id" class="transition-colors hover:bg-surface-hover/50">
            <td class="px-4 py-3">
              <div class="flex min-w-0 items-center gap-2">
                <span class="min-w-0 truncate font-semibold text-text" :title="user.username">{{ user.username }}</span>
                <UiBadge v-if="isCurrentUser(user)" tone="accent" size="sm" class="shrink-0">当前账号</UiBadge>
              </div>
            </td>
            <td class="px-4 py-3 text-text-emphasis truncate">{{ user.display_name }}</td>
            <td class="px-4 py-3">
              <UiBadge :tone="user.role === 'platform_admin' ? 'accent' : 'neutral'">
                {{ roleLabel(user.role) }}
              </UiBadge>
            </td>
            <td class="px-4 py-3">
              <UiBadge :tone="user.status === 'active' ? 'success' : 'neutral'">
                {{ user.status === 'active' ? '启用' : '停用' }}
              </UiBadge>
            </td>
            <td class="space-x-2 px-4 py-3 text-right">
              <UiButton variant="ghost" size="sm" @click="openEdit(user)">编辑</UiButton>
              <UiButton variant="ghost" size="sm" @click="openReset(user)">重置密码</UiButton>
            </td>
          </tr>
          <tr v-if="filteredUsers.length === 0">
            <td colspan="5" class="py-12 text-center text-text-muted">
              <div class="space-y-2">
                <p class="text-sm">没有匹配的用户记录</p>
                <UiButton v-if="searchKeyword || roleFilter !== 'all' || statusFilter !== 'all'" variant="ghost" size="sm" @click="clearFilters">
                  清空筛选条件
                </UiButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 用户创建 / 编辑弹窗 -->
    <UiDialog
      :open="editorVisible"
      :title="editingUser ? '编辑用户' : '新建用户'"
      size="compact"
      @update:open="editorVisible = $event"
    >
      <div class="space-y-4">
        <!-- 防呆提示 -->
        <div
          v-if="isEditingCurrentUser"
          class="flex items-center gap-2 rounded-lg border border-warning-muted bg-warning-muted/20 p-3 text-xs text-warning-strong"
        >
          <AlertTriangle class="h-4 w-4 shrink-0 text-warning" />
          <span>安全防呆保护：您正在编辑当前登录账号，不能降级自身角色或停用自身账号。</span>
        </div>

        <UiFormField v-if="!editingUser" label="用户名" required v-slot="field">
          <UiInput
            v-model="form.username"
            :input-id="field.inputId"
            :described-by="field.describedBy"
            :invalid="field.invalid"
            required
            placeholder="请输入账号登录名"
          />
        </UiFormField>
        <UiFormField label="显示名" required v-slot="field">
          <UiInput
            v-model="form.display_name"
            :input-id="field.inputId"
            :described-by="field.describedBy"
            :invalid="field.invalid"
            required
            placeholder="请输入姓名或昵称"
          />
        </UiFormField>
        <UiFormField v-if="!editingUser" label="初始密码" required v-slot="field">
          <UiInput
            v-model="form.password"
            type="password"
            password-toggle
            :input-id="field.inputId"
            :described-by="field.describedBy"
            :invalid="field.invalid"
            required
            placeholder="设置初始密码"
          />
        </UiFormField>
        <UiFormField label="角色">
          <UiSelect
            v-model="form.role"
            :options="roleOptions"
            :disabled="isEditingCurrentUser"
          />
        </UiFormField>
        <UiFormField label="状态">
          <UiSelect
            v-model="form.status"
            :options="statusOptions"
            :disabled="isEditingCurrentUser"
          />
        </UiFormField>
      </div>
      <template #footer>
        <UiButton variant="ghost" @click="editorVisible = false">取消</UiButton>
        <UiButton variant="primary" :loading="saving" @click="saveUser">保存</UiButton>
      </template>
    </UiDialog>

    <!-- 重置密码弹窗 -->
    <UiDialog :open="resetVisible" title="重置密码" size="compact" @update:open="resetVisible = $event">
      <UiFormField label="新密码" required v-slot="field">
        <UiInput
          v-model="resetPassword"
          type="password"
          password-toggle
          :input-id="field.inputId"
          :described-by="field.describedBy"
          :invalid="field.invalid"
          required
          placeholder="请输入新的登录密码"
        />
      </UiFormField>
      <template #footer>
        <UiButton variant="ghost" @click="resetVisible = false">取消</UiButton>
        <UiButton variant="primary" :loading="saving" @click="savePassword">保存</UiButton>
      </template>
    </UiDialog>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { AlertTriangle, UserPlus } from '@lucide/vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'

import { createUser, listUsers, resetUserPassword, updateUser } from '@/api/users'
import { getErrorMessage } from '@/api/http'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import { SimpleSearchBar } from '@/components/patterns'
import { UiBadge, UiButton, UiDialog, UiFormField, UiInput, UiSelect } from '@/components/ui'
import type { SelectOption } from '@/components/ui/select'
import { useAuthStore } from '@/stores/auth'
import { Message } from '@/utils/message'
import type { UserItem, UserRole } from '@/types/api'

const queryClient = useQueryClient()
const authStore = useAuthStore()

const usersQuery = useQuery({ queryKey: ['users'], queryFn: listUsers })
const editorVisible = ref(false)
const resetVisible = ref(false)
const saving = ref(false)
const editingUser = ref<UserItem | null>(null)
const resettingUser = ref<UserItem | null>(null)
const resetPassword = ref('')

// 搜索与过滤状态
const searchKeyword = ref('')
const roleFilter = ref('all')
const statusFilter = ref('all')

const form = reactive({
  username: '',
  password: '',
  display_name: '',
  role: 'workspace_user' as UserRole,
  status: 'active' as 'active' | 'archived',
})

const roleOptions: SelectOption[] = [
  { label: '普通用户', value: 'workspace_user' },
  { label: '平台管理员', value: 'platform_admin' },
]

const statusOptions: SelectOption[] = [
  { label: '启用', value: 'active' },
  { label: '停用', value: 'archived' },
]

const roleFilterOptions: SelectOption[] = [
  { label: '全部角色', value: 'all' },
  { label: '普通用户', value: 'workspace_user' },
  { label: '平台管理员', value: 'platform_admin' },
]

const statusFilterOptions: SelectOption[] = [
  { label: '全部状态', value: 'all' },
  { label: '启用', value: 'active' },
  { label: '停用', value: 'archived' },
]

/**
 * 判断目标用户是否为当前已登录的用户。
 * @param user 目标用户
 */
function isCurrentUser(user: UserItem): boolean {
  if (!authStore.user) return false
  return authStore.user.id === user.id || authStore.user.username === user.username
}

/**
 * 当前是否正在编辑自己的账号（用于触发防呆策略）。
 */
const isEditingCurrentUser = computed(() => {
  if (!editingUser.value) return false
  return isCurrentUser(editingUser.value)
})

/**
 * 统计数据。
 */
const stats = computed(() => {
  const users = usersQuery.data.value ?? []
  return {
    total: users.length,
    active: users.filter((u) => u.status === 'active').length,
    archived: users.filter((u) => u.status === 'archived').length,
    admin: users.filter((u) => u.role === 'platform_admin').length,
  }
})

/**
 * 根据搜索关键字与筛选条件计算过滤后的用户列表。
 */
const filteredUsers = computed(() => {
  const users = usersQuery.data.value ?? []
  const kw = searchKeyword.value.trim().toLowerCase()

  return users.filter((user) => {
    // 关键字搜索匹配：用户名或显示名
    if (kw) {
      const matchUsername = user.username.toLowerCase().includes(kw)
      const matchDisplayName = (user.display_name || '').toLowerCase().includes(kw)
      if (!matchUsername && !matchDisplayName) return false
    }

    // 角色筛选
    if (roleFilter.value !== 'all' && user.role !== roleFilter.value) {
      return false
    }

    // 状态筛选
    if (statusFilter.value !== 'all' && user.status !== statusFilter.value) {
      return false
    }

    return true
  })
})

/**
 * 清空所有搜索与筛选条件。
 */
function clearFilters() {
  searchKeyword.value = ''
  roleFilter.value = 'all'
  statusFilter.value = 'all'
}

/**
 * 转换用户角色显示标签。
 * @param role 用户角色
 */
function roleLabel(role: UserRole) {
  return role === 'platform_admin' ? '平台管理员' : '普通用户'
}

/**
 * 打开新建用户弹窗。
 */
function openCreate() {
  editingUser.value = null
  Object.assign(form, { username: '', password: '', display_name: '', role: 'workspace_user', status: 'active' })
  editorVisible.value = true
}

/**
 * 打开编辑用户弹窗。
 * @param user 待编辑用户
 */
function openEdit(user: UserItem) {
  editingUser.value = user
  Object.assign(form, {
    username: user.username,
    password: '',
    display_name: user.display_name,
    role: user.role,
    status: user.status,
  })
  editorVisible.value = true
}

/**
 * 打开重置密码弹窗。
 * @param user 待重置密码用户
 */
function openReset(user: UserItem) {
  resettingUser.value = user
  resetPassword.value = ''
  resetVisible.value = true
}

/**
 * 保存用户（带当前登录管理员防呆校验）。
 */
async function saveUser() {
  // 安全防呆防护：若编辑自身账号，禁止降级自身角色或停用自身
  if (editingUser.value && isCurrentUser(editingUser.value)) {
    if (form.status === 'archived') {
      Message.error('不能停用当前登录的管理员账号，以防系统失去控制。')
      return
    }
    if (form.role !== 'platform_admin') {
      Message.error('不能降级当前登录的管理员账号角色。')
      return
    }
  }

  saving.value = true
  try {
    if (editingUser.value) {
      await updateUser(editingUser.value.id, {
        display_name: form.display_name,
        role: form.role,
        status: form.status,
      })
    } else {
      await createUser({
        username: form.username,
        password: form.password,
        display_name: form.display_name,
        role: form.role,
        status: form.status,
      })
    }
    editorVisible.value = false
    Message.success('用户已保存。')
    await queryClient.invalidateQueries({ queryKey: ['users'] })
  } catch (error) {
    Message.error(getErrorMessage(error, '保存用户失败。'))
  } finally {
    saving.value = false
  }
}

/**
 * 重置用户密码。
 */
async function savePassword() {
  if (!resettingUser.value) return
  saving.value = true
  try {
    await resetUserPassword(resettingUser.value.id, resetPassword.value)
    resetVisible.value = false
    Message.success('密码已重置。')
  } catch (error) {
    Message.error(getErrorMessage(error, '重置密码失败。'))
  } finally {
    saving.value = false
  }
}
</script>
