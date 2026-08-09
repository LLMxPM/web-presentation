<!-- 文件功能：承载账号 AI 设置中的紧凑模型详情、能力参数与高级配置表单。 -->
<template>
  <section class="space-y-5 p-5">
    <header class="flex items-start justify-between gap-4 border-b border-border-muted pb-4">
      <div class="min-w-0">
        <h2 class="truncate text-lg font-bold text-text-strong">{{ panelTitle }}</h2>
        <div v-if="mode === 'detail' && selectedModel" class="mt-2 flex flex-wrap gap-2 text-xs font-semibold">
          <span class="rounded-full px-2 py-0.5" :class="selectedModel.status === 'active' ? 'bg-success-muted text-success-strong' : 'bg-surface-muted text-text-muted'">{{ selectedModel.status === 'active' ? '启用' : '不可用' }}</span>
          <span class="rounded-full bg-surface-muted px-2 py-0.5 text-text-secondary">{{ selectedModel.scope === 'global' ? '全局模型' : '个人模型' }}</span>
          <span class="rounded-full bg-surface-muted px-2 py-0.5 text-text-secondary">{{ selectedModel.model_type === 'image_generation' ? '图片生成' : 'Chat' }}</span>
        </div>
        <p v-if="readOnlyModel" class="mt-2 text-xs font-semibold text-warning-strong">全局模型为只读配置，可直接绑定使用。</p>
      </div>
      <div v-if="mode === 'detail' && selectedModel?.editable" class="flex shrink-0 gap-2">
        <UiButton variant="ghost" @click="emit('edit')">编辑</UiButton>
        <UiButton variant="danger" :loading="deletingConfigId === selectedModel.id" @click="emit('deleteModel', selectedModel)">删除</UiButton>
      </div>
    </header>

    <div v-if="mode === 'detail' && selectedModel" class="space-y-5">
      <dl class="grid gap-x-6 gap-y-4 text-sm md:grid-cols-2">
        <div><dt class="text-xs font-semibold text-text-disabled">模型名称</dt><dd class="mt-1 font-semibold text-text-strong">{{ selectedModel.name }}</dd></div>
        <div><dt class="text-xs font-semibold text-text-disabled">模型类型</dt><dd class="mt-1 text-text-emphasis">{{ selectedModel.model_type === 'image_generation' ? '图片生成模型' : '聊天 / 图片理解模型' }}</dd></div>
        <div><dt class="text-xs font-semibold text-text-disabled">供应商配置</dt><dd class="mt-1 font-semibold text-text-strong">{{ selectedModel.provider_config_name }}</dd></div>
        <div><dt class="text-xs font-semibold text-text-disabled">模型 ID</dt><dd class="mt-1 break-all font-mono text-text-emphasis">{{ selectedModel.model_id }}</dd></div>
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">上下文窗口</dt><dd class="mt-1 text-text-emphasis">{{ selectedModel.context_window_tokens.toLocaleString() }} tokens</dd></div>
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">能力</dt><dd class="mt-1 text-text-emphasis">{{ selectedModel.thinking_enabled ? 'Thinking' : '无 Thinking' }} · {{ selectedModel.supports_image_input ? '支持图片输入' : '不支持图片输入' }}</dd></div>
        <div v-if="selectedModel.thinking_enabled"><dt class="text-xs font-semibold text-text-disabled">思考强度</dt><dd class="mt-1 text-text-emphasis">{{ selectedModel.thinking_effort || '供应商默认' }}</dd></div>
      </dl>
    </div>

    <div v-else class="space-y-5" :class="readOnlyModel ? 'pointer-events-none opacity-70' : ''">
      <div class="grid gap-4 md:grid-cols-2">
        <UiFormField v-slot="field" label="模型类型">
          <UiSelect :id="field.inputId" v-model="form.model_type" :aria-describedby="field.describedBy" :options="modelTypeOptions" />
        </UiFormField>
        <UiFormField v-if="mode === 'create' && canCreateGlobal" v-slot="field" label="配置范围">
          <UiSelect :id="field.inputId" v-model="form.scope" :aria-describedby="field.describedBy" :options="scopeOptions" />
        </UiFormField>
        <UiFormField v-slot="field" label="模型名称" required>
          <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.name" placeholder="例如：内容助手默认模型" required @update:model-value="value => form.name = String(value)" />
        </UiFormField>
        <div class="space-y-1.5">
          <label class="ml-1 text-sm font-semibold text-text-emphasis">供应商配置</label>
          <UiCombobox :model-value="form.provider_config_id" :options="providerConfigOptions" placeholder="请选择供应商配置" @update:model-value="value => form.provider_config_id = value === null ? null : Number(value)" />
        </div>
        <UiFormField v-if="form.model_type === 'chat'" v-slot="field" label="模型 ID" required>
          <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.model_id" placeholder="例如：gpt-4.1-mini" required @update:model-value="handleModelIdUpdate" />
        </UiFormField>
        <UiFormField v-else v-slot="field" label="模型 ID" required>
          <UiSelect :id="field.inputId" :model-value="imageModelSelection" :aria-describedby="field.describedBy" :options="imageModelSelectOptions" placeholder="请选择生图模型" @update:model-value="handleImageModelSelection" />
        </UiFormField>
        <UiFormField v-if="form.model_type === 'image_generation' && imageModelSelection === CUSTOM_MODEL_ID" v-slot="field" label="自定义模型 ID" required>
          <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.model_id" placeholder="填写供应商支持的模型 ID" required @update:model-value="handleModelIdUpdate" />
        </UiFormField>
      </div>

      <div v-if="form.model_type === 'chat'" class="grid gap-4 border-t border-border-muted pt-4 md:grid-cols-2">
        <UiFormField v-slot="field" label="上下文窗口（K）">
          <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.context_window_tokens / 1000" type="number" min="128" max="2000" step="1" inputmode="numeric" @update:model-value="value => form.context_window_tokens = (Number(value) || 128) * 1000" />
        </UiFormField>
        <UiFormField v-slot="field" label="思考强度">
          <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.thinking_effort ?? ''" placeholder="例如：medium、high" :disabled="!form.thinking_enabled || (currentProvider ? !currentProvider.supports_thinking : false)" @update:model-value="value => form.thinking_effort = String(value).trim() || null" />
        </UiFormField>
        <label class="flex items-start gap-3 rounded-ui-md border border-border bg-canvas px-4 py-3 text-sm text-text-emphasis">
          <UiCheckbox :model-value="form.thinking_enabled" :disabled="currentProvider ? !currentProvider.supports_thinking : false" @update:model-value="value => form.thinking_enabled = value === true" />
          <span><span class="block font-semibold">启用 Thinking</span><span class="mt-1 block text-xs text-text-muted">{{ thinkingEffortHint }}</span></span>
        </label>
        <label class="flex items-start gap-3 rounded-ui-md border border-border bg-canvas px-4 py-3 text-sm text-text-emphasis">
          <UiCheckbox :model-value="form.supports_image_input" @update:model-value="value => form.supports_image_input = value === true" />
          <span><span class="block font-semibold">支持图片输入</span><span class="mt-1 block text-xs text-text-muted">{{ imageInputHint }}</span></span>
        </label>
      </div>

      <dl v-else-if="currentImageModel" class="grid gap-3 border-t border-border-muted pt-4 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <div><dt class="text-text-disabled">操作</dt><dd class="mt-1 font-semibold text-text-emphasis">{{ currentImageModel.operations.join(' / ') }}</dd></div>
        <div><dt class="text-text-disabled">分辨率</dt><dd class="mt-1 font-semibold text-text-emphasis">{{ currentImageModel.resolution_tiers.join(' / ') }}</dd></div>
        <div><dt class="text-text-disabled">参考图 / 输出</dt><dd class="mt-1 font-semibold text-text-emphasis">{{ currentImageModel.max_reference_images }} / {{ currentImageModel.max_output_count }}</dd></div>
        <div><dt class="text-text-disabled">蒙版</dt><dd class="mt-1 font-semibold text-text-emphasis">{{ currentImageModel.supports_mask ? '支持' : '不支持' }}</dd></div>
      </dl>
    </div>

    <InspectorSection v-if="mode !== 'detail' || selectedModel" title="高级参数" :description="mode === 'detail' ? '查看当前 JSON 配置' : '仅在需要供应商扩展参数时填写'" :open="!collapsedModel" @update:open="value => collapsedModel = !value">
      <UiFormField label="JSON 配置" :error="advancedConfigError">
        <UiInput v-model="advancedTextModel" type="textarea" :rows="9" :placeholder="advancedParameterPlaceholder" :disabled="isFormLocked" />
      </UiFormField>
      <p class="mt-2 text-xs text-text-muted">{{ advancedParameterHint }}</p>
    </InspectorSection>

    <footer v-if="mode !== 'detail'" class="flex justify-end gap-2 border-t border-border-muted pt-4">
      <UiButton v-if="mode === 'edit'" variant="ghost" :disabled="savingConfig" @click="emit('cancel')">取消</UiButton>
      <UiButton variant="ghost" :disabled="readOnlyModel" @click="emit('formatAdvanced')">格式化 JSON</UiButton>
      <UiButton :loading="savingConfig" :disabled="readOnlyModel || !canSubmitModel" @click="emit('submit')">{{ mode === 'edit' ? '保存模型' : '创建模型' }}</UiButton>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { UiButton, UiCheckbox, UiCombobox, UiFormField, UiInput, UiSelect } from '@/components/ui'
