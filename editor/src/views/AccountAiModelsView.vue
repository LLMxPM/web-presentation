<!-- 文件功能：个人设置 - 模型连接视图，管理账号可见的大语言模型、独立生图模型、供应商凭证以及核心能力槽位绑定。 -->
<template>
  <div class="account-ai-models-view space-y-6 pb-16">
    <SettingsPageHeader
      title="模型连接"
      description="维护个人 AI 模型的能力槽位绑定、规格目录与供应商凭据。"
    >
      <template #actions>
        <UiButton
          variant="secondary"
          size="sm"
          :loading="refreshingCatalog"
          @click="handleRefreshCatalog"
        >
          <RotateCw class="h-3.5 w-3.5" :class="{ 'animate-spin': refreshingCatalog }" />
          <span>刷新规格目录</span>
        </UiButton>
      </template>
    </SettingsPageHeader>

    <!-- 助手配置 / 模型管理 / 供应商管理三视图 -->
    <section class="rounded-ui-xl border border-border bg-surface p-5 shadow-xs">
      <UiTabs :model-value="activeTab" :items="tabItems" @update:model-value="handleTabChange">
        <!-- 助手配置：核心能力槽位绑定 -->
        <template #assistant>
          <div class="space-y-4 pt-4">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border-muted pb-3">
              <div>
                <h2 class="text-base font-bold text-text-strong">核心能力槽位</h2>
                <p class="mt-0.5 text-xs text-text-muted">为智能体分别绑定内容生成、图片理解与图片生成模型，单项修改独立生效。</p>
              </div>
              <div class="flex items-center gap-2">
                <span class="rounded-lg border border-border bg-canvas px-3 py-1.5 text-xs font-semibold text-text-secondary">
                  内容模型：{{ contentSlot?.llm_config_name || '未绑定' }}
                </span>
              </div>
            </div>

            <div class="overflow-x-auto rounded-ui-lg border border-border">
              <table class="w-full min-w-[880px] table-fixed text-left text-sm">
                <thead class="bg-canvas text-xs font-semibold text-text-muted">
                  <tr>
                    <th class="w-36 px-4 py-3 whitespace-nowrap">能力槽位</th>
                    <th class="px-4 py-3 whitespace-nowrap">当前绑定模型</th>
                    <th class="w-28 px-4 py-3 whitespace-nowrap">来源</th>
                    <th class="w-24 px-4 py-3 whitespace-nowrap">状态</th>
                    <th class="w-[380px] px-4 py-3 whitespace-nowrap">切换模型</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-border-muted bg-surface">
                  <tr v-for="row in slotRows" :key="row.slot">
                    <td class="px-4 py-4 font-semibold text-text-strong whitespace-nowrap">{{ row.label }}</td>
                    <td class="px-4 py-4">
                      <p class="truncate font-semibold text-text">{{ row.binding?.llm_config_name || '未绑定模型' }}</p>
                      <p class="mt-0.5 truncate text-xs text-text-muted">
                        {{ row.binding?.provider_label || '—' }}<span v-if="row.binding?.model_id"> · {{ row.binding.model_id }}</span>
                      </p>
                    </td>
                    <td class="px-4 py-4 text-xs font-semibold text-text-secondary whitespace-nowrap">
                      {{ row.binding?.inherited_from_global ? '继承全局' : '个人配置' }}
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap">
                      <span class="font-semibold" :class="row.binding?.binding_ready ? 'text-success-strong' : 'text-warning-strong'">
                        {{ row.binding?.binding_ready ? '可用' : '待配置' }}
                      </span>
                    </td>
                    <td class="px-4 py-3">
                      <div class="flex items-center gap-2">
                        <UiCombobox
                          class="min-w-0 flex-1"
                          :model-value="slotDrafts[row.slot] ?? null"
                          :options="row.options"
                          clearable
                          size="compact"
                          placeholder="选择模型"
                          @update:model-value="slotDrafts[row.slot] = $event === null ? null : Number($event)"
                        />
                        <UiButton
                          size="sm"
                          :loading="bindingSlot === row.slot"
                          @click="handleSaveSlot(row.slot, 'personal')"
                        >
                          保存
                        </UiButton>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="allConfigs.length === 0" class="rounded-ui-lg border border-warning-border bg-warning-muted px-4 py-3 text-sm text-warning-strong">
              还没有可绑定模型，请先在「供应商管理」连接供应商，再到「模型管理」从目录添加模型。
            </div>
          </div>
        </template>

        <!-- 模型管理：聊天与生图模型合并列表 -->
        <template #models>
          <div class="space-y-4 pt-4">
            <header class="flex flex-wrap items-center justify-between gap-4 border-b border-border-muted pb-3">
              <div>
                <h2 class="text-base font-bold text-text-strong">模型列表 ({{ filteredModels.length }})</h2>
                <p class="mt-0.5 text-xs" :class="catalogSyncState?.last_error ? 'text-warning-strong' : 'text-text-muted'">{{ catalogStatusText }}</p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <UiButton size="sm" @click="openModelCreateDialog('chat')">
                  <Plus class="h-3.5 w-3.5" />
                  <span>新建聊天模型</span>
                </UiButton>
                <UiButton size="sm" @click="openModelCreateDialog('image_generation')">
                  <Plus class="h-3.5 w-3.5" />
                  <span>新建生图模型</span>
                </UiButton>
              </div>
            </header>

            <div class="grid gap-3 sm:grid-cols-[minmax(240px,1fr)_180px_200px]">
              <SimpleSearchBar v-model="modelKeyword" placeholder="搜索模型名称、ID 或供应商" />
              <UiSelect v-model="modelTypeFilter" :options="modelTypeOptions" />
              <UiSelect v-model="modelProviderFilter" :options="modelProviderOptions" />
            </div>

            <DataState :state="modelDataState" :title="modelEmptyTitle">
              <div class="rounded-ui-lg border border-border">
                <AccountAiModelTable
                  :items="filteredModels"
                  @view="openModelDetailDialog"
                  @edit="openModelEditDialog"
                  @delete="handleDeleteModel"
                />
              </div>
            </DataState>
          </div>
        </template>

        <!-- 供应商管理：聊天与生图供应商合并列表 -->
        <template #providers>
          <div class="space-y-4 pt-4">
            <header class="flex flex-wrap items-center justify-between gap-4 border-b border-border-muted pb-3">
              <div>
                <h2 class="text-base font-bold text-text-strong">供应商列表 ({{ filteredProviders.length }})</h2>
                <p class="mt-0.5 text-xs text-text-muted">配置用于驱动模型调用的供应商接入凭据与连接地址。</p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <UiButton variant="secondary" size="sm" @click="openProviderCreateDialog('chat')">
                  <Plus class="h-3.5 w-3.5" />
                  <span>连接聊天供应商</span>
                </UiButton>
                <UiButton variant="secondary" size="sm" @click="openProviderCreateDialog('image_generation')">
                  <Plus class="h-3.5 w-3.5" />
                  <span>连接生图供应商</span>
                </UiButton>
              </div>
            </header>

            <div class="grid gap-3 sm:grid-cols-[minmax(240px,1fr)_180px]">
              <SimpleSearchBar v-model="providerKeyword" placeholder="搜索供应商配置名称、Key 或显示名" />
              <UiSelect v-model="providerTypeFilter" :options="providerTypeOptions" />
            </div>

            <DataState :state="providerDataState" :title="providerEmptyTitle">
              <div class="rounded-ui-lg border border-border">
                <AccountAiProviderTable
                  :items="filteredProviders"
                  @view="openProviderDetailDialog"
                  @edit="openProviderEditDialog"
                  @delete="handleDeleteProviderConfig"
                />
              </div>
            </DataState>
          </div>
        </template>
      </UiTabs>
    </section>

    <!-- 供应商编辑/新建/详情弹窗 -->
    <UiDialog
      :open="providerDialogOpen"
      :title="providerDialogTitle"
      :description="providerDialogDescription"
      size="standard"
      @update:open="handleProviderDialogVisibility"
    >
      <template #header-extra>
        <div v-if="providerPanelMode === 'detail' && selectedProviderConfig?.editable" class="flex items-center gap-1.5">
          <UiButton variant="ghost" size="sm" @click="handleStartEditProviderConfig">编辑</UiButton>
          <UiButton variant="danger" size="sm" :loading="deletingProviderConfigId === selectedProviderConfig.id" @click="handleDeleteProviderConfig(selectedProviderConfig)">删除</UiButton>
        </div>
      </template>
      <AccountAiProviderDetail
        v-bind="providerDetailProps"
        @cancel="handleCancelProviderDialogEdit"
        @edit="handleStartEditProviderConfig"
        @delete-provider="handleDeleteProviderConfig"
        @submit="handleSubmitProviderConfig"
      />
      <template #footer>
        <UiButton v-if="providerPanelMode === 'detail'" variant="ghost" size="sm" @click="providerDialogOpen = false">关闭</UiButton>
        <UiButton v-else variant="ghost" size="sm" :disabled="savingProviderConfig" @click="handleCancelProviderDialogEdit">取消</UiButton>
        <UiButton v-if="providerPanelMode !== 'detail'" size="sm" :loading="savingProviderConfig" :disabled="!providerCanSubmit" @click="handleSubmitProviderConfig">
          {{ providerPanelMode === 'edit' ? '保存供应商' : '创建供应商' }}
        </UiButton>
      </template>
    </UiDialog>

    <!-- 模型编辑/新建/详情弹窗 -->
    <UiDialog
      :open="modelDialogOpen"
      :title="modelDialogTitle"
      :description="modelDialogDescription"
      size="wide"
      @update:open="handleModelDialogVisibility"
    >
      <template #header-extra>
        <div v-if="modelPanelMode === 'detail' && selectedModel?.editable" class="flex items-center gap-1.5">
          <UiButton variant="ghost" size="sm" @click="handleStartEditModel">编辑</UiButton>
          <UiButton variant="danger" size="sm" :loading="deletingConfigId === selectedModel.id" @click="handleDeleteModel(selectedModel)">删除</UiButton>
        </div>
      </template>
      <AccountAiModelDetail
        v-bind="modelDetailProps"
        @cancel="handleCancelModelDialogEdit"
        @edit="handleStartEditModel"
        @delete-model="handleDeleteModel"
        @format-advanced="formatAdvancedConfig"
        @submit="handleSubmitModel"
        @update:advanced-config-text="advancedConfigText = $event"
        @update:advanced-config-collapsed="advancedConfigCollapsed = $event"
      />
      <template #footer>
        <UiButton v-if="modelPanelMode === 'detail'" variant="ghost" size="sm" @click="modelDialogOpen = false">关闭</UiButton>
        <UiButton v-else variant="ghost" size="sm" :disabled="savingConfig" @click="handleCancelModelDialogEdit">取消</UiButton>
        <UiButton v-if="modelPanelMode !== 'detail'" variant="ghost" size="sm" :disabled="modelReadOnly" @click="formatAdvancedConfig">格式化 JSON</UiButton>
        <UiButton v-if="modelPanelMode !== 'detail'" size="sm" :loading="savingConfig" :disabled="modelReadOnly || !modelCanSubmit" @click="handleSubmitModel">
          {{ modelPanelMode === 'edit' ? '保存模型' : '创建模型' }}
        </UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import { Plus, RotateCw } from '@lucide/vue'

