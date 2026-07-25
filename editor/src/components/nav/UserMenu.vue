<!-- 文件功能：顶部状态栏的用户个人菜单，包含修改密码及退出登录（TailwindCSS & Lucide 版）。 -->
<template>
  <div class="user-menu relative">
    <UiDropdownMenu :items="menuItems" side="bottom" align="end" @select="handleCommand">
      <template #trigger>
        <div
          class="flex items-center gap-3 p-1.5 rounded-xl hover:bg-slate-100 transition-all cursor-pointer select-none"
        >
          <div class="w-9 h-9 flex items-center justify-center rounded-full bg-indigo-600 text-white font-bold text-sm shadow-sm ring-2 ring-white">
            {{ initials }}
          </div>
          <div class="hidden sm:flex flex-col">
            <span class="text-sm font-bold text-slate-800 leading-tight">{{ user?.display_name || '-' }}</span>
            <span class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{{ user?.role === 'platform_admin' ? '平台管理员' : '工作空间用户' }}</span>
          </div>
          <ChevronDown class="w-4 h-4 text-slate-400" />
        </div>
      </template>
    </UiDropdownMenu>

    <!-- Password Dialog -->
    <UiDialog :open="passwordVisible" title="安全设置 - 修改密码" size="compact" @update:open="passwordVisible = $event">
      <div class="space-y-5">
        <UiFormField label="当前密码" required :error="errors.old_password">
          <template #default="field">
            <UiInput v-model="form.old_password" type="password" placeholder="请输入原有的访问密码" required :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" password-toggle />
          </template>
        </UiFormField>
        <UiFormField label="新密码" required :error="errors.new_password">
          <template #default="field">
            <UiInput v-model="form.new_password" type="password" placeholder="请输入 8 到 128 位的新密码" required :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" password-toggle />
          </template>
        </UiFormField>
      </div>
      <template #footer>
        <UiButton variant="ghost" @click="passwordVisible = false">取消</UiButton>
        <UiButton variant="primary" :loading="saving" @click="handleUpdatePassword">确认更新</UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bot, ChevronDown, KeyRound, LogOut, UserCog } from '@lucide/vue'

import { changePassword } from '@/api/auth'
import { getErrorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { Message } from '@/utils/message'
import { UiButton, UiDialog, UiDropdownMenu, UiFormField, UiInput } from '@/components/ui'
import type { DropdownMenuEntry } from '@/components/ui'

const router = useRouter()
const authStore = useAuthStore()

const user = computed(() => authStore.user)
const initials = computed(() => user.value?.display_name?.charAt(0)?.toUpperCase() || 'A')

const passwordVisible = ref(false)
const saving = ref(false)

const form = reactive({
  old_password: '',
  new_password: '',
})

const errors = reactive({
  old_password: '',
  new_password: '',
})

/**
 * 菜单项列表，根据用户角色动态生成。
 */
const menuItems = computed<DropdownMenuEntry[]>(() => {
  const items: DropdownMenuEntry[] = [
    { label: '修改密码', value: 'password', icon: KeyRound },
    { label: 'AI 设置', value: 'ai-settings', icon: Bot },
  ]
  if (user.value?.role === 'platform_admin') {
    items.push({ label: '用户管理', value: 'users', icon: UserCog })
  }
  items.push({ separator: true })
  items.push({ label: '退出登录', value: 'logout', icon: LogOut, danger: true })
  return items
})

/**
 * 处理菜单项选中事件。
 * @param command 菜单项标识
 */
async function handleCommand(command: string) {
  if (command === 'logout') {
    await authStore.signOut()
    Message.success('已安全退出登录。')
    router.push({ name: 'login' })
  } else if (command === 'ai-settings') {
    router.push({ name: 'accountAiSettings' })
  } else if (command === 'users') {
    router.push({ name: 'users' })
  } else if (command === 'password') {
    form.old_password = ''
    form.new_password = ''
    errors.old_password = ''
    errors.new_password = ''
    passwordVisible.value = true
  }
}

/**
 * 提交修改密码表单。
 */
async function handleUpdatePassword() {
  let hasError = false
  if (!form.old_password) {
    errors.old_password = '请输入当前密码'
    hasError = true
  } else {
    errors.old_password = ''
  }

  if (!form.new_password) {
    errors.new_password = '请输入新密码'
    hasError = true
  } else if (form.new_password.length < 8 || form.new_password.length > 128) {
    errors.new_password = '新密码长度必须为 8 到 128 位'
    hasError = true
  } else {
    errors.new_password = ''
  }

  if (hasError) return

  saving.value = true
  try {
    await changePassword({ old_password: form.old_password, new_password: form.new_password })
    Message.success('密码修改成功，请重新登录。')
    passwordVisible.value = false
    await authStore.signOut()
    router.push({ name: 'login' })
  } catch (error) {
    Message.error(getErrorMessage(error, '修改密码失败。'))
  } finally {
    saving.value = false
  }
}
</script>