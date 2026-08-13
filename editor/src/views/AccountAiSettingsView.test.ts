/**
 * 文件功能：验证统一 AI 设置页的智能体模型绑定、提示词、工具配置与模型交互。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountAiSettingsView from '@/views/AccountAiSettingsView.vue'

const listLlmProvidersMock = vi.fn()
const listLlmProviderConfigsMock = vi.fn()
const listLlmConfigsMock = vi.fn()
const listLlmSlotsMock = vi.fn()
const createLlmProviderConfigMock = vi.fn()
const updateLlmProviderConfigMock = vi.fn()
const deleteLlmProviderConfigMock = vi.fn()
const createLlmConfigMock = vi.fn()
const updateLlmConfigMock = vi.fn()
const deleteLlmConfigMock = vi.fn()
const updateLlmSlotBindingMock = vi.fn()
const resolveLlmModelCapabilityMock = vi.fn()
const listChatCatalogModelsMock = vi.fn()
const getModelCatalogSyncStateMock = vi.fn()
const refreshModelCatalogMock = vi.fn()
const listAgentCatalogMock = vi.fn()
const listAgentConfigsMock = vi.fn()
const updateAgentConfigMock = vi.fn()
const updateAgentToolConfigMock = vi.fn()
const messageSuccessMock = vi.fn()
const messageErrorMock = vi.fn()
const createConfirmMock = vi.fn()
const routerReplaceMock = vi.fn()
const routeQuery: Record<string, string> = {}

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery }),
  useRouter: () => ({ replace: (...args: unknown[]) => routerReplaceMock(...args) }),
  onBeforeRouteLeave: vi.fn(),
}))

vi.mock('@/api/llm', () => ({
  listLlmProviders: () => listLlmProvidersMock(),
  listLlmProviderConfigs: () => listLlmProviderConfigsMock(),
  listLlmConfigs: () => listLlmConfigsMock(),
  listLlmSlots: () => listLlmSlotsMock(),
  createLlmProviderConfig: (...args: unknown[]) => createLlmProviderConfigMock(...args),
  updateLlmProviderConfig: (...args: unknown[]) => updateLlmProviderConfigMock(...args),
  deleteLlmProviderConfig: (...args: unknown[]) => deleteLlmProviderConfigMock(...args),
  createLlmConfig: (...args: unknown[]) => createLlmConfigMock(...args),
  updateLlmConfig: (...args: unknown[]) => updateLlmConfigMock(...args),
  deleteLlmConfig: (...args: unknown[]) => deleteLlmConfigMock(...args),
  updateLlmSlotBinding: (...args: unknown[]) => updateLlmSlotBindingMock(...args),
  resolveLlmModelCapability: (...args: unknown[]) => resolveLlmModelCapabilityMock(...args),
  listChatCatalogModels: (...args: unknown[]) => listChatCatalogModelsMock(...args),
  getModelCatalogSyncState: () => getModelCatalogSyncStateMock(),
  refreshModelCatalog: () => refreshModelCatalogMock(),
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
  createConfirm: (...args: unknown[]) => createConfirmMock(...args),
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
    system_prompt: '平台默认提示词',
    default_prompt: '平台默认提示词',
    prompt_override: null,
    effective_prompt: '平台默认提示词',
    prompt_customized: false,
    enabled_tool_count: 1,
    disabled_tool_count: 0,
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

function createLlmConfigItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    scope: 'personal',
    owner_user_id: 1,
    editable: true,
    name: '总控模型',
    provider_config_id: 10,
    provider_config_name: 'OpenAI 工作账号',
    provider_key: 'openai',
    provider_label: 'OpenAI',
    model_id: 'gpt-4.1-mini',
    thinking_enabled: true,
    thinking_effort: 'medium',
    reasoning_mode: 'enabled',
    reasoning_level: 'medium',
    supports_image_input: true,
    context_window_tokens: 128000,
    model_max_output_tokens: 32000,
    request_max_output_tokens: 25600,
    max_output_tokens: 28000,
    history_token_ratio: 0.5,
    compression_target_ratio: 0.1,
    advanced_config_json: {},
    status: 'active',
    created_at: '2026-04-18T10:00:00+08:00',
    updated_at: '2026-04-18T10:00:00+08:00',
    ...overrides,
  }
}

function createProviderConfigItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 10,
    scope: 'personal',
    owner_user_id: 1,
    editable: true,
    name: 'OpenAI 工作账号',
    provider_key: 'openai',
    provider_label: 'OpenAI',
    base_url: 'https://api.openai.com/v1',
    status: 'active',
    has_api_key: true,
    api_key_masked: 'sk-t****test',
    created_at: '2026-04-18T10:00:00+08:00',
    updated_at: '2026-04-18T10:00:00+08:00',
    ...overrides,
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
        UiSelect: {
          props: ['modelValue', 'options'],
          emits: ['update:modelValue'],
          template: `<select :value="modelValue" @change="$emit('update:modelValue', $event.target.value)"><option v-for="option in options" :key="String(option.value)" :value="option.value">{{ option.label }}</option></select>`,
        },
        UiCombobox: {
          props: ['modelValue', 'options', 'placeholder', 'clearable', 'size', 'disabled'],
          emits: ['update:modelValue'],
          template: `<div data-testid="combobox-stub"><span>{{ modelValue != null ? (options.find(o => o.value === modelValue)?.label ?? modelValue) : (placeholder || '请选择') }}</span></div>`,
        },
      },
    },
  }
}

async function waitForSettingsReady() {
  await waitFor(() => {
    expect(screen.getByRole('heading', { name: '内容助手' })).toBeTruthy()
    expect(screen.getByText('内容生成')).toBeTruthy()
    expect(screen.getAllByText('总控模型').length).toBeGreaterThan(0)
  })
}

function getDesktopNavigationButton(name: RegExp) {
  return within(screen.getByRole('navigation', { name: 'AI 设置模块' })).getByRole('button', { name })
}

describe('AccountAiSettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const key of Object.keys(routeQuery)) delete routeQuery[key]
    routerReplaceMock.mockImplementation(async ({ query }: { query: Record<string, string> }) => {
      Object.assign(routeQuery, query)
    })
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
    listChatCatalogModelsMock.mockResolvedValue([])
    getModelCatalogSyncStateMock.mockResolvedValue({
      catalog_version: 'test-catalog',
      last_attempt_at: '2026-08-12T10:00:00Z',
      last_success_at: '2026-08-12T10:00:00Z',
      last_error: null,
      syncing: false,
    })
    refreshModelCatalogMock.mockResolvedValue({
      catalog_version: 'test-catalog',
      last_attempt_at: '2026-08-12T10:00:00Z',
      last_success_at: '2026-08-12T10:00:00Z',
      last_error: null,
      syncing: false,
    })
    listLlmProviderConfigsMock.mockResolvedValue([createProviderConfigItem()])
    listLlmConfigsMock.mockResolvedValue([createLlmConfigItem()])
    listLlmSlotsMock.mockResolvedValue([
      {
        slot: 'agent_coordinator',
        slot_label: '总控智能体',
        llm_config_id: 1,
        llm_config_name: '总控模型',
        provider_config_id: 10,
        provider_config_name: 'OpenAI 工作账号',
        provider_key: 'openai',
        provider_label: 'OpenAI',
        model_id: 'gpt-4.1-mini',
        binding_ready: true,
        supports_image_input: true,
        inherited_from_global: false,
      },
    ])
    createLlmProviderConfigMock.mockImplementation(async (payload: Record<string, unknown>) => createProviderConfigItem({
      id: 20,
      owner_user_id: payload.scope === 'global' ? null : 1,
      ...payload,
      provider_label: payload.provider_key === 'openai' ? 'OpenAI' : String(payload.provider_key ?? ''),
      has_api_key: Boolean(payload.api_key),
      api_key_masked: payload.api_key ? 'sk-n****new' : null,
      status: 'active',
    }))
    updateLlmProviderConfigMock.mockImplementation(async (id: number, payload: Record<string, unknown>) => createProviderConfigItem({
      id,
      ...payload,
      has_api_key: true,
    }))
    deleteLlmProviderConfigMock.mockResolvedValue({ message: '供应商已删除。' })
    listAgentCatalogMock.mockResolvedValue([agentConfig])
    listAgentConfigsMock.mockResolvedValue([agentConfig])
    createLlmConfigMock.mockImplementation(async (payload: Record<string, unknown>) => createLlmConfigItem({
      id: 2,
      owner_user_id: payload.scope === 'global' ? null : 1,
      ...payload,
      provider_config_name: 'OpenAI 工作账号',
      provider_key: 'openai',
      provider_label: 'OpenAI',
      status: 'active',
    }))
    updateLlmConfigMock.mockImplementation(async (id: number, payload: Record<string, unknown>) => createLlmConfigItem({
      id,
      ...payload,
    }))
    deleteLlmConfigMock.mockResolvedValue({ message: '模型已删除。' })
    updateLlmSlotBindingMock.mockResolvedValue(undefined)
    updateAgentConfigMock.mockResolvedValue(agentConfig)
    updateAgentToolConfigMock.mockResolvedValue(agentConfig)
    createConfirmMock.mockResolvedValue(true)
    resolveLlmModelCapabilityMock.mockResolvedValue({
      source: 'built_in',
      verified: true,
      profile_key: 'openai:gpt-4.1',
      profile_version: 1,
      context_window_tokens: 1_000_000,
      model_max_output_tokens: 32_768,
      request_max_output_tokens: 32_768,
      supports_image_input: true,
      supports_reasoning: true,
      supports_explicit_disable: true,
      default_level: 'medium',
      level_mapping: { low: 'low', medium: 'medium', high: 'high', max: 'high' },
      warnings: [],
    })
  })

  it('默认进入内容助手并使用管理后台导航', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitForSettingsReady()
    expect(screen.getByTestId('account-ai-settings-admin')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'AI 设置' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: '内容助手' })).toBeTruthy()
    expect(screen.getByRole('tab', { name: '模型与视觉能力' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('button', { name: /内容助手/ })).toHaveAttribute('aria-current', 'page')
    expect(routerReplaceMock).toHaveBeenCalledWith({ query: { section: 'assistant', tab: 'models' } })
  })

  it('应以固定槽位表格保存内容模型绑定', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getAllByText('总控模型').length).toBeGreaterThan(0)
    })
    const contentRow = screen.getByRole('row', { name: /内容生成.*总控模型/ })
    await fireEvent.click(within(contentRow).getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(updateLlmSlotBindingMock).toHaveBeenCalledWith('agent_coordinator', 1, 'personal')
    })

  })

  it('应保存提示词并在未保存时保护模块切换', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())
    await waitForSettingsReady()

    await fireEvent.mouseDown(screen.getByRole('tab', { name: '提示词' }), { button: 0 })
    const prompt = await screen.findByPlaceholderText('输入内容助手提示词')
    await fireEvent.update(prompt, '新的内容助手提示词')
    await fireEvent.click(screen.getByRole('button', { name: '保存提示词' }))

    await waitFor(() => {
      expect(updateAgentConfigMock).toHaveBeenCalledWith('agent-coordinator', {
        prompt_override: '新的内容助手提示词',
      })
    })

    await fireEvent.update(prompt, '尚未保存的提示词')
    await fireEvent.click(getDesktopNavigationButton(/聊天模型/))
    expect(createConfirmMock).toHaveBeenCalledWith(
      '当前内容助手配置有未保存修改，确定放弃吗？',
      '放弃未保存修改',
    )
  })

  it('模型管理应使用表格，并在宽版弹窗完成详情与创建', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())
    await waitForSettingsReady()

    await fireEvent.click(getDesktopNavigationButton(/聊天模型/))
    await waitFor(() => expect(screen.getByRole('heading', { name: '聊天模型' })).toBeTruthy())
    expect(screen.getByRole('columnheader', { name: '模型 ID' })).toBeTruthy()
    expect(screen.getByRole('row', { name: /总控模型.*gpt-4.1-mini/ })).toBeTruthy()

    await fireEvent.click(screen.getByRole('button', { name: '新建模型' }))
    expect(await screen.findByRole('heading', { name: '新建模型' })).toBeTruthy()
    expect(screen.getByText('选择供应商模型，并配置模型能力与高级参数。')).toBeTruthy()
    expect(screen.getByRole('button', { name: '关闭新建模型' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '取消' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '创建模型' })).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '关闭新建模型' }))
    expect(createConfirmMock).not.toHaveBeenCalled()
    await fireEvent.click(screen.getByRole('button', { name: '新建模型' }))
    expect(screen.getByLabelText(/^模型名称/)).toBeTruthy()
    expect(screen.getByText('Models.dev 模型')).toBeTruthy()
    expect(screen.getByText('配置域')).toBeTruthy()
    expect(screen.queryByText('全部模型类型')).toBeNull()
    expect(screen.queryByText('平台会自动预留 20% 输出空间')).toBeNull()
    expect(screen.getByText(/能力默认来自 Models\.dev/)).toBeTruthy()
    expect(screen.queryByText('推理模式')).toBeNull()
  })

  it('供应商管理应使用表格，并支持详情进入紧凑编辑表单', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())
    await waitForSettingsReady()

    await fireEvent.click(getDesktopNavigationButton(/聊天模型/))
    await waitFor(() => expect(screen.getByRole('heading', { name: '聊天模型' })).toBeTruthy())
    expect(screen.getByRole('columnheader', { name: '连接状态' })).toBeTruthy()

    await fireEvent.click(screen.getByRole('button', { name: '连接供应商' }))
    expect(await screen.findByRole('heading', { name: '新建供应商' })).toBeTruthy()
    expect(screen.getByText('配置供应商协议、服务地址和访问凭证。')).toBeTruthy()
    expect(screen.getByRole('button', { name: '关闭新建供应商' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '取消' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '创建供应商' })).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '关闭新建供应商' }))
    expect(createConfirmMock).not.toHaveBeenCalled()

    const providerRow = screen.getByRole('row', { name: /OpenAI 工作账号.*OpenAI/ })
    await fireEvent.click(within(providerRow).getByRole('button', { name: '查看' }))
    expect(await screen.findByRole('heading', { name: 'OpenAI 工作账号' })).toBeTruthy()
    await fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    expect(screen.getByLabelText(/^配置名称/)).toBeTruthy()
    expect(screen.getByLabelText(/^Base URL/)).toBeTruthy()
    expect(screen.getByLabelText(/^API Key/)).toBeTruthy()
    expect(screen.queryByText('供应商身份')).toBeNull()
    expect(screen.queryByText('目录能力')).toBeNull()
  })

  it('聊天与图片页面应隔离列表、筛选和新建表单域', async () => {
    listLlmProviderConfigsMock.mockResolvedValue([
      createProviderConfigItem(),
      createProviderConfigItem({ id: -20, name: '图片专用连接', provider_key: 'openai_image', provider_label: 'OpenAI Images', provider_type: 'image_generation' }),
    ])
    listLlmConfigsMock.mockResolvedValue([
      createLlmConfigItem(),
      createLlmConfigItem({ id: -2, name: '图片专用模型', provider_config_id: -20, provider_config_name: '图片专用连接', provider_key: 'openai_image', provider_label: 'OpenAI Images', model_id: 'gpt-image-2', model_type: 'image_generation' }),
    ])
    render(AccountAiSettingsView, createTestingRenderOptions())
    await waitForSettingsReady()

    await fireEvent.click(getDesktopNavigationButton(/图片生成/))
    await waitFor(() => expect(screen.getByRole('heading', { name: '图片生成' })).toBeTruthy())
    const imageModelRow = screen.getByRole('row', { name: /图片专用模型.*gpt-image-2/ })
    const imageProviderRow = screen.getByRole('row', { name: /图片专用连接.*OpenAI Images/ })
    expect(imageModelRow.compareDocumentPosition(imageProviderRow) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByRole('row', { name: /总控模型.*gpt-4.1-mini/ })).toBeNull()
    expect(screen.queryByText('全部供应商类型')).toBeNull()

    await fireEvent.click(screen.getByRole('button', { name: '新建模型' }))
    expect(await screen.findByText('图片生成模型')).toBeTruthy()
    expect(screen.queryByText('聊天 / 图片理解模型')).toBeNull()
  })

  it('工具配置应使用筛选表格并展示完整只读契约', async () => {
    render(AccountAiSettingsView, createTestingRenderOptions())
    await waitForSettingsReady()

    await fireEvent.mouseDown(screen.getByRole('tab', { name: '工具配置' }), { button: 0 })
    expect(await screen.findByRole('columnheader', { name: '风险' })).toBeTruthy()
    const toolRow = screen.getByRole('row', { name: /应用页面 Edits.*页面写入/ })
    await fireEvent.click(within(toolRow).getByRole('button', { name: '配置' }))

    expect(await screen.findByRole('heading', { name: '应用页面 Edits' })).toBeTruthy()
    expect(screen.getByText('Agent 完整说明')).toBeTruthy()
    expect(screen.getByText('参数 JSON Schema')).toBeTruthy()
    expect(screen.getByText('调用示例')).toBeTruthy()
    expect(screen.getByText('返回示例')).toBeTruthy()

    const checkbox = screen.getByRole('checkbox')
    await fireEvent.click(checkbox)
    await fireEvent.click(screen.getByRole('button', { name: '保存工具' }))
    await waitFor(() => {
      expect(updateAgentToolConfigMock).toHaveBeenCalledWith('agent-coordinator', 'apply_page_edits', {
        enabled: false,
        description_override: null,
        instructions_override: null,
      })
    })
  })
})