import InspectorSection from '@/components/patterns/InspectorSection.vue'
import type { SelectOption } from '@/components/ui/select'
import type { AiLlmConfigScope, AiModelType, ImageGenerationModelCatalogItem, LlmConfigItem, LlmProviderCatalogItem } from '@/types/api'

interface LlmFormState {
  scope: AiLlmConfigScope
  name: string
  provider_config_id: number | null
  model_id: string
  model_type: AiModelType
  thinking_enabled: boolean
  thinking_effort: string | null
  supports_image_input: boolean
  context_window_tokens: number
}

type ConfigPanelMode = 'create' | 'detail' | 'edit'

const props = defineProps<{
  form: LlmFormState
  selectedConfigId: number | null
  selectedModel: LlmConfigItem | null
  mode: ConfigPanelMode
  currentProvider: LlmProviderCatalogItem | null
  providerConfigOptions: SelectOption[]
  advancedConfigText: string
  advancedConfigError: string
  advancedConfigCollapsed: boolean
  savingConfig: boolean
  deletingConfigId: number | null
  canCreateGlobal: boolean
}>()

const emit = defineEmits<{
  deleteModel: [config: LlmConfigItem]
  cancel: []
  edit: []
  formatAdvanced: []
  submit: []
  'update:advancedConfigText': [value: string]
  'update:advancedConfigCollapsed': [value: boolean]
}>()

