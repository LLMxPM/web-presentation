<!-- 文件功能：承载账号 AI 设置中的模型详情表单，隔离模型编辑界面。 -->
<template>
  <section class="space-y-5 p-5">
    <div class="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-4">
      <div>
        <h2 class="text-lg font-bold text-slate-900">{{ panelTitle }}</h2>
        <p class="mt-1 text-sm text-slate-500">
          {{ panelDescription }}
        </p>
        <div v-if="mode === 'detail' && selectedModel" class="mt-3 flex flex-wrap gap-2 text-xs font-semibold">
          <span
            class="rounded-full px-2.5 py-1"
            :class="selectedModel.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
          >
            {{ selectedModel.status === 'active' ? '启用' : '不可用' }}
          </span>
          <span
            class="rounded-full px-2.5 py-1"
            :class="selectedModel.scope === 'global' ? 'bg-indigo-50 text-indigo-700' : 'bg-slate-100 text-slate-600'"
          >
            {{ selectedModel.scope === 'global' ? '全局模型' : '个人模型' }}
          </span>
          <span class="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">
            {{ selectedModel.provider_config_name }}
          </span>
          <span class="rounded-full bg-violet-50 px-2.5 py-1 text-violet-700">
            {{ selectedModel.model_type === 'image_generation' ? '图片生成' : '聊天模型' }}
          </span>
        </div>
        <p v-if="readOnlyModel" class="mt-2 text-xs font-semibold text-amber-600">管理员全局模型只读，可选择绑定但不能修改。</p>
      </div>
      <div v-if="mode === 'detail' && selectedModel?.editable" class="flex flex-wrap justify-end gap-2">
        <UiButton
          variant="primary"
          @click="emit('edit')"
        >
          编辑模型
        </UiButton>
        <UiButton
          variant="danger"
          :loading="deletingConfigId === selectedModel.id"
          @click="emit('deleteModel', selectedModel)"
        >
          删除模型
        </UiButton>
      </div>
    </div>

    <article v-if="mode === 'detail' && selectedModel" class="space-y-6">
      <section v-if="(selectedModel.model_type ?? 'chat') === 'chat'" class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-indigo-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">模型身份</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">用于识别模型归属、绑定入口和供应商真实模型 ID。</p>
          </div>
        </div>
        <dl class="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">供应商配置</dt>
            <dd class="mt-1 truncate font-bold text-slate-900">{{ selectedModel.provider_config_name }}</dd>
            <dd class="mt-1 text-xs text-slate-500">{{ selectedModel.provider_label }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">模型 ID</dt>
            <dd class="mt-1 min-w-0">
              <code class="block truncate rounded bg-white px-2 py-1 text-xs font-semibold text-slate-700">{{ selectedModel.model_id }}</code>
            </dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">范围</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ selectedModel.scope === 'global' ? '全局模型' : '个人模型' }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">状态</dt>
            <dd class="mt-1 font-semibold" :class="selectedModel.status === 'active' ? 'text-emerald-700' : 'text-slate-500'">
              {{ selectedModel.status === 'active' ? '启用' : '不可用' }}
            </dd>
          </div>
        </dl>
      </section>

      <section v-if="(selectedModel.model_type ?? 'chat') === 'chat'" class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-sky-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">运行预算</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">控制上下文窗口、单次输出和历史压缩目标。</p>
          </div>
        </div>
        <dl class="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">上下文窗口</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ selectedModel.context_window_tokens.toLocaleString() }} tokens</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">最大输出</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ selectedModel.max_output_tokens.toLocaleString() }} tokens</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">历史上下文比例</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ selectedModel.history_token_ratio }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">压缩目标比例</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ selectedModel.compression_target_ratio }}</dd>
          </div>
        </dl>
      </section>

      <section class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-emerald-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">能力声明</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">供 Agent 运行态决定请求参数映射、视觉输入和工具可用性。</p>
          </div>
        </div>
        <dl v-if="(selectedModel.model_type ?? 'chat') === 'chat'" class="grid gap-3 text-sm md:grid-cols-2">
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">Reasoning</dt>
            <dd class="mt-1 font-semibold" :class="selectedModel.thinking_enabled ? 'text-emerald-700' : 'text-slate-500'">
              {{ selectedModel.thinking_enabled ? `启用${selectedModel.thinking_effort ? ` · ${selectedModel.thinking_effort}` : ''}` : '未启用' }}
            </dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">图片输入</dt>
            <dd class="mt-1 font-semibold" :class="selectedModel.supports_image_input ? 'text-emerald-700' : 'text-slate-500'">
              {{ selectedModel.supports_image_input ? '支持' : '不支持' }}
            </dd>
          </div>
        </dl>
        <dl v-else-if="currentImageModel" class="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">操作</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ currentImageModel.operations.join(' / ') }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">参考图 / 输出上限</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ currentImageModel.max_reference_images }} / {{ currentImageModel.max_output_count }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">质量</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ currentImageModel.quality_options.join(' / ') }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">蒙版编辑</dt>
            <dd class="mt-1 font-semibold" :class="currentImageModel.supports_mask ? 'text-emerald-700' : 'text-slate-500'">
              {{ currentImageModel.supports_mask ? '支持' : '不支持' }}
            </dd>
          </div>
        </dl>
      </section>
    </article>

    <div v-else-if="mode === 'detail'" class="rounded-2xl border border-dashed border-slate-200 px-4 py-12 text-center text-sm text-slate-500">
      请选择左侧模型查看详情，或新建一个模型。
    </div>

    <div v-if="mode !== 'detail'" class="space-y-5" :class="readOnlyModel ? 'pointer-events-none opacity-70' : ''">
      <section class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-indigo-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">模型身份</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">模型名称用于绑定选择展示，模型 ID 按供应商真实 ID 填写。</p>
          </div>
        </div>
        <div class="grid gap-4 xl:grid-cols-2">
          <UiFormField label="模型类型" class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
            <UiSelect v-model="form.model_type" :options="modelTypeOptions" />
          </UiFormField>
          <UiFormField v-if="!selectedConfigId && canCreateGlobal" label="模型范围" class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
            <UiSelect v-model="form.scope" :options="scopeOptions" />
          </UiFormField>
          <UiFormField label="模型名称" required>
            <UiInput
              :model-value="form.name"
              placeholder="例如：总控默认模型"
              required
              @update:model-value="value => form.name = String(value)"
            />
          </UiFormField>

          <div class="space-y-1.5">
            <label class="ml-1 text-sm font-semibold text-slate-700">供应商配置</label>
            <UiCombobox
              :model-value="form.provider_config_id"
              :options="providerConfigOptions"
              placeholder="请选择供应商配置"
              @update:model-value="value => form.provider_config_id = value === null ? null : Number(value)"
            />
            <p v-if="currentProvider" class="ml-1 text-xs text-slate-400">{{ currentProvider.provider_adapter }}</p>
          </div>

          <UiFormField label="模型 ID" required>
            <UiInput
              :model-value="form.model_id"
              :placeholder="form.model_type === 'image_generation' ? '选择已知模型或填写兼容模型 ID' : '例如：gpt-4.1-mini'"
              :list="form.model_type === 'image_generation' ? 'image-generation-model-options' : undefined"
              required
              @update:model-value="handleModelIdUpdate"
            />
          </UiFormField>
          <datalist v-if="form.model_type === 'image_generation'" id="image-generation-model-options">
            <option v-for="model in imageModelOptions" :key="model.model_id" :value="model.model_id">{{ model.label }}</option>
          </datalist>
          <p v-if="form.model_type === 'image_generation' && imageModelOptions.length" class="-mt-2 text-xs text-slate-500 xl:col-span-2">
            已知模型：{{ imageModelOptions.map(model => `${model.label} (${model.model_id})`).join('、') }}。
            {{ supportsCustomImageModel ? '也可填写该供应商的兼容模型 ID。' : '当前供应商只允许目录中的模型。' }}
          </p>
          <p
            v-if="currentProvider && !(currentProvider.supported_model_types ?? ['chat']).includes(form.model_type)"
            class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-700 xl:col-span-2"
          >
            当前供应商不支持所选模型类型，请更换供应商配置。
          </p>
        </div>
      </section>

      <section v-if="form.model_type === 'chat'" class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-sky-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">运行预算</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">控制上下文窗口、单次输出和历史压缩目标，保存时会按后端范围归一化。</p>
          </div>
        </div>
        <div class="grid gap-4 xl:grid-cols-2">
          <UiFormField label="上下文窗口 tokens">
            <UiInput
              :model-value="form.context_window_tokens"
              type="number"
              min="1"
              inputmode="numeric"
              placeholder="例如：128000"
              @update:model-value="value => form.context_window_tokens = Number(value) || 128000"
            />
          </UiFormField>
          <UiFormField label="最大输出 tokens">
            <UiInput
              :model-value="form.max_output_tokens"
              type="number"
              min="1"
              inputmode="numeric"
              placeholder="例如：32000"
              @update:model-value="value => form.max_output_tokens = Number(value) || 32000"
            />
          </UiFormField>
          <UiFormField label="历史上下文比例">
            <UiInput
              :model-value="form.history_token_ratio"
              type="number"
              min="0"
              max="0.9"
              step="0.05"
              placeholder="0.5"
              @update:model-value="value => form.history_token_ratio = Number(value)"
            />
          </UiFormField>
          <UiFormField label="压缩目标比例">
            <UiInput
              :model-value="form.compression_target_ratio"
              type="number"
              min="0.02"
              max="0.5"
              step="0.01"
              placeholder="0.1"
              @update:model-value="value => form.compression_target_ratio = Number(value)"
            />
          </UiFormField>
        </div>
      </section>

      <section v-if="form.model_type === 'chat'" class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-emerald-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">能力声明</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">声明 reasoning 与图片输入能力，供 Agent 运行态决定可用工具和参数映射。</p>
          </div>
        </div>
        <div class="grid gap-4 xl:grid-cols-2">
          <div class="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <UiCheckbox
              :model-value="form.thinking_enabled"
              aria-label="启用思考 / reasoning"
              :disabled="currentProvider ? !currentProvider.supports_thinking : false"
              @update:model-value="value => form.thinking_enabled = value === true"
            />
            <span>
              <span class="block font-semibold">启用思考 / reasoning</span>
              <span class="mt-1 block text-xs text-slate-500">
                {{ currentProvider?.supports_thinking ? `当前供应商会按 ${currentProvider.thinking_mode} 规则映射。` : '当前供应商不支持 thinking，保存时会自动忽略。' }}
              </span>
            </span>
          </div>

          <div class="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            <UiCheckbox
              :model-value="form.supports_image_input"
              aria-label="支持图片输入"
              @update:model-value="value => form.supports_image_input = value === true"
            />
            <span>
              <span class="block font-semibold">支持图片输入</span>
              <span class="mt-1 block text-xs text-slate-500">
                {{ imageInputHint }}
              </span>
            </span>
          </div>

          <div class="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 xl:col-span-2">
            <UiFormField label="思考强度">
              <UiInput
                :model-value="form.thinking_effort ?? ''"
                placeholder="例如：medium、high、xhigh、max"
                :disabled="!form.thinking_enabled || (currentProvider ? !currentProvider.supports_thinking : false)"
                @update:model-value="value => form.thinking_effort = String(value).trim() || null"
              />
            </UiFormField>
            <p class="ml-1 text-xs leading-5 text-slate-500">
              {{ thinkingEffortHint }}
            </p>
          </div>
        </div>
      </section>

      <section v-else-if="currentImageModel" class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-emerald-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">生图能力</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">能力由后端模型目录维护，保存和执行时会使用同一份约束。</p>
          </div>
        </div>
        <dl class="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">操作</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ currentImageModel.operations.join(' / ') }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">参考图 / 输出上限</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ currentImageModel.max_reference_images }} / {{ currentImageModel.max_output_count }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">分辨率档位</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ currentImageModel.resolution_tiers.join(' / ') }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">蒙版编辑</dt>
            <dd class="mt-1 font-semibold" :class="currentImageModel.supports_mask ? 'text-emerald-700' : 'text-slate-500'">
              {{ currentImageModel.supports_mask ? '支持' : '不支持' }}
            </dd>
          </div>
        </dl>
      </section>
    </div>

    <InspectorSection
      v-if="mode !== 'detail' || selectedModel"
      title="高级参数"
      :description="advancedParameterSubtitle"
      :open="!collapsedModel"
      :class="readOnlyModel ? 'opacity-70' : ''"
      @update:open="value => collapsedModel = !value"
    >
      <div class="space-y-3">
        <UiFormField label="JSON 配置" :error="advancedConfigError">
          <UiInput
            v-model="advancedTextModel"
            type="textarea"
            :rows="10"
            :placeholder="advancedParameterPlaceholder"
            :disabled="isFormLocked"
          />
        </UiFormField>
        <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-6 text-slate-500">
          {{ advancedParameterHint }}
          <a
            v-if="currentProvider?.docs_url"
            :href="currentProvider.docs_url"
            target="_blank"
            rel="noreferrer"
            class="ml-2 font-semibold text-indigo-600 underline underline-offset-2"
          >
            {{ currentProvider.label }} 文档
          </a>
        </div>
      </div>
    </InspectorSection>

    <div v-if="mode !== 'detail'" class="flex justify-end gap-2">
      <UiButton v-if="mode === 'edit'" variant="ghost" :disabled="savingConfig" @click="emit('cancel')">
        取消
      </UiButton>
      <UiButton variant="ghost" :disabled="readOnlyModel" @click="emit('formatAdvanced')">
        格式化 JSON
      </UiButton>
      <UiButton variant="primary" :loading="savingConfig" :disabled="readOnlyModel || !canSubmitModel" @click="emit('submit')">
        {{ mode === 'edit' ? '保存模型' : '创建模型' }}
      </UiButton>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

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
  max_output_tokens: number
  history_token_ratio: number
  compression_target_ratio: number
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
const modelTypeOptions = [
  { value: 'chat', label: '聊天 / 图片理解模型' },
  { value: 'image_generation', label: '图片生成模型' },
]
const scopeOptions = [
  { value: 'personal', label: '个人模型' },
  { value: 'global', label: '管理员全局模型' },
]
const supportsCustomImageModel = computed(() => imageModelOptions.value.some(model => model.allow_custom_model_id))
const currentImageModel = computed<ImageGenerationModelCatalogItem | null>(() => {
  if (props.form.model_type !== 'image_generation') return null
  return imageModelOptions.value.find(model => model.model_id === props.form.model_id)
    ?? imageModelOptions.value.find(model => model.allow_custom_model_id)
    ?? null
})
const advancedParameterSubtitle = computed(() => props.form.model_type === 'image_generation'
  ? '按模型能力 Schema 校验后映射到图片供应商协议'
  : '默认折叠，透传给 Pydantic AI provider')
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
const panelDescription = computed(() => {
  if (props.mode === 'create') return '保存后可在智能体详情中绑定为模型。'
  if (props.mode === 'detail') return '查看模型身份、运行预算、能力声明和高级参数。'
  return '模型复用供应商配置中的 Base URL 与 API Key。'
})
</script>
