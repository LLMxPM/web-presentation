<!-- 文件功能：平台全局 AI 管理视图，供管理员统一维护全局公共模型/供应商、Models.dev 规格目录同步与平台级 AI 运行时策略。 -->
<template>
  <div class="platform-ai-management space-y-6 pb-16">
    <SettingsPageHeader
      title="平台 AI 管理"
      description="统一维护全平台公共大模型、供应商凭据、Models.dev 规格目录同步及运行时技术参数。"
      badge="平台管理员"
      badge-tone="accent"
    >
      <template #actions>
        <UiButton variant="secondary" size="sm" :disabled="loading || saving" @click="loadData">
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
          <div class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-6">
            <div class="border-b border-border-muted pb-4">
              <h2 class="text-base font-semibold text-text">平台 AI 运行策略</h2>
              <p class="mt-1 text-xs text-text-muted">控制平台 AI 服务可用性与流式推理容错参数。</p>
            </div>

            <div class="space-y-5 max-w-2xl">
              <!-- AI 服务总开关 -->
              <div class="flex items-center justify-between rounded-lg border border-border-muted p-4 bg-surface-muted/30">
                <div>
                  <div class="text-sm font-semibold text-text">平台 AI 总开关</div>
                  <div class="text-xs text-text-muted">关闭后全平台禁用 AI 创作者助手与自动化任务生成</div>
                </div>
                <UiCheckbox
                  v-model="systemSettingsForm.ai_enabled"
                  :disabled="isKeyDisabled('ai_enabled')"
                />
              </div>

              <!-- 图片传输模式 -->
              <UiFormField
                label="AI 图片传输与预览模式"
                description="auto 自动择优，url 使用对象存储直链，base64 内嵌二进制 Base64"
              >
                <div class="flex items-center gap-2">
                  <UiSelect
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
                description="防止长上下文或复杂推理模型因下游网络挂死持续占用协调器任务租约"
              >
                <div class="flex items-center gap-2">
                  <UiInput
                    v-model.number="systemSettingsForm.ai_agent_stream_idle_timeout_seconds"
                    type="number"
                    :disabled="isKeyDisabled('ai_agent_stream_idle_timeout_seconds')"
                  />
                  <UiBadge v-if="isKeyEnvOverridden('ai_agent_stream_idle_timeout_seconds')" tone="accent">ENV 覆盖</UiBadge>
                </div>
              </UiFormField>

              <!-- LLM HTTP Trace -->
              <div class="flex items-center justify-between rounded-lg border border-border-muted p-4 bg-surface-muted/30">
                <div>
                  <div class="text-sm font-semibold text-text">LLM HTTP 协议网络跟踪</div>
                  <div class="text-xs text-text-muted">开启后在服务端日志中记录发往模型供应商的完整 HTTP 请求与响应报文（自动脱敏密钥）</div>
                </div>
                <UiCheckbox
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
          <div class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-6">
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
              <div class="flex items-center justify-between rounded-lg border border-border-muted p-4 bg-surface-muted/30">
                <div>
                  <div class="text-sm font-semibold text-text">模型目录自动定时同步</div>
                  <div class="text-xs text-text-muted">系统后台定期拉取 Models.dev 最新模型能力、上下文窗口与推理选项</div>
                </div>
                <UiCheckbox
                  v-model="systemSettingsForm.ai_model_catalog_sync_enabled"
                  :disabled="isKeyDisabled('ai_model_catalog_sync_enabled')"
                />
              </div>

              <!-- 状态详情卡片 -->
              <div class="rounded-lg border border-border p-4 bg-surface-muted/20 space-y-3">
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
          <div class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-6">
            <div class="border-b border-border-muted pb-4">
              <h2 class="text-base font-semibold text-text">全局公共默认槽位绑定</h2>
              <p class="mt-1 text-xs text-text-muted">
                当普通用户未配置自身个人模型或选择「继承平台默认」时，内容助手将使用以下全局配置。
              </p>
            </div>

            <div class="max-w-xl space-y-4">
              <UiFormField label="平台默认内容助手模型" description="全平台用户默认的内容生成与结构化编辑模型">
                <div class="flex items-center gap-3">
                  <UiSelect
                    v-model="globalSlotModelId"
                    :options="globalModelOptions"
                    placeholder="请选择全局默认模型"
                    class="w-full"
                  />
                  <UiButton
                    variant="primary"
                    size="sm"
                    :loading="savingSlot"
                    :disabled="!isSlotDirty"
                    @click="handleSaveGlobalSlot"
                  >
                    保存槽位
                  </UiButton>
                </div>
              </UiFormField>
            </div>
          </div>

          <!-- 全局模型与供应商概要 -->
          <div class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-4">
            <div class="flex items-center justify-between border-b border-border-muted pb-3">
              <div>
                <h3 class="text-base font-semibold text-text">全局公共模型与凭据</h3>
                <p class="mt-0.5 text-xs text-text-muted">共 {{ globalModels.length }} 个全局模型，{{ globalProviders.length }} 个全局供应商凭证。</p>
              </div>
              <UiButton variant="secondary" size="sm" @click="navigateToAccountAi">
                前往完整配置工作台
              </UiButton>
            </div>

            <div v-if="globalModels.length === 0" class="py-8 text-center text-sm text-text-muted">
              暂无全局公共模型。可在 AI 配置工作台添加 scope 为 global 的模型与供应商。
            </div>
            <div v-else class="divide-y divide-border-muted">
              <div v-for="model in globalModels" :key="model.id" class="flex items-center justify-between py-3 text-sm">
                <div>
                  <div class="font-medium text-text">{{ model.name }}</div>
                  <div class="text-xs font-mono text-text-muted">{{ model.model_id }} ({{ model.provider_key }})</div>
                </div>
                <div class="flex items-center gap-2">
                  <UiBadge tone="accent">Global</UiBadge>
                  <span v-if="globalSlotBinding?.llm_config_id === model.id" class="text-xs font-semibold text-success">
                    当前默认
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </UiTabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { RotateCw, Save } from '@lucide/vue'

