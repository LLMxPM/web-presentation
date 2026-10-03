<!-- 文件功能：平台全局 AI 管理视图，供管理员统一维护全局公共模型/供应商、Models.dev 规格目录同步与平台级 AI 运行时策略。 -->
<template>
  <div class="platform-ai-management space-y-6 pb-16">
    <SettingsPageHeader
      title="平台 AI 管理"
      description="统一维护平台级公共模型、供应商接入凭证与运行时策略。"
      badge="平台管理员"
      badge-tone="accent"
    >
      <template #actions>
        <UiButton variant="secondary" size="sm" :disabled="loading || saving || savingSlot" @click="loadData">
          <RotateCw class="h-3.5 w-3.5" :class="{ 'animate-spin': loading }" />
          <span>刷新</span>
        </UiButton>
        <UiButton variant="primary" size="sm" :loading="saving" :disabled="loading || !isDirty" @click="handleSaveSettings">
          <Save class="h-3.5 w-3.5" />
          <span>保存策略</span>
        </UiButton>
      </template>
    </SettingsPageHeader>

    <UiTabs v-model="activeTab" :items="tabItems" content-class="pt-6">
      <!-- 运行策略与技术参数 -->
      <template #runtime>
        <div class="space-y-6">
          <div class="rounded-ui-xl border border-border bg-surface p-6 shadow-xs space-y-6">
            <div class="border-b border-border-muted pb-4">
              <h2 class="text-base font-semibold text-text">平台 AI 运行策略</h2>
              <p class="mt-1 text-xs text-text-muted">控制平台 AI 服务可用性与流式推理容错参数。</p>
            </div>

            <div class="space-y-5 max-w-2xl">
              <!-- AI 服务总开关 -->
              <div class="flex items-center justify-between rounded-ui-lg border border-border-muted p-4 bg-surface-muted/30">
                <div>
                  <div class="text-sm font-semibold text-text">平台 AI 总开关</div>
                  <div class="text-xs text-text-muted">关闭后全平台禁用 AI 创作者助手与自动化任务生成</div>
                </div>
                <UiCheckbox
                  aria-label="平台 AI 总开关"
                  v-model="systemSettingsForm.ai_enabled"
                  :disabled="isKeyDisabled('ai_enabled')"
                />
              </div>

              <!-- 图片传输模式 -->
              <UiFormField
                label="AI 图片传输与预览模式"
                v-slot="field"
                description="auto 自动择优，url 使用对象存储直链，base64 内嵌二进制 Base64"
              >
                <div class="flex items-center gap-2">
                  <UiSelect
                    :id="field.inputId"
                    :aria-describedby="field.describedBy"
                    v-model="systemSettingsForm.ai_image_transport_mode"
                    :options="imageTransportOptions"
                    :disabled="isKeyDisabled('ai_image_transport_mode')"
                    class="w-full"
                  />
                  <UiBadge v-if="isKeyEnvOverridden('ai_image_transport_mode')" tone="accent">ENV 覆盖</UiBadge>
                </div>
              </UiFormField>

              <!-- 流式空闲超时 -->
              <UiFormField
                label="AI 流式生成无响应空闲超时 (秒)"
                v-slot="field"
                description="防止长上下文或复杂推理模型因下游网络挂死持续占用协调器任务租约"
              >
                <div class="flex items-center gap-2">
                  <UiInput
                    :input-id="field.inputId"
                    :described-by="field.describedBy"
                    v-model.number="systemSettingsForm.ai_agent_stream_idle_timeout_seconds"
                    type="number"
                    :disabled="isKeyDisabled('ai_agent_stream_idle_timeout_seconds')"
                  />
                  <UiBadge v-if="isKeyEnvOverridden('ai_agent_stream_idle_timeout_seconds')" tone="accent">ENV 覆盖</UiBadge>
                </div>
              </UiFormField>

              <!-- LLM HTTP Trace -->
              <div class="flex items-center justify-between rounded-ui-lg border border-border-muted p-4 bg-surface-muted/30">
                <div>
                  <div class="text-sm font-semibold text-text">LLM HTTP 协议网络跟踪</div>
                  <div class="text-xs text-text-muted">开启后在服务端日志中记录发往模型供应商的完整 HTTP 请求与响应报文（自动脱敏密钥）</div>
                </div>
                <UiCheckbox
                  aria-label="LLM HTTP 协议网络跟踪"
                  v-model="systemSettingsForm.ai_llm_http_trace_enabled"
                  :disabled="isKeyDisabled('ai_llm_http_trace_enabled')"
                />
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Models.dev 目录同步 -->
      <template #catalog>
        <div class="space-y-6">
          <div class="rounded-ui-xl border border-border bg-surface p-6 shadow-xs space-y-6">
            <div class="border-b border-border-muted pb-4 flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 class="text-base font-semibold text-text">Models.dev 模型目录管理</h2>
                <p class="mt-1 text-xs text-text-muted">
                  统一管理 Models.dev 模型规格白名单缓存。平台通过白名单接入受信供应商协议，不动态引入外部 SDK。
                </p>
              </div>
              <UiButton
                variant="secondary"
                size="sm"
                :loading="syncingCatalog"
                :disabled="loading || saving || syncingCatalog"
                @click="handleSyncCatalog"
              >
                <RotateCw class="h-3.5 w-3.5" :class="{ 'animate-spin': syncingCatalog }" />
                <span>立即同步目录</span>
              </UiButton>
            </div>

            <div class="space-y-4 max-w-2xl">
              <!-- 自动同步开关 -->
              <div class="flex items-center justify-between rounded-ui-lg border border-border-muted p-4 bg-surface-muted/30">
                <div>
                  <div class="text-sm font-semibold text-text">模型目录自动定时同步</div>
                  <div class="text-xs text-text-muted">系统后台定期拉取 Models.dev 最新模型能力、上下文窗口与推理选项</div>
                </div>
                <UiCheckbox
                  aria-label="模型目录自动定时同步"
                  v-model="systemSettingsForm.ai_model_catalog_sync_enabled"
                  :disabled="isKeyDisabled('ai_model_catalog_sync_enabled')"
                />
              </div>

              <!-- 状态详情卡片 -->
              <div class="rounded-ui-lg border border-border p-4 bg-surface-muted/20 space-y-3">
                <div class="text-xs font-semibold text-text-secondary uppercase tracking-wider">目录缓存当前状态</div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div>
                    <span class="text-text-muted">当前版本: </span>
                    <span class="font-mono font-medium text-text">{{ catalogSyncState?.catalog_version || '未同步 / 本地内置' }}</span>
                  </div>
                  <div>
                    <span class="text-text-muted">上次同步成功: </span>
                    <span class="font-mono font-medium text-text">{{ formatTimestamp(catalogSyncState?.last_success_at) }}</span>
                  </div>
                  <div v-if="catalogSyncState?.last_attempt_at">
                    <span class="text-text-muted">上次尝试时间: </span>
                    <span class="font-mono text-text-secondary">{{ formatTimestamp(catalogSyncState?.last_attempt_at) }}</span>
                  </div>
                  <div v-if="catalogSyncState?.last_error" class="sm:col-span-2 text-danger font-medium">
                    同步异常: {{ catalogSyncState.last_error }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- 全局模型与供应商池 -->
      <template #global-pool>
        <div class="space-y-6">
          <div class="rounded-ui-xl border border-border bg-surface p-6 shadow-xs space-y-6">
            <div class="border-b border-border-muted pb-4">
              <h2 class="text-base font-semibold text-text">全局公共默认槽位绑定</h2>
              <p class="mt-1 text-xs text-text-muted">
                当普通用户未配置自身个人模型或选择「继承平台默认」时，内容助手将使用以下全局配置。
              </p>
            </div>

            <div class="max-w-xl space-y-4">
              <UiFormField label="平台默认内容助手模型" description="全平台用户默认的内容生成与结构化编辑模型" v-slot="field">
                <div class="flex items-center gap-3">
                  <UiSelect
                    :id="field.inputId"
                    :aria-describedby="field.describedBy"
                    v-model="globalSlotModelId"
                    :options="globalModelOptions"
                    :disabled="loading || savingSlot || !loaded"
                    placeholder="请选择全局默认模型"
                    class="w-full"
                  />
                  <UiButton
                    variant="primary"
                    size="sm"
                    :loading="savingSlot"
                    :disabled="loading || !isSlotDirty"
                    @click="handleSaveGlobalSlot"
                  >
                    保存槽位
                  </UiButton>
                </div>
              </UiFormField>
            </div>
          </div>

          <!-- 全局公共模型管理 -->
          <div class="rounded-ui-xl border border-border bg-surface p-6 shadow-xs space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-4 border-b border-border-muted pb-4">
              <div>
                <div class="flex items-center gap-2">
                  <h3 class="text-base font-bold text-text-strong">全局公共模型</h3>
                  <UiBadge tone="neutral" size="sm">{{ filteredGlobalModels.length }} / {{ globalModels.length }}</UiBadge>
                </div>
                <p class="mt-1 text-xs text-text-muted">供全平台用户使用或继承为默认模型。管理员可统一调整可用状态与高级参数。</p>
              </div>
              <div class="flex items-center gap-2">
                <UiButton variant="primary" size="sm" @click="openModelCreateDialog('chat')">
                  <Plus class="h-3.5 w-3.5" />
                  <span>新建全局模型</span>
                </UiButton>
                <UiButton variant="secondary" size="sm" @click="openModelCreateDialog('image_generation')">
                  <Plus class="h-3.5 w-3.5" />
                  <span>新建生图模型</span>
                </UiButton>
              </div>
            </div>

            <!-- 搜索与类型过滤 -->
            <div class="grid gap-3 sm:grid-cols-[minmax(240px,1fr)_180px]">
              <SimpleSearchBar v-model="modelKeyword" placeholder="搜索模型名称、ID 或供应商" />
              <UiSelect v-model="modelTypeFilter" :options="modelTypeOptions" />
            </div>

            <div v-if="globalModels.length === 0" class="py-8 text-center text-sm text-text-muted">
              暂无全局公共模型。点击右上角新建。
            </div>
            <div v-else-if="filteredGlobalModels.length === 0" class="py-8 text-center text-sm text-text-muted">
              没有匹配的模型，请尝试调整搜索关键词或类型筛选。
            </div>
            <div v-else class="rounded-ui-lg border border-border overflow-hidden">
              <AccountAiModelTable
                :items="filteredGlobalModels"
                :default-model-id="globalSlotBinding?.llm_config_id"
                @view="handleViewModel"
                @edit="handleStartEditModel"
                @delete="handleDeleteModel"
              />
            </div>
          </div>

          <!-- 全局供应商凭据管理 -->
          <div class="rounded-ui-xl border border-border bg-surface p-6 shadow-xs space-y-4">
            <div class="flex flex-wrap items-center justify-between gap-4 border-b border-border-muted pb-4">
              <div>
                <div class="flex items-center gap-2">
                  <h3 class="text-base font-bold text-text-strong">全局供应商凭据</h3>
                  <UiBadge tone="neutral" size="sm">{{ filteredGlobalProviders.length }} / {{ globalProviders.length }}</UiBadge>
                </div>
                <p class="mt-1 text-xs text-text-muted">配置平台级 API Key 与 Base URL，可控制供应商状态停用或重新启用。</p>
              </div>
              <div class="flex items-center gap-2">
                <UiButton variant="secondary" size="sm" @click="openProviderCreateDialog('chat')">
                  <Plus class="h-3.5 w-3.5" />
                  <span>连接全局供应商</span>
                </UiButton>
                <UiButton variant="secondary" size="sm" @click="openProviderCreateDialog('image_generation')">
                  <Plus class="h-3.5 w-3.5" />
                  <span>连接生图供应商</span>
                </UiButton>
              </div>
            </div>

            <!-- 搜索与类型过滤 -->
            <div class="grid gap-3 sm:grid-cols-[minmax(240px,1fr)_180px]">
              <SimpleSearchBar v-model="providerKeyword" placeholder="搜索供应商配置名称、Key 或 Base URL" />
              <UiSelect v-model="providerTypeFilter" :options="providerTypeOptions" />
            </div>

            <div v-if="globalProviders.length === 0" class="py-8 text-center text-sm text-text-muted">
              暂无全局供应商凭据。点击右上角连接。
            </div>
            <div v-else-if="filteredGlobalProviders.length === 0" class="py-8 text-center text-sm text-text-muted">
              没有匹配的供应商，请尝试调整搜索关键词或类型筛选。
            </div>
            <div v-else class="rounded-ui-lg border border-border overflow-hidden">
              <AccountAiProviderTable
                :items="filteredGlobalProviders"
                @view="handleViewProvider"
                @edit="handleStartEditProvider"
                @delete="handleDeleteProvider"
              />
            </div>
          </div>
        </div>
      </template>
    </UiTabs>

    <!-- 全局供应商弹窗 -->
    <UiDialog
      :open="providerDialogOpen"
      :title="providerDialogTitle"
      :description="providerDialogDescription"
      size="standard"
      @update:open="providerDialogOpen = $event"
    >
      <template #header-extra>
        <div v-if="providerMode === 'detail'" class="flex items-center gap-1.5">
          <UiButton variant="ghost" size="sm" @click="providerMode = 'edit'">编辑</UiButton>
          <UiButton variant="danger" size="sm" :loading="deletingProviderConfigId === selectedProviderConfig?.id" @click="selectedProviderConfig && handleDeleteProvider(selectedProviderConfig)">删除</UiButton>
        </div>
      </template>
      <AccountAiProviderDetail
        :form="providerForm"
        :selected-provider-config-id="selectedProviderConfigId"
        :selected-provider-config="selectedProviderConfig"
        :mode="providerMode"
        :current-provider="currentProviderForProviderForm"
        :provider-options="providerOptions"
        :saving-provider-config="savingProviderConfig"
        :deleting-provider-config-id="deletingProviderConfigId"
        :can-create-global="false"
        :show-panel-header="false"
        :show-panel-footer="false"
        :embedded-in-dialog="true"
        @cancel="providerDialogOpen = false"
        @edit="providerMode = 'edit'"
        @delete-provider="handleDeleteProvider"
        @submit="handleSubmitProvider"
      />
      <template #footer>
        <UiButton v-if="providerMode === 'detail'" variant="ghost" size="sm" @click="providerDialogOpen = false">关闭</UiButton>
        <UiButton v-else variant="ghost" size="sm" :disabled="savingProviderConfig" @click="providerDialogOpen = false">取消</UiButton>
        <UiButton v-if="providerMode !== 'detail'" size="sm" :loading="savingProviderConfig" :disabled="!providerCanSubmit" @click="handleSubmitProvider">{{ providerMode === 'edit' ? '保存供应商' : '创建供应商' }}</UiButton>
      </template>
    </UiDialog>

    <!-- 全局模型弹窗 -->
    <UiDialog
      :open="modelDialogOpen"
      :title="modelDialogTitle"
      :description="modelDialogDescription"
      size="wide"
      @update:open="modelDialogOpen = $event"
    >
      <template #header-extra>
        <div v-if="modelMode === 'detail'" class="flex items-center gap-1.5">
          <UiButton variant="ghost" size="sm" @click="modelMode = 'edit'">编辑</UiButton>
          <UiButton variant="danger" size="sm" :loading="deletingConfigId === selectedModel?.id" @click="selectedModel && handleDeleteModel(selectedModel)">删除</UiButton>
        </div>
      </template>
      <AccountAiModelDetail
        :form="modelForm"
        :selected-config-id="selectedConfigId"
        :selected-model="selectedModel"
        :mode="modelMode"
        :current-provider="currentProvider"
        :resolved-capability="resolvedCapability ?? null"
        :chat-model-catalog="chatModelCatalog ?? []"
        :provider-config-options="providerConfigOptions"
        :advanced-config-text="advancedConfigText"
        :advanced-config-error="advancedConfigError"
        :advanced-config-collapsed="advancedConfigCollapsed"
        :saving-config="savingConfig"
        :deleting-config-id="deletingConfigId"
        :can-create-global="false"
        :show-panel-header="false"
        :show-panel-footer="false"
        :embedded-in-dialog="true"
        @update:advanced-config-text="advancedConfigText = $event"
        @update:advanced-config-collapsed="advancedConfigCollapsed = $event"
        @cancel="modelDialogOpen = false"
        @edit="modelMode = 'edit'"
        @delete-model="handleDeleteModel"
        @format-advanced="handleFormatAdvancedConfig"
        @submit="handleSubmitModel"
      />
      <template #footer>
        <UiButton v-if="modelMode === 'detail'" variant="ghost" size="sm" @click="modelDialogOpen = false">关闭</UiButton>
        <UiButton v-else variant="ghost" size="sm" :disabled="savingConfig" @click="modelDialogOpen = false">取消</UiButton>
        <UiButton v-if="modelMode !== 'detail'" size="sm" :loading="savingConfig" :disabled="!modelCanSubmit" @click="handleSubmitModel">{{ modelMode === 'edit' ? '保存模型' : '创建模型' }}</UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { Plus, RotateCw, Save } from '@lucide/vue'

import { ADMIN_SETTINGS_QUERY_KEY, fetchAdminSettings, updateAdminSettings } from '@/api/adminSettings'
import {
  getModelCatalogSyncState,
  listLlmConfigs,
  listLlmProviderConfigs,
  listLlmProviders,
  listChatCatalogModels,
  getChatSlotBinding,
  refreshModelCatalog,
  updateLlmSlotBinding,
  createLlmProviderConfig,
  updateLlmProviderConfig,
  deleteLlmProviderConfig,
  createLlmConfig,
  updateLlmConfig,
  deleteLlmConfig,
  resolveLlmModelCapability,
  type LlmConfigUpdatePayload,
  type LlmProviderConfigUpdatePayload,
  type ModelCatalogSyncState,
} from '@/api/llm'
import type { ChatModelCatalogItem } from '@/api/model-config'
import { getErrorMessage } from '@/api/http'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import {
  UiBadge,
  UiButton,
  UiCheckbox,
  UiDialog,
  UiFormField,
  UiInput,
  UiSelect,
  UiTabs,
} from '@/components/ui'
import type { SelectOption } from '@/components/ui/select'
import type {
  AiLlmConfigScope,
  AiModelType,
  LlmConfigItem,
  LlmModelCapabilityItem,
  LlmProviderCatalogItem,
  LlmProviderConfigItem,
  LlmSlotBindingItem,
  RecordStatus,
  SystemSettingItem,
} from '@/types/api'
import AccountAiModelTable from '@/components/account-ai/AccountAiModelTable.vue'
import AccountAiProviderTable from '@/components/account-ai/AccountAiProviderTable.vue'
import AccountAiModelDetail from '@/components/account-ai/AccountAiModelDetail.vue'
import AccountAiProviderDetail from '@/components/account-ai/AccountAiProviderDetail.vue'
import { Message, createConfirm } from '@/utils/message'
import { formatDateTimeInAppTimezone } from '@/utils/timezone'

const queryClient = useQueryClient()
const activeTab = ref('runtime')
const loading = ref(false)
const loaded = ref(false)
const saving = ref(false)
const savingSlot = ref(false)
const syncingCatalog = ref(false)

const settingsItems = ref<SystemSettingItem[]>([])
const catalogSyncState = ref<ModelCatalogSyncState | null>(null)
const globalModels = ref<LlmConfigItem[]>([])
const globalProviders = ref<LlmProviderConfigItem[]>([])
const llmProviders = ref<LlmProviderCatalogItem[]>([])
const globalSlotBinding = ref<LlmSlotBindingItem | null>(null)
const initialGlobalSlotModelId = ref<number | null>(null)
const globalSlotModelId = ref<number | null>(null)

// 供应商检索与过滤状态
const providerKeyword = ref('')
const providerTypeFilter = ref<string>('all')
const providerTypeOptions: SelectOption[] = [
  { label: '全部供应商类型', value: 'all' },
  { label: '对话供应商 (Chat)', value: 'chat' },
  { label: '生图供应商 (Image)', value: 'image_generation' },
]

// 模型检索与过滤状态
const modelKeyword = ref('')
const modelTypeFilter = ref<string>('all')
const modelTypeOptions: SelectOption[] = [
  { label: '全部模型类型', value: 'all' },
  { label: '对话模型 (Chat)', value: 'chat' },
  { label: '生图模型 (Image)', value: 'image_generation' },
]

// 供应商弹窗状态
const providerDialogOpen = ref(false)
const providerMode = ref<'create' | 'edit' | 'detail'>('create')
const selectedProviderConfigId = ref<number | null>(null)
const savingProviderConfig = ref(false)
const deletingProviderConfigId = ref<number | null>(null)

const providerForm = reactive({
  scope: 'global' as AiLlmConfigScope,
  name: '',
  provider_key: null as string | null,
  base_url: '',
  api_key: '',
  status: 'active' as RecordStatus,
})

// 模型弹窗状态
const modelDialogOpen = ref(false)
const modelMode = ref<'create' | 'edit' | 'detail'>('create')
const selectedConfigId = ref<number | null>(null)
const savingConfig = ref(false)
const deletingConfigId = ref<number | null>(null)
const advancedConfigText = ref('{}')
const advancedConfigError = ref('')
const advancedConfigCollapsed = ref(true)
const chatModelCatalog = ref<ChatModelCatalogItem[]>([])
const resolvedCapability = ref<LlmModelCapabilityItem | null>(null)

const modelForm = reactive({
  scope: 'global' as AiLlmConfigScope,
  name: '',
  provider_config_id: null as number | null,
  model_id: '',
  model_type: 'chat' as AiModelType,
  supports_image_input: false,
  context_window_tokens: 128_000,
  status: 'active' as RecordStatus,
})

const systemSettingsForm = reactive<Record<string, any>>({
  ai_enabled: true,
  ai_model_catalog_sync_enabled: true,
  ai_image_transport_mode: 'auto',
  ai_agent_stream_idle_timeout_seconds: 60,
  ai_llm_http_trace_enabled: false,
})

const initialSystemSettingsForm = reactive<Record<string, any>>({})

const tabItems = [
  { value: 'runtime', label: '运行策略与参数' },
  { value: 'catalog', label: 'Models.dev 规格目录' },
  { value: 'global-pool', label: '全局公共模型池' },
]

const imageTransportOptions = [
  { label: '自动判定 (auto)', value: 'auto' },
  { label: '对象存储直链 (url)', value: 'url' },
  { label: '内嵌二进制 Base64 (base64)', value: 'base64' },
]

const globalModelOptions = computed<SelectOption[]>(() => [
  { label: '未指定全局默认模型', value: 0 },
  ...globalModels.value.filter(item => item.model_type === 'chat' && item.status === 'active').map(item => ({
    label: `${item.name} (${item.model_id})`,
    value: item.id,
  })),
])

const filteredGlobalModels = computed(() => {
  const kw = modelKeyword.value.trim().toLowerCase()
  return globalModels.value.filter(item => {
    if (modelTypeFilter.value !== 'all' && (item.model_type ?? 'chat') !== modelTypeFilter.value) {
      return false
    }
    if (!kw) return true
    return (
      item.name.toLowerCase().includes(kw) ||
      item.model_id.toLowerCase().includes(kw) ||
      (item.provider_label && item.provider_label.toLowerCase().includes(kw))
    )
  })
})

const filteredGlobalProviders = computed(() => {
  const kw = providerKeyword.value.trim().toLowerCase()
  return globalProviders.value.filter(item => {
    const type = getProviderConfigType(item)
    if (providerTypeFilter.value !== 'all' && type !== providerTypeFilter.value) {
      return false
    }
    if (!kw) return true
    return (
      item.name.toLowerCase().includes(kw) ||
      item.provider_key.toLowerCase().includes(kw) ||
      (item.provider_label && item.provider_label.toLowerCase().includes(kw)) ||
      (item.base_url && item.base_url.toLowerCase().includes(kw))
    )
  })
})

const isDirty = computed(() => {
  return loaded.value && (
    systemSettingsForm.ai_enabled !== initialSystemSettingsForm.ai_enabled ||
    systemSettingsForm.ai_model_catalog_sync_enabled !== initialSystemSettingsForm.ai_model_catalog_sync_enabled ||
    systemSettingsForm.ai_image_transport_mode !== initialSystemSettingsForm.ai_image_transport_mode ||
    systemSettingsForm.ai_agent_stream_idle_timeout_seconds !== initialSystemSettingsForm.ai_agent_stream_idle_timeout_seconds ||
    systemSettingsForm.ai_llm_http_trace_enabled !== initialSystemSettingsForm.ai_llm_http_trace_enabled
  )
})

const isSlotDirty = computed(() => loaded.value && globalSlotModelId.value !== initialGlobalSlotModelId.value)

const selectedProviderConfig = computed<LlmProviderConfigItem | null>(() => (
  globalProviders.value.find(p => p.id === selectedProviderConfigId.value) ?? null
))

const currentProviderForProviderForm = computed<LlmProviderCatalogItem | null>(() => (
  llmProviders.value.find(p => p.provider_key === providerForm.provider_key) ?? null
))

const providerOptions = computed<SelectOption[]>(() => (
  llmProviders.value.map(provider => ({
    label: provider.label,
    value: provider.provider_key,
    description: getCatalogProviderType(provider) === 'image_generation'
      ? `图片生成供应商${provider.default_image_generation_model_id ? ` · ${provider.default_image_generation_model_id}` : ''}`
      : provider.provider_adapter === 'openai_compatible_chat'
        ? '推理能力由具体模型决定 · 标准 effort 按 Models.dev 开放'
        : '推理能力由具体模型决定 · 支持显式参数控制',
    keywords: [provider.provider_key, provider.provider_adapter],
  }))
))

// 新建全局供应商时，供应商切换自动联动 Base URL 与凭证可用状态
watch(
  () => providerForm.provider_key,
  (newKey, oldKey) => {
    if (providerMode.value !== 'create' || !newKey || newKey === oldKey) return
    const provider = llmProviders.value.find(item => item.provider_key === newKey) ?? null
    if (!provider) return
    providerForm.base_url = provider.supports_base_url ? (provider.default_base_url ?? '') : ''
    if (!provider.supports_api_key) {
      providerForm.api_key = ''
    }
  },
)

const providerCanSubmit = computed(() => Boolean(
  providerForm.name.trim()
  && providerForm.provider_key
  && (!currentProviderForProviderForm.value?.requires_base_url || providerForm.base_url.trim())
))

const providerDialogTitle = computed(() => {
  if (providerMode.value === 'create') return '新建全局供应商'
  if (providerMode.value === 'edit') return selectedProviderConfig.value?.name ? `编辑全局供应商：${selectedProviderConfig.value.name}` : '编辑全局供应商'
  return selectedProviderConfig.value?.name ?? '全局供应商详情'
})

const providerDialogDescription = computed(() => {
  if (providerMode.value === 'detail') return '查看全局供应商连接与凭证状态。'
  return '配置全局供应商协议、服务地址、访问凭证与可用状态，供全平台模型使用。'
})

const selectedModel = computed<LlmConfigItem | null>(() => (
  globalModels.value.find(m => m.id === selectedConfigId.value) ?? null
))

const selectedModelProviderConfig = computed<LlmProviderConfigItem | null>(() => (
  globalProviders.value.find(item => item.id === modelForm.provider_config_id) ?? null
))

const currentProvider = computed<LlmProviderCatalogItem | null>(() => (
  llmProviders.value.find(p => p.provider_key === selectedModelProviderConfig.value?.provider_key) ?? null
))

const providerConfigOptions = computed<SelectOption[]>(() => (
  globalProviders.value
    .filter(config => getProviderConfigType(config) === modelForm.model_type)
    .filter(config => config.status === 'active' || config.id === modelForm.provider_config_id)
    .map(config => ({
      label: config.name,
      value: config.id,
      description: `全局供应商 · ${config.provider_label}${config.status === 'active' ? '' : ' · 停用'}`,
      keywords: [config.provider_key, config.provider_label, config.base_url ?? ''],
    }))
))

const modelCanSubmit = computed(() => Boolean(
  modelForm.name.trim()
  && modelForm.provider_config_id
  && modelForm.model_id.trim()
  && (!currentProvider.value || (currentProvider.value.supported_model_types ?? ['chat']).includes(modelForm.model_type))
))

const modelDialogTitle = computed(() => {
  if (modelMode.value === 'create') return modelForm.model_type === 'image_generation' ? '新建全局生图模型' : '新建全局模型'
  if (modelMode.value === 'edit') return selectedModel.value?.name ? `编辑全局模型：${selectedModel.value.name}` : '编辑全局模型'
  return selectedModel.value?.name ?? '全局模型详情'
})

const modelDialogDescription = computed(() => {
  if (modelMode.value === 'detail') return '查看全局模型能力与配置。'
  return '配置全局模型能力、可用状态与高级参数，供全平台使用或作为默认槽位。'
})

function getCatalogProviderType(provider: LlmProviderCatalogItem | null | undefined): AiModelType {
  if (provider?.provider_type) return provider.provider_type
  return (provider?.supported_model_types ?? ['chat']).includes('chat') ? 'chat' : 'image_generation'
}

function findProviderForConfig(config: LlmProviderConfigItem | null | undefined): LlmProviderCatalogItem | null {
  if (!config) return null
  return llmProviders.value.find(item => item.provider_key === config.provider_key) ?? null
}

function getProviderConfigType(config: LlmProviderConfigItem): AiModelType {
  return config.provider_type ?? getCatalogProviderType(findProviderForConfig(config))
}

watch(
  () => [selectedModelProviderConfig.value?.provider_key, modelDialogOpen.value] as const,
  async ([providerKey, isOpen]) => {
    if (!isOpen || !providerKey) {
      chatModelCatalog.value = []
      return
    }
    try {
      chatModelCatalog.value = await listChatCatalogModels(providerKey)
    } catch {
      chatModelCatalog.value = []
    }
  },
  { immediate: true },
)

watch(
  () => [modelForm.provider_config_id, modelForm.model_id, modelForm.model_type] as const,
  async ([providerConfigId, modelId, modelType]) => {
    if (modelType !== 'chat' || !providerConfigId || !modelId?.trim()) {
      resolvedCapability.value = null
      return
    }
    try {
      const capability = await resolveLlmModelCapability(providerConfigId, modelId.trim())
      resolvedCapability.value = capability
      if (modelMode.value === 'create') {
        modelForm.supports_image_input = capability.supports_image_input
      }
    } catch {
      resolvedCapability.value = null
    }
  },
  { immediate: true },
)

function parseAdvancedConfig(): Record<string, unknown> {
  const trimmed = advancedConfigText.value.trim()
  if (!trimmed) return {}
  const parsed = JSON.parse(trimmed)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('高级配置必须为 JSON 对象。')
  }
  return parsed as Record<string, unknown>
}

