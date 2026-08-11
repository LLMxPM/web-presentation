<!-- 文件功能：承载账号 AI 设置中的紧凑模型详情、能力参数与高级配置表单。 -->
<template>
  <section class="space-y-5" :class="embeddedInDialog ? '' : 'p-5'">
    <header v-if="showPanelHeader" class="flex items-start justify-between gap-4 border-b border-border-muted pb-4">
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
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">平台可用输入窗口</dt><dd class="mt-1 text-text-emphasis">{{ selectedModel.context_window_tokens.toLocaleString() }} tokens</dd></div>
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">模型最低总上下文</dt><dd class="mt-1 text-text-emphasis">{{ selectedModel.required_model_context_tokens.toLocaleString() }} tokens</dd></div>
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">压缩触发 / 摘要目标</dt><dd class="mt-1 text-text-emphasis">{{ selectedModel.compression_trigger_tokens.toLocaleString() }} / {{ selectedModel.compression_target_tokens.toLocaleString() }} tokens</dd></div>
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">能力来源</dt><dd class="mt-1 text-text-emphasis">{{ capabilitySourceLabel(selectedModel.capability_source, selectedModel.capability_verified) }}</dd></div>
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">推理策略</dt><dd class="mt-1 text-text-emphasis">{{ reasoningModeLabel(selectedModel.reasoning_mode) }}{{ selectedModel.reasoning_level ? ` · ${selectedModel.reasoning_level}` : '' }}</dd></div>
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">最终生效</dt><dd class="mt-1 text-text-emphasis">{{ selectedModel.effective_reasoning?.message || '跟随模型默认。' }}</dd></div>
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

      <div v-if="form.model_type === 'chat'" class="space-y-4 border-t border-border-muted pt-4">
        <UiFormField v-slot="field" label="平台可用输入窗口（K）" required>
          <UiInput :input-id="field.inputId" :model-value="form.context_window_tokens / 1000" type="number" min="128" max="2000" step="1" required @update:model-value="value => form.context_window_tokens = (Number(value) || 128) * 1000" />
        </UiFormField>
        <div class="grid gap-3 rounded-ui-md border border-border bg-surface-muted p-4 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <div><span class="block text-text-disabled">模型最低总上下文</span><strong class="mt-1 block text-text-emphasis">{{ effectiveRequiredContextTokens.toLocaleString() }}</strong></div>
          <div><span class="block text-text-disabled">压缩触发点</span><strong class="mt-1 block text-text-emphasis">{{ effectiveCompressionTriggerTokens.toLocaleString() }}</strong></div>
          <div><span class="block text-text-disabled">单次输出上限</span><strong class="mt-1 block text-text-emphasis">{{ effectiveRequestOutputTokens.toLocaleString() }}</strong></div>
          <div><span class="block text-text-disabled">压缩摘要目标</span><strong class="mt-1 block text-text-emphasis">{{ effectiveCompressionTargetTokens.toLocaleString() }}</strong></div>
          <p class="sm:col-span-2 lg:col-span-4" :class="modelContextUnsupported ? 'text-danger-strong' : 'text-text-muted'">{{ capabilitySummary }}</p>
        </div>
        <UiFormField label="推理模式">
          <UiSegmentedControl :model-value="form.reasoning_mode" :options="reasoningModeOptions" :disabled="currentProvider ? !currentProvider.supports_thinking : false" @update:model-value="handleReasoningModeUpdate" />
        </UiFormField>
        <UiFormField v-if="form.reasoning_mode === 'enabled'" label="推理强度">
          <UiSegmentedControl :model-value="form.reasoning_level ?? 'medium'" :options="reasoningLevelOptions" @update:model-value="handleReasoningLevelUpdate" />
          <p class="mt-2 text-xs" :class="form.reasoning_level === 'max' ? 'text-warning-strong' : 'text-text-muted'">{{ effectiveReasoningHint }}</p>
        </UiFormField>
        <div class="grid gap-4 md:grid-cols-2">
        <label class="flex items-start gap-3 rounded-ui-md border border-border bg-canvas px-4 py-3 text-sm text-text-emphasis">
          <UiCheckbox :model-value="form.supports_image_input" @update:model-value="value => form.supports_image_input = value === true" />
          <span><span class="block font-semibold">支持图片输入</span><span class="mt-1 block text-xs text-text-muted">{{ imageInputHint }}</span></span>
        </label>
        </div>
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

    <footer v-if="showPanelFooter && mode !== 'detail'" class="flex justify-end gap-2 border-t border-border-muted pt-4">
      <UiButton v-if="mode === 'edit'" variant="ghost" :disabled="savingConfig" @click="emit('cancel')">取消</UiButton>
      <UiButton variant="ghost" :disabled="readOnlyModel" @click="emit('formatAdvanced')">格式化 JSON</UiButton>
      <UiButton :loading="savingConfig" :disabled="readOnlyModel || !canSubmitModel" @click="emit('submit')">{{ mode === 'edit' ? '保存模型' : '创建模型' }}</UiButton>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { UiButton, UiCheckbox, UiCombobox, UiFormField, UiInput, UiSegmentedControl, UiSelect } from '@/components/ui'
