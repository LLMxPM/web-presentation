/** 文件功能：验证明确选择空间、默认只读、批准/拒绝、过期与 HTTP 失败的可操作边界。 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { OAuthConsentView as ConsentData } from '@/types/api.generated'
import OAuthConsentView from '@/views/OAuthConsentView.vue'

const mocks = vi.hoisted(() => ({ begin: vi.fn(), decide: vi.fn(), navigate: vi.fn(), query: { authorization_query: 'original-query' } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: mocks.query }) }))
vi.mock('@/api/oauth', () => ({ beginOAuthConsent: mocks.begin, decideOAuthConsent: mocks.decide }))
vi.mock('@/utils/oauth', async original => ({
  ...await original<typeof import('@/utils/oauth')>(), navigateOAuthCallback: mocks.navigate,
}))

/** 保留真实生成 DTO 形状，nonce 不属于前端路由参数。 */
function consentData(changes: Partial<ConsentData> = {}): ConsentData {
  return {
    request_id: 'request-1', csrf_token: 'test-nonce', client_name: 'ChatGPT',
    resource: 'https://mcp.test/mcp', expires_at: new Date(Date.now() + 60000).toISOString(),
    workspaces: [{ id: 7, name: '产品文稿' }],
    scopes: [{ scope: 'page:read', operations: ['读取页面源码'] }, { scope: 'page:write', operations: ['创建、更新与归档页面'] }],
    ...changes,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.query.authorization_query = 'original-query'
  mocks.begin.mockResolvedValue(consentData())
  mocks.decide.mockResolvedValue({ redirect_uri: 'https://chatgpt.com/connector_platform_oauth_redirect?code=once' })
})

/** 挂载独立确认页，用户身份依赖已有平台 Pinia，测试不绕过选择按钮。 */
function mount() {
  return render(OAuthConsentView, { global: { plugins: [createPinia()] } })
}

describe('ChatGPT 授权确认', () => {
  it('必须选择具体空间，默认只读并明确批准后才提交', async () => {
    mount()
    const approve = await screen.findByRole('button', { name: '授权并返回 ChatGPT' })
    expect(approve).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: '读取页面' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: '管理页面' })).not.toBeChecked()
    expect(mocks.decide).not.toHaveBeenCalled()
    await fireEvent.click(screen.getByRole('checkbox', { name: '产品文稿' }))
    expect(approve).not.toBeDisabled()
    await fireEvent.click(approve)
    await waitFor(() => expect(mocks.decide).toHaveBeenCalledWith('request-1', {
      csrf_token: 'test-nonce', approved: true, scopes: ['page:read'], workspace_ids: [7],
    }))
    expect(mocks.begin).toHaveBeenCalledWith({ authorization_query: 'original-query' })
    expect(mocks.navigate).toHaveBeenCalledOnce()
  })

  it('管理权限只能通过用户额外勾选进入确认载荷', async () => {
    mount()
    await screen.findByRole('button', { name: '授权并返回 ChatGPT' })
    await fireEvent.click(screen.getByRole('checkbox', { name: '产品文稿' }))
    await fireEvent.click(screen.getByRole('checkbox', { name: '管理页面' }))
    await fireEvent.click(screen.getByRole('button', { name: '授权并返回 ChatGPT' }))
    await waitFor(() => expect(mocks.decide.mock.calls[0]?.[1].scopes).toEqual(['page:read', 'page:write']))
  })

  it('拒绝无需选择空间，明确返回拒绝决定', async () => {
    mount()
    await fireEvent.click(await screen.findByRole('button', { name: '拒绝' }))
    await waitFor(() => expect(mocks.decide).toHaveBeenCalledWith('request-1', {
      csrf_token: 'test-nonce', approved: false, scopes: [], workspace_ids: [],
    }))
  })

  it('过期请求不能提交批准', async () => {
    mocks.begin.mockResolvedValue(consentData({ expires_at: new Date(Date.now() - 1000).toISOString() }))
    mount()
    expect(await screen.findByRole('button', { name: '授权并返回 ChatGPT' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('已过期')
    expect(mocks.decide).not.toHaveBeenCalled()
  })

  it('缺少原始请求时不创建确认', async () => {
    mocks.query.authorization_query = ''
    mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('缺少授权请求')
    expect(mocks.begin).not.toHaveBeenCalled()
  })

  it('服务端拒绝时显示错误且不导航', async () => {
    mocks.decide.mockRejectedValue(new Error('服务端拒绝本次授权'))
    mount()
    await fireEvent.click(await screen.findByRole('button', { name: '拒绝' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('服务端拒绝本次授权')
    expect(mocks.navigate).not.toHaveBeenCalled()
  })

  it('离开确认页后迟到的响应不能导航浏览器', async () => {
    let complete: (value: { redirect_uri: string }) => void = () => {}
    mocks.decide.mockImplementation(() => new Promise(resolve => { complete = resolve }))
    const instance = mount()
    await fireEvent.click(await screen.findByRole('button', { name: '拒绝' }))
    instance.unmount()
    complete({ redirect_uri: 'https://chatgpt.com/connector_platform_oauth_redirect?code=once' })
    await Promise.resolve()
    expect(mocks.navigate).not.toHaveBeenCalled()
  })
})
