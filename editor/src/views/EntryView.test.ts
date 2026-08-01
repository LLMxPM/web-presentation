/**
 * 文件功能：验证平台入口会自动进入已有工作空间，并在无启用空间时引导用户创建。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import EntryView from '@/views/EntryView.vue'

const mocked = vi.hoisted(() => ({
  createWorkspace: vi.fn(),
  listWorkspaces: vi.fn(),
  replace: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace: mocked.replace }),
}))

vi.mock('@/api/catalog', () => ({
  createWorkspace: (...args: unknown[]) => mocked.createWorkspace(...args),
  listWorkspaces: (...args: unknown[]) => mocked.listWorkspaces(...args),
}))

vi.mock('@/utils/message', () => ({
  Message: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/utils/client-logger', () => ({
  reportClientError: vi.fn(),
}))

describe('EntryView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('存在启用工作空间时应自动进入最近使用的空间', async () => {
    mocked.listWorkspaces.mockResolvedValue({ items: [{ id: 7 }] })

    render(EntryView)

    await waitFor(() => expect(mocked.replace).toHaveBeenCalledWith('/workspaces/7/home'))
  })

  it('没有启用工作空间时应展示创建引导，并在创建后进入新空间', async () => {
    mocked.listWorkspaces.mockResolvedValue({ items: [] })
    mocked.createWorkspace.mockResolvedValue({ id: 9 })

    render(EntryView)

    const createButton = await screen.findByRole('button', { name: '创建工作空间' })
    expect(screen.getByText('创建第一个工作空间')).toBeVisible()
    await fireEvent.click(createButton)
    await fireEvent.update(screen.getByLabelText(/工作空间名称/), '  产品演示  ')
    await fireEvent.update(screen.getByLabelText(/工作空间描述/), '  面向客户  ')
    await fireEvent.click(screen.getByRole('button', { name: '创建并进入' }))

    await waitFor(() => {
      expect(mocked.createWorkspace).toHaveBeenCalledWith({
        name: '产品演示',
        description: '面向客户',
        status: 'active',
      })
      expect(mocked.replace).toHaveBeenCalledWith('/workspaces/9/home')
    })
  })

  it('加载失败时应提供重试入口', async () => {
    mocked.listWorkspaces.mockRejectedValueOnce(new Error('network'))
    mocked.listWorkspaces.mockResolvedValueOnce({ items: [] })

    render(EntryView)

    await fireEvent.click(await screen.findByRole('button', { name: '重试' }))

    expect(await screen.findByText('创建第一个工作空间')).toBeVisible()
    expect(mocked.listWorkspaces).toHaveBeenCalledTimes(2)
  })
})
