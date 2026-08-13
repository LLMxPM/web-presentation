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
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">推理能力</dt><dd class="mt-1 text-text-emphasis">{{ selectedModel.model_capability_json.supports_reasoning ? '支持' : '未声明支持' }}</dd></div>
        <div v-if="selectedModel.model_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">使用策略</dt><dd class="mt-1 text-text-emphasis">发起会话时按模型能力选择</dd></div>
      </dl>
    </div>

    <div v-else class="space-y-5" :class="readOnlyModel ? 'pointer-events-none opacity-70' : ''">
      <section class="space-y-3">
        <div>
          <h3 class="text-sm font-bold text-text-strong">基础信息</h3>
          <p class="mt-1 text-xs text-text-muted">定义模型用途，并关联可用的供应商连接。</p>
        </div>
      <div class="grid gap-4 md:grid-cols-2">
        <UiFormField label="配置域">
          <div class="flex h-10 items-center rounded-ui-md border border-border bg-surface-muted px-3 text-sm font-semibold text-text-emphasis">{{ form.model_type === 'image_generation' ? '图片生成模型' : '聊天 / 图片理解模型' }}</div>
        </UiFormField>
        <UiFormField v-if="mode === 'create' && canCreateGlobal" v-slot="field" label="配置范围">
          <UiSelect :id="field.inputId" v-model="form.scope" :aria-describedby="field.describedBy" :options="scopeOptions" />
        </UiFormField>
        <UiFormField v-slot="field" label="模型名称" required>
          <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.name" placeholder="例如：内容助手默认模型" required @update:model-value="value => form.name = String(value)" />
        </UiFormField>
        <div class="space-y-1.5 md:col-span-2">
          <label class="ml-1 text-sm font-semibold text-text-emphasis">供应商配置</label>
          <UiCombobox :model-value="form.provider_config_id" :options="providerConfigOptions" placeholder="请选择供应商配置" @update:model-value="value => form.provider_config_id = value === null ? null : Number(value)" />
        </div>
        <div v-if="form.model_type === 'chat'" class="space-y-1.5 md:col-span-2">
          <label class="ml-1 text-sm font-semibold text-text-emphasis">Models.dev 模型</label>
          <UiCombobox :model-value="chatModelSelection" :options="chatModelSelectOptions" placeholder="选择目录模型或手工输入模型 ID" @update:model-value="handleChatModelSelection" />
        </div>
        <UiFormField v-if="form.model_type === 'chat' && chatModelSelection === CUSTOM_CHAT_MODEL_ID" v-slot="field" label="自定义模型 ID" required>
          <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.model_id" placeholder="例如：gpt-4.1-mini" required @update:model-value="handleModelIdUpdate" />
        </UiFormField>
        <UiFormField v-if="form.model_type === 'image_generation'" v-slot="field" label="模型 ID" required>
          <UiSelect :id="field.inputId" :model-value="imageModelSelection" :aria-describedby="field.describedBy" :options="imageModelSelectOptions" placeholder="请选择生图模型" @update:model-value="handleImageModelSelection" />
        </UiFormField>
        <UiFormField v-if="form.model_type === 'image_generation' && imageModelSelection === CUSTOM_MODEL_ID" v-slot="field" label="自定义模型 ID" required>
          <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.model_id" placeholder="填写供应商支持的模型 ID" required @update:model-value="handleModelIdUpdate" />
        </UiFormField>
      </div>
      </section>

      <section v-if="form.model_type === 'chat'" class="space-y-4 border-t border-border-muted pt-5">
        <div>
          <h3 class="text-sm font-bold text-text-strong">模型能力</h3>
          <p class="mt-1 text-xs text-text-muted">能力默认来自 Models.dev；未收录模型使用保守默认。需要覆盖时在高级配置的 capability_override 中显式填写。</p>
        </div>
        <div class="grid gap-3 rounded-ui-md border border-border bg-surface-muted p-4 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <div><span class="block text-text-disabled">上下文上限</span><strong class="mt-1 block text-text-emphasis">{{ (resolvedCapability?.model_context_window_tokens ?? 200000).toLocaleString() }}</strong></div>
          <div><span class="block text-text-disabled">输入上限</span><strong class="mt-1 block text-text-emphasis">{{ (resolvedCapability?.context_window_tokens ?? 191808).toLocaleString() }}</strong></div>
          <div><span class="block text-text-disabled">单次输出上限</span><strong class="mt-1 block text-text-emphasis">{{ effectiveRequestOutputTokens.toLocaleString() }}</strong></div>
          <div><span class="block text-text-disabled">图片输入</span><strong class="mt-1 block text-text-emphasis">{{ resolvedCapability?.supports_image_input ? '支持' : '未声明' }}</strong></div>
          <p v-if="capabilitySummary" class="text-text-muted sm:col-span-2 lg:col-span-4">{{ capabilitySummary }}</p>
        </div>
      </section>

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

