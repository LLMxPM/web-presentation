<!-- 文件功能：平台系统设置管理视图，支持存储、常规、安全与诊断配置的热更新及 S3 连通性测试。 -->
<template>
  <div class="admin-settings-view space-y-6 pb-16">
    <SettingsPageHeader
      title="系统设置"
      description="管理存储驱动、业务时区、安全策略与日志级别，修改后即时生效。"
    >
      <template #actions>
        <UiButton variant="secondary" size="sm" :disabled="loading || saving" @click="loadSettings">
          <RotateCw class="h-3.5 w-3.5" :class="{ 'animate-spin': loading }" />
          <span>刷新</span>
        </UiButton>
        <UiButton variant="primary" size="sm" :loading="saving" :disabled="loading || !isDirty" @click="handleSave">
          <Save class="h-3.5 w-3.5" />
          <span>保存设置</span>
        </UiButton>
      </template>
    </SettingsPageHeader>

    <!-- Safe-Mode 降级警告横条 -->
    <div
      v-if="safeModeWarnings.length > 0"
      class="rounded-xl border border-warning-muted bg-warning-muted/30 p-4 text-sm text-warning-strong"
    >
      <div class="flex items-start gap-3">
        <AlertTriangle class="h-5 w-5 shrink-0 text-warning" />
        <div class="space-y-2">
          <div class="font-semibold">系统已触发 Safe-Mode 安全降级防护</div>
          <p class="text-xs text-text-secondary leading-relaxed">
            检测到数据库中存在非法或无法识别的配置项，系统已自动回退到出厂安全默认值以防止服务崩溃（Crash-Loop）。请检查以下异常并保存正确值：
          </p>
          <ul class="list-inside list-disc space-y-1 text-xs">
            <li v-for="(warn, idx) in safeModeWarnings" :key="idx">
              <span class="font-mono font-semibold">{{ warn.key }}</span>: {{ warn.error }} (已降级回退为: {{ warn.fallback_value }})
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- 骨架加载中 -->
    <div v-if="loading && items.length === 0" class="space-y-4 py-8 text-center text-text-muted">
      <RotateCw class="mx-auto h-6 w-6 animate-spin text-accent" />
      <p class="text-sm">正在加载系统配置...</p>
    </div>

    <!-- 主配置面板 -->
    <div v-else class="space-y-6">
      <UiTabs v-model="activeTab" :items="tabItems" content-class="pt-6">
        <!-- 存储管理 Tab -->
        <template #storage>
          <div class="space-y-6">
            <div class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-6">
              <div class="border-b border-border-muted pb-4">
                <h2 class="text-base font-semibold text-text">对象存储驱动</h2>
                <p class="mt-1 text-xs text-text-muted">
                  存储页面截图、用户上传资源、项目导出包及临时缓存。多 Backend 副本部署下必须使用 S3 兼容共享对象存储。
                </p>
              </div>

              <!-- 驱动选择 -->
              <UiFormField label="存储驱动类型" description="local 为本地磁盘存储，s3 为兼容 AWS S3 的对象存储服务">
                <div class="flex items-center gap-4">
                  <UiRadioGroup
                    v-model="formData.asset_storage_driver"
                    :options="storageDriverOptions"
                    :disabled="isKeyDisabled('asset_storage_driver')"
                    orientation="horizontal"
                  />
                  <UiBadge v-if="isKeyEnvOverridden('asset_storage_driver')" tone="accent">环境变量锁定</UiBadge>
                </div>
              </UiFormField>

              <!-- S3 详情配置区 -->
              <div v-if="formData.asset_storage_driver === 's3'" class="rounded-lg border border-border-muted bg-surface-muted/40 p-5 space-y-4">
                <div class="text-xs font-semibold uppercase tracking-wider text-text-muted">S3 详细连接参数</div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <UiFormField label="Endpoint URL" description="S3 兼容服务接口基址（AWS S3 可留空）">
                    <UiInput
                      v-model="formData.s3_endpoint_url"
                      placeholder="https://s3.us-east-1.amazonaws.com"
                      :disabled="isKeyDisabled('s3_endpoint_url')"
                    />
                  </UiFormField>

                  <UiFormField label="Region 区域" description="例如 us-east-1, ap-northeast-1">
                    <UiInput
                      v-model="formData.s3_region"
                      placeholder="us-east-1"
                      :disabled="isKeyDisabled('s3_region')"
                    />
                  </UiFormField>

                  <UiFormField label="Access Key ID" description="S3 访问密钥 ID">
                    <UiInput
                      v-model="formData.s3_access_key"
                      placeholder="AKIA..."
                      :disabled="isKeyDisabled('s3_access_key')"
                    />
                  </UiFormField>

                  <UiFormField label="Secret Access Key" description="S3 访问私钥（加密脱敏显示）">
                    <UiInput
                      v-model="formData.s3_secret_key"
                      type="password"
                      password-toggle
                      placeholder="******"
                      :disabled="isKeyDisabled('s3_secret_key')"
                    />
                  </UiFormField>

                  <UiFormField label="主存储桶 (Bucket)" description="保存平台私有对象的主 Bucket 名称" required>
                    <UiInput
                      v-model="formData.s3_bucket"
                      placeholder="web-presentation-assets"
                      :disabled="isKeyDisabled('s3_bucket')"
                    />
                  </UiFormField>

                  <UiFormField label="公开存储桶 (Public Bucket)" description="可选：分流公开资源的 Bucket（留空使用主桶）">
                    <UiInput
                      v-model="formData.s3_public_bucket"
                      placeholder="留空则复用主存储桶"
                      :disabled="isKeyDisabled('s3_public_bucket')"
                    />
                  </UiFormField>
                </div>

                <UiFormField label="公开访问基址 (Public Base URL)" description="可选：绑定的 CDN 加速域名或对外 HTTP 根路径">
                  <UiInput
                    v-model="formData.s3_public_base_url"
                    placeholder="https://cdn.example.com"
                    :disabled="isKeyDisabled('s3_public_base_url')"
                  />
                </UiFormField>

                <!-- 测试连通性控制区 -->
                <div class="mt-4 flex flex-wrap items-center gap-3 border-t border-border-muted pt-4">
                  <UiButton
                    variant="secondary"
                    size="sm"
                    :loading="testingS3"
                    :disabled="!formData.s3_bucket"
                    @click="handleTestS3"
                  >
                    <Radio class="h-3.5 w-3.5" />
                    <span>测试 S3 连接与存储桶权限</span>
                  </UiButton>
                  <span v-if="s3TestResult" class="text-xs" :class="s3TestResult.success ? 'text-success-strong font-medium' : 'text-danger font-medium'">
                    {{ s3TestResult.message }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- 常规设置 Tab -->
        <template #general>
          <div class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-6">
            <div class="border-b border-border-muted pb-4">
              <h2 class="text-base font-semibold text-text">平台常规设置</h2>
              <p class="mt-1 text-xs text-text-muted">自定义品牌显示名称与业务时区。</p>
            </div>

            <div class="space-y-4 max-w-xl">
              <SettingsFieldRenderer
                label="平台品牌名称 (APP_NAME)"
                description="显示于浏览器标题与导航栏"
                v-model="formData.app_name"
                placeholder="页面管理后台"
                :disabled="isKeyDisabled('app_name')"
                :env-overridden="isKeyEnvOverridden('app_name')"
              />

              <SettingsFieldRenderer
                type="select"
                label="业务时区 (APP_TIMEZONE)"
                description="系统时间呈现与任务时间戳所依附的业务时区"
                v-model="formData.app_timezone"
                :options="timezoneOptions"
                :disabled="isKeyDisabled('app_timezone')"
                :env-overridden="isKeyEnvOverridden('app_timezone')"
              />
            </div>
          </div>
        </template>

        <!-- 安全策略 Tab -->
        <template #security>
          <div class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-6">
            <div class="border-b border-border-muted pb-4">
              <h2 class="text-base font-semibold text-text">安全策略</h2>
              <p class="mt-1 text-xs text-text-muted">控制用户会话有效时长与个人访问令牌（PAT）配额。</p>
            </div>

            <div class="space-y-4 max-w-xl">
              <SettingsFieldRenderer
                type="number"
                label="用户会话有效期 (小时)"
                description="Cookie 登录态在浏览器端的有效持续时间"
                v-model="formData.session_ttl_hours"
                :min="1"
                :disabled="isKeyDisabled('session_ttl_hours')"
                :env-overridden="isKeyEnvOverridden('session_ttl_hours')"
              />

              <SettingsFieldRenderer
                type="number"
                label="单用户 PAT 最大活跃数量"
                description="防止生成过多长期未收回的访问凭证"
                v-model="formData.pat_max_active_tokens"
                :min="1"
                :disabled="isKeyDisabled('pat_max_active_tokens')"
                :env-overridden="isKeyEnvOverridden('pat_max_active_tokens')"
              />

              <SettingsFieldRenderer
                type="number"
                label="PAT 最长有效期 (天)"
                description="签发访问令牌所能允许的最长时间跨度"
                v-model="formData.pat_max_ttl_days"
                :min="1"
                :disabled="isKeyDisabled('pat_max_ttl_days')"
                :env-overridden="isKeyEnvOverridden('pat_max_ttl_days')"
              />
            </div>
          </div>
        </template>

        <!-- 系统诊断 Tab -->
        <template #diagnostic>
          <div class="rounded-xl border border-border bg-surface p-6 shadow-xs space-y-6">
            <div class="border-b border-border-muted pb-4">
              <h2 class="text-base font-semibold text-text">系统诊断与运维</h2>
              <p class="mt-1 text-xs text-text-muted">运行时热调日志输出级别，辅助定位生产疑难问题。</p>
            </div>

            <div class="space-y-5 max-w-xl">
              <SettingsFieldRenderer
                type="select"
                label="运行时日志级别 (LOG_LEVEL)"
                description="动态调整 Backend 进程的日志过滤级别，立即生效"
                v-model="formData.log_level"
                :options="logLevelOptions"
                :disabled="isKeyDisabled('log_level')"
                :env-overridden="isKeyEnvOverridden('log_level')"
              />

            </div>
          </div>
        </template>
      </UiTabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import {
  AlertTriangle,
  Radio,
  RotateCw,
  Save,
} from '@lucide/vue'

import {
  fetchAdminSettings,
  ADMIN_SETTINGS_QUERY_KEY,
  testS3StorageConnection,
  updateAdminSettings,
} from '@/api/adminSettings'
import { getErrorMessage } from '@/api/http'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import { SettingsFieldRenderer } from '@/components/patterns'
import {
  UiBadge,
  UiButton,
  UiFormField,
  UiInput,
  UiRadioGroup,
  UiTabs,
} from '@/components/ui'
import type { SystemSettingItem } from '@/types/api'
import { Message } from '@/utils/message'

const activeTab = ref('storage')
const queryClient = useQueryClient()
const loading = ref(false)
const saving = ref(false)
const testingS3 = ref(false)

const items = ref<SystemSettingItem[]>([])
const safeModeWarnings = ref<Array<Record<string, any>>>([])
const s3TestResult = ref<{ success: boolean; message: string } | null>(null)

// 表单响应式数据
const formData = reactive<Record<string, any>>({
  asset_storage_driver: 'local',
  s3_endpoint_url: '',
  s3_access_key: '',
  s3_secret_key: '',
  s3_bucket: '',
  s3_public_bucket: '',
  s3_region: '',
  s3_public_base_url: '',
  app_name: '页面管理后台',
  app_timezone: 'Asia/Shanghai',
  session_ttl_hours: 24,
  pat_max_active_tokens: 25,
  pat_max_ttl_days: 365,
  log_level: 'INFO',
})

// 初始快照用于 isDirty 判定
const initialSnapshot = ref<string>('')

const isDirty = computed(() => {
  return JSON.stringify(formData) !== initialSnapshot.value
})

const tabItems = [
  { label: '存储管理', value: 'storage' },
  { label: '常规设置', value: 'general' },
  { label: '安全策略', value: 'security' },
  { label: '系统诊断', value: 'diagnostic' },
]

const storageDriverOptions = [
  { label: '本地磁盘存储 (local)', value: 'local' },
  { label: 'S3 兼容对象存储 (s3)', value: 's3' },
]

const timezoneOptions = [
  { label: 'Asia/Shanghai (中国标准时间 UTC+8)', value: 'Asia/Shanghai' },
  { label: 'Asia/Tokyo (日本标准时间 UTC+9)', value: 'Asia/Tokyo' },
  { label: 'UTC (协调世界时)', value: 'UTC' },
  { label: 'America/New_York (美东时间)', value: 'America/New_York' },
  { label: 'America/Los_Angeles (美西时间)', value: 'America/Los_Angeles' },
  { label: 'Europe/London (伦敦时间)', value: 'Europe/London' },
]

const logLevelOptions = [
  { label: 'DEBUG (详细排查)', value: 'DEBUG' },
  { label: 'INFO (标准运行)', value: 'INFO' },
  { label: 'WARNING (告警)', value: 'WARNING' },
  { label: 'ERROR (错误)', value: 'ERROR' },
  { label: 'CRITICAL (致命故障)', value: 'CRITICAL' },
]

function getItemByKey(key: string): SystemSettingItem | undefined {
  return items.value.find((i) => i.key === key)
}

function isKeyEnvOverridden(key: string): boolean {
  return getItemByKey(key)?.is_env_overridden ?? false
}

function isKeyDisabled(key: string): boolean {
  return loading.value || saving.value || isKeyEnvOverridden(key)
}

async function loadSettings() {
  loading.value = true
  try {
    const res = await fetchAdminSettings()
    queryClient.setQueryData(ADMIN_SETTINGS_QUERY_KEY, res)
    items.value = res.items
    safeModeWarnings.value = (res.safe_mode_warnings as unknown as Array<Record<string, any>>) ?? []

    // 填充表单
    for (const item of res.items) {
      if (item.key in formData) {
        formData[item.key] = item.value ?? ''
      }
    }
    initialSnapshot.value = JSON.stringify(formData)
  } catch (err) {
    Message.error(getErrorMessage(err, '加载系统设置失败'))
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    const payload: Record<string, any> = {}
    for (const [k, v] of Object.entries(formData)) {
      if (!isKeyEnvOverridden(k)) {
        payload[k] = v
      }
    }
    const res = await updateAdminSettings(payload)
    queryClient.setQueryData(ADMIN_SETTINGS_QUERY_KEY, res)
    items.value = res.items
    safeModeWarnings.value = (res.safe_mode_warnings as unknown as Array<Record<string, any>>) ?? []
    for (const item of res.items) {
      if (item.key in formData) {
        formData[item.key] = item.value ?? ''
      }
    }
    initialSnapshot.value = JSON.stringify(formData)
    Message.success('系统设置已成功保存并即时热更新生效。')
  } catch (err) {
    Message.error(getErrorMessage(err, '保存系统设置失败'))
  } finally {
    saving.value = false
  }
}

async function handleTestS3() {
  testingS3.value = true
  s3TestResult.value = null
  try {
    const res = await testS3StorageConnection({
      endpoint_url: formData.s3_endpoint_url || undefined,
      region: formData.s3_region || undefined,
      access_key: formData.s3_access_key || undefined,
      secret_key: formData.s3_secret_key || undefined,
      bucket: formData.s3_bucket,
    })
    s3TestResult.value = res
    if (res.success) {
      Message.success(res.message)
    } else {
      Message.error(res.message)
    }
  } catch (err) {
    const msg = getErrorMessage(err, 'S3 连通性测试异常')
    s3TestResult.value = { success: false, message: msg }
    Message.error(msg)
  } finally {
    testingS3.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>