import InspectorSection from '@/components/patterns/InspectorSection.vue'
import type { SelectOption } from '@/components/ui/select'
import type { AiLlmConfigScope, AiModelType, AiReasoningLevel, AiReasoningMode, ImageGenerationModelCatalogItem, LlmConfigItem, LlmModelCapabilityItem, LlmProviderCatalogItem } from '@/types/api'

interface LlmFormState {
  scope: AiLlmConfigScope
  name: string
  provider_config_id: number | null
  model_id: string
  model_type: AiModelType
  reasoning_mode: AiReasoningMode
  reasoning_level: AiReasoningLevel | null
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
  resolvedCapability: LlmModelCapabilityItem | null
  providerConfigOptions: SelectOption[]
  advancedConfigText: string
  advancedConfigError: string
  advancedConfigCollapsed: boolean
  savingConfig: boolean
  deletingConfigId: number | null
  canCreateGlobal: boolean
  showPanelHeader?: boolean
  showPanelFooter?: boolean
  embeddedInDialog?: boolean
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

const reasoningModeOptions = computed(() => [
  { value: 'auto', label: '跟随模型' },
  { value: 'disabled', label: '关闭推理', disabled: !props.resolvedCapability?.supports_explicit_disable },
  { value: 'enabled', label: '指定强度', disabled: props.resolvedCapability ? !props.resolvedCapability.supports_reasoning : false },
])
const reasoningLevelOptions = [
  { value: 'low', label: '快速' }, { value: 'medium', label: '均衡' }, { value: 'high', label: '深入' }, { value: 'max', label: '极致' },
]
const effectiveReasoningHint = computed(() => {
  const level = props.form.reasoning_level ?? 'medium'
  const native = props.resolvedCapability?.level_mapping?.[level]
  const prefix = level === 'max' ? '极致模式可能显著增加延迟和成本。' : ''
  return `${prefix}${native === null ? '当前模型只支持推理开关，强度不参与请求。' : `最终生效：${native ?? level}。`}`
})
const capabilitySummary = computed(() => {
  const capability = props.resolvedCapability
  if (!capability) return '等待识别模型能力。'
  const source = capabilitySourceLabel(capability.source, capability.verified)
  if (modelContextUnsupported.value) {
    return `${source} · 模型档案仅支持 ${capability.model_context_window_tokens?.toLocaleString()} tokens，总上下文不足。`
  }
  return `${source}${capability.warnings.length ? ` · ${capability.warnings.join('；')}` : ' · 当前预算满足模型能力。'}`
})
const effectiveRequestOutputTokens = computed(() => props.resolvedCapability?.request_output_tokens ?? props.selectedModel?.request_output_tokens ?? 32_768)
const effectiveRequiredContextTokens = computed(() => props.form.context_window_tokens + effectiveRequestOutputTokens.value)
const effectiveCompressionTriggerTokens = computed(() => Math.max(0, props.form.context_window_tokens - 32_768))
const effectiveCompressionTargetTokens = computed(() => props.resolvedCapability?.compression_target_tokens ?? props.selectedModel?.compression_target_tokens ?? 16_384)
const modelContextUnsupported = computed(() => {
  const total = props.resolvedCapability?.model_context_window_tokens
  return Boolean(total && effectiveRequiredContextTokens.value > total)
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
  : '{"temperature":0.2}')
const advancedParameterHint = computed(() => {
  if (props.form.model_type !== 'image_generation') {
    return '历史上下文超过预算后会自动摘要；推理模式、强度和输出预算属于受管字段，不能在 JSON 中重复配置。'
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
  && !modelContextUnsupported.value
  && (!props.currentProvider || (props.currentProvider.supported_model_types ?? ['chat']).includes(props.form.model_type)),
))
const panelTitle = computed(() => {
  if (props.mode === 'create') return '新建模型'
  if (props.mode === 'detail') return props.selectedModel?.name ?? '模型详情'
  return readOnlyModel.value ? '查看模型' : '编辑模型'
})

/** 更新推理三态，并维护档位字段的组合约束。 */
function handleReasoningModeUpdate(value: string) {
  props.form.reasoning_mode = value as AiReasoningMode
  props.form.reasoning_level = value === 'enabled' ? props.form.reasoning_level ?? 'medium' : null
}

/** 更新平台四档推理强度。 */
function handleReasoningLevelUpdate(value: string) {
  props.form.reasoning_level = value as AiReasoningLevel
}

/** 返回能力来源的用户可读名称。 */
function capabilitySourceLabel(source: string, verified: boolean) {
  const labels: Record<string, string> = { built_in: '内置模型档案', provider_default: '供应商默认', manual_override: '手工覆盖' }
  return `${labels[source] ?? source}${verified ? '' : ' · 未验证'}`
}

/** 返回推理三态的用户可读名称。 */
function reasoningModeLabel(mode: AiReasoningMode) {
  return ({ auto: '跟随模型', disabled: '关闭推理', enabled: '指定强度' } as const)[mode]
}
</script>
