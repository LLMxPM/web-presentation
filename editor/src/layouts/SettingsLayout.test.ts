/**
 * 文件功能：验证设置与管理中心统一二层布局（SettingsLayout）在不同角色下的导航呈现与链接行为。
 */
import { render, screen } from '@testing-library/vue'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, reactive } from 'vue'

import SettingsLayout from '@/layouts/SettingsLayout.vue'
import { useAuthStore } from '@/stores/auth'

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
  beforeEach(() => {
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

    render(SettingsLayout)

    expect(screen.getByText('个人设置')).toBeTruthy()
    expect(screen.getByText('AI 设置')).toBeTruthy()
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

    render(SettingsLayout)

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

    render(SettingsLayout)

    const tokenLink = screen.getByText('访问令牌').closest('a')
    expect(tokenLink?.getAttribute('href')).toContain('/workspaces/1/home')
  })
})
