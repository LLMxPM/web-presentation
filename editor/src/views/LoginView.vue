<!-- 文件功能：提供平台用户登录入口，承载产品定位展示与账号密码登录表单。 -->
<template>
  <div data-testid="login-view" class="min-h-screen bg-surface-muted text-text-strong">
    <main class="mx-auto flex min-h-screen w-full max-w-[1180px] items-center px-10 py-8">
      <div class="grid w-full grid-cols-[minmax(0,760px)_400px] gap-5">
        <section
          aria-label="平台概览"
          class="min-h-[500px] rounded-lg border border-border bg-surface p-8 shadow-sm"
        >
          <header class="flex items-center justify-between gap-6">
            <div class="flex min-w-0 items-center gap-3">
              <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-border bg-surface p-2 shadow-sm">
                <img :src="faviconSrc" alt="" class="h-full w-full object-contain" aria-hidden="true" />
              </div>
              <div class="min-w-0">
                <p class="text-lg font-extrabold text-text-strong">Web-Presentation</p>
                <p class="truncate text-sm font-medium text-text-muted">AI 演示文稿创作平台</p>
              </div>
            </div>
            <span class="inline-flex shrink-0 items-center gap-2 rounded-lg border border-success-border bg-success-muted px-3 py-1.5 text-xs font-bold text-success-strong">
              <span class="h-2 w-2 rounded-full bg-success" aria-hidden="true"></span>
              Runtime 就绪
            </span>
          </header>

          <div class="mt-8 grid grid-cols-[minmax(0,1fr)_190px] items-center gap-7">
            <div class="min-w-0">
              <h1 class="max-w-3xl whitespace-nowrap text-[30px] font-extrabold leading-[1.15] text-text-strong">
                让演示内容成为可复用资产
              </h1>
              <p class="mt-5 max-w-2xl text-sm font-medium leading-7 text-text-secondary">
                面向 PPT、图文卡片和报告页创作，平台将项目上下文、资产清单与 Runtime 能力分层管理，让 AI 专注具体页面内容。
              </p>
            </div>

            <div class="flex min-h-[190px] items-center justify-center rounded-lg border border-border bg-canvas">
              <img :src="heroImage" alt="" class="h-40 w-40 object-contain" />
            </div>
          </div>

          <div class="mt-8 grid grid-cols-4 gap-3">
            <div
              v-for="item in capabilityItems"
              :key="item.label"
              class="rounded-lg border border-border bg-canvas p-3.5"
            >
              <component :is="item.icon" class="mb-3 h-5 w-5" :class="item.iconClass" aria-hidden="true" />
              <p class="text-sm font-bold text-text-strong">{{ item.label }}</p>
              <p class="mt-1 text-xs font-medium leading-5 text-text-muted">{{ item.text }}</p>
            </div>
          </div>
        </section>

        <section class="flex min-h-[500px] rounded-lg border border-border bg-surface p-8 shadow-sm">
          <div class="flex w-full flex-col">
            <div class="flex items-start justify-between gap-4">
              <div>
                <h2 class="text-3xl font-extrabold text-text-strong">登录工作台</h2>
                <p class="mt-2 text-sm font-medium text-text-muted">使用平台账号继续创作</p>
              </div>
              <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border bg-canvas text-text-secondary">
                <ShieldCheck class="h-5 w-5" aria-hidden="true" />
              </div>
            </div>

            <form @submit.prevent="handleSubmit" class="mt-10 space-y-6">
              <UiFormField label="用户名" required v-slot="field">
                <UiInput
                  v-model="form.username"
                  data-testid="login-username"
                  :input-id="field.inputId"
                  :described-by="field.describedBy"
                  :invalid="field.invalid"
                  placeholder="请输入用户名"
                  required
                  @keydown.enter.prevent="focusPassword"
                />
              </UiFormField>
              <UiFormField label="密码" required v-slot="field">
                <UiInput
                  ref="passwordRef"
                  v-model="form.password"
                  data-testid="login-password"
                  :input-id="field.inputId"
                  :described-by="field.describedBy"
                  :invalid="field.invalid"
                  type="password"
                  password-toggle
                  placeholder="请输入访问密码"
                  required
                />
              </UiFormField>

              <div class="pt-4">
                <UiButton
                  data-testid="login-submit"
                  type="submit"
                  variant="primary"
                  class="h-12 w-full text-base shadow-accent-ring"
                  :loading="submitting"
                >
                  <template #icon>
                    <LogIn class="h-4 w-4" aria-hidden="true" />
                  </template>
                  登录
                </UiButton>
              </div>
            </form>

            <p class="mt-10 text-center text-xs font-medium text-text-disabled">
              © 2026
              <a
                class="font-semibold text-text-muted transition-colors hover:text-text-strong"
                href="https://github.com/LLMxPM/web-presentation"
                target="_blank"
                rel="noreferrer"
              >
                Web-Presentation
              </a>
            </p>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Boxes, Layers3, LogIn, Palette, ShieldCheck, Sparkles } from '@lucide/vue'

import { getErrorMessage } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { Message } from '@/utils/message'
import { UiButton, UiFormField, UiInput } from '@/components/ui'
import heroImage from '@/assets/hero.png'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const submitting = ref(false)
const passwordRef = ref()
const faviconSrc = `${import.meta.env.BASE_URL}favicon.svg`
const capabilityItems = [
  {
    label: 'AI 上下文',
    text: '按项目、页面和资产隔离注入',
    icon: Sparkles,
    iconClass: 'text-accent',
  },
  {
    label: '组件复用',
    text: '沉淀可复用演示模块',
    icon: Boxes,
    iconClass: 'text-success',
  },
  {
    label: '样式资产',
    text: '管理主题和样式，形成可复用资产',
    icon: Palette,
    iconClass: 'text-warning',
  },
  {
    label: '页面编排',
    text: '管理项目路由与页面',
    icon: Layers3,
    iconClass: 'text-info',
  },
]

const form = reactive({
  username: '',
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
