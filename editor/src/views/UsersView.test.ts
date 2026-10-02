/**
 * 文件功能：用户管理视图单元测试，覆盖指标统计、多维搜索过滤与当前登录账号防呆保护。
 */
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { fireEvent, render, screen } from '@testing-library/vue'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import UsersView from './UsersView.vue'
import { listUsers } from '@/api/users'
import { useAuthStore } from '@/stores/auth'
import type { UserItem } from '@/types/api'

vi.mock('@/api/users', () => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  resetUserPassword: vi.fn(),
}))

const mockUsers: UserItem[] = [
  {
    id: 1,
    username: 'admin',
    display_name: '超级管理员',
    role: 'platform_admin',
    status: 'active',
    last_login_at: '2026-10-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 2,
    username: 'alice',
    display_name: '爱丽丝',
    role: 'workspace_user',
    status: 'active',
    last_login_at: null,
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
  {
    id: 3,
    username: 'bob',
    display_name: '鲍勃',
    role: 'workspace_user',
    status: 'archived',
    last_login_at: null,
    created_at: '2026-01-03T00:00:00Z',
    updated_at: '2026-01-03T00:00:00Z',
  },
]

describe('UsersView', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    setActivePinia(createPinia())
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    const authStore = useAuthStore()
    authStore.user = {
      id: 1,
      username: 'admin',
      display_name: '超级管理员',
      role: 'platform_admin',
      status: 'active',
    } as any
    vi.mocked(listUsers).mockResolvedValue(mockUsers)
  })

  it('正确统计并呈现用户指标卡片与当前用户标识', async () => {
    render(UsersView, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          SettingsPageHeader: {
            template: '<div><slot name="actions" /></div>',
          },
        },
      },
    })

    // 等待数据加载
    expect(await screen.findByText('admin')).toBeInTheDocument()
    expect(screen.getByText('当前账号')).toBeInTheDocument()

    // 检查指标统计数值
    expect(screen.getByText('总用户数')).toBeInTheDocument()
    expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('2')).toBeInTheDocument() // 活跃数
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(1) // 停用数与管理员数
  })

  it('支持根据关键词搜索过滤用户列表', async () => {
    render(UsersView, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          SettingsPageHeader: {
            template: '<div><slot name="actions" /></div>',
          },
        },
      },
    })

    expect(await screen.findByText('admin')).toBeInTheDocument()
    expect(screen.getByText('alice')).toBeInTheDocument()
    expect(screen.getByText('bob')).toBeInTheDocument()

    const searchInput = screen.getByPlaceholderText('搜索用户名或显示名...')
    await fireEvent.update(searchInput, '爱丽丝')

    expect(screen.getByText('alice')).toBeInTheDocument()
    expect(screen.queryByText('admin')).not.toBeInTheDocument()
    expect(screen.queryByText('bob')).not.toBeInTheDocument()
  })

  it('防呆机制：编辑自身账号时显示警告保护文案', async () => {
    render(UsersView, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          SettingsPageHeader: {
            template: '<div><slot name="actions" /></div>',
          },
          UiDialog: {
            props: ['open', 'title'],
            template: '<div v-if="open"><h2>{{ title }}</h2><slot /><slot name="footer" /></div>',
          },
        },
      },
    })

    expect(await screen.findByText('admin')).toBeInTheDocument()

    // 找到 admin 的编辑按钮（第一个用户）
    const editButtons = screen.getAllByRole('button', { name: '编辑' })
    await fireEvent.click(editButtons[0])

    // 应弹出防呆保护警告
    expect(screen.getByText(/安全防呆保护：您正在编辑当前登录账号/)).toBeInTheDocument()
  })
})
