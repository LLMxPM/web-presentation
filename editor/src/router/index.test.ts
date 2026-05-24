/**
 * 文件功能：验证路由守卫在登录页和受保护页面之间的跳转逻辑。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/layouts/AdminLayout.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/LoginView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/EntryView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/ProjectsView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/PagesView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/PageDetailView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/ComponentsView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/AssetsView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/ThemesView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/WorkspaceStylesView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/AccountAiSettingsView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/UsersView.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/NotFoundView.vue', () => ({ default: { template: '<div />' } }))

import { router } from '@/router'
import { useAuthStore } from '@/stores/auth'

describe('router guard', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.$reset()
    await router.push('/login')
  })

  it('未登录访问受保护页面时应跳回登录页', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = null

    await router.push('/')

    expect(router.currentRoute.value.name).toBe('login')
  })

  it('已登录访问登录页时应跳到工作空间页', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = {
      id: 1,
      username: 'admin',
      display_name: '平台系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    await router.push('/')
    await router.push('/login')

    expect(router.currentRoute.value.fullPath).toBe('/')
  })

  it('已登录时应允许进入 AI 设置页', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = {
      id: 1,
      username: 'admin',
      display_name: '平台系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    await router.push('/account/ai-settings')

    expect(router.currentRoute.value.name).toBe('accountAiSettings')
  })

  it('旧 AI 设置子路径应进入 404 兜底页', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = {
      id: 1,
      username: 'admin',
      display_name: '平台系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    await router.push('/account/ai-models')
    expect(router.currentRoute.value.name).toBe('notFound')

    await router.push('/account/agents')
    expect(router.currentRoute.value.name).toBe('notFound')
  })

  it('已登录时应允许进入工作空间组件库页', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = {
      id: 1,
      username: 'admin',
      display_name: '平台系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    await router.push('/workspaces/1/components')

    expect(router.currentRoute.value.name).toBe('components')
  })

  it('工作空间主页面应带有右侧 Dock 导航元信息', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = {
      id: 1,
      username: 'admin',
      display_name: '平台系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    await router.push('/workspaces/1/home')
    expect(router.currentRoute.value.meta.workspaceNav).toBe('projects')

    await router.push('/workspaces/1/components')
    expect(router.currentRoute.value.meta.workspaceNav).toBe('components')

    await router.push('/workspaces/1/assets')
    expect(router.currentRoute.value.meta.workspaceNav).toBe('assets')

    await router.push('/workspaces/1/themes')
    expect(router.currentRoute.value.meta.workspaceNav).toBe('themes')

    await router.push('/workspaces/1/styles')
    expect(router.currentRoute.value.meta.workspaceNav).toBe('styles')

    await router.push('/workspaces/1/projects/2/pages')
    expect(router.currentRoute.value.meta.workspaceNav).toBe('projects')
    expect(router.currentRoute.value.meta.fullHeight).toBe(true)

    await router.push('/workspaces/1/projects/2/pages/3')
    expect(router.currentRoute.value.meta.workspaceNav).toBe('projects')
    expect(router.currentRoute.value.meta.fullHeight).toBe(true)
  })

  it('已登录时应允许进入空间首页，并把旧项目列表路径重定向到空间首页', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = {
      id: 1,
      username: 'admin',
      display_name: '平台系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    await router.push('/workspaces/1/home')
    expect(router.currentRoute.value.name).toBe('workspaceHome')

    await router.push('/workspaces/1/projects')
    expect(router.currentRoute.value.fullPath).toBe('/workspaces/1/home')
    expect(router.currentRoute.value.name).toBe('workspaceHome')
  })

  it('已登录访问未知路径时应进入 404 兜底页', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = {
      id: 1,
      username: 'admin',
      display_name: '平台系统管理员',
      role: 'platform_admin',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    await router.push('/workspaces/1/unknown-page')
    expect(router.currentRoute.value.name).toBe('workspaceNotFound')
    expect(router.currentRoute.value.params.workspaceId).toBe('1')

    await router.push('/missing/path')
    expect(router.currentRoute.value.name).toBe('notFound')
  })

  it('普通用户访问用户管理页时应回到工作空间页', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = {
      id: 2,
      username: 'user',
      display_name: '普通用户',
      role: 'workspace_user',
      status: 'active',
      last_login_at: null,
      preview_size_presets: [],
    }

    await router.push('/admin/users')

    expect(router.currentRoute.value.fullPath).toBe('/')
  })

  it('未登录访问未知路径时仍应先跳回登录页', async () => {
    const store = useAuthStore()
    vi.spyOn(store, 'ensureLoaded').mockResolvedValue()
    store.user = null

    await router.push('/missing/path')

    expect(router.currentRoute.value.name).toBe('login')
  })
})
