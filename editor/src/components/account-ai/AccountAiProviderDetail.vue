<!-- 文件功能：承载账号 AI 设置中的供应商配置详情表单，集中维护 Base URL 与 API Key。 -->
<template>
  <section class="space-y-5 p-5">
    <div class="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-4">
      <div>
        <h2 class="text-lg font-bold text-slate-900">{{ selectedProviderConfigId ? (readOnlyProvider ? '查看供应商' : '编辑供应商') : '新建供应商' }}</h2>
        <p class="mt-1 text-sm text-slate-500">
          {{ selectedProviderConfigId ? '编辑时 API Key 留空表示保持原值；如需更换请输入新 Key。' : '保存后可被同范围的多个模型复用。' }}
        </p>
        <p v-if="readOnlyProvider" class="mt-2 text-xs font-semibold text-amber-600">管理员全局供应商只读，可随全局模型被使用但不能修改。</p>
      </div>
      <BaseButton
        v-if="selectedProviderConfig && selectedProviderConfig.editable"
        variant="ghost"
        :loading="statusUpdatingProviderConfigId === selectedProviderConfig.id"
        @click="emit('toggleStatus', selectedProviderConfig)"
      >
        {{ selectedProviderConfig.status === 'active' ? '归档供应商' : '恢复供应商' }}
      </BaseButton>
    </div>

    <div class="grid gap-4 xl:grid-cols-2" :class="readOnlyProvider ? 'pointer-events-none opacity-70' : ''">
      <label v-if="!selectedProviderConfigId && canCreateGlobal" class="space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
        <span>供应商范围</span>
        <select v-model="form.scope" class="w-full rounded-md border border-slate-300 bg-white px-3 py-2">
          <option value="personal">个人供应商</option>
          <option value="global">管理员全局供应商</option>
        </select>
      </label>

      <BaseInput
        :model-value="form.name"
        label="供应商配置名称"
        placeholder="例如：OpenAI 工作账号"
        required
        @update:model-value="value => form.name = String(value)"
      />

      <div class="space-y-1.5">
        <label class="ml-1 text-sm font-semibold text-slate-700">供应商</label>
        <SearchableSelect
          :model-value="form.provider_key"
          :options="providerOptions"
          placeholder="请选择供应商"
          :disabled="Boolean(selectedProviderConfigId)"
          @update:model-value="value => form.provider_key = value as string | null"
        />
        <p v-if="currentProvider" class="ml-1 text-xs text-slate-400">{{ currentProvider.provider_adapter }}</p>
      </div>

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
    </div>

    <article class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-6 text-slate-500" :class="readOnlyProvider ? 'opacity-70' : ''">
      当前供应商配置只保存连接信息和密钥。模型 ID、上下文窗口、thinking 与高级 JSON 在模型配置中维护。
      <a
        v-if="currentProvider?.docs_url"
        :href="currentProvider.docs_url"
        target="_blank"
        rel="noreferrer"
        class="ml-2 font-semibold text-indigo-600 underline underline-offset-2"
      >
        {{ currentProvider.label }} 文档
      </a>
    </article>

    <div class="flex justify-end gap-2">
      <BaseButton variant="primary" :loading="savingProviderConfig" :disabled="readOnlyProvider" @click="emit('submit')">
        {{ selectedProviderConfigId ? '保存供应商' : '创建供应商' }}
      </BaseButton>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import SearchableSelect from '@/components/ui/SearchableSelect.vue'
import type { SelectOption } from '@/components/ui/select'
import type { AiLlmConfigScope, LlmProviderCatalogItem, LlmProviderConfigItem } from '@/types/api'

interface LlmProviderFormState {
  scope: AiLlmConfigScope
  name: string
  provider_key: string | null
  base_url: string
  api_key: string
}

const props = defineProps<{
  form: LlmProviderFormState
  selectedProviderConfigId: number | null
  selectedProviderConfig: LlmProviderConfigItem | null
  currentProvider: LlmProviderCatalogItem | null
  providerOptions: SelectOption[]
  savingProviderConfig: boolean
  statusUpdatingProviderConfigId: number | null
  canCreateGlobal: boolean
}>()

const emit = defineEmits<{
  toggleStatus: [config: LlmProviderConfigItem]
  submit: []
}>()

const readOnlyProvider = computed(() => Boolean(props.selectedProviderConfig && !props.selectedProviderConfig.editable))
</script>