import { fetchAdminSettings, updateAdminSettings } from '@/api/adminSettings'
import {
  getModelCatalogSyncState,
  listLlmConfigs,
  listLlmProviderConfigs,
  listLlmSlots,
  refreshModelCatalog,
  updateLlmSlotBinding,
  type ModelCatalogSyncState,
} from '@/api/llm'
import { getErrorMessage } from '@/api/http'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import {
  UiBadge,
  UiButton,
  UiCheckbox,
  UiFormField,
  UiInput,
  UiSelect,
  UiTabs,
} from '@/components/ui'
import type { SelectOption } from '@/components/ui/select'
import type { LlmConfigItem, LlmProviderConfigItem, LlmSlotBindingItem, SystemSettingItem } from '@/types/api'
import { Message } from '@/utils/message'

const router = useRouter()
const activeTab = ref('runtime')
const loading = ref(false)
const saving = ref(false)
const savingSlot = ref(false)
const syncingCatalog = ref(false)

const settingsItems = ref<SystemSettingItem[]>([])
const catalogSyncState = ref<ModelCatalogSyncState | null>(null)
const globalModels = ref<LlmConfigItem[]>([])
const globalProviders = ref<LlmProviderConfigItem[]>([])
const globalSlotBinding = ref<LlmSlotBindingItem | null>(null)
const initialGlobalSlotModelId = ref<number | null>(null)
const globalSlotModelId = ref<number | null>(null)

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
  ...globalModels.value.map(item => ({
    label: `${item.name} (${item.model_id})`,
    value: item.id,
  })),
])

