<!-- 文件功能：设置与管理中心通用二层布局，承载个人设置与平台管理二级导航，并调度具体设置子视图。 -->
<template>
  <div class="settings-layout flex h-full min-h-0 w-full overflow-hidden bg-canvas">
    <!-- 左侧设置二级导航栏 -->
    <aside class="settings-sidebar flex w-60 shrink-0 flex-col border-r border-border bg-surface px-3 py-4 select-none">
      <div class="flex-1 space-y-6 overflow-y-auto">
        <!-- 个人设置组 (Account Scope) -->
        <div class="space-y-1.5">
          <div class="px-2 text-[11px] font-bold uppercase tracking-wider text-text-muted">
            个人设置
          </div>
          <nav class="space-y-0.5" aria-label="个人设置导航">
            <RouterLink
              v-for="item in accountNavItems"
              :key="item.path"
              :to="resolveItemLocation(item.path)"
              class="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors"
              :class="isActive(item.path)
                ? 'bg-accent/10 text-accent font-semibold'
                : 'text-text-secondary hover:bg-surface-hover hover:text-text'"
            >
              <component :is="item.icon" class="h-4 w-4 shrink-0" />
              <span class="truncate">{{ item.label }}</span>
            </RouterLink>
          </nav>
        </div>

        <!-- 平台管理组 (Platform Scope - 仅平台管理员可见) -->
        <div v-if="isPlatformAdmin" class="space-y-1.5">
          <div class="flex items-center justify-between px-2 text-[11px] font-bold uppercase tracking-wider text-text-muted">
            <span>平台管理</span>
            <UiBadge tone="accent" size="sm">Admin</UiBadge>
          </div>
          <nav class="space-y-0.5" aria-label="平台管理导航">
            <RouterLink
              v-for="item in platformNavItems"
              :key="item.path"
              :to="resolveItemLocation(item.path)"
              class="flex items-center justify-between rounded-lg px-2.5 py-2 text-sm font-medium transition-colors"
              :class="isActive(item.path)
                ? 'bg-accent/10 text-accent font-semibold'
                : 'text-text-secondary hover:bg-surface-hover hover:text-text'"
            >
              <div class="flex items-center gap-2.5 min-w-0">
                <component :is="item.icon" class="h-4 w-4 shrink-0" />
                <span class="truncate">{{ item.label }}</span>
              </div>
              <span
                v-if="item.warningCount && item.warningCount > 0"
                class="flex h-4 min-w-4 items-center justify-center rounded-full bg-warning px-1 text-[10px] font-bold text-text-inverse"
                :title="`存在 ${item.warningCount} 项安全模式降级警告`"
              >
                {{ item.warningCount }}
              </span>
            </RouterLink>
          </nav>
        </div>
      </div>
    </aside>

    <!-- 右侧设置子页面主内容区 -->
    <main class="settings-content min-h-0 min-w-0 flex-1 overflow-y-auto p-6 md:p-8">
      <div class="mx-auto max-w-5xl">
        <!-- 全局 Safe-Mode 警告横幅（仅在访问平台管理页面且存在降级警告时常驻） -->
        <div
          v-if="isPlatformRoute && safeModeWarnings.length > 0"
          class="mb-6 rounded-xl border border-warning-muted bg-warning-muted/20 p-4 text-sm text-warning-strong"
        >
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-2.5">
              <AlertTriangle class="h-4 w-4 shrink-0 text-warning" />
              <span class="font-semibold">系统正处于 Safe-Mode 保护运行状态</span>
              <span class="text-xs text-text-secondary">检测到 {{ safeModeWarnings.length }} 项配置存在非法值，系统已自动回退安全默认值以防止崩溃。</span>
            </div>
            <RouterLink
              :to="resolveItemLocation('/settings/platform/settings')"
              class="shrink-0 text-xs font-semibold text-accent hover:underline"
            >
              前往系统设置修复 &rarr;
            </RouterLink>
          </div>
        </div>

        <RouterView v-slot="{ Component }">
          <Transition name="fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { AlertTriangle, Bot, Key, Settings, ShieldCheck, UserCog } from '@lucide/vue'

import { fetchAdminSettings } from '@/api/adminSettings'
import { useAuthStore } from '@/stores/auth'
import { UiBadge } from '@/components/ui'

const route = useRoute()
const authStore = useAuthStore()

const isPlatformAdmin = computed(() => authStore.user?.role === 'platform_admin')
const isPlatformRoute = computed(() => route.path.startsWith('/settings/platform') || route.path.startsWith('/admin'))
const safeModeWarnings = ref<Array<Record<string, unknown>>>([])

/** 个人设置导航项列表 */
const accountNavItems = [
  { label: 'AI 设置', path: '/settings/account/ai', icon: Bot },
  { label: '访问令牌', path: '/settings/account/tokens', icon: Key },
  { label: '账户安全', path: '/settings/account/security', icon: ShieldCheck },
]

/** 平台管理导航项列表 */
const platformNavItems = computed(() => [
  { label: '用户管理', path: '/settings/platform/users', icon: UserCog },
  { label: 'AI 管理', path: '/settings/platform/ai', icon: Bot },
  {
    label: '系统设置',
    path: '/settings/platform/settings',
    icon: Settings,
    warningCount: safeModeWarnings.value.length,
  },
])

/**
 * 若为平台管理员，加载系统配置概况以获取 Safe-Mode 告警。
 */
async function loadAdminSummary() {
  if (!isPlatformAdmin.value) return
  try {
    const res = await fetchAdminSettings()
    safeModeWarnings.value = res.safe_mode_warnings ?? []
  } catch {
    // 忽略加载失败，不阻塞正常页面导航
  }
}

onMounted(() => {
  void loadAdminSummary()
})

/**
 * 判断当前导航项是否处于激活状态（支持前缀匹配与兼容旧路由匹配）。
 * @param path 目标路径
 */
function isActive(path: string): boolean {
  if (route.path === path || route.path.startsWith(`${path}/`)) {
    return true
  }
  // 路由映射高亮判定
  if (path === '/settings/account/ai' && (route.name === 'accountAiSettings' || route.path === '/account/ai-settings')) {
    return true
  }
  if (path === '/settings/account/tokens' && (route.name === 'accountAccessTokens' || route.path === '/account/access-tokens')) {
    return true
  }
  if (path === '/settings/account/security' && (route.name === 'accountSecurity' || route.path === '/settings/account/security')) {
    return true
  }
  if (path === '/settings/platform/users' && (route.name === 'platformUsers' || route.name === 'users' || route.path === '/admin/users')) {
    return true
  }
  if (path === '/settings/platform/ai' && (route.name === 'platformAi' || route.path === '/settings/platform/ai')) {
    return true
  }
  if (path === '/settings/platform/settings' && (route.name === 'platformSettings' || route.name === 'adminSettings' || route.path === '/admin/settings')) {
    return true
  }
  return false
}

/**
 * 传递来源参数 returnTo，以便子页面统一保留返回工作空间路径。
 * @param path 目标路径
 */
function resolveItemLocation(path: string) {
  const returnTo = route.query.returnTo
  return returnTo ? { path, query: { returnTo } } : { path }
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
