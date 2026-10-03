/** 文件功能：验证模型管理表格与供应商管理表格的列渲染、徽章状态、快捷复制与行操作事件。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountAiModelTable from './AccountAiModelTable.vue'
import AccountAiProviderTable from './AccountAiProviderTable.vue'
import type { LlmConfigItem, LlmProviderConfigItem } from '@/types/api'

describe('AccountAiModelTable', () => {
  const writeTextMock = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: writeTextMock.mockResolvedValue(undefined),
      },
      writable: true,
      configurable: true,
    })
  })

  it('正确渲染模型信息、类型/能力徽章并支持点击复制与操作抛出', async () => {
    const mockModel: LlmConfigItem = {
      id: 1,
      name: '阿里v4flash',
      model_id: 'deepseek-v4-flash-0731',
      provider_config_id: 10,
      provider_config_name: '阿里token plan',
      provider_key: 'alibaba-token-plan-cn',
      provider_label: 'Alibaba Token Plan (China)',
      model_type: 'chat',
      scope: 'personal',
      owner_user_id: 1,
      editable: true,
      status: 'active',
      supports_image_input: true,
      reasoning_mode: 'enabled',
      reasoning_level: 'high',
      thinking_enabled: true,
      thinking_effort: 'high',
      context_window_tokens: 64000,
      required_model_context_tokens: 32000,
      request_output_tokens: 4096,
      runtime_headroom_tokens: 2000,
      compression_trigger_tokens: 50000,
      compression_target_tokens: 30000,
      budget_policy_version: '1.0',
      model_max_output_tokens: 8192,
      request_max_output_tokens: 4096,
      max_output_tokens: 4096,
      capability_source: 'built_in',
      capability_verified: true,
      model_capability_json: { supports_reasoning: true },
      effective_reasoning: {
        mode: 'enabled',
        requested_level: 'high',
        native_value: 'high',
        degraded: false,
        message: '',
      },
      history_token_ratio: 0.5,
      compression_target_ratio: 0.3,
      advanced_config_json: {},
      created_at: '2026-10-01T10:00:00Z',
      updated_at: '2026-10-03T09:00:00Z',
    }

    const mockArchivedModel: LlmConfigItem = {
      ...mockModel,
      id: 2,
      name: '停用模型',
      model_id: 'archived-model',
      status: 'archived',
    }

    const onView = vi.fn()
    const onEdit = vi.fn()
    const onDelete = vi.fn()

    render(AccountAiModelTable, {
      props: {
        items: [mockModel, mockArchivedModel],
        defaultModelId: 1,
        onView,
        onEdit,
        onDelete,
      },
    })

    // 检查模型名称与状态
    expect(screen.getByText('阿里v4flash')).toBeTruthy()
    expect(screen.getByText('当前默认')).toBeTruthy()
    expect(screen.getByText('启用')).toBeTruthy()
    expect(screen.getByText('停用模型')).toBeTruthy()
    expect(screen.getByText('停用')).toBeTruthy()

    // 检查模型 ID 与供应商
    expect(screen.getByText('deepseek-v4-flash-0731')).toBeTruthy()
    expect(screen.getAllByText('阿里token plan').length).toBe(2)

    // 检查类型与能力徽章
    expect(screen.getAllByText('Chat').length).toBe(2)
    expect(screen.getAllByText('支持推理').length).toBe(2)
    expect(screen.getAllByText('图片输入').length).toBe(2)

    // 检查复制按钮交互
    const copyButton = screen.getAllByTitle('复制模型 ID')[0]
    await fireEvent.click(copyButton)
    expect(writeTextMock).toHaveBeenCalledWith('deepseek-v4-flash-0731')

    // 检查操作按钮
    const viewButton = screen.getAllByRole('button', { name: '查看' })[0]
    const editButton = screen.getAllByRole('button', { name: '编辑' })[0]
    const deleteButton = screen.getAllByRole('button', { name: '删除' })[0]

    await fireEvent.click(viewButton)
    expect(onView).toHaveBeenCalledWith(mockModel)

    await fireEvent.click(editButton)
    expect(onEdit).toHaveBeenCalledWith(mockModel)

    await fireEvent.click(deleteButton)
    expect(onDelete).toHaveBeenCalledWith(mockModel)
  })
})

describe('AccountAiProviderTable', () => {
  const writeTextMock = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: writeTextMock.mockResolvedValue(undefined),
      },
      writable: true,
      configurable: true,
    })
  })

  it('正确渲染供应商信息、连接状态及更新时间回退，并支持行操作', async () => {
    const mockProvider: LlmProviderConfigItem = {
      id: 10,
      scope: 'personal',
      owner_user_id: 1,
      editable: true,
      name: '阿里云token-plan',
      provider_key: 'alibaba-token-plan-cn',
      provider_label: '阿里云百炼图片',
      provider_type: 'image_generation',
      base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      status: 'active',
      has_api_key: true,
      api_key_masked: 'sk-****',
      created_at: '2026-10-02T12:00:00+08:00',
      updated_at: null,
    }

    const onView = vi.fn()
    const onEdit = vi.fn()
    const onDelete = vi.fn()

    render(AccountAiProviderTable, {
      props: {
        items: [mockProvider],
        onView,
        onEdit,
        onDelete,
      },
    })

    // 检查配置名称与 key
    expect(screen.getByText('阿里云token-plan')).toBeTruthy()
    expect(screen.getByText('alibaba-token-plan-cn')).toBeTruthy()
    expect(screen.getByText('阿里云百炼图片')).toBeTruthy()
    expect(screen.getByText('https://dashscope.aliyuncs.com/compatible-mode/v1')).toBeTruthy()

    // 检查生图类型与个人范围徽章
    expect(screen.getByText('图片生成')).toBeTruthy()
    expect(screen.getByText('个人')).toBeTruthy()

    // 检查连接状态
    expect(screen.getByText('密钥已配置')).toBeTruthy()

    // 检查时间是否回退使用 created_at 而不是 '-'
    expect(screen.queryByText('-')).toBeNull()

    // 检查复制交互
    const copyButton = screen.getByTitle('复制 Provider Key')
    await fireEvent.click(copyButton)
    expect(writeTextMock).toHaveBeenCalledWith('alibaba-token-plan-cn')

    // 检查操作按钮
    const deleteButton = screen.getByRole('button', { name: '删除' })
    await fireEvent.click(deleteButton)
    expect(onDelete).toHaveBeenCalledWith(mockProvider)
  })
})
