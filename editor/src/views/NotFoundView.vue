<!-- 文件功能：提供 Editor 未匹配路由的 404 兜底页面，帮助用户回到空间首页或平台入口。 -->
<template>
  <section class="flex min-h-[520px] items-center justify-center px-6 py-12">
    <div class="w-full max-w-xl text-center">
      <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
        <RouteOff class="h-8 w-8" />
      </div>
      <p class="mt-6 text-xs font-black uppercase tracking-[0.24em] text-slate-400">404</p>
      <h1 class="mt-3 text-2xl font-black text-slate-900">页面不存在</h1>
      <p class="mx-auto mt-3 max-w-md text-sm leading-6 text-slate-500">
        当前地址没有匹配到 Editor 页面，可能是链接已调整或路径输入有误。
      </p>

      <div class="mt-8 flex flex-wrap justify-center gap-3">
        <BaseButton v-if="workspaceHomePath" variant="primary" @click="goToWorkspaceHome">
          <Home class="h-4 w-4" />
          返回空间首页
        </BaseButton>
        <BaseButton variant="ghost" @click="goToEntry">
          <Compass class="h-4 w-4" />
          回到入口
        </BaseButton>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Compass, Home, RouteOff } from 'lucide-vue-next'

import BaseButton from '@/components/ui/BaseButton.vue'
import { buildWorkspaceHomePath } from '@/utils/workspace-routes'

const route = useRoute()
const router = useRouter()

const workspaceHomePath = computed(() => {
  const rawWorkspaceId = route.params.workspaceId
  const workspaceId = Array.isArray(rawWorkspaceId) ? rawWorkspaceId[0] : rawWorkspaceId
  return workspaceId ? buildWorkspaceHomePath(workspaceId) : null
})

/**
 * 返回当前工作空间首页。
 */
function goToWorkspaceHome(): void {
  if (!workspaceHomePath.value) {
    return
  }
  void router.push(workspaceHomePath.value)
}

/**
 * 回到平台入口，由 EntryView 负责进入最近访问的工作空间。
 */
function goToEntry(): void {
  void router.push('/')
}
</script>
