<!-- 文件功能：提供平台用户登录入口（TailwindCSS 版）。 -->
<template>
  <div data-testid="login-view" class="min-h-screen grid place-items-center p-8 bg-slate-50">
    <div class="w-full max-w-5xl grid lg:grid-cols-[1.1fr_0.9fr] gap-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <!-- Left: Intro Section -->
      <section class="bg-indigo-900 rounded-[32px] p-12 text-white flex flex-col justify-center relative overflow-hidden shadow-2xl border border-indigo-800">
        <!-- Abstract Decoration (Solid Circles instead of Gradients) -->
        <div class="absolute -top-24 -left-24 w-64 h-64 bg-indigo-800 rounded-full opacity-50"></div>
        <div class="absolute -bottom-24 -right-24 w-80 h-80 bg-indigo-950 rounded-full opacity-30"></div>
        
        <div class="relative z-10">
          <div class="inline-flex px-4 py-1.5 rounded-full bg-white/10 text-xs font-bold uppercase tracking-widest mb-8 border border-white/5">
            页面管理一期
          </div>
          <h1 class="text-5xl font-extrabold leading-[1.1] mb-6 tracking-tight">先把页面管理后台搭稳，再逐步衔接运行时能力。</h1>
          <p class="text-lg leading-relaxed text-indigo-100/90 font-medium">
            当前版本支持多用户登录、工作空间隔离、项目管理、页面资源库与 AI 配置管理，平台管理员可统一维护用户与全局模型默认值。
          </p>
        </div>
      </section>

      <!-- Right: Login Form -->
      <section class="bg-white/80 backdrop-blur-md rounded-[32px] p-12 shadow-2xl border border-white flex flex-col justify-center">
        <div class="mb-10">
          <h2 class="text-3xl font-extrabold text-slate-900 mb-2 tracking-tight">用户登录</h2>
          <p class="text-slate-500 font-medium italic">使用平台账号进入管理后台。</p>
        </div>

        <form @submit.prevent="handleSubmit" class="space-y-6">
          <BaseInput 
            v-model="form.username" 
            data-testid="login-username"
            label="用户名" 
            placeholder="请输入用户名" 
            required
            @keydown.enter="focusPassword"
          />
          <BaseInput 
            ref="passwordRef"
            v-model="form.password" 
            data-testid="login-password"
            label="密码" 
            type="password" 
            placeholder="请输入访问密码" 
            required
            @keydown.enter="handleSubmit"
          />
          
          <div class="pt-4">
            <BaseButton 
              data-testid="login-submit"
              variant="primary" 
              class="w-full h-12 text-base shadow-indigo-200"
              :loading="submitting"
              @click="handleSubmit"
            >
              登 录
            </BaseButton>
          </div>
        </form>
        
        <p class="mt-8 text-center text-xs text-slate-400 font-medium">
          &copy; 2026 Web-Presentation | Advanced Agentic Coding
        </p>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getErrorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { Message } from '@/utils/message'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const submitting = ref(false)
const passwordRef = ref()

const form = reactive({
  username: 'admin',
  password: '',
})

function focusPassword() {
  passwordRef.value?.$el?.querySelector('input')?.focus()
}

/**
 * 登录成功后优先回跳来源页面，否则进入入口。
 */
async function handleSubmit() {
  if (!form.username || !form.password) {
    Message.warning('请填写完整登录凭据')
    return
  }

  submitting.value = true
  try {
    await authStore.signIn({ username: form.username, password: form.password })
    Message.success('欢迎回来，登录成功。')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  } catch (error) {
    Message.error(getErrorMessage(error, '登录失败，请检查凭据。'))
  } finally {
    submitting.value = false
  }
}
</script>