const advancedTextModel = computed({
  get: () => props.advancedConfigText,
  set: value => emit('update:advancedConfigText', value),
})

const collapsedModel = computed({
  get: () => props.advancedConfigCollapsed,
  set: value => emit('update:advancedConfigCollapsed', value),
})

const thinkingEffortHint = computed(() => {
  if (!props.currentProvider?.supports_thinking) {
    return '当前供应商不支持 thinking。'
  }
  if (!props.form.thinking_enabled) {
    return '开启思考后才会向模型传递强度参数。'
  }
  if (props.currentProvider.thinking_mode === 'dashscope_enable_thinking') {
    return 'DashScope 的 low / medium / high 会映射为 thinking_budget；其他值会按默认预算处理。'
  }
  if (props.currentProvider.thinking_mode === 'google_thinking_level') {
    return 'Google Gemini 会映射为 thinking_level。'
  }
  if (props.currentProvider.thinking_mode === 'openrouter_reasoning') {
    return 'OpenRouter 会映射为 openrouter_reasoning.effort。'
  }
  if (props.currentProvider.thinking_mode === 'ollama_think') {
    return 'Ollama 会映射到 extra_body.think。'
  }
  if (props.currentProvider.thinking_mode === 'openai_extra_body_thinking') {
    if (props.currentProvider.provider_key === 'deepseek') {
      return 'DeepSeek 会写入 extra_body.thinking.type；强度仅使用 high / max，历史 low / medium 会兼容为 high，xhigh 会兼容为 max。'
    }
    return 'MiMo 会写入 extra_body.thinking.type；思考强度不参与请求参数。'
  }
  return 'OpenAI 兼容供应商会映射为 Pydantic AI reasoning settings。'
})

const imageInputHint = computed(() => {
  if (props.currentProvider?.provider_key === 'mimo') {
    return 'MiMo 仅 mimo-v2.5 / mimo-v2-omni 支持图片理解；选择其他 MiMo 模型时不要勾选。'
  }
  return '开启后，Agent 可发送用户图片附件并申请页面截图视觉工具。'
})

