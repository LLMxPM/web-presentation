<!-- 文件功能：承载账号 AI 设置中的模型详情表单，隔离模型编辑界面。 -->
<template>
  <section class="space-y-5 p-5">
    <div class="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-4">
      <div>
        <h2 class="text-lg font-bold text-slate-900">{{ selectedConfigId ? (readOnlyModel ? '查看模型' : '编辑模型') : '新建模型' }}</h2>
        <p class="mt-1 text-sm text-slate-500">
          {{ selectedConfigId ? '编辑时 API Key 留空表示保持原值；如需更换请输入新 Key。' : '保存后可在智能体详情中绑定为模型。' }}
        </p>
        <p v-if="readOnlyModel" class="mt-2 text-xs font-semibold text-amber-600">管理员全局模型只读，可选择绑定但不能修改。</p>
      </div>
      <BaseButton
        v-if="selectedModel && selectedModel.editable"
        variant="ghost"
        :loading="statusUpdatingConfigId === selectedModel.id"
        @click="emit('toggleStatus', selectedModel)"
      >
        {{ selectedModel.status === 'active' ? '归档模型' : '恢复模型' }}
      </BaseButton>
    </div>

    <div class="grid gap-4 xl:grid-cols-2" :class="readOnlyModel ? 'pointer-events-none opacity-70' : ''">
      <label v-if="!selectedConfigId && canCreateGlobal" class="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
        <span>模型范围</span>
        <select v-model="form.scope" class="w-full rounded-md border border-slate-300 bg-white px-3 py-2">
          <option value="personal">个人模型</option>
          <option value="global">管理员全局模型</option>
        </select>
      </label>
      <BaseInput
        :model-value="form.name"
        label="模型名称"
        placeholder="例如：总控默认模型"
        required
        @update:model-value="value => form.name = String(value)"
      />

      <div class="space-y-1.5">
        <label class="ml-1 text-sm font-semibold text-slate-700">供应商</label>
        <SearchableSelect
          :model-value="form.provider_key"
          :options="providerOptions"
          placeholder="请选择供应商"
          @update:model-value="value => form.provider_key = value as string | null"
        />
        <p v-if="currentProvider" class="ml-1 text-xs text-slate-400">{{ currentProvider.provider_adapter }}</p>
      </div>

      <BaseInput
        :model-value="form.model_id"
        label="模型 ID"
        placeholder="例如：gpt-4.1-mini"
        required
        @update:model-value="value => form.model_id = String(value)"
      />
      <BaseInput
        :model-value="form.context_window_tokens"
        label="上下文窗口 tokens"
        type="number"
        placeholder="例如：128000"
        @update:model-value="value => form.context_window_tokens = Number(value) || 128000"
      />
      <BaseInput
        :model-value="form.max_output_tokens"
        label="最大输出 tokens"
        type="number"
        placeholder="例如：32000"
        @update:model-value="value => form.max_output_tokens = Number(value) || 32000"
      />
      <BaseInput
        :model-value="form.history_token_ratio"
        label="历史上下文比例"
        type="number"
        placeholder="0.5"
        @update:model-value="value => form.history_token_ratio = Number(value)"
      />
      <BaseInput
        :model-value="form.compression_target_ratio"
        label="压缩目标比例"
        type="number"
        placeholder="0.1"
        @update:model-value="value => form.compression_target_ratio = Number(value)"
      />
      <BaseInput
        :model-value="form.base_url"
        label="Base URL"
        placeholder="例如：https://openrouter.ai/api/v1"
        :disabled="currentProvider ? !currentProvider.supports_base_url : false"
        @update:model-value="value => form.base_url = String(value)"
      />
      <BaseInput
        :model-value="form.api_key"
        label="API Key"
        placeholder="请输入 API Key；编辑时留空表示保持原值"
        type="password"
        :disabled="currentProvider ? !currentProvider.supports_api_key : false"
        @update:model-value="value => form.api_key = String(value)"
      />

      <label class="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
        <input
          :checked="form.thinking_enabled"
          type="checkbox"
          class="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
          :disabled="currentProvider ? !currentProvider.supports_thinking : false"
          @change="event => form.thinking_enabled = (event.target as HTMLInputElement).checked"
        >
        <span>
          <span class="block font-semibold">启用思考 / reasoning</span>
          <span class="mt-1 block text-xs text-slate-500">
            {{ currentProvider?.supports_thinking ? `当前供应商会按 ${currentProvider.thinking_mode} 规则映射。` : '当前供应商不支持 thinking，保存时会自动忽略。' }}
          </span>
        </span>
      </label>

      <div class="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
        <BaseInput
          :model-value="form.thinking_effort ?? ''"
          label="思考强度"
          placeholder="例如：medium、high、xhigh、max"
          :disabled="!form.thinking_enabled || (currentProvider ? !currentProvider.supports_thinking : false)"
          @update:model-value="value => form.thinking_effort = String(value).trim() || null"
        />
        <p class="ml-1 text-xs leading-5 text-slate-500">
          {{ thinkingEffortHint }}
        </p>
      </div>

      <label class="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
        <input
          :checked="form.supports_image_input"
          type="checkbox"
          class="mt-0.5 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
          @change="event => form.supports_image_input = (event.target as HTMLInputElement).checked"
        >
        <span>
          <span class="block font-semibold">支持图片输入</span>
          <span class="mt-1 block text-xs text-slate-500">
            {{ imageInputHint }}
          </span>
        </span>
      </label>
    </div>

    <article class="overflow-hidden rounded-xl border border-slate-200" :class="readOnlyModel ? 'opacity-70' : ''">
      <button type="button" class="flex w-full items-center justify-between bg-slate-50 px-4 py-3 text-left" @click="collapsedModel = !collapsedModel">
        <span>
          <span class="text-sm font-bold text-slate-900">高级 JSON 配置</span>
          <span class="ml-2 text-xs text-slate-400">默认折叠，透传给 Pydantic AI provider</span>
        </span>
        <component :is="collapsedModel ? ChevronRight : ChevronDown" class="h-4 w-4 text-slate-400" />
      </button>
      <div v-show="!collapsedModel" class="space-y-3 border-t border-slate-100 p-4">
        <BaseInput
          v-model="advancedTextModel"
          type="textarea"
          label="高级 JSON 配置"
          :rows="10"
          placeholder='例如：{"temperature":0.2,"openai_reasoning_effort":"medium"}'
          :error="advancedConfigError"
          :disabled="readOnlyModel"
        />
        <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-6 text-slate-500">
          历史上下文超过预算后会自动摘要，压缩后的历史上下文目标约占模型窗口的“压缩目标比例”。
          高级配置不能覆盖 `id / provider / api_key / base_url / client / async_client / http_client` 等受管字段。
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
    </article>

    <div class="flex justify-end gap-2">
      <BaseButton variant="ghost" :disabled="readOnlyModel" @click="emit('formatAdvanced')">
        格式化 JSON
      </BaseButton>
      <BaseButton variant="primary" :loading="savingConfig" :disabled="readOnlyModel" @click="emit('submit')">
        {{ selectedConfigId ? '保存模型' : '创建模型' }}
      </BaseButton>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown, ChevronRight } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import SearchableSelect from '@/components/ui/SearchableSelect.vue'
