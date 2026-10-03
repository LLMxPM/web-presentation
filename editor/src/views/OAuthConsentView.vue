<!-- 文件功能：为 ChatGPT 连接展示登录身份、明确空间与权限选择，并执行一次性批准或拒绝。 -->
<template>
  <main class="min-h-screen bg-canvas px-4 py-8 text-text">
    <div class="mx-auto max-w-2xl space-y-4">
      <SettingsPageHeader title="连接 ChatGPT" description="选择允许 ChatGPT 访问的工作空间和能力。" />
      <p class="text-sm text-text-secondary">当前账户：{{ auth.user?.display_name || auth.user?.username }}</p>
      <p v-if="loading" role="status" class="text-sm text-text-secondary">正在准备授权…</p>
      <p v-if="error" role="alert" class="rounded-ui-md border border-danger-border bg-danger-muted p-3 text-sm text-danger-strong">{{ error }}</p>
      <template v-if="view">
        <section class="space-y-3 rounded-ui-lg border border-border bg-surface p-4">
          <h2 class="text-sm font-semibold">允许访问的工作空间</h2>
          <p class="text-xs text-text-secondary">至少选择一个空间。授权仅包含您选择的空间。</p>
          <p v-if="!view.workspaces.length" class="text-sm text-text-secondary">当前没有可授权的工作空间，可以拒绝本次连接。</p>
          <div v-for="workspace in view.workspaces" :key="workspace.id" class="flex items-center gap-2">
            <UiCheckbox :id="`oauth-workspace-${workspace.id}`" :model-value="workspaceIds.includes(workspace.id)" :disabled="submitting || expired" @update:model-value="selectWorkspace(workspace.id, $event)" />
            <label :for="`oauth-workspace-${workspace.id}`" class="min-w-0 cursor-pointer break-words text-sm">{{ workspace.name }}</label>
          </div>
        </section>
        <section class="space-y-3 rounded-ui-lg border border-border bg-surface p-4">
          <h2 class="text-sm font-semibold">允许使用的能力</h2>
          <p class="text-xs text-text-secondary">读取权限默认选中。创建、修改、归档和执行任务需要您勾选对应的管理权限。</p>
          <div v-for="scope in view.scopes" :key="scope.scope" class="flex items-start gap-2 border-t border-border-muted pt-3">
            <UiCheckbox :id="`oauth-scope-${scope.scope}`" :model-value="scopes.includes(scope.scope)" :disabled="submitting || expired" class="mt-0.5" @update:model-value="selectScope(scope.scope, $event)" />
            <div class="min-w-0 flex-1 space-y-1">
              <div class="flex items-center gap-2">
                <label :for="`oauth-scope-${scope.scope}`" class="cursor-pointer text-sm font-medium">{{ oauthScopeLabel(scope.scope) }}</label>
                <UiBadge v-if="scope.scope.endsWith(':write')" tone="warning" size="sm">写入</UiBadge>
              </div>
              <p class="break-words text-xs text-text-secondary">{{ scope.operations.join('；') }}</p>
            </div>
          </div>
        </section>
        <p class="break-all text-xs text-text-secondary">连接服务：{{ view.resource }}</p>
        <p v-if="expired" role="alert" class="text-sm text-danger-strong">授权请求已过期，请返回 ChatGPT 重新连接。</p>
        <p v-else class="text-xs text-text-secondary">请在 {{ formatDateTime(view.expires_at) }} 前完成确认。之后可在账户设置的“外部授权”中撤销。</p>
        <div class="flex justify-end gap-2 border-t border-border pt-4">
          <UiButton variant="secondary" :disabled="submitting || expired" @click="decide(false)">拒绝</UiButton>
          <UiButton :disabled="!canApprove" :loading="submitting" @click="decide(true)">授权并返回 ChatGPT</UiButton>
        </div>
      </template>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import SettingsPageHeader from '@/components/layout/SettingsPageHeader.vue'
import { UiBadge, UiButton, UiCheckbox } from '@/components/ui'
import { useOAuthConsent } from '@/composables/useOAuthConsent'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'
import { oauthScopeLabel } from '@/utils/oauth'

const auth = useAuthStore()
const route = useRoute()
const query = computed(() => typeof route.query.authorization_query === 'string' ? route.query.authorization_query : '')
const { view, loading, submitting, error, scopes, workspaceIds, expired, canApprove, decide, selectScope, selectWorkspace } = useOAuthConsent(query)
</script>
