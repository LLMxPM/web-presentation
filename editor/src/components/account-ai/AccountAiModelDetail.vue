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
        </div>
        <p v-if="readOnlyModel" class="mt-2 text-xs font-semibold text-amber-600">管理员全局模型只读，可选择绑定但不能修改。</p>
      </div>
      <div v-if="mode === 'detail' && selectedModel?.editable" class="flex flex-wrap justify-end gap-2">
        <BaseButton
          variant="primary"
          @click="emit('edit')"
        >
          编辑模型
        </BaseButton>
        <BaseButton
          variant="danger"
          :loading="deletingConfigId === selectedModel.id"
          @click="emit('deleteModel', selectedModel)"
        >
          删除模型
        </BaseButton>
      </div>
    </div>

    <article v-if="mode === 'detail' && selectedModel" class="space-y-6">
      <section class="space-y-3">
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

      <section class="space-y-3">
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
        <dl class="grid gap-3 text-sm md:grid-cols-2">
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
            <label class="ml-1 text-sm font-semibold text-slate-700">供应商配置</label>
            <SearchableSelect
              :model-value="form.provider_config_id"
              :options="providerConfigOptions"
              placeholder="请选择供应商配置"
              @update:model-value="value => form.provider_config_id = value === null ? null : Number(value)"
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
        </div>
      </section>

      <section class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-sky-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">运行预算</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">控制上下文窗口、单次输出和历史压缩目标，保存时会按后端范围归一化。</p>
          </div>
        </div>
        <div class="grid gap-4 xl:grid-cols-2">
          <BaseInput
            :model-value="form.context_window_tokens"
            label="上下文窗口 tokens"
            type="number"
            min="1"
            inputmode="numeric"
            placeholder="例如：128000"
            @update:model-value="value => form.context_window_tokens = Number(value) || 128000"
          />
          <BaseInput
            :model-value="form.max_output_tokens"
            label="最大输出 tokens"
            type="number"
            min="1"
            inputmode="numeric"
            placeholder="例如：32000"
            @update:model-value="value => form.max_output_tokens = Number(value) || 32000"
          />
          <BaseInput
            :model-value="form.history_token_ratio"
            label="历史上下文比例"
            type="number"
            min="0"
            max="0.9"
            step="0.05"
            placeholder="0.5"
            @update:model-value="value => form.history_token_ratio = Number(value)"
          />
          <BaseInput
            :model-value="form.compression_target_ratio"
            label="压缩目标比例"
            type="number"
            min="0.02"
            max="0.5"
            step="0.01"
            placeholder="0.1"
            @update:model-value="value => form.compression_target_ratio = Number(value)"
          />
        </div>
      </section>

      <section class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-emerald-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">能力声明</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">声明 reasoning 与图片输入能力，供 Agent 运行态决定可用工具和参数映射。</p>
          </div>
        </div>
        <div class="grid gap-4 xl:grid-cols-2">
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

          <div class="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 xl:col-span-2">
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
        </div>
      </section>
    </div>

    <article v-if="mode !== 'detail' || selectedModel" class="overflow-hidden rounded-xl border border-slate-200" :class="readOnlyModel ? 'opacity-70' : ''">
      <button type="button" class="flex w-full items-center justify-between bg-slate-50 px-4 py-3 text-left" @click="collapsedModel = !collapsedModel">
        <span class="flex items-start gap-3">
          <span class="mt-1 h-5 w-1 rounded-full bg-slate-400"></span>
          <span>
            <span class="block text-base font-bold text-slate-900">高级参数</span>
            <span class="mt-1 block text-xs text-slate-400">默认折叠，透传给 Pydantic AI provider</span>
          </span>
        </span>
        <component :is="collapsedModel ? ChevronRight : ChevronDown" class="h-4 w-4 text-slate-400" />
      </button>
      <div v-show="!collapsedModel" class="space-y-3 border-t border-slate-100 p-4">
        <BaseInput
          v-model="advancedTextModel"
          type="textarea"
          label="JSON 配置"
          :rows="10"
          placeholder='例如：{"temperature":0.2,"openai_reasoning_effort":"medium"}'
          :error="advancedConfigError"
          :disabled="isFormLocked"
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

    <div v-if="mode !== 'detail'" class="flex justify-end gap-2">
      <BaseButton v-if="mode === 'edit'" variant="ghost" :disabled="savingConfig" @click="emit('cancel')">
        取消
      </BaseButton>
      <BaseButton variant="ghost" :disabled="readOnlyModel" @click="emit('formatAdvanced')">
        格式化 JSON
      </BaseButton>
      <BaseButton variant="primary" :loading="savingConfig" :disabled="readOnlyModel || !canSubmitModel" @click="emit('submit')">
        {{ mode === 'edit' ? '保存模型' : '创建模型' }}
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
  provider_config_id: number | null
  model_id: string
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

const readOnlyModel = computed(() => Boolean(props.selectedModel && !props.selectedModel.editable))
const isFormLocked = computed(() => readOnlyModel.value || props.mode === 'detail')
const canSubmitModel = computed(() => Boolean(
  props.form.name.trim()
  && props.form.provider_config_id
  && props.form.model_id.trim(),
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
