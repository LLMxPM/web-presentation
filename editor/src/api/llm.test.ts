/**
 * 文件功能：验证拆分模型配置兼容门面的目录投影和必填规则。
 */
import { describe, expect, it, vi } from 'vitest'

const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }))

vi.mock('@/api/http', () => ({
  http: {
    get: getMock,
  },
}))

import { listLlmProviders } from '@/api/llm'

describe('llm catalog facade', () => {
  it('目录已有默认地址时不要求用户重复填写 Base URL', async () => {
    getMock
      .mockResolvedValueOnce({
        data: [{
          provider_key: 'opencode',
          name: 'OpenCode',
          api_url: 'https://api.opencode.ai/v1',
          docs_url: null,
          default_base_url: 'https://api.opencode.ai/v1',
          protocol_key: 'openai_compatible_chat',
          catalog_version: 'test',
        }],
      })
      .mockResolvedValueOnce({ data: [] })

    const providers = await listLlmProviders()

    expect(providers.find(item => item.provider_key === 'opencode')?.requires_base_url).toBe(false)
    expect(providers.find(item => item.provider_key === 'custom-openai-compatible')?.requires_base_url).toBe(true)
  })
})
