/** 文件功能：验证模型详情表单在图片生成场景使用标准选择组件并正确切换自定义模型 ID。 */
import { nextTick, reactive } from 'vue'
import { render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import AccountAiModelDetail from './AccountAiModelDetail.vue'
import type { LlmProviderCatalogItem } from '@/types/api'

const imageProvider: LlmProviderCatalogItem = {
  provider_key: 'image-provider',
  label: '图片供应商',
  provider_type: 'image_generation',
  provider_adapter: 'image-provider',
  docs_url: '',
  supports_base_url: true,
  supports_api_key: true,
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
  supported_model_types: ['image_generation'],
  image_generation_models: [{
    model_id: 'image-v1',
    label: 'Image V1',
    operations: ['generate'],
    aspect_ratios: ['1:1'],
    resolution_tiers: ['1k'],
    quality_options: ['standard'],
    max_reference_images: 0,
    max_output_count: 1,
    supports_mask: false,
    advanced_schema: {},
    advanced_defaults: { quality: 'standard' },
    allow_custom_model_id: true,
  }],
}

describe('AccountAiModelDetail', () => {
  it('生图模型 ID 应使用标准下拉，并按选择显示自定义输入', async () => {
    const form = reactive({
      scope: 'personal' as const,
      name: '图片模型',
      provider_config_id: 10,
      model_id: '',
      model_type: 'image_generation' as const,
      reasoning_mode: 'auto' as const,
      reasoning_level: null,
      supports_image_input: false,
      context_window_tokens: 128000,
    })
    const view = render(AccountAiModelDetail, {
      props: {
        form,
        selectedConfigId: null,
        selectedModel: null,
        mode: 'create',
        currentProvider: imageProvider,
        resolvedCapability: null,
        providerConfigOptions: [{ value: 10, label: '图片供应商配置' }],
        advancedConfigText: '{}',
        advancedConfigError: '',
        advancedConfigCollapsed: true,
        savingConfig: false,
        deletingConfigId: null,
        canCreateGlobal: false,
      },
    })

    const modelIdSelect = screen.getByLabelText(/^模型 ID/)
    expect(modelIdSelect.tagName).toBe('BUTTON')
    expect(view.container.querySelector('datalist')).toBeNull()

    form.model_id = 'vendor-custom-image-model'
    await nextTick()
    expect(await screen.findByLabelText(/^自定义模型 ID/)).toBeTruthy()
  })

  it('聊天模型只能选择 Models.dev 目录模型，不提供手工录入 ID 入口', async () => {
    const chatProvider: LlmProviderCatalogItem = {
      provider_key: 'deepseek',
      label: 'DeepSeek',
      provider_type: 'chat',
      provider_adapter: 'deepseek',
      docs_url: '',
      supports_base_url: true,
      supports_api_key: true,
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
    const form = reactive({
      scope: 'personal' as const,
      name: '聊天模型',
      provider_config_id: 1,
      model_id: 'deepseek-chat',
      model_type: 'chat' as const,
      supports_image_input: false,
      context_window_tokens: 128000,
    })
    render(AccountAiModelDetail, {
      props: {
        form,
        selectedConfigId: null,
        selectedModel: null,
        mode: 'create',
        currentProvider: chatProvider,
        resolvedCapability: null,
        chatModelCatalog: [{
          provider_key: 'deepseek',
          model_id: 'deepseek-chat',
          name: 'DeepSeek V3',
          protocol_key: 'deepseek',
          context_tokens: 65536,
          input_tokens: 61440,
          output_tokens: 4096,
          input_modalities: ['text'],
          supports_tool_call: true,
          supports_reasoning: false,
          reasoning_options: {},
          catalog_version: 'v1',
        }],
        providerConfigOptions: [{ value: 1, label: 'DeepSeek 官方' }],
        advancedConfigText: '{}',
        advancedConfigError: '',
        advancedConfigCollapsed: true,
        savingConfig: false,
        deletingConfigId: null,
        canCreateGlobal: false,
      },
    })

    expect(screen.getByText('Models.dev 模型')).toBeTruthy()
    expect(screen.queryByLabelText(/^自定义模型 ID/)).toBeNull()

    // 改造前录入的目录外模型只回显，不会重新出现手工输入框
    form.model_id = 'vendor-only-model'
    await nextTick()
    expect(screen.queryByLabelText(/^自定义模型 ID/)).toBeNull()
  })
})
