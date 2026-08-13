<!-- 文件功能：承载账号 AI 设置中的紧凑供应商详情与连接凭证表单。 -->
<template>
  <section class="space-y-5" :class="embeddedInDialog ? '' : 'p-5'">
    <header v-if="showPanelHeader" class="flex items-start justify-between gap-4 border-b border-border-muted pb-4">
      <div class="min-w-0">
        <h2 class="truncate text-lg font-bold text-text-strong">{{ panelTitle }}</h2>
        <div v-if="mode === 'detail' && selectedProviderConfig" class="mt-2 flex flex-wrap gap-2 text-xs font-semibold">
          <span class="rounded-full px-2 py-0.5" :class="selectedProviderConfig.status === 'active' ? 'bg-success-muted text-success-strong' : 'bg-surface-muted text-text-muted'">{{ selectedProviderConfig.status === 'active' ? '启用' : '不可用' }}</span>
          <span class="rounded-full bg-surface-muted px-2 py-0.5 text-text-secondary">{{ selectedProviderConfig.scope === 'global' ? '全局供应商' : '个人供应商' }}</span>
          <span class="rounded-full px-2 py-0.5" :class="selectedProviderConfig.has_api_key ? 'bg-surface-muted text-text-secondary' : 'bg-warning-muted text-warning-strong'">{{ selectedProviderConfig.has_api_key ? '密钥已配置' : '缺少密钥' }}</span>
        </div>
        <p v-if="readOnlyProvider" class="mt-2 text-xs font-semibold text-warning-strong">全局供应商为只读配置。</p>
      </div>
      <div v-if="mode === 'detail' && selectedProviderConfig?.editable" class="flex shrink-0 gap-2">
        <UiButton variant="ghost" @click="emit('edit')">编辑</UiButton>
        <UiButton variant="danger" :loading="deletingProviderConfigId === selectedProviderConfig.id" @click="emit('deleteProvider', selectedProviderConfig)">删除</UiButton>
      </div>
    </header>

    <dl v-if="mode === 'detail' && selectedProviderConfig" class="grid gap-x-6 gap-y-4 text-sm md:grid-cols-2">
      <div><dt class="text-xs font-semibold text-text-disabled">配置名称</dt><dd class="mt-1 font-semibold text-text-strong">{{ selectedProviderConfig.name }}</dd></div>
      <div><dt class="text-xs font-semibold text-text-disabled">供应商</dt><dd class="mt-1 font-semibold text-text-strong">{{ selectedProviderConfig.provider_label }}</dd></div>
      <div><dt class="text-xs font-semibold text-text-disabled">供应商 Key</dt><dd class="mt-1"><code class="text-xs text-text-emphasis">{{ selectedProviderConfig.provider_key }}</code></dd></div>
      <div><dt class="text-xs font-semibold text-text-disabled">类型</dt><dd class="mt-1 text-text-emphasis">{{ currentProvider?.provider_type === 'image_generation' ? '图片生成' : 'Chat' }}</dd></div>
      <div class="md:col-span-2"><dt class="text-xs font-semibold text-text-disabled">Base URL</dt><dd class="mt-1 break-all text-text-emphasis">{{ selectedProviderConfig.base_url || '使用供应商默认地址' }}</dd></div>
      <div><dt class="text-xs font-semibold text-text-disabled">API Key</dt><dd class="mt-1 font-semibold" :class="selectedProviderConfig.has_api_key ? 'text-text-emphasis' : 'text-warning-strong'">{{ selectedProviderConfig.has_api_key ? selectedProviderConfig.api_key_masked : '未配置' }}</dd></div>
      <div v-if="currentProvider?.provider_type !== 'image_generation'"><dt class="text-xs font-semibold text-text-disabled">推理参数</dt><dd class="mt-1 text-text-emphasis">{{ reasoningTransportLabel }}</dd></div>
    </dl>

    <div v-else class="space-y-5" :class="readOnlyProvider ? 'pointer-events-none opacity-70' : ''">
      <section class="space-y-3">
        <div>
          <h3 class="text-sm font-bold text-text-strong">基础信息</h3>
          <p class="mt-1 text-xs text-text-muted">先定义配置名称和使用范围，便于在模型配置中识别。</p>
        </div>
        <div class="grid gap-4 md:grid-cols-2">
          <UiFormField v-slot="field" label="配置名称" required>
            <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.name" placeholder="例如：OpenAI 工作账号" required @update:model-value="value => form.name = String(value)" />
          </UiFormField>
          <UiFormField v-if="!selectedProviderConfigId && canCreateGlobal" label="配置范围">
            <UiSelect v-model="form.scope" :options="scopeOptions" />
          </UiFormField>
        </div>
      </section>

      <section class="space-y-3 border-t border-border-muted pt-5">
        <div>
          <h3 class="text-sm font-bold text-text-strong">供应商连接</h3>
          <p class="mt-1 text-xs text-text-muted">选择协议后，填写该供应商的服务地址和访问凭证。</p>
        </div>
        <div class="grid gap-4 md:grid-cols-2">
          <div class="space-y-1.5 md:col-span-2">
            <label class="ml-1 text-sm font-semibold text-text-emphasis">供应商</label>
            <UiCombobox :model-value="form.provider_key" :options="providerOptions" placeholder="请选择供应商" :disabled="Boolean(selectedProviderConfigId)" @update:model-value="value => form.provider_key = value as string | null" />
          </div>
          <UiFormField v-slot="field" label="Base URL">
            <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.base_url" :placeholder="currentProvider?.base_url_hint || '使用供应商默认地址'" :disabled="currentProvider ? !currentProvider.supports_base_url : false" @update:model-value="value => form.base_url = String(value)" />
            <p v-if="currentProvider?.requires_base_url" class="mt-1 text-xs text-warning-strong">当前供应商必须填写 Base URL。</p>
          </UiFormField>
          <UiFormField v-slot="field" label="API Key">
            <UiInput :input-id="field.inputId" :described-by="field.describedBy" :invalid="field.invalid" :model-value="form.api_key" placeholder="编辑时留空表示保持原密钥" type="password" password-toggle :disabled="currentProvider ? !currentProvider.supports_api_key : false" @update:model-value="value => form.api_key = String(value)" />
          </UiFormField>
        </div>
        <p class="text-xs text-text-muted">连接凭证由后端安全存储；模型 ID 和运行参数请在模型管理中维护。</p>
      </section>
    </div>

    <footer v-if="showPanelFooter && mode !== 'detail'" class="flex justify-end gap-2 border-t border-border-muted pt-4">
      <UiButton v-if="mode === 'edit'" variant="ghost" :disabled="savingProviderConfig" @click="emit('cancel')">取消</UiButton>
      <UiButton :loading="savingProviderConfig" :disabled="readOnlyProvider || !canSubmitProvider" @click="emit('submit')">{{ mode === 'edit' ? '保存供应商' : '创建供应商' }}</UiButton>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { UiButton, UiCombobox, UiFormField, UiInput, UiSelect } from '@/components/ui'
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
  showPanelHeader?: boolean
  showPanelFooter?: boolean
  embeddedInDialog?: boolean
}>()

const emit = defineEmits<{
  deleteProvider: [config: LlmProviderConfigItem]
  cancel: []
  edit: []
  submit: []
}>()

const readOnlyProvider = computed(() => Boolean(props.selectedProviderConfig && !props.selectedProviderConfig.editable))
const reasoningTransportLabel = computed(() => props.currentProvider?.provider_adapter === 'openai_compatible_chat'
  ? '支持 Models.dev 明确声明的标准 effort；其他推理参数保持自动'
  : '支持固定协议控制；可用选项由具体模型决定')
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
const scopeOptions = [
  { value: 'personal', label: '个人供应商' },
  { value: 'global', label: '管理员全局供应商' },
]
</script>