import type { SelectOption } from '@/components/ui/select'
import type { AiLlmConfigScope, LlmConfigItem, LlmProviderCatalogItem } from '@/types/api'

interface LlmFormState {
  scope: AiLlmConfigScope
  name: string
  provider_key: string | null
  model_id: string
  base_url: string
  api_key: string
  thinking_enabled: boolean
  thinking_effort: string | null
  supports_image_input: boolean
  context_window_tokens: number
  max_output_tokens: number
  history_token_ratio: number
  compression_target_ratio: number
}

const props = defineProps<{
  form: LlmFormState
  selectedConfigId: number | null
  selectedModel: LlmConfigItem | null
  currentProvider: LlmProviderCatalogItem | null
  providerOptions: SelectOption[]
  advancedConfigText: string
  advancedConfigError: string
  advancedConfigCollapsed: boolean
  savingConfig: boolean
  statusUpdatingConfigId: number | null
  canCreateGlobal: boolean
}>()

const emit = defineEmits<{
  toggleStatus: [config: LlmConfigItem]
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
    return '该供应商会写入 extra_body.thinking.type；MiMo 不使用 openai_reasoning_effort。'
  }
  return 'OpenAI 兼容供应商会映射为 Pydantic AI reasoning settings。'
})

const imageInputHint = computed(() => {
  if (props.currentProvider?.provider_key === 'mimo') {
    return 'MiMo 仅 mimo-v2.5 / mimo-v2-omni 支持图片理解；选择其他 MiMo 模型时不要勾选。'
  }
  return '开启后，Agent 可发送用户图片附件并申请页面截图视觉工具。'
})

const readOnlyModel = computed(() => Boolean(props.selectedModel && !props.selectedModel.editable))
</script>