import {
  createLlmConfig,
  createLlmProviderConfig,
  deleteLlmConfig,
  deleteLlmProviderConfig,
  listLlmConfigs,
  listLlmProviderConfigs,
  listLlmProviders,
  listChatCatalogModels,
  getModelCatalogSyncState,
  refreshModelCatalog,
  resolveLlmModelCapability,
  listLlmSlots,
  updateLlmConfig,
  updateLlmProviderConfig,
  updateLlmSlotBinding,
} from '@/api/llm'
import type { ModelCatalogSyncState } from '@/api/llm'
import type { ChatModelCatalogItem } from '@/api/model-config'
import { listAgentConfigs } from '@/api/agent-config'
import { getErrorMessage } from '@/api/http'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import AccountAiModelTable from '@/components/account-ai/AccountAiModelTable.vue'
import AccountAiProviderTable from '@/components/account-ai/AccountAiProviderTable.vue'
import AccountAiModelDetail from '@/components/account-ai/AccountAiModelDetail.vue'
import AccountAiProviderDetail from '@/components/account-ai/AccountAiProviderDetail.vue'
import SimpleSearchBar from '@/components/patterns/SimpleSearchBar.vue'
import DataState from '@/components/patterns/DataState.vue'
import { UiButton, UiCombobox, UiDialog, UiSelect, UiTabs } from '@/components/ui'
import type { SelectOption } from '@/components/ui/select'
import type {
  AiLlmConfigScope,
  AiModelType,
  LlmConfigItem,
  LlmModelCapabilityItem,
  LlmProviderCatalogItem,
  LlmProviderConfigItem,
  RecordStatus,
} from '@/types/api'
import { formatDateTime } from '@/utils/format'
import { Message, createConfirm } from '@/utils/message'