function handleFormatAdvancedConfig() {
  try {
    advancedConfigText.value = JSON.stringify(parseAdvancedConfig(), null, 2)
    advancedConfigError.value = ''
  } catch (error) {
    advancedConfigError.value = getErrorMessage(error, '高级配置 JSON 格式不合法')
  }
}

function normalizePositiveInteger(value: unknown, fallback: number): number {
  const parsed = typeof value === 'number' ? value : Number.parseInt(String(value ?? ''), 10)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

function openProviderCreateDialog(modelType: AiModelType = 'chat') {
  providerMode.value = 'create'
  selectedProviderConfigId.value = null
  providerForm.scope = 'global'
  providerForm.name = ''
  providerForm.status = 'active'
  const matchingProviders = llmProviders.value.filter(item => getCatalogProviderType(item) === modelType)
  const provider = matchingProviders.find(p => p.provider_key === 'deepseek') ?? matchingProviders[0]
  providerForm.provider_key = provider?.provider_key ?? null
  providerForm.base_url = provider?.supports_base_url ? provider.default_base_url ?? '' : ''
  providerForm.api_key = ''
  providerDialogOpen.value = true
}

function handleViewProvider(config: LlmProviderConfigItem) {
  providerMode.value = 'detail'
  selectedProviderConfigId.value = config.id
  providerForm.scope = 'global'
  providerForm.name = config.name
  providerForm.provider_key = config.provider_key
  providerForm.base_url = config.base_url ?? ''
  providerForm.api_key = ''
  providerForm.status = config.status ?? 'active'
  providerDialogOpen.value = true
}

function handleStartEditProvider(config?: LlmProviderConfigItem) {
  if (config) {
    selectedProviderConfigId.value = config.id
    providerForm.scope = 'global'
    providerForm.name = config.name
    providerForm.provider_key = config.provider_key
    providerForm.base_url = config.base_url ?? ''
    providerForm.api_key = ''
    providerForm.status = config.status ?? 'active'
  }
  providerMode.value = 'edit'
  providerDialogOpen.value = true
}

async function handleSubmitProvider() {
  const providerKey = providerForm.provider_key
  const provider = currentProviderForProviderForm.value
  if (!providerForm.name.trim() || !providerKey) {
    Message.error('请填写供应商配置名称并选择供应商。')
    return
  }
  const baseUrl = providerForm.base_url.trim() || null
  const apiKey = providerForm.api_key.trim() || null
  if (provider?.requires_base_url && !baseUrl) {
    Message.error('当前供应商必须填写 Base URL。')
    return
  }

  savingProviderConfig.value = true
  try {
    if (selectedProviderConfigId.value) {
      const updatePayload: LlmProviderConfigUpdatePayload = {
        name: providerForm.name.trim(),
        base_url: baseUrl,
        status: providerForm.status,
      }
      if (apiKey) {
        updatePayload.api_key = apiKey
      }
      const updated = await updateLlmProviderConfig(selectedProviderConfigId.value, updatePayload)
      globalProviders.value = globalProviders.value.map(p => p.id === updated.id ? updated : p)
      providerDialogOpen.value = false
      Message.success('全局供应商已更新。')
    } else {
      const created = await createLlmProviderConfig({
        name: providerForm.name.trim(),
        scope: 'global',
        provider_key: providerKey,
        provider_type: getCatalogProviderType(provider),
        base_url: baseUrl,
        api_key: apiKey,
      })
      globalProviders.value = [created, ...globalProviders.value.filter(p => p.id !== created.id)]
      providerDialogOpen.value = false
      Message.success('全局供应商已创建。')
    }
    await queryClient.invalidateQueries({ queryKey: ['llm-provider-configs'] })
  } catch (error) {
    Message.error(getErrorMessage(error, '保存全局供应商失败。'))
  } finally {
    savingProviderConfig.value = false
  }
}

async function handleDeleteProvider(config: LlmProviderConfigItem) {
  const confirmed = await createConfirm(
    `确认删除全局供应商「${config.name}」吗？删除前必须先删除所有关联模型。`,
    '删除全局供应商',
  )
  if (!confirmed) return

  deletingProviderConfigId.value = config.id
  try {
    await deleteLlmProviderConfig(config.id)
    globalProviders.value = globalProviders.value.filter(item => item.id !== config.id)
    if (selectedProviderConfigId.value === config.id) {
      selectedProviderConfigId.value = null
      providerDialogOpen.value = false
    }
    Message.success('全局供应商已删除。')
    await queryClient.invalidateQueries({ queryKey: ['llm-provider-configs'] })
  } catch (error) {
    Message.error(getErrorMessage(error, '删除全局供应商失败。'))
  } finally {
    deletingProviderConfigId.value = null
  }
}

function openModelCreateDialog(modelType: AiModelType = 'chat') {
  modelMode.value = 'create'
  selectedConfigId.value = null
  modelForm.scope = 'global'
  modelForm.model_type = modelType
  modelForm.name = ''
  modelForm.status = 'active'
  const providerConfig = globalProviders.value.find(p => getProviderConfigType(p) === modelType)
  modelForm.provider_config_id = providerConfig?.id ?? null
  const provider = findProviderForConfig(providerConfig)
  modelForm.model_id = modelType === 'image_generation'
    ? provider?.default_image_generation_model_id ?? ''
    : provider?.default_model_id ?? ''
  modelForm.supports_image_input = Boolean(provider?.default_supports_image_input)
  modelForm.context_window_tokens = 128_000
  advancedConfigText.value = '{}'
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
  modelDialogOpen.value = true
}

function handleViewModel(config: LlmConfigItem) {
  modelMode.value = 'detail'
  selectedConfigId.value = config.id
  modelForm.scope = 'global'
  modelForm.name = config.name
  modelForm.provider_config_id = config.provider_config_id
  modelForm.model_type = config.model_type ?? 'chat'
  modelForm.model_id = config.model_id
  modelForm.supports_image_input = config.supports_image_input
  modelForm.context_window_tokens = config.context_window_tokens
  modelForm.status = config.status ?? 'active'
  advancedConfigText.value = JSON.stringify(config.advanced_config_json ?? {}, null, 2)
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
  modelDialogOpen.value = true
}

function handleStartEditModel(config?: LlmConfigItem) {
  if (config) {
    selectedConfigId.value = config.id
    modelForm.scope = 'global'
    modelForm.name = config.name
    modelForm.provider_config_id = config.provider_config_id
    modelForm.model_type = config.model_type ?? 'chat'
    modelForm.model_id = config.model_id
    modelForm.supports_image_input = config.supports_image_input
    modelForm.context_window_tokens = config.context_window_tokens
    modelForm.status = config.status ?? 'active'
    advancedConfigText.value = JSON.stringify(config.advanced_config_json ?? {}, null, 2)
    advancedConfigError.value = ''
    advancedConfigCollapsed.value = true
  }
  modelMode.value = 'edit'
  modelDialogOpen.value = true
}

async function handleSubmitModel() {
  const providerConfigId = modelForm.provider_config_id
  if (!modelForm.name.trim() || !providerConfigId || !modelForm.model_id.trim()) {
    Message.error('请先填写模型名称、供应商配置和模型 ID。')
    return
  }

  let advancedConfig: Record<string, unknown>
  try {
    advancedConfig = parseAdvancedConfig()
  } catch {
    Message.error('高级 JSON 配置不合法。')
    return
  }

  const contextWindowTokens = normalizePositiveInteger(modelForm.context_window_tokens, 128_000)

  savingConfig.value = true
  try {
    if (selectedConfigId.value) {
      const updatePayload: LlmConfigUpdatePayload = {
        name: modelForm.name.trim(),
        provider_config_id: providerConfigId,
        model_id: modelForm.model_id.trim(),
        model_type: modelForm.model_type,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: contextWindowTokens,
        advanced_config_json: advancedConfig,
        status: modelForm.status,
      }
      const updated = await updateLlmConfig(selectedConfigId.value, updatePayload)
      globalModels.value = globalModels.value.map(m => m.id === updated.id ? updated : m)
      modelDialogOpen.value = false
      Message.success('全局模型已更新。')
    } else {
      const created = await createLlmConfig({
        name: modelForm.name.trim(),
        scope: 'global',
        provider_config_id: providerConfigId,
        model_id: modelForm.model_id.trim(),
        model_type: modelForm.model_type,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: contextWindowTokens,
        advanced_config_json: advancedConfig,
      })
      globalModels.value = [created, ...globalModels.value.filter(m => m.id !== created.id)]
      modelDialogOpen.value = false
      Message.success('全局模型已创建。')
    }
    await queryClient.invalidateQueries({ queryKey: ['llm-configs'] })
  } catch (error) {
    Message.error(getErrorMessage(error, '保存全局模型失败。'))
  } finally {
    savingConfig.value = false
  }
}

async function handleDeleteModel(config: LlmConfigItem) {
  const confirmed = await createConfirm(
    `确认删除全局模型「${config.name}」吗？删除后已关联会话无法继续发起运行，相关全局默认槽位会自动解除。`,
    '删除全局模型',
  )
  if (!confirmed) return

  deletingConfigId.value = config.id
  try {
    await deleteLlmConfig(config.id)
    globalModels.value = globalModels.value.filter(item => item.id !== config.id)
    if (selectedConfigId.value === config.id) {
      selectedConfigId.value = null
      modelDialogOpen.value = false
    }
    if (globalSlotModelId.value === config.id) {
      globalSlotModelId.value = 0
      initialGlobalSlotModelId.value = 0
    }
    Message.success('全局模型已删除。')
    await queryClient.invalidateQueries({ queryKey: ['llm-configs'] })
  } catch (error) {
    Message.error(getErrorMessage(error, '删除全局模型失败。'))
  } finally {
    deletingConfigId.value = null
  }
}

/** 未取得快照时保持只读，环境变量覆盖项由部署配置管理。 */
function isKeyDisabled(key: string): boolean {
  const item = settingsItems.value.find(s => s.key === key)
  return loading.value || saving.value || !loaded.value || Boolean(item?.is_env_overridden)
}

/** 查询字段的环境变量覆盖状态，用于展示来源。 */
function isKeyEnvOverridden(key: string): boolean {
  const item = settingsItems.value.find(s => s.key === key)
  return Boolean(item?.is_env_overridden)
}

/** 同步时间遵循后端业务时区；历史无时区值统一补 UTC。 */
function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return '无记录'
  return formatDateTimeInAppTimezone(ts)
}

