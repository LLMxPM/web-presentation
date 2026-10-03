/**
 * 文件功能：验证设置与管理中心统一二层布局（SettingsLayout）在不同角色下的导航呈现与链接行为。
 */
import { render, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, reactive } from 'vue'

import SettingsLayout from '@/layouts/SettingsLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { ADMIN_SETTINGS_QUERY_KEY } from '@/api/adminSettings'

vi.mock('@/api/adminSettings', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/adminSettings')>(),
  fetchAdminSettings: vi.fn().mockResolvedValue({ items: [], categories: [], safe_mode_warnings: [] }),
}))

interface MutableRoute {
  path: string
  name: string
  query: Record<string, string>
}

const routerMock = vi.hoisted(() => ({
  route: null as MutableRoute | null,
  push: vi.fn(),
}))

vi.mock('vue-router', async () => {
  const { defineComponent, h, reactive } = await vi.importActual<typeof import('vue')>('vue')
  routerMock.route = reactive({
    path: '/settings/account/ai',
    name: 'accountAiSettings',
    query: {},
  })

  const RouterLinkStub = defineComponent({
    name: 'RouterLink',
    props: {
      to: {
        type: [String, Object],
        required: true,
      },
    },
    setup(props, { slots }) {
      return () => h('a', { href: typeof props.to === 'string' ? props.to : JSON.stringify(props.to) }, slots.default?.())
    },
  })

  const RouterViewStub = defineComponent({
    name: 'RouterView',
    setup() {
      return () => h('div', { 'data-testid': 'router-view' }, 'Content')
    },
  })

  return {
    useRoute: () => routerMock.route,
    useRouter: () => ({ push: routerMock.push }),
    RouterLink: RouterLinkStub,
    RouterView: RouterViewStub,
  }
})

describe('SettingsLayout', () => {
  let queryClient: QueryClient
  /** 布局与子页使用同一缓存实例，告警必须随保存快照即时变化。 */
  function renderLayout() {
    return render(SettingsLayout, { global: { plugins: [[VueQueryPlugin, { queryClient }]] } })
  }
  beforeEach(() => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    setActivePinia(createPinia())
    if (routerMock.route) {
      routerMock.route.path = '/settings/account/ai'
      routerMock.route.name = 'accountAiSettings'
      routerMock.route.query = {}
    }
  })

  it('普通用户访问时仅展示个人设置导航组，不展示平台管理', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: 2,
      username: 'normal_user',
      display_name: '普通创作者',
      role: 'workspace_user',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    renderLayout()

    expect(screen.getByText('个人设置')).toBeTruthy()
    expect(screen.getByText('模型连接')).toBeTruthy()
    expect(screen.getByText('助手提示词')).toBeTruthy()
    expect(screen.getByText('代码规范')).toBeTruthy()
    expect(screen.getByText('工具配置')).toBeTruthy()
    expect(screen.getByText('访问令牌')).toBeTruthy()
    expect(screen.getByText('账户安全')).toBeTruthy()

    // 普通用户不应出现平台管理组
    expect(screen.queryByText('平台管理')).toBeNull()
    expect(screen.queryByText('用户管理')).toBeNull()
    expect(screen.queryByText('系统设置')).toBeNull()
  })

  it('平台管理员访问时同时展示个人设置与平台管理两组导航', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: 1,
      username: 'admin',
      display_name: '系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    renderLayout()

    expect(screen.getByText('个人设置')).toBeTruthy()
    expect(screen.getByText('平台管理')).toBeTruthy()
    expect(screen.getByText('用户管理')).toBeTruthy()
    expect(screen.getByText('系统设置')).toBeTruthy()
  })

  it('导航链接应透传 returnTo 查询参数', () => {
    const authStore = useAuthStore()
    authStore.user = {
      id: 1,
      username: 'admin',
      display_name: '系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    if (routerMock.route) {
      routerMock.route.query = { returnTo: '/workspaces/1/home' }
    }

    renderLayout()

    const tokenLink = screen.getByText('访问令牌').closest('a')
    expect(tokenLink?.getAttribute('href')).toContain('/workspaces/1/home')
  })

  it('子页发布修复后的快照时应立即移除横幅与导航告警数', async () => {
    const authStore = useAuthStore()
    authStore.user = { id: 1, username: 'admin', role: 'platform_admin' } as typeof authStore.user
    routerMock.route!.path = '/settings/platform/users'
    renderLayout()
    await waitFor(() => expect(queryClient.getQueryData(ADMIN_SETTINGS_QUERY_KEY)).toBeDefined())
    queryClient.setQueryData(ADMIN_SETTINGS_QUERY_KEY, {
      items: [], categories: [], safe_mode_warnings: [{ key: 'log_level', error: '非法值', fallback_value: 'INFO' }],
    })
    expect(await screen.findByText('系统正处于 Safe-Mode 保护运行状态')).toBeInTheDocument()
    expect(screen.getByTitle('存在 1 项安全模式降级警告')).toBeInTheDocument()
    queryClient.setQueryData(ADMIN_SETTINGS_QUERY_KEY, { items: [], categories: [], safe_mode_warnings: [] })
    await waitFor(() => expect(screen.queryByText('系统正处于 Safe-Mode 保护运行状态')).toBeNull())
    expect(screen.queryByTitle('存在 1 项安全模式降级警告')).toBeNull()
    queryClient.setQueryData(ADMIN_SETTINGS_QUERY_KEY, {
      items: [], categories: [], safe_mode_warnings: [{ key: 'ai_enabled', error: '非法值', fallback_value: true }],
    })
    const repairLink = await screen.findByText('前往AI 管理修复 →')
    expect(repairLink.getAttribute('href')).toContain('/settings/platform/ai')
  })
})
