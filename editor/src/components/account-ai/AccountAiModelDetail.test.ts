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
      thinking_enabled: false,
      thinking_effort: null,
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
})