type ConfigPanelMode = 'create' | 'detail' | 'edit'
/** 设置中心的三个视图 Tab；聊天与生图在模型/供应商视图内用类型筛选区分。 */
type SettingsTab = 'assistant' | 'models' | 'providers'
type SettingsTypeFilter = 'all' | AiModelType

const SETTINGS_TABS: SettingsTab[] = ['assistant', 'models', 'providers']

/** 解析路由 tab 参数，未知取值回落到助手配置。 */
function resolveSettingsTab(raw: unknown): SettingsTab {
  const value = String(raw ?? '')
  return (SETTINGS_TABS as string[]).includes(value) ? value as SettingsTab : 'assistant'
}

const DEFAULT_CONTEXT_WINDOW_TOKENS = 200000
const DEFAULT_NEW_MODEL_PROVIDER_KEY = 'deepseek'

interface LlmFormState {
  scope: AiLlmConfigScope
  name: string
  provider_config_id: number | null
  model_id: string
  model_type: AiModelType
  supports_image_input: boolean
  context_window_tokens: number
  status: RecordStatus
}

interface LlmProviderFormState {
  scope: AiLlmConfigScope
  name: string
  provider_key: string | null
  base_url: string
  api_key: string
  status: RecordStatus
}

const queryClient = useQueryClient()
const route = useRoute()
const router = useRouter()

const activeTab = ref<SettingsTab>(resolveSettingsTab(route.query.tab))
const tabItems = [
  { label: '助手配置', value: 'assistant' },
  { label: '模型管理', value: 'models' },
  { label: '供应商管理', value: 'providers' },
]

const modelKeyword = ref('')
const providerKeyword = ref('')
const modelTypeFilter = ref<SettingsTypeFilter>('all')
const providerTypeFilter = ref<SettingsTypeFilter>('all')
const modelProviderFilter = ref('all')

const modelTypeOptions = [
  { label: '全部模型类型', value: 'all' },
  { label: '聊天 / 图片理解', value: 'chat' },
  { label: '图片生成', value: 'image_generation' },
]
const providerTypeOptions = [
  { label: '全部供应商类型', value: 'all' },
  { label: '聊天供应商', value: 'chat' },
  { label: '生图供应商', value: 'image_generation' },
]

const slotDrafts = reactive<Record<string, number | null>>({})
const bindingSlot = ref<string | null>(null)

const selectedProviderConfigId = ref<number | null>(null)
const providerPanelMode = ref<ConfigPanelMode>('create')
const savingProviderConfig = ref(false)
const deletingProviderConfigId = ref<number | null>(null)
const applyingExistingProviderConfig = ref(false)
const providerDialogOpen = ref(false)
const providerDialogBaseline = ref('')

