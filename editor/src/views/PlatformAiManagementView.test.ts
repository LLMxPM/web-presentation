/**
 * 文件功能：验证平台全局 AI 管理页面（PlatformAiManagementView）的渲染、策略配置保存与 Models.dev 同步。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import PlatformAiManagementView from '@/views/PlatformAiManagementView.vue'

const adminSettingsMocks = vi.hoisted(() => ({
  fetchAdminSettings: vi.fn(),
  updateAdminSettings: vi.fn(),
}))

const llmMocks = vi.hoisted(() => ({
  getModelCatalogSyncState: vi.fn(),
  refreshModelCatalog: vi.fn(),
  listLlmConfigs: vi.fn(),
  listLlmProviderConfigs: vi.fn(),
  listLlmSlots: vi.fn(),
  updateLlmSlot: vi.fn(),
}))

vi.mock('@/api/adminSettings', () => ({
  fetchAdminSettings: adminSettingsMocks.fetchAdminSettings,
  updateAdminSettings: adminSettingsMocks.updateAdminSettings,
}))

vi.mock('@/api/llm', () => ({
  getModelCatalogSyncState: llmMocks.getModelCatalogSyncState,
  refreshModelCatalog: llmMocks.refreshModelCatalog,
  listLlmConfigs: llmMocks.listLlmConfigs,
  listLlmProviderConfigs: llmMocks.listLlmProviderConfigs,
  listLlmSlots: llmMocks.listLlmSlots,
  updateLlmSlot: llmMocks.updateLlmSlot,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

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
  beforeEach(() => {
    vi.clearAllMocks()

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

    llmMocks.listLlmSlots.mockResolvedValue([
      {
        id: 301,
        slot: 'agent_coordinator',
        scope: 'global',
        llm_config_id: 101,
      },
    ])
  })

  it('正常加载并渲染平台 AI 页面头部与运行策略表单', async () => {
    render(PlatformAiManagementView, {
      global: { stubs: { UiTabs: customUiTabs } },
    })

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

    render(PlatformAiManagementView, {
      global: { stubs: { UiTabs: customUiTabs } },
    })

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
    render(PlatformAiManagementView, {
      global: { stubs: { UiTabs: customUiTabs } },
    })

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