/**
 * 完整拉取系统设置、Models.dev 状态与全局模型池。
 */
async function loadData(): Promise<void> {
  loading.value = true
  try {
    const [settingsRes, catalogRes, allModels, allProviders, coordinatorSlot, catalogProviders] = await Promise.all([
      fetchAdminSettings(),
      getModelCatalogSyncState(),
      listLlmConfigs(),
      listLlmProviderConfigs(),
      getChatSlotBinding('agent_coordinator', 'global'),
      listLlmProviders(),
    ])

    applySettingsSnapshot(settingsRes)
    catalogSyncState.value = catalogRes
    llmProviders.value = catalogProviders

    // 过滤 global scope 的模型与凭据
    globalModels.value = allModels.filter(m => m.scope === 'global')
    globalProviders.value = allProviders.filter(p => p.scope === 'global')

    // 获取全局默认槽位
    globalSlotBinding.value = coordinatorSlot
    globalSlotModelId.value = coordinatorSlot?.llm_config_id ?? 0
    initialGlobalSlotModelId.value = coordinatorSlot?.llm_config_id ?? 0
    loaded.value = true
  } catch (err) {
    Message.error(getErrorMessage(err, '加载平台 AI 管理数据失败'))
  } finally {
    loading.value = false
  }
}

/** 更新策略表单与共享告警快照，不覆盖尚未保存的全局槽位草稿。 */
function applySettingsSnapshot(snapshot: Awaited<ReturnType<typeof fetchAdminSettings>>): void {
  settingsItems.value = snapshot.items
  queryClient.setQueryData(ADMIN_SETTINGS_QUERY_KEY, snapshot)
  for (const item of snapshot.items) {
    if (item.key in systemSettingsForm) {
      systemSettingsForm[item.key] = item.value
      initialSystemSettingsForm[item.key] = item.value
    }
  }
}

