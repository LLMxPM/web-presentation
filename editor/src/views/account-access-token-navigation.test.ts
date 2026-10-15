/** 文件功能：使用真实设置布局与路由验证接入指南触发的令牌弹窗能正常关闭并释放模态锁。 */
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { createPinia } from 'pinia'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SettingsLayout from '@/layouts/SettingsLayout.vue'
import AccountAccessTokensView from './AccountAccessTokensView.vue'
import AccountCliIntegrationView from './AccountCliIntegrationView.vue'

vi.mock('@/api/accessTokens', () => ({
  listAccessTokens: vi.fn().mockResolvedValue({ items: [], max_active_tokens: 10 }),
  listAccessTokenScopes: vi.fn().mockResolvedValue([
    { scope: 'read:all', description: '只读权限', operation_count: 5 },
  ]),
  createAccessToken: vi.fn(),
  resetAccessToken: vi.fn(),
  revokeAccessToken: vi.fn(),
  updateAccessToken: vi.fn(),
}))

vi.mock('@/api/catalog', () => ({
  listWorkspaces: vi.fn().mockResolvedValue({
    items: [{ id: 11, name: '演示空间', status: 'active' }],
  }),
}))

let queryClient: QueryClient | undefined

afterEach(async () => {
  cleanup()
  await nextTick()
  queryClient?.clear()
})

/** 挂载真实路由与设置页过渡，仅模拟只读接口，保留 query 消费及 Reka 模态生命周期。 */
async function renderSettingsNavigation() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{
      path: '/settings',
      component: SettingsLayout,
      children: [
        { path: 'account/cli', component: AccountCliIntegrationView },
        { path: 'account/tokens', name: 'accountAccessTokens', component: AccountAccessTokensView },
        { path: ':pathMatch(.*)*', component: { template: '<div />' } },
      ],
    }],
  })
  await router.push('/settings/account/cli?returnTo=/workspaces/11/home')
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(defineComponent({ components: { RouterView }, template: '<RouterView />' }), {
    global: {
      plugins: [router, createPinia(), [VueQueryPlugin, { queryClient }]],
      stubs: { transition: false },
    },
  })
  return { router, view }
}

describe('接入指南与访问令牌导航', () => {
  it.each(['取消', '关闭按钮', 'Esc'] as const)('自动创建弹窗通过%s关闭后应允许再次操作页面', async closeMethod => {
    const { router } = await renderSettingsNavigation()
    await fireEvent.click(await screen.findByRole('button', { name: '前往创建访问令牌' }))

    const dialog = await screen.findByRole('dialog', { name: '创建个人访问令牌' })
    await waitFor(() => {
      expect(router.currentRoute.value.query).toEqual({ returnTo: '/workspaces/11/home' })
      expect(document.body.style.pointerEvents).toBe('none')
    })

    if (closeMethod === 'Esc') {
      await fireEvent.keyDown(window, { key: 'Escape' })
    } else {
      await fireEvent.click(within(dialog).getByRole('button', {
        name: closeMethod === '取消' ? '取消' : '关闭创建个人访问令牌',
        exact: true,
      }))
    }
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(document.body.style.pointerEvents).toBe('')
    })

    await fireEvent.click(screen.getByRole('button', { name: '创建新令牌', exact: true }))
    expect(await screen.findByRole('dialog', { name: '创建个人访问令牌' })).toBeInTheDocument()
    expect(document.body.style.pointerEvents).toBe('none')

    // 打开的弹窗随页面卸载时也应交由 Reka 释放锁，保证返回指南后仍可使用。
    await router.push('/settings/account/cli')
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '前往创建访问令牌' })).toBeInTheDocument()
      expect(document.body.style.pointerEvents).toBe('')
    })
  })
})
