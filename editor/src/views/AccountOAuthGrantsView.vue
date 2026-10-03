<!-- 文件功能：展示本人外部授权、权限和具体空间，提供整条授权的幂等撤销操作。 -->
<template>
  <div class="space-y-4">
    <SettingsPageHeader title="外部授权" description="管理 ChatGPT 等外部客户端获得的工作空间访问权限。">
      <template #actions><UiButton variant="secondary" :loading="loading" @click="load">刷新</UiButton></template>
    </SettingsPageHeader>
    <p v-if="error" role="alert" class="rounded-ui-md border border-danger-border bg-danger-muted p-3 text-sm text-danger-strong">{{ error }}</p>
    <p v-if="loading && !data" role="status" class="text-sm text-text-secondary">正在加载授权…</p>
    <p v-else-if="data && !data.enabled" class="text-sm text-text-secondary">平台尚未启用外部 OAuth 授权。</p>
    <p v-else-if="data && !data.items.length" class="text-sm text-text-secondary">您还没有外部授权。连接 ChatGPT 时，平台会让您选择工作空间和权限。</p>
    <section v-for="grant in data?.items ?? []" :key="grant.grant_id" class="space-y-3 rounded-ui-lg border border-border bg-surface p-4">
      <header class="flex min-w-0 items-center gap-3">
        <h2 class="min-w-0 flex-1 truncate text-sm font-semibold">{{ grant.client_name }}</h2>
        <UiBadge :tone="grant.revoked_at ? 'neutral' : grant.is_active ? 'success' : 'warning'">{{ grant.revoked_at ? '已撤销' : grant.is_active ? '已授权' : '已失效' }}</UiBadge>
        <UiButton v-if="!grant.revoked_at" variant="danger" size="sm" :loading="revokingId === grant.grant_id" :disabled="!!revokingId" @click="revoke(grant.grant_id, grant.client_name)">撤销</UiButton>
      </header>
      <p class="break-all text-xs text-text-secondary">{{ grant.resource }}</p>
      <p class="break-words text-sm">工作空间：{{ grant.workspaces.map(item => item.name).join('、') }}</p>
      <div class="flex flex-wrap gap-1.5"><UiBadge v-for="scope in grant.scopes" :key="scope" :tone="scope.endsWith(':write') ? 'warning' : 'neutral'">{{ oauthScopeLabel(scope) }}</UiBadge></div>
      <p class="text-xs text-text-secondary">授权时间：{{ formatDateTime(grant.created_at) }}<span v-if="grant.revoked_at"> · 撤销时间：{{ formatDateTime(grant.revoked_at) }}</span></p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listOAuthGrants, revokeOAuthGrant } from '@/api/oauth'
import { getErrorMessage } from '@/api/http'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import { UiBadge, UiButton } from '@/components/ui'
import type { OAuthGrantList } from '@/types/api.generated'
import { createConfirm } from '@/utils/confirm'
import { formatDateTime } from '@/utils/format'
import { oauthScopeLabel } from '@/utils/oauth'

const data = ref<OAuthGrantList | null>(null)
const loading = ref(false)
const revokingId = ref('')
const error = ref('')

/** 加载本人授权的公共信息，失败保留明确错误，不从本地缓存补造状态。 */
async function load() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try { data.value = await listOAuthGrants() }
  catch (cause) { error.value = getErrorMessage(cause, '无法加载外部授权。') }
  finally { loading.value = false }
}

/** 解释撤销效果并调用整链撤销；后台已接受任务不自动取消。 */
async function revoke(grantId: string, name: string) {
  if (revokingId.value) return
  if (!await createConfirm(`撤销后，${name} 无法继续使用这条授权。已接受的后台任务会继续执行。`, '撤销外部授权', { dangerous: true, confirmLabel: '撤销授权' })) return
  revokingId.value = grantId
  error.value = ''
  try { await revokeOAuthGrant(grantId); await load() }
  catch (cause) { error.value = getErrorMessage(cause, '撤销授权失败。') }
  finally { revokingId.value = '' }
}
onMounted(load)
</script>