import { UiButton, UiCombobox, UiFormField, UiInput, UiSelect } from '@/components/ui'
import InspectorSection from '@/components/patterns/InspectorSection.vue'
import type { SelectOption } from '@/components/ui/select'
import type { AiLlmConfigScope, AiModelType, ImageGenerationModelCatalogItem, LlmConfigItem, LlmModelCapabilityItem, LlmProviderCatalogItem } from '@/types/api'
import type { ChatModelCatalogItem } from '@/api/model-config'

interface LlmFormState {
  scope: AiLlmConfigScope
  name: string
  provider_config_id: number | null
  model_id: string
  model_type: AiModelType
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
  chatModelCatalog: ChatModelCatalogItem[]
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

const capabilitySummary = computed(() => {
  const capability = props.resolvedCapability
  if (!capability) return ''
  return capability.warnings[0] ?? ''
})
const effectiveRequestOutputTokens = computed(() => props.resolvedCapability?.request_output_tokens ?? props.selectedModel?.request_output_tokens ?? 32_768)

const imageModelOptions = computed(() => props.currentProvider?.image_generation_models ?? [])
const CUSTOM_MODEL_ID = '__custom_model_id__'
const CUSTOM_CHAT_MODEL_ID = '__custom_chat_model_id__'
const imageModelSelection = ref<string | null>(null)
const chatModelSelection = ref<string | null>(null)
const chatModelSelectOptions = computed<SelectOption[]>(() => [
  ...props.chatModelCatalog.map(model => ({
    value: model.model_id,
    label: `${model.name}（${model.model_id}）`,
    description: [model.context_tokens ? `${model.context_tokens.toLocaleString()} context` : '', model.supports_tool_call ? 'Tool Call' : ''].filter(Boolean).join(' · '),
    keywords: [model.model_id, model.name, model.provider_key],
  })),
  { value: CUSTOM_CHAT_MODEL_ID, label: '手工输入未收录模型 ID' },
])
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
  : '{"temperature":0.2,"capability_override":{"supports_tool_call":true}}')
const advancedParameterHint = computed(() => {
  if (props.form.model_type !== 'image_generation') {
    return '请求参数直接发送给供应商；手工模型可在 capability_override 中显式开启 tool call、图片输入、推理或 structured output。推理策略在发起会话时选择，输入与输出预算由平台自动计算。'
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

/** 选择 Models.dev 模型；目录外模型明确进入手工输入，不混入图片模型注册表。 */
function handleChatModelSelection(value: string | number | null | (string | number)[]) {
  if (Array.isArray(value) || value === null) return
  chatModelSelection.value = String(value)
  if (value === CUSTOM_CHAT_MODEL_ID) {
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

watch(
  () => [props.form.model_type, props.currentProvider?.provider_key, props.form.model_id, props.chatModelCatalog] as const,
  ([modelType, , modelId]) => {
    if (modelType !== 'chat') {
      chatModelSelection.value = null
      return
    }
    if (props.chatModelCatalog.some(model => model.model_id === modelId)) {
      chatModelSelection.value = modelId
      return
    }
    chatModelSelection.value = modelId || chatModelSelection.value === CUSTOM_CHAT_MODEL_ID
      ? CUSTOM_CHAT_MODEL_ID
      : null
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

/** 返回能力来源的用户可读名称。 */
function capabilitySourceLabel(source: string, verified: boolean) {
  const labels: Record<string, string> = { built_in: '内置模型档案', provider_default: '供应商默认', manual_override: '手工覆盖' }
  return `${labels[source] ?? source}${verified ? '' : ' · 未验证'}`
}

</script>