const selectedConfigId = ref<number | null>(null)
const modelPanelMode = ref<ConfigPanelMode>('create')
const advancedConfigText = ref('{}')
const advancedConfigError = ref('')
const advancedConfigCollapsed = ref(true)
const savingConfig = ref(false)
const refreshingCatalog = ref(false)
const deletingConfigId = ref<number | null>(null)
const applyingExistingModel = ref(false)
const modelDialogOpen = ref(false)
const modelDialogBaseline = ref('')

const modelForm = reactive<LlmFormState>({
  scope: 'personal',
  name: '',
  provider_config_id: null,
  model_id: '',
  model_type: 'chat',
  supports_image_input: false,
  context_window_tokens: DEFAULT_CONTEXT_WINDOW_TOKENS,
  status: 'active',
})

const providerForm = reactive<LlmProviderFormState>({
  scope: 'personal',
  name: '',
  provider_key: null,
  base_url: '',
  api_key: '',
  status: 'active',
})

const resolvedCapability = ref<LlmModelCapabilityItem | null>(null)
let capabilityRequestSequence = 0

// 查询服务
const providersQuery = useQuery({ queryKey: ['llm-providers'], queryFn: listLlmProviders })
const configsQuery = useQuery({ queryKey: ['llm-configs'], queryFn: listLlmConfigs })
const providerConfigsQuery = useQuery({ queryKey: ['llm-provider-configs'], queryFn: listLlmProviderConfigs })
const slotsQuery = useQuery({ queryKey: ['llm-slots'], queryFn: listLlmSlots })
const agentConfigsQuery = useQuery({ queryKey: ['agent-configs'], queryFn: listAgentConfigs })
const catalogSyncQuery = useQuery<ModelCatalogSyncState>({
  queryKey: ['model-catalog-sync'],
  queryFn: getModelCatalogSyncState,
  refetchInterval: query => query.state.data?.syncing ? 2_000 : false,
})

const allConfigs = computed(() => configsQuery.data.value ?? [])
const allProviderConfigs = computed(() => providerConfigsQuery.data.value ?? [])
const catalogSyncState = computed(() => catalogSyncQuery.data.value ?? null)

const agentConfig = computed(() => agentConfigsQuery.data.value?.[0] ?? null)
const contentSlot = computed(() => {
  const contentSlotKey = agentConfig.value?.llm_slot || 'agent_coordinator'
  return slotsQuery.data.value?.find(slot => slot.slot === contentSlotKey) ?? null
})

// 槽位行
const slotRows = computed(() => {
  const contentSlotKey = agentConfig.value?.llm_slot || 'agent_coordinator'
  return [
    { slot: contentSlotKey, label: '内容生成' },
    { slot: 'image_understanding', label: '图片理解' },
    { slot: 'image_generation', label: '图片生成' },
  ].map(row => ({
    ...row,
    binding: slotsQuery.data.value?.find(slot => slot.slot === row.slot) ?? null,
    options: slotOptions(row.slot),
  }))
})

/** 按槽位能力约束筛选可绑定模型。 */
function slotOptions(slot: string): SelectOption[] {
  return allConfigs.value
    .filter(item => item.status === 'active')
    .filter(item => {
      if (slot === 'image_generation') return item.model_type === 'image_generation'
      if (slot === 'image_understanding') return (item.model_type ?? 'chat') === 'chat' && item.supports_image_input
      return (item.model_type ?? 'chat') === 'chat'
    })
    .map(item => ({ label: item.name, value: item.id, description: `${item.provider_config_name} / ${item.model_id}` }))
}

// 模型与供应商筛选
const modelProviderOptions = computed<SelectOption[]>(() => [
  { label: '全部供应商配置', value: 'all' },
  ...allProviderConfigs.value.map(provider => ({ label: provider.name, value: String(provider.id) })),
])

const filteredModels = computed(() => {
  const keyword = modelKeyword.value.trim().toLowerCase()
  return allConfigs.value
    .filter(item => modelTypeFilter.value === 'all' || (item.model_type ?? 'chat') === modelTypeFilter.value)
    .filter(item => modelProviderFilter.value === 'all' || String(item.provider_config_id) === modelProviderFilter.value)
    .filter(item => !keyword || [item.name, item.model_id, item.provider_config_name].some(text => text?.toLowerCase().includes(keyword)))
})

const filteredProviders = computed(() => {
  const keyword = providerKeyword.value.trim().toLowerCase()
  return allProviderConfigs.value
    .filter(item => providerTypeFilter.value === 'all' || (item.provider_type ?? 'chat') === providerTypeFilter.value)
    .filter(item => !keyword || [item.name, item.provider_key, item.provider_label].some(text => text?.toLowerCase().includes(keyword)))
})

const modelDataState = computed(() => (filteredModels.value.length > 0 ? 'ready' : 'empty'))
const providerDataState = computed(() => (filteredProviders.value.length > 0 ? 'ready' : 'empty'))
const modelEmptyTitle = computed(() => (allConfigs.value.length === 0 ? '还没有模型，请先连接供应商后从目录添加' : '没有符合条件的模型'))
const providerEmptyTitle = computed(() => (allProviderConfigs.value.length === 0 ? '还没有连接供应商' : '没有符合条件的供应商'))

