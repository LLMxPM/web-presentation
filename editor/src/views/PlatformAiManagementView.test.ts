/**
 * 文件功能：验证平台全局 AI 管理页面（PlatformAiManagementView）的渲染、策略配置保存与 Models.dev 同步。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import PlatformAiManagementView from '@/views/PlatformAiManagementView.vue'
import { ADMIN_SETTINGS_QUERY_KEY } from '@/api/adminSettings'
import { Message } from '@/utils/message'

const adminSettingsMocks = vi.hoisted(() => ({
  fetchAdminSettings: vi.fn(),
  updateAdminSettings: vi.fn(),
}))

const llmMocks = vi.hoisted(() => ({
  getModelCatalogSyncState: vi.fn(),
  refreshModelCatalog: vi.fn(),
  listLlmConfigs: vi.fn(),
  listLlmProviderConfigs: vi.fn(),
  getChatSlotBinding: vi.fn(),
  updateLlmSlotBinding: vi.fn(),
  push: vi.fn(),
}))

vi.mock('@/api/adminSettings', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/adminSettings')>(),
  fetchAdminSettings: adminSettingsMocks.fetchAdminSettings,
  updateAdminSettings: adminSettingsMocks.updateAdminSettings,
}))

vi.mock('@/api/llm', () => ({
  getModelCatalogSyncState: llmMocks.getModelCatalogSyncState,
  refreshModelCatalog: llmMocks.refreshModelCatalog,
  listLlmConfigs: llmMocks.listLlmConfigs,
  listLlmProviderConfigs: llmMocks.listLlmProviderConfigs,
  getChatSlotBinding: llmMocks.getChatSlotBinding,
  updateLlmSlotBinding: llmMocks.updateLlmSlotBinding,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: llmMocks.push }),
  useRoute: () => ({ query: { returnTo: '/workspaces/1/home' } }),
}))

vi.mock('@/utils/message', () => ({ Message: { error: vi.fn(), success: vi.fn() } }))

const customUiTabs = {
  name: 'UiTabs',
  props: ['modelValue', 'items'],
  emits: ['update:modelValue'],
  template: `
    <div class="tabs-stub">
      <div class="tab-triggers">
        <button
          v-for="item in items"
          :key="item.value"
          @click="$emit('update:modelValue', item.value)"
        >
          {{ item.label }}
        </button>
      </div>
      <div class="tab-contents">
        <div v-for="item in items" :key="item.value">
          <slot v-if="modelValue === item.value" :name="item.value" />
        </div>
      </div>
    </div>
  `,
}

describe('PlatformAiManagementView', () => {
  let queryClient: QueryClient
  /** 隔离查询缓存，保留控件事件以覆盖真正的写入路径。 */
  function renderView() {
    return render(PlatformAiManagementView, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }]],
        stubs: {
          UiTabs: customUiTabs,
          UiSelect: {
            props: ['modelValue', 'options', 'disabled'],
            emits: ['update:modelValue'],
            template: `<select :value="modelValue" :disabled="disabled" @change="$emit('update:modelValue', Number($event.target.value))"><option v-for="item in options" :key="item.value" :value="item.value">{{ item.label }}</option></select>`,
          },
        },
      },
    })
  }
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient()

    adminSettingsMocks.fetchAdminSettings.mockResolvedValue({
      categories: ['ai'],
      safe_mode_warnings: [],
      items: [
        {
          key: 'ai_enabled',
          category: 'ai',
          description: '平台 AI 总开关',
          value_type: 'bool',
          value: true,
          default_value: true,
          is_secret: false,
          editable: true,
          is_env_overridden: false,
        },
        {
          key: 'ai_model_catalog_sync_enabled',
          category: 'ai',
          description: '模型目录自动同步',
          value_type: 'bool',
          value: true,
          default_value: true,
          is_secret: false,
          editable: true,
          is_env_overridden: false,
        },
        {
          key: 'ai_image_transport_mode',
          category: 'ai',
          description: '图片传输模式',
          value_type: 'str',
          value: 'auto',
          default_value: 'auto',
          is_secret: false,
          editable: true,
          is_env_overridden: false,
        },
        {
          key: 'ai_agent_stream_idle_timeout_seconds',
          category: 'ai',
          description: '流式超时',
          value_type: 'float',
          value: 60,
          default_value: 60,
          is_secret: false,
          editable: true,
          is_env_overridden: false,
        },
        {
          key: 'ai_llm_http_trace_enabled',
          category: 'ai',
          description: 'HTTP 追踪',
          value_type: 'bool',
          value: false,
          default_value: false,
          is_secret: false,
          editable: true,
          is_env_overridden: false,
        },
      ],
    })

    llmMocks.getModelCatalogSyncState.mockResolvedValue({
      catalog_version: '2026.10.01',
      last_attempt_at: '2026-10-02T10:00:00Z',
      last_success_at: '2026-10-02T10:00:00Z',
      last_error: null,
      syncing: false,
    })

    llmMocks.listLlmConfigs.mockResolvedValue([
      {
        id: 101,
        name: '公共 Claude 3.5 Sonnet',
        model_id: 'claude-3-5-sonnet',
        protocol_key: 'anthropic_chat',
        scope: 'global',
        model_type: 'chat',
        status: 'active',
      },
      {
        id: 102,
        name: '个人私有模型',
        model_id: 'gpt-4o',
        protocol_key: 'openai_chat',
        scope: 'personal',
      },
    ])

    llmMocks.listLlmProviderConfigs.mockResolvedValue([
      {
        id: 201,
        name: '官方 Anthropic',
        provider_key: 'anthropic',
        scope: 'global',
      },
    ])

    llmMocks.getChatSlotBinding.mockResolvedValue({ slot: 'agent_coordinator', llm_config_id: 101 })
    llmMocks.updateLlmSlotBinding.mockResolvedValue({ slot: 'agent_coordinator', llm_config_id: 103 })
  })

  it('读取全局槽位且仅允许启用中的全局聊天模型参与绑定', async () => {
    const existing = await llmMocks.listLlmConfigs()
    llmMocks.listLlmConfigs.mockResolvedValue([
      ...existing,
      { id: 103, name: '备用聊天模型', model_id: 'chat-backup', scope: 'global', model_type: 'chat', status: 'active' },
      { id: -1, name: '公共图片模型', scope: 'global', model_type: 'image_generation', status: 'active' },
      { id: 104, name: '归档聊天模型', scope: 'global', model_type: 'chat', status: 'archived' },
    ])
    renderView()
    await waitFor(() => expect(queryClient.getQueryData(ADMIN_SETTINGS_QUERY_KEY)).toBeDefined())
    expect(llmMocks.getChatSlotBinding).toHaveBeenCalledWith('agent_coordinator', 'global')
    await fireEvent.click(screen.getByText('全局公共模型池'))
    const select = screen.getByRole('combobox', { name: '平台默认内容助手模型' })
    expect(select).toHaveValue('101')
    expect([...select.querySelectorAll('option')].map(item => item.value)).toEqual(['0', '101', '103'])
    await fireEvent.update(select, '103')
    await fireEvent.click(screen.getByRole('button', { name: '保存槽位' }))
    await waitFor(() => expect(llmMocks.updateLlmSlotBinding).toHaveBeenCalledWith('agent_coordinator', 103, 'global'))
    expect(screen.getByText('当前默认').closest('div')?.parentElement).toHaveTextContent('备用聊天模型')
  })

  it('保存策略时排除 ENV 锁定字段并更新管理中心共享快照', async () => {
    const settings = await adminSettingsMocks.fetchAdminSettings()
    settings.items[0].is_env_overridden = true
    settings.safe_mode_warnings = [{ key: 'ai_llm_http_trace_enabled', error: '非法值', fallback_value: false }]
    adminSettingsMocks.fetchAdminSettings.mockResolvedValue(settings)
    adminSettingsMocks.updateAdminSettings.mockResolvedValue({ ...settings, safe_mode_warnings: [] })
    renderView()
    await waitFor(() => expect(queryClient.getQueryData(ADMIN_SETTINGS_QUERY_KEY)).toBeDefined())
    expect(screen.getByRole('checkbox', { name: '平台 AI 总开关' })).toBeDisabled()
    await fireEvent.click(screen.getByRole('checkbox', { name: 'LLM HTTP 协议网络跟踪' }))
    // 后续刷新应得到保存后的服务端快照。
    adminSettingsMocks.fetchAdminSettings.mockResolvedValue({ ...settings, safe_mode_warnings: [] })
    await fireEvent.click(screen.getByRole('button', { name: '保存策略' }))
    await waitFor(() => expect(adminSettingsMocks.updateAdminSettings).toHaveBeenCalled())
    expect(adminSettingsMocks.updateAdminSettings.mock.calls[0][0]).not.toHaveProperty('ai_enabled')
    expect(adminSettingsMocks.updateAdminSettings.mock.calls[0][0]).toHaveProperty('ai_llm_http_trace_enabled', true)
    await waitFor(() => expect(queryClient.getQueryData(ADMIN_SETTINGS_QUERY_KEY)).toMatchObject({ safe_mode_warnings: [] }))
  })

  it('加载失败后保持只读，不能把前端默认值覆盖到服务端', async () => {
    adminSettingsMocks.fetchAdminSettings.mockRejectedValue(new Error('加载失败'))
    renderView()
    await waitFor(() => expect(Message.error).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: '保存策略' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: '平台 AI 总开关' })).toBeDisabled()
    expect(adminSettingsMocks.updateAdminSettings).not.toHaveBeenCalled()
  })

  it('进入完整配置工作台时保留返回工作空间的来源参数', async () => {
    renderView()
    await fireEvent.click(screen.getByText('全局公共模型池'))
    await fireEvent.click(screen.getByRole('button', { name: '前往完整配置工作台' }))
    expect(llmMocks.push).toHaveBeenCalledWith({ name: 'accountAiSettings', query: { returnTo: '/workspaces/1/home' } })
  })

  it('正常加载并渲染平台 AI 页面头部与运行策略表单', async () => {
    renderView()

    await waitFor(() => {
      expect(screen.getByText('平台 AI 管理')).toBeTruthy()
      expect(screen.getByText('平台 AI 运行策略')).toBeTruthy()
      expect(screen.getByText('平台 AI 总开关')).toBeTruthy()
    })
  })

  it('切换到模型规格目录 Tab 时展示缓存版本并支持点击同步', async () => {
    llmMocks.refreshModelCatalog.mockResolvedValue({
      catalog_version: '2026.10.02',
      last_attempt_at: '2026-10-02T12:00:00Z',
      last_success_at: '2026-10-02T12:00:00Z',
      last_error: null,
      syncing: false,
    })

    renderView()

    await waitFor(() => {
      expect(screen.getByText('Models.dev 规格目录')).toBeTruthy()
    })

    await fireEvent.click(screen.getByText('Models.dev 规格目录'))

    await waitFor(() => {
      expect(screen.getByText('Models.dev 模型目录管理')).toBeTruthy()
      expect(screen.getByText(/2026\.10\.01/)).toBeTruthy()
    })

    const syncButton = screen.getByText('立即同步目录')
    await fireEvent.click(syncButton)

    await waitFor(() => {
      expect(llmMocks.refreshModelCatalog).toHaveBeenCalled()
    })
  })

  it('切换到全局模型池 Tab 时仅列出 scope 为 global 的模型', async () => {
    renderView()

    await waitFor(() => {
      expect(screen.getByText('全局公共模型池')).toBeTruthy()
    })

    await fireEvent.click(screen.getByText('全局公共模型池'))

    await waitFor(() => {
      expect(screen.getByText('全局公共模型与凭据')).toBeTruthy()
      expect(screen.getByText('公共 Claude 3.5 Sonnet')).toBeTruthy()
      // 个人私有模型不应该出现在全局公共模型池中
      expect(screen.queryByText('个人私有模型')).toBeNull()
    })
  })
})
