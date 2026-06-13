<!-- 文件功能：提供平台管理员维护用户账号、角色、状态和重置密码的管理页。 -->
<template>
  <section class="space-y-5">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-slate-900">用户管理</h1>
      </div>
      <button
        class="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
        @click="openCreate"
      >
        新建用户
      </button>
    </div>

    <div class="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <table class="w-full table-fixed text-left text-sm">
        <thead class="bg-slate-50 text-xs font-semibold uppercase text-slate-500">
          <tr>
            <th class="w-40 px-4 py-3">用户名</th>
            <th class="px-4 py-3">显示名</th>
            <th class="w-40 px-4 py-3">角色</th>
            <th class="w-32 px-4 py-3">状态</th>
            <th class="w-64 px-4 py-3 text-right">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr v-for="user in usersQuery.data.value ?? []" :key="user.id">
            <td class="px-4 py-3 font-semibold text-slate-800">{{ user.username }}</td>
            <td class="px-4 py-3 text-slate-700">{{ user.display_name }}</td>
            <td class="px-4 py-3 text-slate-600">{{ roleLabel(user.role) }}</td>
            <td class="px-4 py-3">
              <span
                class="rounded-full px-2 py-1 text-xs font-semibold"
                :class="user.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
              >
                {{ user.status === 'active' ? '启用' : '停用' }}
              </span>
            </td>
            <td class="space-x-2 px-4 py-3 text-right">
              <button class="text-sm font-semibold text-slate-700 hover:text-slate-950" @click="openEdit(user)">编辑</button>
              <button class="text-sm font-semibold text-slate-700 hover:text-slate-950" @click="openReset(user)">重置密码</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <BaseDialog v-model="editorVisible" :title="editingUser ? '编辑用户' : '新建用户'" size="compact">
      <div class="space-y-4">
        <BaseInput v-if="!editingUser" v-model="form.username" label="用户名" required />
        <BaseInput v-model="form.display_name" label="显示名" required />
        <BaseInput v-if="!editingUser" v-model="form.password" type="password" label="初始密码" required />
        <label class="block space-y-1 text-sm font-semibold text-slate-700">
          <span>角色</span>
          <select v-model="form.role" class="w-full rounded-md border border-slate-300 px-3 py-2">
            <option value="workspace_user">普通用户</option>
            <option value="platform_admin">平台管理员</option>
          </select>
        </label>
        <label class="block space-y-1 text-sm font-semibold text-slate-700">
          <span>状态</span>
          <select v-model="form.status" class="w-full rounded-md border border-slate-300 px-3 py-2">
            <option value="active">启用</option>
            <option value="archived">停用</option>
          </select>
        </label>
      </div>
      <template #footer>
        <BaseButton variant="ghost" @click="editorVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :loading="saving" @click="saveUser">保存</BaseButton>
      </template>
    </BaseDialog>

    <BaseDialog v-model="resetVisible" title="重置密码" size="compact">
      <BaseInput v-model="resetPassword" type="password" label="新密码" required />
      <template #footer>
        <BaseButton variant="ghost" @click="resetVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :loading="saving" @click="savePassword">保存</BaseButton>
      </template>
    </BaseDialog>
  </section>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'

import { createUser, listUsers, resetUserPassword, updateUser } from '@/api/users'
import { getErrorMessage } from '@/api/http'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import { Message } from '@/utils/message'
import type { UserItem, UserRole } from '@/types/api'

const queryClient = useQueryClient()
const usersQuery = useQuery({ queryKey: ['users'], queryFn: listUsers })
const editorVisible = ref(false)
const resetVisible = ref(false)
const saving = ref(false)
const editingUser = ref<UserItem | null>(null)
const resettingUser = ref<UserItem | null>(null)
const resetPassword = ref('')
const form = reactive({
  username: '',
  password: '',
  display_name: '',
  role: 'workspace_user' as UserRole,
  status: 'active' as 'active' | 'archived',
})

function roleLabel(role: UserRole) {
  return role === 'platform_admin' ? '平台管理员' : '普通用户'
}

function openCreate() {
  editingUser.value = null
  Object.assign(form, { username: '', password: '', display_name: '', role: 'workspace_user', status: 'active' })
  editorVisible.value = true
}

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

function openReset(user: UserItem) {
  resettingUser.value = user
  resetPassword.value = ''
  resetVisible.value = true
}

async function saveUser() {
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

