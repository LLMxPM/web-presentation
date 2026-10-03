/** 文件功能：验证外部授权关闭/空态、显示范围及用户确认后的整链撤销和刷新。 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, expect, it, vi } from 'vitest'
import AccountOAuthGrantsView from '@/views/AccountOAuthGrantsView.vue'

const mocks = vi.hoisted(() => ({ list: vi.fn(), revoke: vi.fn(), confirm: vi.fn() }))
vi.mock('@/api/oauth', () => ({ listOAuthGrants: mocks.list, revokeOAuthGrant: mocks.revoke }))
vi.mock('@/utils/confirm', () => ({ createConfirm: mocks.confirm }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.confirm.mockResolvedValue(true)
  mocks.revoke.mockResolvedValue(undefined)
})

it('服务关闭和空授权均有明确状态', async () => {
  mocks.list.mockResolvedValue({ enabled: false, items: [] })
  const instance = render(AccountOAuthGrantsView)
  expect(await screen.findByText('平台尚未启用外部 OAuth 授权。')).toBeVisible()
  mocks.list.mockResolvedValue({ enabled: true, items: [] })
  await fireEvent.click(screen.getByRole('button', { name: '刷新' }))
  expect(await screen.findByText(/您还没有外部授权/)).toBeVisible()
  instance.unmount()
})

it('撤销前确认，提交后刷新授权状态', async () => {
  const grant = { grant_id: 'g-1', client_name: 'ChatGPT', resource: 'https://mcp.test/mcp',
    scopes: ['page:read'], workspace_ids: [7], workspaces: [{ id: 7, name: '产品文稿' }], created_at: '2026-10-04T00:00:00Z', revoked_at: null, is_active: true }
  mocks.list.mockResolvedValueOnce({ enabled: true, items: [grant] })
    .mockResolvedValue({ enabled: true, items: [{ ...grant, revoked_at: '2026-10-04T00:01:00Z', is_active: false }] })
  render(AccountOAuthGrantsView)
  expect(await screen.findByText('工作空间：产品文稿')).toBeVisible()
  await fireEvent.click(screen.getByRole('button', { name: '撤销' }))
  await waitFor(() => expect(mocks.revoke).toHaveBeenCalledWith('g-1'))
  expect(mocks.confirm.mock.calls[0]?.[0]).toContain('后台任务会继续执行')
  expect(await screen.findByText('已撤销')).toBeVisible()
})

it('取消撤销不发送写请求', async () => {
  mocks.list.mockResolvedValue({ enabled: true, items: [{ grant_id: 'g-1', client_name: 'ChatGPT',
    resource: 'https://mcp.test/mcp', scopes: [], workspace_ids: [7], workspaces: [{ id: 7, name: '产品文稿' }], created_at: '2026-10-04T00:00:00Z', revoked_at: null, is_active: true }] })
  mocks.confirm.mockResolvedValue(false)
  render(AccountOAuthGrantsView)
  await fireEvent.click(await screen.findByRole('button', { name: '撤销' }))
  expect(mocks.revoke).not.toHaveBeenCalled()
})