const catalogStatusText = computed(() => {
  const state = catalogSyncState.value
  if (!state) return '正在读取 Models.dev 目录状态…'
  if (state.syncing) return '正在后台同步 Models.dev，现有配置仍可使用。'
  if (state.last_error) return `上次同步失败，当前使用上一版缓存：${state.last_error}`
  if (state.catalog_version === 'bootstrap-v1' || !state.last_success_at) return '当前仅有离线启动目录；后台联网同步完成后会自动扩展供应商和模型。'
  return `Models.dev 目录已同步 · ${formatDateTime(state.last_success_at)}`
})

// 监听槽位原始数据填充草稿
watch(
  () => slotsQuery.data.value,
  slots => {
    for (const slot of slots ?? []) {
      slotDrafts[slot.slot] = slot.llm_config_id
    }
  },
  { immediate: true },
)

/** 切换助手配置/模型管理/供应商管理 Tab 并同步路由查询参数。 */
function handleTabChange(tab: string | number) {
  activeTab.value = resolveSettingsTab(tab)
  void router.replace({ query: { ...route.query, tab: activeTab.value } })
}

/** 保存槽位绑定配置。 */
async function handleSaveSlot(slot: string, scope: 'personal' | 'global') {
  const configId = slotDrafts[slot] ?? null
  try {
    bindingSlot.value = slot
    await updateLlmSlotBinding(slot, configId, scope)
    Message.success('槽位模型绑定已更新')
    await queryClient.invalidateQueries({ queryKey: ['llm-slots'] })
  } catch (err) {
    Message.error(getErrorMessage(err, '更新槽位绑定失败'))
  } finally {
    bindingSlot.value = null
  }
}

/** 刷新 Models.dev 目录。 */
async function handleRefreshCatalog() {
  try {
    refreshingCatalog.value = true
    await refreshModelCatalog()
    Message.success('已触发 Models.dev 目录同步')
    await queryClient.invalidateQueries({ queryKey: ['model-catalog-sync'] })
    await queryClient.invalidateQueries({ queryKey: ['llm-providers'] })
  } catch (err) {
    Message.error(getErrorMessage(err, '刷新模型目录失败'))
  } finally {
    refreshingCatalog.value = false
  }
}

// ----------------- 供应商弹窗逻辑 -----------------
const selectedProviderConfig = computed(() => allProviderConfigs.value.find(item => item.id === selectedProviderConfigId.value) ?? null)
const currentProviderForProviderForm = computed(() => providersQuery.data.value?.find(provider => provider.provider_key === providerForm.provider_key) ?? null)
// 供应商目录按聊天/生图分列，弹窗内的候选项只跟随本次连接的业务类型。
const providerDraftType = ref<AiModelType>('chat')
const providerOptions = computed<SelectOption[]>(() => (
  providersQuery.data.value
    ?.filter(provider => getCatalogProviderType(provider) === providerDraftType.value)
    .map(provider => ({
      label: provider.label,
      value: provider.provider_key,
      description: getCatalogProviderType(provider) === 'image_generation'
        ? `图片生成供应商${provider.default_image_generation_model_id ? ` · ${provider.default_image_generation_model_id}` : ''}`
        : '推理能力由具体模型决定',
      keywords: [provider.provider_key, provider.provider_adapter],
    })) ?? []
))

// 新建供应商时，供应商切换自动联动 Base URL 与凭证可用状态
watch(
  () => providerForm.provider_key,
  (newKey, oldKey) => {
    if (providerPanelMode.value !== 'create' || !newKey || newKey === oldKey) return
    const provider = providersQuery.data.value?.find(item => item.provider_key === newKey) ?? null
    if (!provider) return
    providerForm.base_url = provider.supports_base_url ? (provider.default_base_url ?? '') : ''
    if (!provider.supports_api_key) {
      providerForm.api_key = ''
    }
  },
)

const providerDialogTitle = computed(() => {
  if (providerPanelMode.value === 'create') {
    return providerDraftType.value === 'image_generation' ? '连接生图供应商' : '连接聊天供应商'
  }
  if (providerPanelMode.value === 'edit') {
    return selectedProviderConfig.value?.name ? `编辑供应商：${selectedProviderConfig.value.name}` : '编辑供应商'
  }
  return selectedProviderConfig.value?.name ?? '供应商详情'
})
const providerDialogDescription = computed(() => providerPanelMode.value === 'detail' ? '查看供应商连接、范围和凭证状态。' : '配置供应商协议、服务地址、访问凭证与可用状态。')
const providerCanSubmit = computed(() => Boolean(providerForm.name.trim() && providerForm.provider_key && (!currentProviderForProviderForm.value?.requires_base_url || providerForm.base_url.trim())))
const providerDialogDirty = computed(() => providerDialogOpen.value && providerPanelMode.value !== 'detail' && providerDialogBaseline.value !== serializeProviderForm())

const providerDetailProps = computed(() => ({
  form: providerForm,
  selectedProviderConfigId: selectedProviderConfigId.value,
  selectedProviderConfig: selectedProviderConfig.value,
  mode: providerPanelMode.value,
  currentProvider: currentProviderForProviderForm.value,
  providerOptions: providerOptions.value,
  savingProviderConfig: savingProviderConfig.value,
  deletingProviderConfigId: deletingProviderConfigId.value,
  canCreateGlobal: false,
  showPanelHeader: false,
  showPanelFooter: false,
  embeddedInDialog: true,
}))