const isDirty = computed(() => {
  return (
    systemSettingsForm.ai_enabled !== initialSystemSettingsForm.ai_enabled ||
    systemSettingsForm.ai_model_catalog_sync_enabled !== initialSystemSettingsForm.ai_model_catalog_sync_enabled ||
    systemSettingsForm.ai_image_transport_mode !== initialSystemSettingsForm.ai_image_transport_mode ||
    systemSettingsForm.ai_agent_stream_idle_timeout_seconds !== initialSystemSettingsForm.ai_agent_stream_idle_timeout_seconds ||
    systemSettingsForm.ai_llm_http_trace_enabled !== initialSystemSettingsForm.ai_llm_http_trace_enabled
  )
})

const isSlotDirty = computed(() => globalSlotModelId.value !== initialGlobalSlotModelId.value)

function isKeyDisabled(key: string): boolean {
  const item = settingsItems.value.find(s => s.key === key)
  return loading.value || saving.value || Boolean(item?.is_env_overridden)
}

function isKeyEnvOverridden(key: string): boolean {
  const item = settingsItems.value.find(s => s.key === key)
  return Boolean(item?.is_env_overridden)
}

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return '无记录'
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

/**
 * 完整拉取系统设置、Models.dev 状态与全局模型池。
 */
async function loadData(): Promise<void> {
  loading.value = true
  try {
    const [settingsRes, catalogRes, allModels, allProviders, allSlots] = await Promise.all([
      fetchAdminSettings(),
      getModelCatalogSyncState().catch(() => null),
      listLlmConfigs().catch(() => []),
      listLlmProviderConfigs().catch(() => []),
      listLlmSlots().catch(() => []),
    ])

    settingsItems.value = settingsRes.items
    catalogSyncState.value = catalogRes

    for (const item of settingsRes.items) {
      if (item.key in systemSettingsForm) {
        systemSettingsForm[item.key] = item.value
        initialSystemSettingsForm[item.key] = item.value
      }
    }

    // 过滤 global scope 的模型与凭据
    globalModels.value = allModels.filter(m => m.scope === 'global')
    globalProviders.value = allProviders.filter(p => p.scope === 'global')

    // 获取全局默认槽位
    const coordinatorSlot = allSlots.find(s => s.slot === 'agent_coordinator')
    globalSlotBinding.value = coordinatorSlot ?? null
    globalSlotModelId.value = coordinatorSlot?.llm_config_id ?? 0
    initialGlobalSlotModelId.value = coordinatorSlot?.llm_config_id ?? 0
  } catch (err) {
    Message.error(getErrorMessage(err, '加载平台 AI 管理数据失败'))
  } finally {
    loading.value = false
  }
}

/**
 * 保存 AI 运行策略与系统参数。
 */
async function handleSaveSettings(): Promise<void> {
  saving.value = true
  try {
    const payload = {
      ai_enabled: systemSettingsForm.ai_enabled,
      ai_model_catalog_sync_enabled: systemSettingsForm.ai_model_catalog_sync_enabled,
      ai_image_transport_mode: systemSettingsForm.ai_image_transport_mode,
      ai_agent_stream_idle_timeout_seconds: Number(systemSettingsForm.ai_agent_stream_idle_timeout_seconds),
      ai_llm_http_trace_enabled: systemSettingsForm.ai_llm_http_trace_enabled,
    }
    await updateAdminSettings(payload)
    Message.success('平台 AI 策略已更新并即时热生效。')
    await loadData()
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
  savingSlot.value = true
  try {
    const targetId = globalSlotModelId.value === 0 ? null : globalSlotModelId.value
    await updateLlmSlotBinding('agent_coordinator', targetId, 'global')
    Message.success('全局默认模型槽位已更新。')
    initialGlobalSlotModelId.value = globalSlotModelId.value
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

function navigateToAccountAi(): void {
  void router.push('/settings/account/ai')
}

onMounted(() => {
  void loadData()
})
</script>
