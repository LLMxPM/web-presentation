/** 文件功能：验证供应商详情与凭证表单在新建与编辑模式下的交互行为，重点覆盖供应商切换时的 Base URL 与凭证联动。 */
import { nextTick, reactive } from 'vue'
import { render } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import AccountAiProviderDetail from './AccountAiProviderDetail.vue'
import type { LlmProviderCatalogItem } from '@/types/api'

const deepseekProvider: LlmProviderCatalogItem = {
  provider_key: 'deepseek',
  label: 'DeepSeek',
  provider_type: 'chat',
  provider_adapter: 'openai_compatible_chat',
  docs_url: 'https://platform.deepseek.com',
  supports_base_url: true,
  supports_api_key: true,
  supports_thinking: true,
  thinking_mode: 'effort',
  default_base_url: 'https://api.deepseek.com',
  default_model_id: 'deepseek-chat',
  default_thinking_enabled: false,
  default_thinking_effort: 'medium',
  default_context_window_tokens: 64000,
  default_max_output_tokens: 8192,
  default_supports_image_input: false,
  thinking_effort_options: ['low', 'medium', 'high'],
  advanced_json_hint: {},
  supported_model_types: ['chat'],
}

const openaiProvider: LlmProviderCatalogItem = {
  provider_key: 'openai',
  label: 'OpenAI',
  provider_type: 'chat',
  provider_adapter: 'openai_chat',
  docs_url: 'https://platform.openai.com',
  supports_base_url: true,
  supports_api_key: true,
  supports_thinking: false,
  thinking_mode: 'none',
  default_base_url: 'https://api.openai.com/v1',
  default_model_id: 'gpt-4o',
  default_thinking_enabled: false,
  default_thinking_effort: null,
  default_context_window_tokens: 128000,
  default_max_output_tokens: 4096,
  default_supports_image_input: true,
  thinking_effort_options: [],
  advanced_json_hint: {},
  supported_model_types: ['chat'],
}

const customNoBaseUrlProvider: LlmProviderCatalogItem = {
  provider_key: 'internal-fixed',
  label: '固定通道',
  provider_type: 'chat',
  provider_adapter: 'fixed_chat',
  docs_url: '',
  supports_base_url: false,
  supports_api_key: false,
  supports_thinking: false,
  thinking_mode: 'none',
  default_base_url: null,
  default_model_id: null,
  default_thinking_enabled: false,
  default_thinking_effort: null,
  default_context_window_tokens: null,
  default_max_output_tokens: null,
  default_supports_image_input: false,
  thinking_effort_options: [],
  advanced_json_hint: {},
  supported_model_types: ['chat'],
}

describe('AccountAiProviderDetail', () => {
  it('在新建模式下切换供应商时，应自动将 base_url 更新为新供应商的默认地址', async () => {
    const form = reactive({
      scope: 'personal' as const,
      name: '测试供应商',
      provider_key: 'deepseek',
      base_url: 'https://api.deepseek.com',
      api_key: 'sk-test',
      status: 'active' as const,
    })

    const view = render(AccountAiProviderDetail, {
      props: {
        form,
        selectedProviderConfigId: null,
        selectedProviderConfig: null,
        mode: 'create',
        currentProvider: deepseekProvider,
        providerOptions: [
          { value: 'deepseek', label: 'DeepSeek' },
          { value: 'openai', label: 'OpenAI' },
        ],
        savingProviderConfig: false,
        deletingProviderConfigId: null,
        canCreateGlobal: false,
      },
    })

    expect(form.base_url).toBe('https://api.deepseek.com')

    // 模拟切换供应商为 OpenAI
    form.provider_key = 'openai'
    await view.rerender({
      currentProvider: openaiProvider,
    })
    await nextTick()

    // 验证 base_url 联动切换为 OpenAI 的默认 Base URL
    expect(form.base_url).toBe('https://api.openai.com/v1')
  })

  it('在新建模式下切换到不支持 Base URL 和 API Key 的供应商时，应清空对应字段', async () => {
    const form = reactive({
      scope: 'personal' as const,
      name: '测试供应商',
      provider_key: 'deepseek',
      base_url: 'https://api.deepseek.com',
      api_key: 'sk-test',
      status: 'active' as const,
    })

    const view = render(AccountAiProviderDetail, {
      props: {
        form,
        selectedProviderConfigId: null,
        selectedProviderConfig: null,
        mode: 'create',
        currentProvider: deepseekProvider,
        providerOptions: [
          { value: 'deepseek', label: 'DeepSeek' },
          { value: 'internal-fixed', label: '固定通道' },
        ],
        savingProviderConfig: false,
        deletingProviderConfigId: null,
        canCreateGlobal: false,
      },
    })

    form.provider_key = 'internal-fixed'
    await view.rerender({
      currentProvider: customNoBaseUrlProvider,
    })
    await nextTick()

    expect(form.base_url).toBe('')
    expect(form.api_key).toBe('')
  })

  it('在编辑模式下切换 currentProvider 时，不得覆盖已有配置的 base_url', async () => {
    const form = reactive({
      scope: 'personal' as const,
      name: '已有自建网关',
      provider_key: 'deepseek',
      base_url: 'https://custom-proxy.internal/v1',
      api_key: '',
      status: 'active' as const,
    })

    const view = render(AccountAiProviderDetail, {
      props: {
        form,
        selectedProviderConfigId: 99,
        selectedProviderConfig: {
          id: 99,
          scope: 'personal',
          name: '已有自建网关',
          provider_key: 'deepseek',
          provider_label: 'DeepSeek',
          base_url: 'https://custom-proxy.internal/v1',
          has_api_key: true,
          api_key_masked: 'sk-***',
          status: 'active',
          editable: true,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        mode: 'edit',
        currentProvider: deepseekProvider,
        providerOptions: [
          { value: 'deepseek', label: 'DeepSeek' },
          { value: 'openai', label: 'OpenAI' },
        ],
        savingProviderConfig: false,
        deletingProviderConfigId: null,
        canCreateGlobal: false,
      },
    })

    await view.rerender({
      currentProvider: openaiProvider,
    })
    await nextTick()

    // 验证已有配置的自定义 base_url 未被破坏
    expect(form.base_url).toBe('https://custom-proxy.internal/v1')
  })
})