function serializeProviderForm(): string {
  return JSON.stringify(providerForm)
}

function resetProviderForm(modelType: AiModelType = 'chat') {
  selectedProviderConfigId.value = null
  providerPanelMode.value = 'create'
  providerDraftType.value = modelType
  providerForm.name = ''
  providerForm.scope = 'personal'
  providerForm.status = 'active'
  const targetProviders = providersQuery.data.value?.filter(p => getCatalogProviderType(p) === modelType) ?? []
  const provider = targetProviders.find(p => p.provider_key === DEFAULT_NEW_MODEL_PROVIDER_KEY) ?? targetProviders[0] ?? null
  providerForm.provider_key = provider?.provider_key ?? null
  providerForm.base_url = provider?.supports_base_url ? provider.default_base_url ?? '' : ''
  providerForm.api_key = ''
}

async function openProviderCreateDialog(modelType: AiModelType = 'chat') {
  resetProviderForm(modelType)
  await nextTick()
  providerDialogBaseline.value = serializeProviderForm()
  providerDialogOpen.value = true
}

async function openProviderDetailDialog(config: LlmProviderConfigItem) {
  selectedProviderConfigId.value = config.id
  providerPanelMode.value = 'detail'
  providerDraftType.value = config.provider_type ?? 'chat'
  applyingExistingProviderConfig.value = true
  providerForm.name = config.name
  providerForm.scope = config.scope
  providerForm.provider_key = config.provider_key
  providerForm.base_url = config.base_url ?? ''
  providerForm.api_key = ''
  providerForm.status = config.status ?? 'active'
  await nextTick()
  applyingExistingProviderConfig.value = false
  providerDialogBaseline.value = serializeProviderForm()
  providerDialogOpen.value = true
}

async function openProviderEditDialog(config: LlmProviderConfigItem) {
  selectedProviderConfigId.value = config.id
  providerPanelMode.value = 'edit'
  providerDraftType.value = config.provider_type ?? 'chat'
  providerForm.name = config.name
  providerForm.scope = config.scope
  providerForm.provider_key = config.provider_key
  providerForm.base_url = config.base_url ?? ''
  providerForm.api_key = ''
  providerForm.status = config.status ?? 'active'
  await nextTick()
  providerDialogBaseline.value = serializeProviderForm()
  providerDialogOpen.value = true
}

function handleStartEditProviderConfig() {
  providerPanelMode.value = 'edit'
}

async function handleCancelProviderDialogEdit() {
  if (providerDialogDirty.value && !(await createConfirm('当前供应商配置有未保存修改，确定放弃并关闭吗？', '放弃修改'))) return
  providerDialogOpen.value = false
}

async function handleProviderDialogVisibility(open: boolean) {
  if (open) {
    providerDialogOpen.value = true
    return
  }
  if (providerDialogDirty.value && !(await createConfirm('当前供应商配置有未保存修改，确定关闭吗？', '放弃未保存修改'))) return
  providerDialogOpen.value = false
}

async function handleSubmitProviderConfig() {
  const name = providerForm.name.trim()
  if (!providerForm.provider_key || !name) return
  try {
    savingProviderConfig.value = true
    if (providerPanelMode.value === 'edit' && selectedProviderConfigId.value) {
      await updateLlmProviderConfig(selectedProviderConfigId.value, {
        name,
        base_url: providerForm.base_url.trim() || null,
        api_key: providerForm.api_key.trim() || undefined,
        status: providerForm.status,
      })
      Message.success('供应商配置已更新')
    } else {
      await createLlmProviderConfig({
        name,
        scope: providerForm.scope,
        provider_key: providerForm.provider_key,
        base_url: providerForm.base_url.trim() || null,
        api_key: providerForm.api_key.trim() || null,
      })
      Message.success('供应商配置已创建')
    }
    providerDialogOpen.value = false
    await queryClient.invalidateQueries({ queryKey: ['llm-provider-configs'] })
  } catch (err) {
    Message.error(getErrorMessage(err, '保存供应商失败'))
  } finally {
    savingProviderConfig.value = false
  }
}

async function handleDeleteProviderConfig(config: LlmProviderConfigItem) {
  const confirmed = await createConfirm(`确定要删除供应商配置「${config.name}」吗？关联模型可能会失效。`, '确认删除')
  if (!confirmed) return
  try {
    deletingProviderConfigId.value = config.id
    await deleteLlmProviderConfig(config.id)
    Message.success('供应商配置已删除')
    if (selectedProviderConfigId.value === config.id) {
      providerDialogOpen.value = false
    }
    await queryClient.invalidateQueries({ queryKey: ['llm-provider-configs'] })
    await queryClient.invalidateQueries({ queryKey: ['llm-configs'] })
  } catch (err) {
    Message.error(getErrorMessage(err, '删除供应商失败'))
  } finally {
    deletingProviderConfigId.value = null
  }
}

