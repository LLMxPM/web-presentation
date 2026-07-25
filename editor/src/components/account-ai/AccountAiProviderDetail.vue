<!-- 文件功能：承载账号 AI 设置中的供应商配置详情表单，集中维护 Base URL 与 API Key。 -->
<template>
  <section class="space-y-5 p-5">
    <div class="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-4">
      <div>
        <h2 class="text-lg font-bold text-slate-900">{{ panelTitle }}</h2>
        <p class="mt-1 text-sm text-slate-500">
          {{ panelDescription }}
        </p>
        <div v-if="mode === 'detail' && selectedProviderConfig" class="mt-3 flex flex-wrap gap-2 text-xs font-semibold">
          <span
            class="rounded-full px-2.5 py-1"
            :class="selectedProviderConfig.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'"
          >
            {{ selectedProviderConfig.status === 'active' ? '启用' : '不可用' }}
          </span>
          <span
            class="rounded-full px-2.5 py-1"
            :class="selectedProviderConfig.scope === 'global' ? 'bg-indigo-50 text-indigo-700' : 'bg-slate-100 text-slate-600'"
          >
            {{ selectedProviderConfig.scope === 'global' ? '全局供应商' : '个人供应商' }}
          </span>
          <span
            class="rounded-full px-2.5 py-1"
            :class="selectedProviderConfig.has_api_key ? 'bg-slate-100 text-slate-600' : 'bg-amber-50 text-amber-700'"
          >
            {{ selectedProviderConfig.has_api_key ? '已保存密钥' : '缺少密钥' }}
          </span>
        </div>
        <p v-if="readOnlyProvider" class="mt-2 text-xs font-semibold text-amber-600">管理员全局供应商只读，可随全局模型被使用但不能修改。</p>
      </div>
      <div v-if="mode === 'detail' && selectedProviderConfig?.editable" class="flex flex-wrap justify-end gap-2">
        <UiButton
          variant="primary"
          @click="emit('edit')"
        >
          编辑供应商
        </UiButton>
        <UiButton
          variant="danger"
          :loading="deletingProviderConfigId === selectedProviderConfig.id"
          @click="emit('deleteProvider', selectedProviderConfig)"
        >
          删除供应商
        </UiButton>
      </div>
    </div>

    <article v-if="mode === 'detail' && selectedProviderConfig" class="space-y-6">
      <section class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-indigo-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">供应商身份</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">用于识别这组连接配置的目录来源、使用范围和可用状态。</p>
          </div>
        </div>
        <dl class="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">供应商</dt>
            <dd class="mt-1 font-bold text-slate-900">{{ selectedProviderConfig.provider_label }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">供应商 Key</dt>
            <dd class="mt-1 min-w-0">
              <code class="block truncate rounded bg-white px-2 py-1 text-xs font-semibold text-slate-700">{{ selectedProviderConfig.provider_key }}</code>
            </dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">范围</dt>
            <dd class="mt-1 font-semibold text-slate-700">{{ selectedProviderConfig.scope === 'global' ? '全局供应商' : '个人供应商' }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">状态</dt>
            <dd class="mt-1 font-semibold" :class="selectedProviderConfig.status === 'active' ? 'text-emerald-700' : 'text-slate-500'">
              {{ selectedProviderConfig.status === 'active' ? '启用' : '不可用' }}
            </dd>
          </div>
        </dl>
      </section>

      <section class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-sky-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">连接凭证</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">这里只读展示连接地址和密钥保存情况，不承载编辑输入。</p>
          </div>
        </div>
        <dl class="grid gap-3 text-sm md:grid-cols-2">
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">Base URL</dt>
            <dd class="mt-1 truncate font-semibold text-slate-700">{{ selectedProviderConfig.base_url || '使用默认地址' }}</dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">API Key</dt>
            <dd class="mt-1 font-semibold" :class="selectedProviderConfig.has_api_key ? 'text-slate-700' : 'text-amber-600'">
              {{ selectedProviderConfig.has_api_key ? selectedProviderConfig.api_key_masked : '未保存 API Key' }}
            </dd>
          </div>
        </dl>
      </section>

      <section v-if="currentProvider" class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-emerald-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">目录能力</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">来自供应商目录的只读能力，供模型配置继承默认值和参数映射。</p>
          </div>
        </div>
        <dl class="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">Base URL</dt>
            <dd class="mt-1 font-semibold" :class="currentProvider.supports_base_url ? 'text-emerald-700' : 'text-slate-500'">
              {{ currentProvider.supports_base_url ? '可配置' : '不支持' }}
            </dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">API Key</dt>
            <dd class="mt-1 font-semibold" :class="currentProvider.supports_api_key ? 'text-emerald-700' : 'text-slate-500'">
              {{ currentProvider.supports_api_key ? '需要密钥' : '不需要' }}
            </dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">Thinking</dt>
            <dd class="mt-1 font-semibold" :class="currentProvider.supports_thinking ? 'text-emerald-700' : 'text-slate-500'">
              {{ currentProvider.supports_thinking ? currentProvider.thinking_mode : '不支持' }}
            </dd>
          </div>
          <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <dt class="text-xs font-semibold text-slate-400">默认模型</dt>
            <dd class="mt-1 truncate font-semibold text-slate-700">
              {{ currentProvider.provider_type === 'image_generation' ? currentProvider.default_image_generation_model_id || '未设置' : currentProvider.default_model_id || '未设置' }}
            </dd>
          </div>
        </dl>
      </section>
    </article>

    <div v-else-if="mode === 'detail'" class="rounded-2xl border border-dashed border-slate-200 px-4 py-12 text-center text-sm text-slate-500">
      请选择左侧供应商查看详情，或新建一个供应商。
    </div>

    <div v-if="mode !== 'detail'" class="space-y-5" :class="readOnlyProvider ? 'pointer-events-none opacity-70' : ''">
      <section class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-indigo-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">供应商身份</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">选择供应商目录项并命名这组连接配置。</p>
          </div>
        </div>
        <div class="grid gap-4 xl:grid-cols-2">
          <UiFormField v-if="!selectedProviderConfigId && canCreateGlobal" label="供应商范围" class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
            <UiSelect v-model="form.scope" :options="scopeOptions" />
          </UiFormField>

          <UiFormField label="供应商配置名称" required>
            <UiInput
              :model-value="form.name"
              placeholder="例如：OpenAI 工作账号"
              required
              @update:model-value="value => form.name = String(value)"
            />
          </UiFormField>

          <div class="space-y-1.5 xl:col-span-2">
            <label class="ml-1 text-sm font-semibold text-slate-700">供应商</label>
            <UiCombobox
              :model-value="form.provider_key"
              :options="providerOptions"
              placeholder="请选择供应商"
              :disabled="Boolean(selectedProviderConfigId)"
              @update:model-value="value => form.provider_key = value as string | null"
            />
            <p v-if="currentProvider" class="ml-1 text-xs text-slate-400">
              {{ currentProvider.provider_type === 'image_generation' ? '图片生成供应商' : 'Chat 供应商' }} · 协议由供应商类型固定
            </p>
          </div>
        </div>
      </section>

      <section class="space-y-3">
        <div class="flex items-start gap-3 border-b border-slate-100 pb-2">
          <span class="mt-1 h-5 w-1 rounded-full bg-sky-500"></span>
          <div>
            <h3 class="text-base font-bold text-slate-900">连接凭证</h3>
            <p class="mt-1 text-xs leading-5 text-slate-500">仅保存连接地址和密钥；模型 ID 与预算在模型配置中维护。</p>
          </div>
        </div>
        <div class="grid gap-4 xl:grid-cols-2">
          <UiFormField label="Base URL">
            <UiInput
              :model-value="form.base_url"
              :placeholder="currentProvider?.base_url_hint || '例如：https://openrouter.ai/api/v1'"
              :disabled="currentProvider ? !currentProvider.supports_base_url : false"
              @update:model-value="value => form.base_url = String(value)"
            />
          </UiFormField>
          <p v-if="currentProvider?.requires_base_url" class="-mt-2 ml-1 text-xs text-amber-600">
            当前供应商必须配置独立 Base URL。
          </p>

          <UiFormField label="API Key">
            <UiInput
              :model-value="form.api_key"
              placeholder="请输入 API Key；编辑时留空表示保持原值"
              type="password"
              password-toggle
              :disabled="currentProvider ? !currentProvider.supports_api_key : false"
              @update:model-value="value => form.api_key = String(value)"
            />
          </UiFormField>
          <PropertyRow
            label="密钥安全"
            description="密钥不会在界面回显；编辑时留空会保持已保存的值。"
            class="xl:col-span-2"
          >
            <span class="text-xs font-medium text-[rgb(var(--ui-text-secondary))]">仅在提交时发送到后端安全存储。</span>
          </PropertyRow>
        </div>
      </section>
    </div>

    <InspectorSection
      v-if="mode !== 'detail' || selectedProviderConfig"
      title="配置说明"
      :description="helperText"
      :collapsible="false"
      class="rounded-xl border border-slate-200 bg-slate-50 text-xs leading-6 text-slate-500"
      :class="readOnlyProvider ? 'opacity-70' : ''"
    >
      <a
        v-if="currentProvider?.docs_url"
        :href="currentProvider.docs_url"
        target="_blank"
        rel="noreferrer"
        class="ml-2 font-semibold text-indigo-600 underline underline-offset-2"
      >
        {{ currentProvider.label }} 文档
      </a>
    </InspectorSection>

    <div v-if="mode !== 'detail'" class="flex justify-end gap-2">
      <UiButton v-if="mode === 'edit'" variant="ghost" :disabled="savingProviderConfig" @click="emit('cancel')">
        取消
      </UiButton>
      <UiButton variant="primary" :loading="savingProviderConfig" :disabled="readOnlyProvider || !canSubmitProvider" @click="emit('submit')">
        {{ mode === 'edit' ? '保存供应商' : '创建供应商' }}
      </UiButton>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { UiButton, UiCombobox, UiFormField, UiInput, UiSelect } from '@/components/ui'
import PropertyRow from '@/components/patterns/PropertyRow.vue'
import InspectorSection from '@/components/patterns/InspectorSection.vue'
import type { SelectOption } from '@/components/ui/select'
import type { AiLlmConfigScope, LlmProviderCatalogItem, LlmProviderConfigItem } from '@/types/api'

interface LlmProviderFormState {
  scope: AiLlmConfigScope
  name: string
  provider_key: string | null
  base_url: string
  api_key: string
}

type ConfigPanelMode = 'create' | 'detail' | 'edit'

const props = defineProps<{
  form: LlmProviderFormState
  selectedProviderConfigId: number | null
  selectedProviderConfig: LlmProviderConfigItem | null
  mode: ConfigPanelMode
  currentProvider: LlmProviderCatalogItem | null
  providerOptions: SelectOption[]
  savingProviderConfig: boolean
  deletingProviderConfigId: number | null
  canCreateGlobal: boolean
}>()

const emit = defineEmits<{
  deleteProvider: [config: LlmProviderConfigItem]
  cancel: []
  edit: []
  submit: []
}>()

const readOnlyProvider = computed(() => Boolean(props.selectedProviderConfig && !props.selectedProviderConfig.editable))
const canSubmitProvider = computed(() => Boolean(
  props.form.name.trim()
  && props.form.provider_key
  && (!props.currentProvider?.requires_base_url || props.form.base_url.trim()),
))
const panelTitle = computed(() => {
  if (props.mode === 'create') return '新建供应商'
  if (props.mode === 'detail') return props.selectedProviderConfig?.name ?? '供应商详情'
  return readOnlyProvider.value ? '查看供应商' : '编辑供应商'
})
const panelDescription = computed(() => {
  if (props.mode === 'create') return '保存后可被同范围的多个模型复用。'
  if (props.mode === 'detail') return '查看供应商身份、连接凭证和目录能力。'
  return '编辑时 API Key 留空表示保持原值；如需更换请输入新 Key。'
})
const helperText = computed(() => {
  if (props.mode === 'detail') return '详情页为只读视图；需要变更连接凭证时请先进入编辑。'
  if (props.mode === 'edit') return '当前供应商配置只保存连接凭证和密钥。模型 ID、上下文窗口、thinking 与高级 JSON 在模型配置中维护。'
  return '新建供应商需要至少填写配置名称和供应商；如果供应商要求密钥，请在创建时填写 API Key。'
})
const scopeOptions = [
  { value: 'personal', label: '个人供应商' },
  { value: 'global', label: '管理员全局供应商' },
]
</script>