/**
 * 保存 AI 运行策略与系统参数。
 */
async function handleSaveSettings(): Promise<void> {
  if (!loaded.value || loading.value || saving.value) return
  saving.value = true
  try {
    const payload = Object.fromEntries(Object.entries(systemSettingsForm).filter(([key]) => !isKeyEnvOverridden(key)))
    if ('ai_agent_stream_idle_timeout_seconds' in payload) {
      payload.ai_agent_stream_idle_timeout_seconds = Number(payload.ai_agent_stream_idle_timeout_seconds)
    }
    applySettingsSnapshot(await updateAdminSettings(payload))
    Message.success('平台 AI 策略已更新并即时热生效。')
  } catch (err) {
    Message.error(getErrorMessage(err, '保存平台 AI 策略失败'))
  } finally {
    saving.value = false
  }
}

/**
 * 保存全局默认模型槽位绑定。
 */
async function handleSaveGlobalSlot(): Promise<void> {
  if (!loaded.value || loading.value || savingSlot.value) return
  savingSlot.value = true
  try {
    const targetId = globalSlotModelId.value === 0 ? null : globalSlotModelId.value
    globalSlotBinding.value = await updateLlmSlotBinding('agent_coordinator', targetId, 'global')
    Message.success('全局默认模型槽位已更新。')
    initialGlobalSlotModelId.value = targetId ?? 0
  } catch (err) {
    Message.error(getErrorMessage(err, '更新全局默认模型槽位失败'))
  } finally {
    savingSlot.value = false
  }
}

/**
 * 手动同步 Models.dev 目录。
 */
async function handleSyncCatalog(): Promise<void> {
  syncingCatalog.value = true
  try {
    const res = await refreshModelCatalog()
    catalogSyncState.value = res
    Message.success('已成功同步 Models.dev 模型目录。')
  } catch (err) {
    Message.error(getErrorMessage(err, '同步 Models.dev 目录失败'))
  } finally {
    syncingCatalog.value = false
  }
}

onMounted(() => {
  void loadData()
})
</script>
