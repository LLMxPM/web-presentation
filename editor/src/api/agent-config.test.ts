/**
 * 文件功能：验证智能体配置 API 路径和载荷，避免账户级配置接口漂移。
 */
import { describe, expect, it, vi } from 'vitest'

const { getMock, patchMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  patchMock: vi.fn(),
}))

vi.mock('@/api/http', () => ({
  http: {
    get: getMock,
    patch: patchMock,
  },
}))

import {
  listAgentCatalog,
  listAgentConfigs,
  updateAgentConfig,
  updateAgentToolConfig,
} from '@/api/agent-config'

describe('agent config api', () => {
  it('应读取智能体目录与用户配置', async () => {
    getMock.mockResolvedValue({ data: [] })

    await listAgentCatalog()
    await listAgentConfigs()

    expect(getMock).toHaveBeenNthCalledWith(1, '/ai/agent-catalog')
    expect(getMock).toHaveBeenNthCalledWith(2, '/ai/agent-configs')
  })

  it('应更新提示词与单个工具配置', async () => {
    patchMock.mockResolvedValue({ data: {} })

    await updateAgentConfig('agent-coordinator', { prompt_override: '新的提示词' })
    await updateAgentToolConfig('agent-coordinator', 'apply_page_edits', {
      enabled: false,
      description_override: '关闭页面写入',
    })

    expect(patchMock).toHaveBeenNthCalledWith(1, '/ai/agent-configs/agent-coordinator', {
      prompt_override: '新的提示词',
    })
    expect(patchMock).toHaveBeenNthCalledWith(2, '/ai/agent-configs/agent-coordinator/tools/apply_page_edits', {
      enabled: false,
      description_override: '关闭页面写入',
    })
  })
})