// ----------------- 模型弹窗逻辑 -----------------
const selectedModel = computed(() => allConfigs.value.find(item => item.id === selectedConfigId.value) ?? null)
const selectedModelProviderConfig = computed(() => allProviderConfigs.value.find(item => item.id === modelForm.provider_config_id) ?? null)
const currentProvider = computed(() => providersQuery.data.value?.find(p => p.provider_key === selectedModelProviderConfig.value?.provider_key) ?? null)
const selectedChatCatalogProviderKey = computed(() => {
  if (modelForm.model_type !== 'chat') return ''
  const provider = selectedModelProviderConfig.value
  return provider?.provider_type === 'chat' && provider.provider_key !== 'custom-openai-compatible' ? provider.provider_key : ''
})

const chatModelCatalogQuery = useQuery<ChatModelCatalogItem[]>({
  queryKey: computed(() => ['chat-model-catalog', selectedChatCatalogProviderKey.value]),
  queryFn: () => listChatCatalogModels(selectedChatCatalogProviderKey.value),
  enabled: computed(() => Boolean(selectedChatCatalogProviderKey.value && modelDialogOpen.value)),
})

const providerConfigOptions = computed<SelectOption[]>(() => (
  allProviderConfigs.value
    .filter(config => config.scope === modelForm.scope)
    .filter(config => (config.provider_type ?? 'chat') === modelForm.model_type)
    .map(config => ({
      label: config.name,
      value: config.id,
      description: `${config.provider_label} · ${config.has_api_key ? '密钥已配置' : '缺少密钥'}`,
    }))
))

const modelDialogTitle = computed(() => {
  if (modelPanelMode.value === 'create') {
    return modelForm.model_type === 'image_generation' ? '新建生图模型' : '新建聊天模型'
  }
  if (modelPanelMode.value === 'edit') {
    return selectedModel.value?.name ? `编辑模型：${selectedModel.value.name}` : '编辑模型'
  }
  return selectedModel.value?.name ?? '模型详情'
})
const modelDialogDescription = computed(() => modelPanelMode.value === 'detail' ? '查看模型只读配置与平台可用上下文能力。' : '选择供应商模型，并配置模型连接、可用状态与高级参数。')
const modelReadOnly = computed(() => Boolean(selectedModel.value && !selectedModel.value.editable))
const modelCanSubmit = computed(() => Boolean(modelForm.name.trim() && modelForm.provider_config_id && modelForm.model_id.trim()))
const modelDialogDirty = computed(() => modelDialogOpen.value && modelPanelMode.value !== 'detail' && modelDialogBaseline.value !== serializeModelForm())

const modelDetailProps = computed(() => ({
  form: modelForm,
  selectedConfigId: selectedConfigId.value,
  selectedModel: selectedModel.value,
  mode: modelPanelMode.value,
  currentProvider: currentProvider.value,
  resolvedCapability: resolvedCapability.value ?? null,
  chatModelCatalog: chatModelCatalogQuery.data.value ?? [],
  providerConfigOptions: providerConfigOptions.value,
  advancedConfigText: advancedConfigText.value,
  advancedConfigError: advancedConfigError.value,
  advancedConfigCollapsed: advancedConfigCollapsed.value,
  savingConfig: savingConfig.value,
  deletingConfigId: deletingConfigId.value,
  canCreateGlobal: false,
  showPanelHeader: false,
  showPanelFooter: false,
  embeddedInDialog: true,
}))

function serializeModelForm(): string {
  return JSON.stringify({ ...modelForm, advancedConfigText: advancedConfigText.value })
}

function resetModelForm(modelType: AiModelType = 'chat') {
  selectedConfigId.value = null
  modelPanelMode.value = 'create'
  modelForm.scope = 'personal'
  modelForm.name = ''
  modelForm.model_type = modelType
  modelForm.status = 'active'
  const matchingProviderConfigs = allProviderConfigs.value.filter(c => c.scope === 'personal' && (c.provider_type ?? 'chat') === modelType)
  const defaultProviderConfig = matchingProviderConfigs[0] ?? null
  modelForm.provider_config_id = defaultProviderConfig?.id ?? null
  const provider = providersQuery.data.value?.find(p => p.provider_key === defaultProviderConfig?.provider_key) ?? null
  modelForm.model_id = modelType === 'image_generation' ? provider?.default_image_generation_model_id ?? '' : provider?.default_model_id ?? ''
  modelForm.supports_image_input = Boolean(provider?.default_supports_image_input)
  modelForm.context_window_tokens = DEFAULT_CONTEXT_WINDOW_TOKENS
  advancedConfigText.value = '{}'
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
}

async function openModelCreateDialog(modelType: AiModelType = 'chat') {
  resetModelForm(modelType)
  await nextTick()
  modelDialogBaseline.value = serializeModelForm()
  modelDialogOpen.value = true
}

async function openModelDetailDialog(config: LlmConfigItem) {
  selectedConfigId.value = config.id
  modelPanelMode.value = 'detail'
  applyingExistingModel.value = true
  modelForm.scope = config.scope
  modelForm.name = config.name
  modelForm.provider_config_id = config.provider_config_id
  modelForm.model_id = config.model_id
  modelForm.model_type = config.model_type ?? 'chat'
  modelForm.supports_image_input = config.supports_image_input
  modelForm.context_window_tokens = config.context_window_tokens ?? DEFAULT_CONTEXT_WINDOW_TOKENS
  modelForm.status = config.status ?? 'active'
  advancedConfigText.value = JSON.stringify(config.advanced_config_json ?? {}, null, 2)
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
  await nextTick()
  applyingExistingModel.value = false
  modelDialogBaseline.value = serializeModelForm()
  modelDialogOpen.value = true
}

