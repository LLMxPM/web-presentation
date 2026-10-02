<!-- 文件功能：个人账户安全设置页，展示用户个人基础信息，并提供修改访问密码功能。 -->
<template>
  <div class="account-security-view space-y-6 pb-12">
    <SettingsPageHeader
      title="账户安全"
      description="管理您的个人账户基本信息、身份凭证与登录密码。"
    />

    <!-- 账户信息卡片 -->
    <section class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-4">
      <div class="border-b border-border-muted pb-3">
        <h2 class="text-base font-semibold text-text">基本信息</h2>
        <p class="mt-0.5 text-xs text-text-muted">当前已登录用户的系统身份标识与权限级别。</p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        <div class="space-y-1">
          <div class="text-xs text-text-secondary">用户名</div>
          <div class="font-medium text-text">{{ user?.username || '-' }}</div>
        </div>
        <div class="space-y-1">
          <div class="text-xs text-text-secondary">显示名称</div>
          <div class="font-medium text-text">{{ user?.display_name || '-' }}</div>
        </div>
        <div class="space-y-1">
          <div class="text-xs text-text-secondary">角色与权限</div>
          <div class="flex items-center gap-2">
            <UiBadge :tone="user?.role === 'platform_admin' ? 'accent' : 'neutral'">
              {{ user?.role === 'platform_admin' ? '平台管理员' : '普通用户' }}
            </UiBadge>
          </div>
        </div>
        <div class="space-y-1">
          <div class="text-xs text-text-secondary">账户状态</div>
          <div class="flex items-center gap-2">
            <UiBadge tone="success">正常启用</UiBadge>
          </div>
        </div>
      </div>
    </section>

    <!-- 修改密码卡片 -->
    <section class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-5">
      <div class="border-b border-border-muted pb-3">
        <h2 class="text-base font-semibold text-text">修改登录密码</h2>
        <p class="mt-0.5 text-xs text-text-muted">更新后将要求重新登录以使新密码生效。</p>
      </div>

      <form class="max-w-md space-y-4" @submit.prevent="handleUpdatePassword">
        <UiFormField label="当前密码" required :error="errors.old_password">
          <template #default="field">
            <UiInput
              v-model="form.old_password"
              type="password"
              placeholder="请输入原有的访问密码"
              required
              :input-id="field.inputId"
              :described-by="field.describedBy"
              :invalid="field.invalid"
              password-toggle
            />
          </template>
        </UiFormField>

        <UiFormField label="新密码" required :error="errors.new_password" description="密码长度需在 8 到 128 位之间。">
          <template #default="field">
            <UiInput
              v-model="form.new_password"
              type="password"
              placeholder="请输入 8 到 128 位的新密码"
              required
              :input-id="field.inputId"
              :described-by="field.describedBy"
              :invalid="field.invalid"
              password-toggle
            />
          </template>
        </UiFormField>

        <div class="pt-2">
          <UiButton variant="primary" type="submit" :loading="saving">
            更新密码
          </UiButton>
        </div>
      </form>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { changePassword } from '@/api/auth'
import { getErrorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { Message } from '@/utils/message'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import { UiBadge, UiButton, UiFormField, UiInput } from '@/components/ui'

const router = useRouter()
const authStore = useAuthStore()
const user = computed(() => authStore.user)

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
 * 校验并提交修改密码表单。
 */
async function handleUpdatePassword(): Promise<void> {
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
    await authStore.signOut()
    void router.push({ name: 'login' })
  } catch (err) {
    Message.error(getErrorMessage(err, '密码更新失败，请检查原密码是否正确'))
  } finally {
    saving.value = false
  }
}
</script>