const imageModelOptions = computed(() => props.currentProvider?.image_generation_models ?? [])
const CUSTOM_MODEL_ID = '__custom_model_id__'
const imageModelSelection = ref<string | null>(null)
const imageModelSelectOptions = computed<SelectOption[]>(() => {
  const options = imageModelOptions.value.map(model => ({
    value: model.model_id,
    label: `${model.label}（${model.model_id}）`,
  }))
  if (imageModelOptions.value.some(model => model.allow_custom_model_id)) {
    options.push({ value: CUSTOM_MODEL_ID, label: '自定义模型 ID' })
  }
  return options
})
const modelTypeOptions = [
  { value: 'chat', label: '聊天 / 图片理解模型' },
  { value: 'image_generation', label: '图片生成模型' },
]
const scopeOptions = [
  { value: 'personal', label: '个人模型' },
  { value: 'global', label: '管理员全局模型' },
]
const currentImageModel = computed<ImageGenerationModelCatalogItem | null>(() => {
  if (props.form.model_type !== 'image_generation') return null
  return imageModelOptions.value.find(model => model.model_id === props.form.model_id)
    ?? imageModelOptions.value.find(model => model.allow_custom_model_id)
    ?? null
})
const advancedParameterPlaceholder = computed(() => props.form.model_type === 'image_generation'
  ? JSON.stringify(currentImageModel.value?.advanced_defaults ?? {}, null, 2)
  : '{"temperature":0.2,"openai_reasoning_effort":"medium"}')
const advancedParameterHint = computed(() => {
  if (props.form.model_type !== 'image_generation') {
    return '历史上下文超过预算后会自动摘要；高级配置不能覆盖 id / provider / api_key / base_url / client / async_client / http_client 等受管字段。'
  }
  const properties = currentImageModel.value?.advanced_schema?.properties
  const keys = properties && typeof properties === 'object' ? Object.keys(properties) : []
  return keys.length
    ? `当前模型允许的高级参数：${keys.join('、')}。未声明字段会被后端拒绝。`
    : '当前模型没有开放额外供应商参数。'
})

/** 更新模型 ID；选择目录模型时用其安全默认值初始化高级参数。 */
function handleModelIdUpdate(value: string | number) {
  props.form.model_id = String(value)
  if (props.form.model_type !== 'image_generation') return
  const model = imageModelOptions.value.find(item => item.model_id === props.form.model_id)
  if (model && (!props.advancedConfigText.trim() || props.advancedConfigText.trim() === '{}')) {
    emit('update:advancedConfigText', JSON.stringify(model.advanced_defaults ?? {}, null, 2))
  }
}

/** 处理标准下拉中的生图模型选择，并初始化目录模型的安全默认参数。 */
function handleImageModelSelection(value: string | number | null | (string | number)[]) {
  if (Array.isArray(value) || value === null) return
  imageModelSelection.value = String(value)
  if (value === CUSTOM_MODEL_ID) {
    props.form.model_id = ''
    return
  }
  handleModelIdUpdate(value)
}

watch(
  () => [props.form.model_type, props.currentProvider?.provider_key, props.form.model_id] as const,
  ([modelType, , modelId]) => {
    if (modelType !== 'image_generation') {
      imageModelSelection.value = null
      return
    }
    if (imageModelOptions.value.some(model => model.model_id === modelId)) {
      imageModelSelection.value = modelId
      return
    }
    if (modelId || imageModelSelection.value === CUSTOM_MODEL_ID) {
      imageModelSelection.value = CUSTOM_MODEL_ID
      return
    }
    imageModelSelection.value = null
  },
  { immediate: true },
)

const readOnlyModel = computed(() => Boolean(props.selectedModel && !props.selectedModel.editable))
const isFormLocked = computed(() => readOnlyModel.value || props.mode === 'detail')
const canSubmitModel = computed(() => Boolean(
  props.form.name.trim()
  && props.form.provider_config_id
  && props.form.model_id.trim()
  && (!props.currentProvider || (props.currentProvider.supported_model_types ?? ['chat']).includes(props.form.model_type)),
))
const panelTitle = computed(() => {
  if (props.mode === 'create') return '新建模型'
  if (props.mode === 'detail') return props.selectedModel?.name ?? '模型详情'
  return readOnlyModel.value ? '查看模型' : '编辑模型'
})
</script>