async function openModelEditDialog(config: LlmConfigItem) {
  selectedConfigId.value = config.id
  modelPanelMode.value = 'edit'
  modelForm.scope = config.scope
  modelForm.name = config.name
  modelForm.provider_config_id = config.provider_config_id
  modelForm.model_id = config.model_id
  modelForm.model_type = config.model_type ?? 'chat'
  modelForm.supports_image_input = config.supports_image_input
  modelForm.context_window_tokens = config.context_window_tokens ?? DEFAULT_CONTEXT_WINDOW_TOKENS
  modelForm.status = config.status ?? 'active'
  advancedConfigText.value = JSON.stringify(config.advanced_config_json ?? {}, null, 2)
  advancedConfigError.value = ''
  advancedConfigCollapsed.value = true
  await nextTick()
  modelDialogBaseline.value = serializeModelForm()
  modelDialogOpen.value = true
}

function handleStartEditModel() {
  modelPanelMode.value = 'edit'
}

async function handleCancelModelDialogEdit() {
  if (modelDialogDirty.value && !(await createConfirm('当前模型配置有未保存修改，确定放弃并关闭吗？', '放弃修改'))) return
  modelDialogOpen.value = false
}

async function handleModelDialogVisibility(open: boolean) {
  if (open) {
    modelDialogOpen.value = true
    return
  }
  if (modelDialogDirty.value && !(await createConfirm('当前模型配置有未保存修改，确定关闭吗？', '放弃未保存修改'))) return
  modelDialogOpen.value = false
}

function formatAdvancedConfig() {
  try {
    const parsed = JSON.parse(advancedConfigText.value || '{}') as Record<string, unknown>
    advancedConfigText.value = JSON.stringify(parsed, null, 2)
    advancedConfigError.value = ''
  } catch (err) {
    advancedConfigError.value = '高级参数必须为有效 JSON'
  }
}

async function handleSubmitModel() {
  const name = modelForm.name.trim()
  const modelId = modelForm.model_id.trim()
  if (!name || !modelForm.provider_config_id || !modelId) return
  let advancedJson: Record<string, unknown> = {}
  try {
    advancedJson = JSON.parse(advancedConfigText.value.trim() || '{}') as Record<string, unknown>
  } catch {
    advancedConfigError.value = '高级参数必须为有效 JSON'
    return
  }
  try {
    savingConfig.value = true
    if (modelPanelMode.value === 'edit' && selectedConfigId.value) {
      await updateLlmConfig(selectedConfigId.value, {
        name,
        provider_config_id: modelForm.provider_config_id,
        model_id: modelId,
        model_type: modelForm.model_type,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: modelForm.context_window_tokens,
        advanced_config_json: advancedJson,
        status: modelForm.status,
      })
      Message.success('模型配置已更新')
    } else {
      await createLlmConfig({
        name,
        scope: modelForm.scope,
        provider_config_id: modelForm.provider_config_id,
        model_id: modelId,
        model_type: modelForm.model_type,
        supports_image_input: modelForm.supports_image_input,
        context_window_tokens: modelForm.context_window_tokens,
        advanced_config_json: advancedJson,
        status: modelForm.status,
      })
      Message.success('模型配置已创建')
    }
    modelDialogOpen.value = false
    await queryClient.invalidateQueries({ queryKey: ['llm-configs'] })
    await queryClient.invalidateQueries({ queryKey: ['llm-slots'] })
  } catch (err) {
    Message.error(getErrorMessage(err, '保存模型失败'))
  } finally {
    savingConfig.value = false
  }
}

async function handleDeleteModel(config: LlmConfigItem) {
  const confirmed = await createConfirm(`确定要删除模型配置「${config.name}」吗？`, '确认删除')
  if (!confirmed) return
  try {
    deletingConfigId.value = config.id
    await deleteLlmConfig(config.id)
    Message.success('模型配置已删除')
    if (selectedConfigId.value === config.id) {
      modelDialogOpen.value = false
    }
    await queryClient.invalidateQueries({ queryKey: ['llm-configs'] })
    await queryClient.invalidateQueries({ queryKey: ['llm-slots'] })
  } catch (err) {
    Message.error(getErrorMessage(err, '删除模型失败'))
  } finally {
    deletingConfigId.value = null
  }
}

function getCatalogProviderType(provider: LlmProviderCatalogItem): AiModelType {
  return provider.provider_type === 'image_generation' ? 'image_generation' : 'chat'
}

watch(
  () => [modelForm.provider_config_id, modelForm.model_id, modelForm.model_type] as const,
  async ([providerConfigId, modelId, modelType]) => {
    const sequence = ++capabilityRequestSequence
    if (modelType !== 'chat' || !providerConfigId || !modelId.trim()) {
      resolvedCapability.value = null
      return
    }
    try {
      const capability = await resolveLlmModelCapability(providerConfigId, modelId.trim())
      if (sequence !== capabilityRequestSequence) return
      resolvedCapability.value = capability
      if (!applyingExistingModel.value) {
        modelForm.supports_image_input = capability.supports_image_input
      }
    } catch {
      if (sequence === capabilityRequestSequence) resolvedCapability.value = null
    }
  },
  { immediate: true },
)
</script>
