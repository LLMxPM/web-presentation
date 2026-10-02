<!-- 文件功能：顶部状态栏的用户个人菜单，提供账户标识、进入设置与管理中心及安全退出登录。 -->
<template>
  <div class="user-menu relative">
    <UiDropdownMenu :items="menuItems" side="bottom" align="end" @select="handleCommand">
      <template #trigger>
        <div
          class="flex items-center gap-3 p-1.5 rounded-xl hover:bg-surface-muted transition-all cursor-pointer select-none"
        >
          <div class="w-9 h-9 flex items-center justify-center rounded-full bg-accent text-text-inverse font-bold text-sm shadow-sm ring-2 ring-surface">
            {{ initials }}
          </div>
          <div class="hidden sm:flex flex-col">
            <span class="text-sm font-bold text-text leading-tight">{{ user?.display_name || '-' }}</span>
            <span class="text-[11px] font-semibold text-text-disabled uppercase tracking-wider">{{ user?.role === 'platform_admin' ? '平台管理员' : '工作空间用户' }}</span>
          </div>
          <ChevronDown class="w-4 h-4 text-text-disabled" />
        </div>
      </template>
    </UiDropdownMenu>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronDown, LogOut, Settings } from '@lucide/vue'

import { useAuthStore } from '@/stores/auth'
import { Message } from '@/utils/message'
import { resolveGlobalReturnPath } from '@/utils/global-page-navigation'
import { UiDropdownMenu } from '@/components/ui'
import type { DropdownMenuEntry } from '@/components/ui'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const user = computed(() => authStore.user)
const initials = computed(() => user.value?.display_name?.charAt(0)?.toUpperCase() || 'A')

/**
 * 用户下拉菜单项列表，收敛为统一的设置与管理入口及登出操作。
 */
const menuItems = computed<DropdownMenuEntry[]>(() => [
  { label: '设置与管理', value: 'settings', icon: Settings },
  { separator: true },
  { label: '退出登录', value: 'logout', icon: LogOut, danger: true },
])

/**
 * 处理菜单项命令触发。
 * @param command 选中菜单项的值
 */
async function handleCommand(command: string) {
  if (command === 'logout') {
    await authStore.signOut()
    Message.success('已安全退出登录。')
    void router.push({ name: 'login' })
  } else if (command === 'settings') {
    const returnTo = resolveGlobalReturnPath(route.fullPath)
    void router.push(returnTo ? { path: '/settings', query: { returnTo } } : { path: '/settings' })
  }
}
</script>
