/**
 * 文件功能：验证个人设置拆分后的四个一级视图（模型连接、助手提示词、代码规范、工具配置）的渲染与交互。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountAiModelsView from '@/views/AccountAiModelsView.vue'
import AccountAiPromptView from '@/views/AccountAiPromptView.vue'
import AccountAiCodeStandardsView from '@/views/AccountAiCodeStandardsView.vue'
import AccountAiToolsView from '@/views/AccountAiToolsView.vue'

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
const listAgentConfigsMock = vi.fn()
const listAgentCodeStandardsMock = vi.fn()
const updateAgentConfigMock = vi.fn()
const updateAgentCodeStandardMock = vi.fn()
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
  listAgentConfigs: () => listAgentConfigsMock(),
  listAgentCodeStandards: (...args: unknown[]) => listAgentCodeStandardsMock(...args),
  updateAgentConfig: (...args: unknown[]) => updateAgentConfigMock(...args),
  updateAgentCodeStandard: (...args: unknown[]) => updateAgentCodeStandardMock(...args),
  updateAgentToolConfig: (...args: unknown[]) => updateAgentToolConfigMock(...args),
}))

vi.mock('@/utils/message', () => ({
  Message: {
    success: (...args: unknown[]) => messageSuccessMock(...args),
    error: (...args: unknown[]) => messageErrorMock(...args),
  },
  createConfirm: (...args: unknown[]) => createConfirmMock(...args),
}))

function createAgentConfig() {
  return {
    id: 'agent-coordinator',
    name: '内容助手',
    llm_slot: 'agent_coordinator',
    system_prompt: '系统默认提示词',
    effective_prompt: '系统默认提示词',
    prompt_customized: false,
    tool_groups: [
      {
        key: 'page_write',
        label: '页面写入',
        tools: [
          {
            key: 'apply_page_edits',
            label: '应用页面 Edits',
            group_key: 'page_write',
            group_label: '页面写入',
            default_description: '应用页面 Edits 说明。',
            description_override: null,
            instructions_override: null,
            enabled: true,
            configurable: true,
            requires_confirmation: true,
            risk_level: 'danger',
            agent_guide: {
              effective_description: '应用页面 Edits 生效说明',
              system_description: '应用页面 Edits 系统说明',
              required_context_fields: [],
              runtime_disclosure_groups: [],
              instructions: null,
              parameters_schema: {},
              call_example: {},
              response_example: null,
              response_notes: null,
            },
          },
        ],
      },
    ],
  }
}

function createTestingRenderOptions() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
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
          props: ['modelValue', 'options', 'placeholder'],
          emits: ['update:modelValue'],
          template: `<div data-testid="combobox-stub"><span>{{ placeholder || '选择模型' }}</span></div>`,
        },
      },
    },
  }
}

describe('个人设置拆分后一级视图测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    for (const key of Object.keys(routeQuery)) delete routeQuery[key]
    listAgentConfigsMock.mockResolvedValue([createAgentConfig()])
    listLlmProvidersMock.mockResolvedValue([])
    listChatCatalogModelsMock.mockResolvedValue([])
    getModelCatalogSyncStateMock.mockResolvedValue({
      catalog_version: null,
      last_attempt_at: null,
      last_success_at: null,
      last_error: null,
      syncing: false,
    })
    listLlmProviderConfigsMock.mockResolvedValue([
      {
        id: 1,
        scope: 'personal',
        name: 'DeepSeek 官方',
        provider_key: 'deepseek',
        provider_label: 'DeepSeek',
        provider_type: 'chat',
        status: 'active',
        has_api_key: true,
        editable: true,
        updated_at: '2026-04-18T10:00:00+08:00',
      },
    ])
    listLlmConfigsMock.mockResolvedValue([
      {
        id: 10,
        scope: 'personal',
        name: 'DeepSeek V3',
        model_id: 'deepseek-chat',
        provider_config_id: 1,
        provider_config_name: 'DeepSeek 官方',
        model_type: 'chat',
        status: 'active',
        editable: true,
        supports_image_input: false,
      },
    ])
    listLlmSlotsMock.mockResolvedValue([
      {
        slot: 'agent_coordinator',
        label: '内容生成',
        llm_config_id: 10,
        llm_config_name: 'DeepSeek V3',
        binding_ready: true,
        inherited_from_global: false,
      },
    ])
    listAgentCodeStandardsMock.mockResolvedValue([
      {
        standard_type: 'page',
        content: '页面规范内容',
        default_content: '页面默认规范',
        customized: false,
      },
      {
        standard_type: 'component',
        content: '组件规范内容',
        default_content: '组件默认规范',
        customized: false,
      },
    ])
  })

  it('AccountAiModelsView 应按助手配置、模型管理、供应商管理三个 Tab 分栏渲染', async () => {
    render(AccountAiModelsView, createTestingRenderOptions())

    // 默认停在助手配置：只渲染槽位表，模型与供应商列表各自藏在其它 Tab 内
    await waitFor(() => {
      expect(screen.getAllByText('模型连接').length).toBeGreaterThan(0)
      expect(screen.getByText('核心能力槽位')).toBeTruthy()
      expect(screen.getAllByText('DeepSeek V3').length).toBeGreaterThan(0)
    })
    expect(screen.queryByText('模型列表 (1)')).toBeNull()
    expect(screen.queryByText('供应商列表 (1)')).toBeNull()

    await fireEvent.mouseDown(screen.getByRole('tab', { name: '模型管理' }), { button: 0 })
    await waitFor(() => {
      expect(screen.getByText('模型列表 (1)')).toBeTruthy()
      expect(screen.getByText('deepseek-chat')).toBeTruthy()
    })
    expect(routerReplaceMock).toHaveBeenCalledWith({ query: { tab: 'models' } })
    expect(screen.queryByText('核心能力槽位')).toBeNull()

    // 类型筛选把唯一的聊天模型过滤掉后，应回落到空状态而不是隐藏整张表
    const modelTypeSelect = (Array.from(document.querySelectorAll('select')) as HTMLSelectElement[])
      .find(el => Array.from(el.options).some(option => option.textContent === '全部模型类型'))
    expect(modelTypeSelect).toBeTruthy()
    await fireEvent.update(modelTypeSelect, 'image_generation')
    await waitFor(() => {
      expect(screen.getByText('模型列表 (0)')).toBeTruthy()
      expect(screen.getByText('没有符合条件的模型')).toBeTruthy()
    })
    await fireEvent.update(modelTypeSelect, 'chat')
    await waitFor(() => {
      expect(screen.getByText('模型列表 (1)')).toBeTruthy()
      expect(screen.getByText('deepseek-chat')).toBeTruthy()
    })

    await fireEvent.mouseDown(screen.getByRole('tab', { name: '供应商管理' }), { button: 0 })
    await waitFor(() => {
      expect(screen.getByText('供应商列表 (1)')).toBeTruthy()
      expect(screen.getByText('DeepSeek 官方')).toBeTruthy()
    })
  })

  it('AccountAiModelsView 应按路由 tab 参数直接进入对应 Tab', async () => {
    routeQuery.tab = 'providers'
    render(AccountAiModelsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getByText('供应商列表 (1)')).toBeTruthy()
    })
    expect(screen.queryByText('核心能力槽位')).toBeNull()
    expect(screen.queryByText('模型列表 (1)')).toBeNull()
  })

  it('AccountAiModelsView 编辑模型时支持状态设置并直接关闭弹窗（消除两层弹窗）', async () => {
    routeQuery.tab = 'models'
    updateLlmConfigMock.mockResolvedValue({
      id: 10,
      scope: 'personal',
      name: 'DeepSeek V3',
      model_id: 'deepseek-chat',
      provider_config_id: 1,
      model_type: 'chat',
      status: 'archived',
      editable: true,
    })

    render(AccountAiModelsView, createTestingRenderOptions())
    await waitFor(() => {
      expect(screen.getByText('DeepSeek V3')).toBeTruthy()
    })

    // 点击行或操作列编辑直接进入编辑模式
    await fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /编辑模型/ })).toBeTruthy()
    })

    // 表单包含模型状态字段
    const statusSelect = (Array.from(document.querySelectorAll('select')) as HTMLSelectElement[])
      .find(el => Array.from(el.options).some(option => option.textContent?.includes('启用 (Active)')))
    expect(statusSelect).toBeTruthy()
    await fireEvent.update(statusSelect!, 'archived')

    // 提交保存后直接关闭弹窗，不退回详情
    await fireEvent.click(screen.getByRole('button', { name: '保存模型' }))
    await waitFor(() => {
      expect(updateLlmConfigMock).toHaveBeenCalledWith(
        10,
        expect.objectContaining({
          status: 'archived',
        }),
      )
      expect(screen.queryByRole('heading', { name: /编辑模型/ })).toBeNull()
      expect(screen.queryByRole('heading', { name: 'DeepSeek V3' })).toBeNull()
    })
  })

  it('AccountAiPromptView 应展示系统提示词编辑器与保存交互', async () => {
    render(AccountAiPromptView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getAllByText('助手提示词').length).toBeGreaterThan(0)
      expect(screen.getByText('系统默认')).toBeTruthy()
      const textarea = screen.getByLabelText('完整提示词内容') as HTMLTextAreaElement
      expect(textarea.value).toBe('系统默认提示词')
    })

    const textarea = screen.getByLabelText('完整提示词内容') as HTMLTextAreaElement
    await fireEvent.update(textarea, '新修改的提示词内容')
    expect(screen.getByText('提示词修改尚未保存，离开前请先保存。')).toBeTruthy()

    const saveButton = screen.getByRole('button', { name: '保存提示词' })
    await fireEvent.click(saveButton)

    expect(updateAgentConfigMock).toHaveBeenCalledWith('agent-coordinator', {
      prompt_override: '新修改的提示词内容',
    })
  })

  it('AccountAiCodeStandardsView 应展示代码规范编辑与切换', async () => {
    render(AccountAiCodeStandardsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getAllByText('代码规范').length).toBeGreaterThan(0)
      expect(screen.getAllByText('页面代码规范').length).toBeGreaterThan(0)
      expect(screen.getAllByText('组件代码规范').length).toBeGreaterThan(0)
      const textarea = screen.getByLabelText('代码规范内容') as HTMLTextAreaElement
      expect(textarea.value).toBe('页面规范内容')
    })
  })

  it('AccountAiToolsView 应展示工具列表与搜索筛选', async () => {
    render(AccountAiToolsView, createTestingRenderOptions())

    await waitFor(() => {
      expect(screen.getAllByText('工具配置').length).toBeGreaterThan(0)
    })
    await waitFor(() => {
      expect(screen.getByText('应用页面 Edits')).toBeTruthy()
    })
    expect(screen.getAllByText('页面写入').length).toBeGreaterThan(0)
  })
})
