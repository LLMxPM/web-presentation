/**
 * 文件功能：验证统一 AI 设置页的智能体模型绑定、提示词、工具配置与模型交互。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountAiSettingsView from '@/views/AccountAiSettingsView.vue'

const listLlmProvidersMock = vi.fn()
const listLlmConfigsMock = vi.fn()
const listLlmSlotsMock = vi.fn()
const createLlmConfigMock = vi.fn()
const updateLlmConfigMock = vi.fn()
const updateLlmSlotBindingMock = vi.fn()
const listAgentCatalogMock = vi.fn()
const listAgentConfigsMock = vi.fn()
const updateAgentConfigMock = vi.fn()
const updateAgentToolConfigMock = vi.fn()
const messageSuccessMock = vi.fn()
const messageErrorMock = vi.fn()

vi.mock('@/api/llm', () => ({
  listLlmProviders: () => listLlmProvidersMock(),
  listLlmConfigs: () => listLlmConfigsMock(),
  listLlmSlots: () => listLlmSlotsMock(),
  createLlmConfig: (...args: unknown[]) => createLlmConfigMock(...args),
  updateLlmConfig: (...args: unknown[]) => updateLlmConfigMock(...args),
  updateLlmSlotBinding: (...args: unknown[]) => updateLlmSlotBindingMock(...args),
}))

vi.mock('@/api/agent-config', () => ({
  listAgentCatalog: () => listAgentCatalogMock(),
  listAgentConfigs: () => listAgentConfigsMock(),
  updateAgentConfig: (...args: unknown[]) => updateAgentConfigMock(...args),
  updateAgentToolConfig: (...args: unknown[]) => updateAgentToolConfigMock(...args),
}))

vi.mock('@/utils/message', () => ({
  Message: {
    success: (...args: unknown[]) => messageSuccessMock(...args),
    error: (...args: unknown[]) => messageErrorMock(...args),
  },
}))

function createAgentGuide(toolName: string, responseExample: unknown | null = null) {
  return {
    tool_name: toolName,
    effective_description: `${toolName} 当前生效说明。`,
    system_description: `${toolName} 系统默认说明。`,
    instructions: null,
    parameters_schema: {
      type: 'object',
      properties: {
        edits: { type: 'array' },
        base_version_no: { type: 'integer' },
      },
      required: ['edits', 'base_version_no'],
    },
    call_example: {
      tool_name: toolName,
      arguments: {
        edits: [],
        base_version_no: 1,
      },
    },
    response_example: responseExample,
    response_notes: null,
    required_context_fields: ['page_id'],
    runtime_disclosure_groups: ['page_write'],
    requires_confirmation: false,
    risk_level: 'write',
  }
}

function createAgentConfig() {
  return {
    id: 'agent-coordinator',
    name: '内容助手',
    icon: 'content-spark',
    summary: '内容助手 Team 入口。',
    default_session_name: '内容助手会话',
    capabilities: ['页面/项目处理', '组件助手调度', '资源助手调度'],
    scope_type: 'workspace',
    entry_kind: 'team',
    llm_slot: 'agent_coordinator',
    default_description: '统一智能体。',
    description: '统一智能体。',
    description_override: null,
    description_customized: false,
    role: '理解用户目标。',
    system_prompt: '系统底线提示词',
    default_prompt: '',
    prompt_override: null,
    effective_prompt: '',
    prompt_customized: false,
    enabled_tool_count: 1,
    disabled_tool_count: 0,
    team_members: [
      {
        id: 'component-manager',
        name: '组件助手',
        icon: 'component-blocks',
        default_description: '管理工作空间组件库。',
        description: '管理工作空间组件库。',
        description_override: null,
        description_customized: false,
      },
    ],
    tool_groups: [
      {
        key: 'page_write',
        label: '页面写入',
        description: '页面写入工具。',
        tools: [
          {
            key: 'apply_page_edits',
            label: '应用页面 Edits',
            group_key: 'page_write',
            group_label: '页面写入',
            default_description: '应用页面 Edits。',
            description: '应用页面 Edits。',
            description_override: null,
            default_instructions: null,
            instructions: null,
            instructions_override: null,
            enabled: true,
            configurable: true,
            requires_confirmation: true,
            risk_level: 'danger',
            agent_guide: createAgentGuide('apply_page_edits', {
              success: true,
              version_no: 2,
            }),
          },
          {
            key: 'get_current_scope_summary',
            label: '读取当前范围',
            group_key: 'page_write',
            group_label: '页面写入',
            default_description: '读取当前范围。',
            description: '读取当前范围。',
            description_override: null,
            default_instructions: null,
            instructions: null,
            instructions_override: null,
            enabled: true,
            configurable: false,
            requires_confirmation: false,
            risk_level: 'system',
            agent_guide: createAgentGuide('get_current_scope_summary', null),
          },
        ],
      },
    ],
  }
}

function createTestingRenderOptions() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return {
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient }] as [typeof VueQueryPlugin, { queryClient: QueryClient }],
        createPinia(),
      ],
      stubs: {
        teleport: true,
      },
    },
  }
}

describe('AccountAiSettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    const agentConfig = createAgentConfig()
    listLlmProvidersMock.mockResolvedValue([
      {
        provider_key: 'openai',
        label: 'OpenAI',
        provider_adapter: 'pydantic_ai.models.openai.OpenAIChatModel',
        docs_url: 'https://pydantic.dev/docs/ai/models/openai/',
        supports_base_url: true,
        supports_api_key: true,
        supports_thinking: true,
        thinking_mode: 'openai_reasoning',
        default_base_url: 'https://api.openai.com/v1',
        default_model_id: null,
        default_thinking_enabled: false,
        default_thinking_effort: 'medium',
        default_context_window_tokens: null,
        default_max_output_tokens: null,
        default_supports_image_input: false,
        thinking_effort_options: ['low', 'medium', 'high'],
        advanced_json_hint: {},
      },
    ])
    listLlmConfigsMock.mockResolvedValue([
      {
        id: 1,
        scope: 'personal',
        owner_user_id: 1,
        editable: true,
        name: '总控模型',
        provider_key: 'openai',
        provider_label: 'OpenAI',
        model_id: 'gpt-4.1-mini',
        base_url: 'https://api.openai.com/v1',
        thinking_enabled: true,
        thinking_effort: 'medium',
        supports_image_input: true,
        context_window_tokens: 128000,
        max_output_tokens: 32000,
        history_token_ratio: 0.5,
        compression_target_ratio: 0.1,
        advanced_config_json: {},
        status: 'active',
        has_api_key: true,
        api_key_masked: 'sk-t****test',
        created_at: '2026-04-18T10:00:00+08:00',
        updated_at: '2026-04-18T10:00:00+08:00',
      },
    ])
    listLlmSlotsMock.mockResolvedValue([
      {
        slot: 'agent_coordinator',
        slot_label: '总控智能体',
        llm_config_id: 1,
        llm_config_name: '总控模型',
        provider_key: 'openai',
        provider_label: 'OpenAI',
        model_id: 'gpt-4.1-mini',
        binding_ready: true,
        supports_image_input: true,
        inherited_from_global: false,
      },
    ])
    listAgentCatalogMock.mockResolvedValue([agentConfig])
    listAgentConfigsMock.mockResolvedValue([agentConfig])
    createLlmConfigMock.mockResolvedValue({ id: 2, name: '新的模型' })
    updateLlmConfigMock.mockResolvedValue(undefined)
    updateLlmSlotBindingMock.mockResolvedValue(undefined)
    updateAgentConfigMock.mockResolvedValue(agentConfig)
    updateAgentToolConfigMock.mockResolvedValue(agentConfig)
  })

  it('应展示统一 AI 设置，并在智能体详情中保存模型绑定、提示词和工具配置', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('AI 设置')).toBeTruthy()
      expect(screen.getAllByText('工具').length).toBeGreaterThan(0)
      expect(screen.getAllByText('内容助手').length).toBeGreaterThan(0)
      expect(screen.getAllByText('总控模型').length).toBeGreaterThan(0)
    })

    await fireEvent.click(screen.getByRole('button', { name: '保存模型绑定' }))
    await waitFor(() => {
      expect(updateLlmSlotBindingMock).toHaveBeenCalledWith('agent_coordinator', 1, 'personal')
    })

    await fireEvent.update(screen.getByPlaceholderText('输入当前账号下的业务补充提示词'), '新的业务提示词')
    await fireEvent.click(screen.getByRole('button', { name: '保存提示词' }))
    await waitFor(() => {
      expect(updateAgentConfigMock).toHaveBeenCalledWith('agent-coordinator', {
        prompt_override: '新的业务提示词',
      })
    })

    await fireEvent.update(screen.getByPlaceholderText('管理工作空间组件库。'), '新的组件助手成员描述')
    await fireEvent.click(screen.getByRole('button', { name: '保存描述' }))
    await waitFor(() => {
      expect(updateAgentConfigMock).toHaveBeenCalledWith('component-manager', {
        description_override: '新的组件助手成员描述',
      })
    })

    await fireEvent.click(screen.getByText('页面写入'))
    await fireEvent.click(screen.getByRole('checkbox'))
    await fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(updateAgentToolConfigMock).toHaveBeenCalledWith('agent-coordinator', 'apply_page_edits', {
        enabled: false,
        description_override: null,
        instructions_override: null,
      })
      expect(messageSuccessMock).toHaveBeenCalled()
    })
  })

  it('应以卡片管理模型，并支持归档和创建', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('页面写入')).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '模型' }))
    await waitFor(() => {
      expect(screen.getByText('gpt-4.1-mini')).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: /总控模型/ }))
    await fireEvent.click(screen.getByRole('button', { name: '归档模型' }))
    await waitFor(() => {
      expect(updateLlmConfigMock).toHaveBeenCalledWith(1, { status: 'archived' })
    })

    expect(screen.getAllByRole('button', { name: '新建模型' })).toHaveLength(1)
    await fireEvent.click(screen.getByRole('button', { name: '新建模型' }))
    await fireEvent.update(screen.getByPlaceholderText('例如：总控默认模型'), '新的模型')
    await fireEvent.update(screen.getByPlaceholderText('例如：gpt-4.1-mini'), 'gpt-4.1')
    await fireEvent.click(screen.getByRole('button', { name: '创建模型' }))

    await waitFor(() => {
      expect(createLlmConfigMock).toHaveBeenCalledWith({
        name: '新的模型',
        scope: 'personal',
        provider_key: 'openai',
        model_id: 'gpt-4.1',
        base_url: 'https://api.openai.com/v1',
        api_key: null,
        thinking_enabled: false,
        thinking_effort: 'medium',
        supports_image_input: false,
        context_window_tokens: 128000,
        max_output_tokens: 32000,
        history_token_ratio: 0.5,
        compression_target_ratio: 0.1,
        advanced_config_json: {},
      })
    })
  })

  it('新建模型应优先默认选择 DeepSeek 供应商', async () => {
    listLlmProvidersMock.mockResolvedValue([
      {
        provider_key: 'openai',
        label: 'OpenAI',
        provider_adapter: 'pydantic_ai.models.openai.OpenAIChatModel',
        docs_url: 'https://pydantic.dev/docs/ai/models/openai/',
        supports_base_url: true,
        supports_api_key: true,
        supports_thinking: true,
        thinking_mode: 'openai_reasoning',
        default_base_url: 'https://api.openai.com/v1',
        default_model_id: null,
        default_thinking_enabled: false,
        default_thinking_effort: 'medium',
        default_context_window_tokens: null,
        default_max_output_tokens: null,
        default_supports_image_input: false,
        thinking_effort_options: ['low', 'medium', 'high'],
        advanced_json_hint: {},
      },
      {
        provider_key: 'deepseek',
        label: 'DeepSeek',
        provider_adapter: 'pydantic_ai.providers.deepseek.DeepSeekProvider',
        docs_url: 'https://pydantic.dev/docs/ai/models/openai/',
        supports_base_url: true,
        supports_api_key: true,
        supports_thinking: true,
        thinking_mode: 'openai_extra_body_thinking',
        default_base_url: 'https://api.deepseek.com',
        default_model_id: 'deepseek-v4-pro',
        default_thinking_enabled: true,
        default_thinking_effort: 'high',
        default_context_window_tokens: 1000000,
        default_max_output_tokens: 384000,
        default_supports_image_input: false,
        thinking_effort_options: ['high', 'max'],
        advanced_json_hint: {},
      },
    ])
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('页面写入')).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '模型' }))
    await fireEvent.click(screen.getByRole('button', { name: '新建模型' }))
    await fireEvent.update(screen.getByPlaceholderText('例如：总控默认模型'), 'DeepSeek 模型')
    await fireEvent.click(screen.getByRole('button', { name: '创建模型' }))

    await waitFor(() => {
      expect(createLlmConfigMock).toHaveBeenCalled()
    })
    const payload = createLlmConfigMock.mock.calls[0][0] as Record<string, unknown>
    expect(payload.provider_key).toBe('deepseek')
    expect(payload.model_id).toBe('deepseek-v4-pro')
    expect(payload.base_url).toBe('https://api.deepseek.com')
    expect(payload.thinking_enabled).toBe(true)
    expect(payload.thinking_effort).toBe('high')
    expect(payload.context_window_tokens).toBe(1000000)
    expect(payload.max_output_tokens).toBe(384000)
  })

  it('新建 MiMo 模型时应只预填 Base URL，不预填模型和图片能力', async () => {
    listLlmProvidersMock.mockResolvedValue([
      {
        provider_key: 'mimo',
        label: 'MiMo',
        provider_adapter: 'pydantic_ai.providers.openai.OpenAIProvider',
        docs_url: 'https://platform.xiaomimimo.com/docs/zh-CN/quick-start/first-api-call',
        supports_base_url: true,
        supports_api_key: true,
        supports_thinking: true,
        thinking_mode: 'openai_extra_body_thinking',
        default_base_url: 'https://api.xiaomimimo.com/v1',
        default_model_id: null,
        default_thinking_enabled: false,
        default_thinking_effort: null,
        default_context_window_tokens: null,
        default_max_output_tokens: null,
        default_supports_image_input: false,
        thinking_effort_options: [],
        advanced_json_hint: {},
      },
    ])
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('页面写入')).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '模型' }))
    await fireEvent.click(screen.getByRole('button', { name: '新建模型' }))
    const modelIdInput = screen.getByPlaceholderText('例如：gpt-4.1-mini') as HTMLInputElement
    expect(modelIdInput.value).toBe('')

    await fireEvent.update(screen.getByPlaceholderText('例如：总控默认模型'), 'MiMo 模型')
    await fireEvent.update(modelIdInput, 'mimo-v2.5')
    await fireEvent.click(screen.getByRole('button', { name: '创建模型' }))

    await waitFor(() => {
      expect(createLlmConfigMock).toHaveBeenCalled()
    })
    const payload = createLlmConfigMock.mock.calls[0][0] as Record<string, unknown>
    expect(payload.provider_key).toBe('mimo')
    expect(payload.base_url).toBe('https://api.xiaomimimo.com/v1')
    expect(payload.supports_image_input).toBe(false)
    expect(payload.advanced_config_json).toEqual({})
  })

  it('OpenRouter 新建模型不应保存旧 app_name 高级配置', async () => {
    listLlmProvidersMock.mockResolvedValue([
      {
        provider_key: 'openrouter',
        label: 'OpenRouter',
        provider_adapter: 'pydantic_ai.models.openrouter.OpenRouterModel',
        docs_url: 'https://pydantic.dev/docs/ai/models/openrouter/',
        supports_base_url: true,
        supports_api_key: true,
        supports_thinking: true,
        thinking_mode: 'openai_reasoning',
        default_base_url: 'https://openrouter.ai/api/v1',
        default_model_id: null,
        default_thinking_enabled: false,
        default_thinking_effort: 'medium',
        default_context_window_tokens: null,
        default_max_output_tokens: null,
        default_supports_image_input: false,
        thinking_effort_options: ['low', 'medium', 'high'],
        advanced_json_hint: {},
      },
    ])
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('页面写入')).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '模型' }))
    await fireEvent.click(screen.getByRole('button', { name: '新建模型' }))
    await fireEvent.update(screen.getByPlaceholderText('例如：总控默认模型'), 'OpenRouter 模型')
    await fireEvent.update(screen.getByPlaceholderText('例如：gpt-4.1-mini'), 'openai/gpt-4.1-mini')
    await fireEvent.click(screen.getByRole('button', { name: '创建模型' }))

    await waitFor(() => {
      expect(createLlmConfigMock).toHaveBeenCalled()
    })
    const payload = createLlmConfigMock.mock.calls[0][0] as Record<string, unknown>
    expect(payload.provider_key).toBe('openrouter')
    expect(payload.base_url).toBe('https://openrouter.ai/api/v1')
    expect(payload.advanced_config_json).toEqual({})
  })

  it('编辑模型时 API Key 留空应保留原值', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('页面写入')).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '模型' }))
    await fireEvent.click(screen.getByRole('button', { name: /总控模型/ }))
    await fireEvent.click(screen.getByRole('button', { name: '保存模型' }))

    await waitFor(() => {
      expect(updateLlmConfigMock).toHaveBeenCalled()
    })
    const payload = updateLlmConfigMock.mock.calls[0][1] as Record<string, unknown>
    expect(payload).not.toHaveProperty('api_key')
    expect(payload.name).toBe('总控模型')
  })

  it('模型思考强度应允许输入供应商扩展值', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('页面写入')).toBeTruthy()
    })

    await fireEvent.click(screen.getByRole('button', { name: '模型' }))
    await fireEvent.click(screen.getByRole('button', { name: /总控模型/ }))
    await fireEvent.update(screen.getByPlaceholderText('例如：medium、high、xhigh、max'), 'xhigh')
    await fireEvent.click(screen.getByRole('button', { name: '保存模型' }))

    await waitFor(() => {
      expect(updateLlmConfigMock).toHaveBeenCalled()
    })
    const payload = updateLlmConfigMock.mock.calls[0][1] as Record<string, unknown>
    expect(payload.thinking_effort).toBe('xhigh')
  })

  it('应在工具详情中展示面向 Agent 的完整只读说明', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('页面写入')).toBeTruthy()
    })

    await fireEvent.click(screen.getByText('页面写入'))
    await fireEvent.click(screen.getByRole('button', { name: '编辑' }))

    await waitFor(() => {
      expect(screen.getByText('Agent 完整说明')).toBeTruthy()
      expect(screen.getByText('apply_page_edits 当前生效说明。')).toBeTruthy()
      expect(screen.getByText('参数 JSON Schema')).toBeTruthy()
      expect(screen.getByText('调用示例')).toBeTruthy()
      expect(screen.getByText('返回示例')).toBeTruthy()
      expect(screen.getAllByText(/version_no/).length).toBeGreaterThan(0)
    })

    await fireEvent.click(screen.getByRole('button', { name: '收起' }))
    await fireEvent.click(screen.getByRole('button', { name: '说明' }))

    await waitFor(() => {
      expect(screen.getByText('暂无返回示例')).toBeTruthy()
      expect(screen.getAllByText('系统工具').length).toBeGreaterThan(0)
    })
  })
})
