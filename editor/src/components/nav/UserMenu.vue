<!-- 文件功能：顶部状态栏的用户个人菜单，包含修改密码及退出登录（TailwindCSS & Lucide 版）。 -->
<template>
  <div class="user-menu relative" v-click-outside="closeDropdown">
    <!-- Trigger -->
    <div 
      @click="dropdownVisible = !dropdownVisible"
      class="flex items-center gap-3 p-1.5 rounded-xl hover:bg-slate-100 transition-all cursor-pointer select-none"
      :class="{ 'bg-slate-100': dropdownVisible }"
    >
      <div class="w-9 h-9 flex items-center justify-center rounded-full bg-indigo-600 text-white font-bold text-sm shadow-sm ring-2 ring-white">
        {{ initials }}
      </div>
      <div class="hidden sm:flex flex-col">
        <span class="text-sm font-bold text-slate-800 leading-tight">{{ user?.display_name || '-' }}</span>
        <span class="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">{{ user?.role === 'platform_admin' ? '平台管理员' : '工作空间用户' }}</span>
      </div>
      <ChevronDown class="w-4 h-4 text-slate-400 transition-transform duration-200" :class="{ 'rotate-180': dropdownVisible }" />
    </div>

    <!-- Dropdown Menu -->
    <Transition name="fade-scale">
      <div 
        v-if="dropdownVisible"
        class="absolute right-0 mt-2 w-48 bg-white border border-slate-200 rounded-2xl shadow-xl z-50 py-1.5 overflow-hidden"
      >
        <button 
          @click="handleCommand('password')"
          class="w-full flex items-center gap-3 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
        >
          <KeyRound class="w-4 h-4 text-slate-400" />
          修改密码
        </button>
        <button 
          @click="handleCommand('ai-settings')"
          class="w-full flex items-center gap-3 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
        >
          <Bot class="w-4 h-4 text-slate-400" />
          AI 设置
        </button>
        <button
          v-if="user?.role === 'platform_admin'"
          @click="handleCommand('users')"
          class="w-full flex items-center gap-3 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
        >
          <UserCog class="w-4 h-4 text-slate-400" />
          用户管理
        </button>
        <div class="my-1.5 border-t border-slate-100"></div>
        <button 
          @click="handleCommand('logout')"
          class="w-full flex items-center gap-3 px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 transition-colors"
        >
          <LogOut class="w-4 h-4 text-red-400" />
          退出登录
        </button>
      </div>
    </Transition>

    <!-- Password Dialog -->
    <BaseDialog v-model="passwordVisible" title="安全设置 - 修改密码" width="420px">
      <div class="space-y-5">
        <BaseInput 
          v-model="form.old_password" 
          type="password" 
          label="当前密码" 
          placeholder="请输入原有的访问密码"
          required
          :error="errors.old_password"
        />
        <BaseInput 
          v-model="form.new_password" 
          type="password" 
          label="新密码" 
          placeholder="请输入 8 到 128 位的新密码"
          required
          :error="errors.new_password"
        />
      </div>
      <template #footer>
        <BaseButton variant="ghost" @click="passwordVisible = false">取消</BaseButton>
        <BaseButton variant="primary" :loading="saving" @click="handleUpdatePassword">确认更新</BaseButton>
      </template>
    </BaseDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Bot, ChevronDown, LogOut, KeyRound, UserCog } from 'lucide-vue-next'

import { changePassword } from '@/api/auth'
import { getErrorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { Message } from '@/utils/message'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseDialog from '@/components/ui/BaseDialog.vue'

const router = useRouter()
const authStore = useAuthStore()

const user = computed(() => authStore.user)
const initials = computed(() => user.value?.display_name?.charAt(0)?.toUpperCase() || 'A')

const dropdownVisible = ref(false)
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

async function handleCommand(command: string) {
  closeDropdown()
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

async function handleUpdatePassword() {
  // 简易校验
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

<style scoped>
.fade-scale-enter-active, .fade-scale-leave-active {
  transition: all 0.2s ease-out;
}
.fade-scale-enter-from, .fade-scale-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(-10px);
}
</style>
