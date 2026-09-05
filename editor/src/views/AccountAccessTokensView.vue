<!-- 文件功能：管理用户个人访问令牌（PAT），提供创建、权限选择、明文密钥单次展示与即时吊销功能。 -->
<template>
  <div class="max-w-6xl mx-auto space-y-6 py-6 px-4">
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-text-strong">个人访问令牌 (PAT)</h1>
        <p class="text-sm text-text-secondary mt-1">
          用于通过 External API、CLI (<code class="text-xs bg-surface-muted px-1.5 py-0.5 rounded text-accent font-mono">wp</code>) 及桌面开发工具安全访问工作空间资源与自动化构建。
        </p>
      </div>
      <UiButton variant="primary" @click="openCreateDialog">
        <template #icon><Key class="w-4 h-4 mr-1.5" /></template>
        创建新令牌
      </UiButton>
    </div>

    <!-- Token Table -->
    <div class="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
      <div v-if="loading" class="p-8 text-center text-sm text-text-muted">
        正在加载访问令牌...
      </div>
      <div v-else-if="tokens.length === 0" class="p-12 text-center space-y-3">
        <ShieldAlert class="w-10 h-10 text-text-disabled mx-auto" />
        <p class="text-base font-semibold text-text">暂无访问令牌</p>
        <p class="text-sm text-text-secondary max-w-md mx-auto">
          创建个人访问令牌后，您可以在命令行或脚本中直接调用平台 API 与构建服务。
        </p>
        <UiButton variant="secondary" size="sm" @click="openCreateDialog">创建首个令牌</UiButton>
      </div>
      <table v-else class="w-full table-fixed text-left text-sm">
        <thead class="bg-canvas text-xs font-semibold uppercase text-text-muted border-b border-border">
          <tr>
            <th class="w-48 px-4 py-3.5">令牌名称</th>
            <th class="w-48 px-4 py-3.5">标识</th>
            <th class="px-4 py-3.5">权限 Scope</th>
            <th class="w-28 px-4 py-3.5">状态</th>
            <th class="w-40 px-4 py-3.5">最后使用</th>
            <th class="w-40 px-4 py-3.5">到期时间</th>
            <th class="w-24 px-4 py-3.5 text-right">操作</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border-muted">
          <tr v-for="item in tokens" :key="item.id" class="hover:bg-surface-muted/50 transition-colors">
            <td class="px-4 py-3.5">
              <div class="truncate font-medium text-text">{{ item.name }}</div>
              <div class="mt-0.5 truncate text-[11px] text-text-muted">
                {{ formatWorkspaceAuthorization(item) }}
              </div>
            </td>
            <td class="px-4 py-3.5 font-mono text-xs text-text-secondary truncate">
              {{ item.token_masked }}
            </td>
            <td class="px-4 py-3.5">
              <div class="flex flex-wrap gap-1 max-h-16 overflow-y-auto">
                <span
                  v-for="scope in item.scopes"
                  :key="scope"
                  class="inline-block px-1.5 py-0.5 rounded text-[11px] font-mono bg-surface-muted text-text-secondary border border-border-muted"
                >
                  {{ scope }}
                </span>
              </div>
            </td>
            <td class="px-4 py-3.5">
              <span
                v-if="item.revoked_at"
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-surface-muted text-text-disabled"
              >
                已吊销
              </span>
              <span
                v-else-if="!item.is_active"
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-warning-muted text-warning-strong"
              >
                已过期
              </span>
              <span
                v-else
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-success-muted text-success-strong"
              >
                活跃中
              </span>
            </td>
            <td class="px-4 py-3.5 text-xs text-text-secondary">
              <div v-if="item.last_used_at">
                <div>{{ formatDate(item.last_used_at) }}</div>
                <div v-if="item.last_used_ip" class="text-text-disabled text-[11px] font-mono">{{ item.last_used_ip }}</div>
              </div>
              <span v-else class="text-text-disabled">从未</span>
            </td>
            <td class="px-4 py-3.5 text-xs text-text-secondary">
              {{ item.expires_at ? formatDate(item.expires_at) : '长期有效' }}
            </td>
            <td class="px-4 py-3.5 text-right">
              <UiButton
                v-if="item.is_active"
                variant="ghost"
                size="sm"
                class="text-danger hover:text-danger-strong hover:bg-danger-muted"
                @click="openRevokeConfirm(item)"
              >
                吊销
              </UiButton>
              <span v-else class="text-xs text-text-disabled">-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create Dialog -->
    <UiDialog
      :open="createDialogOpen"
      title="创建个人访问令牌"
      size="standard"
      @update:open="createDialogOpen = $event"
    >
      <div class="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
        <UiFormField label="令牌名称" required :error="formErrors.name" v-slot="field">
          <UiInput
            v-model="createForm.name"
            placeholder="例如：CLI-MacBook-Pro 或 CI-Build-Worker"
            :input-id="field.inputId"
            :described-by="field.describedBy"
            :invalid="field.invalid"
          />
        </UiFormField>

        <UiFormField label="有效期限" required v-slot="field">
          <UiSelect
            v-model="createForm.expires_in_days"
            :options="expiresOptions"
            :input-id="field.inputId"
          />
        </UiFormField>

        <!-- Workspace selection -->
        <UiFormField label="授权工作空间" required :error="formErrors.workspaces">
          <UiSegmentedControl
            v-model="createForm.workspace_authorization"
            aria-label="工作空间授权范围"
            :options="workspaceAuthorizationOptions"
          />
          <p v-if="createForm.workspace_authorization === 'all'" class="mt-2 text-xs text-text-secondary">
            可访问您当前及未来加入的所有工作空间；每次访问仍会校验有效成员资格。
          </p>
          <div v-else class="mt-2 border border-border rounded-lg p-3 max-h-40 overflow-y-auto space-y-2 bg-canvas">
            <div
              v-for="ws in availableWorkspaces"
              :key="ws.id"
              class="flex items-center gap-2 cursor-pointer select-none"
              @click="toggleWorkspace(ws.id)"
            >
              <UiCheckbox
                :model-value="createForm.workspace_ids.includes(ws.id)"
                @click.stop
                @update:model-value="toggleWorkspace(ws.id)"
              />
              <span class="text-sm font-medium text-text">{{ ws.name }}</span>
              <span class="text-xs text-text-disabled font-mono">(ID: {{ ws.id }})</span>
            </div>
          </div>
        </UiFormField>

        <!-- Scope selection -->
        <UiFormField label="授权权限 Scope" required :error="formErrors.scopes">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs text-text-secondary">选择该令牌可执行的操作范围</span>
            <div class="space-x-2 text-xs">
              <UiButton variant="ghost" size="xs" @click="selectAllScopes">全选</UiButton>
              <UiButton variant="ghost" size="xs" @click="createForm.scopes = []">清空</UiButton>
            </div>
          </div>
          <div class="border border-border rounded-lg p-3 max-h-56 overflow-y-auto space-y-2.5 bg-canvas divide-y divide-border-muted">
            <div
              v-for="scopeInfo in availableScopes"
              :key="scopeInfo.scope"
              class="pt-2 first:pt-0 flex items-start gap-2.5 cursor-pointer select-none"
              @click="toggleScope(scopeInfo.scope)"
            >
              <UiCheckbox
                class="mt-0.5"
                :model-value="createForm.scopes.includes(scopeInfo.scope)"
                @click.stop
                @update:model-value="toggleScope(scopeInfo.scope)"
              />
              <div class="flex-1">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-mono font-semibold text-text">{{ scopeInfo.scope }}</span>
                  <span class="text-[10px] text-text-disabled">({{ scopeInfo.operation_count }} 项操作)</span>
                </div>
                <p class="text-xs text-text-secondary mt-0.5">{{ scopeInfo.description }}</p>
              </div>
            </div>
          </div>
        </UiFormField>
      </div>

      <template #footer>
        <UiButton variant="ghost" @click="createDialogOpen = false">取消</UiButton>
        <UiButton variant="primary" :loading="creating" @click="handleCreateToken">生成令牌</UiButton>
      </template>
    </UiDialog>

    <!-- Token Created Success Dialog -->
    <UiDialog
      :open="successDialogOpen"
      title="令牌创建成功"
      size="standard"
      @update:open="successDialogOpen = $event"
    >
      <div class="space-y-4">
        <div class="p-3.5 rounded-lg bg-warning-muted/40 border border-warning-strong/30 flex items-start gap-3">
          <ShieldAlert class="w-5 h-5 text-warning-strong flex-shrink-0 mt-0.5" />
          <div class="text-xs text-text space-y-1">
            <p class="font-semibold text-warning-strong">请立即复制并妥善保管您的访问令牌！</p>
            <p>出于安全原因，该完整明文令牌<strong>将不会再次显示</strong>。离开本页面后您将无法找回此令牌。</p>
          </div>
        </div>

        <div class="space-y-2">
          <label class="text-xs font-semibold text-text-secondary">访问令牌 (Bearer Token)</label>
          <div class="flex items-center gap-2">
            <UiInput
              :model-value="createdTokenSecret"
              class="font-mono text-xs"
              readonly
            />
            <UiButton variant="secondary" size="sm" @click="copySecret">
              <template #icon><Copy class="w-4 h-4 mr-1" /></template>
              复制
            </UiButton>
          </div>
        </div>

        <div class="text-xs text-text-secondary space-y-1 border-t border-border pt-3">
          <p><strong>使用提示：</strong></p>
          <p>CLI 快速登录：<code class="font-mono bg-surface-muted px-1.5 py-0.5 rounded text-accent">wp login --token &lt;YOUR_TOKEN&gt;</code></p>
          <p>HTTP 调用方式：在请求头中附带 <code class="font-mono bg-surface-muted px-1.5 py-0.5 rounded">Authorization: Bearer &lt;YOUR_TOKEN&gt;</code></p>
        </div>
      </div>

      <template #footer>
        <UiButton variant="primary" @click="successDialogOpen = false">我已安全保存令牌</UiButton>
      </template>
    </UiDialog>

    <!-- Revoke Confirm Dialog -->
    <UiDialog
      :open="revokeDialogOpen"
      title="吊销访问令牌"
      size="compact"
      @update:open="revokeDialogOpen = $event"
    >
      <div class="space-y-3">
        <p class="text-sm text-text">
          确定要吊销令牌 <strong>{{ tokenToRevoke?.name }}</strong> 吗？
        </p>
        <p class="text-xs text-text-secondary">
          吊销后，使用该令牌的所有 CLI、自动化脚本及 API 请求将立即失效且不可恢复。
        </p>
      </div>

      <template #footer>
        <UiButton variant="ghost" @click="revokeDialogOpen = false">取消</UiButton>
        <UiButton variant="danger" :loading="revoking" @click="handleRevokeToken">
          确认吊销
        </UiButton>
      </template>
    </UiDialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { Copy, Key, ShieldAlert } from '@lucide/vue'

import { createAccessToken, listAccessTokens, listAccessTokenScopes, revokeAccessToken } from '@/api/accessTokens'
import { listWorkspaces } from '@/api/catalog'
import { getErrorMessage } from '@/api/http'
import { UiButton, UiCheckbox, UiDialog, UiFormField, UiInput, UiSegmentedControl, UiSelect } from '@/components/ui'
import type { SelectOption } from '@/components/ui/select'
import type {
  ApiAccessTokenItem,
  ApiAccessTokenScopeInfo,
} from '@/types/accessTokens'
import type { WorkspaceItem } from '@/types/api'
import { Message } from '@/utils/message'

const loading = ref(false)
const tokens = ref<ApiAccessTokenItem[]>([])
const availableScopes = ref<ApiAccessTokenScopeInfo[]>([])
const availableWorkspaces = ref<WorkspaceItem[]>([])

const expiresOptions: SelectOption[] = [
  { label: '7 天', value: 7 },
  { label: '30 天（推荐）', value: 30 },
  { label: '90 天', value: 90 },
  { label: '180 天', value: 180 },
  { label: '365 天', value: 365 },
  { label: '长期有效', value: 'never' },
]

const workspaceAuthorizationOptions = [
  { label: '所有工作空间', value: 'all' },
  { label: '指定工作空间', value: 'selected' },
]

type WorkspaceAuthorization = 'all' | 'selected'
type ExpirationSelection = number | 'never'

const createDialogOpen = ref(false)
const creating = ref(false)
const createForm = reactive({
  name: '',
  expires_in_days: 30 as ExpirationSelection,
  workspace_authorization: 'selected' as WorkspaceAuthorization,
  workspace_ids: [] as number[],
  scopes: [] as string[],
})
const formErrors = reactive({
  name: '',
  workspaces: '',
  scopes: '',
})

const successDialogOpen = ref(false)
const createdTokenSecret = ref('')

const revokeDialogOpen = ref(false)
const revoking = ref(false)
const tokenToRevoke = ref<ApiAccessTokenItem | null>(null)

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  try {
    const d = new Date(dateStr)
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

/** 生成人类可读的工作空间授权范围，避免把空 ID 列表误解为无权限。 */
function formatWorkspaceAuthorization(item: ApiAccessTokenItem): string {
  if (item.all_workspaces) return '所有工作空间'
  if (item.workspace_ids.length === 1) {
    const workspace = availableWorkspaces.value.find((candidate) => candidate.id === item.workspace_ids[0])
    return workspace?.name ?? `工作空间 ID: ${item.workspace_ids[0]}`
  }
  return `${item.workspace_ids.length} 个指定工作空间`
}

async function loadData() {
  loading.value = true
  try {
    const [tokensRes, scopesRes, wsRes] = await Promise.all([
      listAccessTokens(),
      listAccessTokenScopes(),
      listWorkspaces({ page: 1, page_size: 100 }),
    ])
    tokens.value = tokensRes.items
    availableScopes.value = scopesRes
    availableWorkspaces.value = wsRes.items
  } catch (err) {
    Message.error(getErrorMessage(err, '加载访问令牌列表失败'))
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  createForm.name = ''
  createForm.expires_in_days = 30
  createForm.workspace_authorization = 'selected'
  createForm.workspace_ids = availableWorkspaces.value.map((w) => w.id)
  createForm.scopes = availableScopes.value.map((s) => s.scope)
  formErrors.name = ''
  formErrors.workspaces = ''
  formErrors.scopes = ''
  createDialogOpen.value = true
}

function toggleWorkspace(wsId: number) {
  const index = createForm.workspace_ids.indexOf(wsId)
  if (index >= 0) {
    createForm.workspace_ids.splice(index, 1)
  } else {
    createForm.workspace_ids.push(wsId)
  }
}

function toggleScope(scope: string) {
  const index = createForm.scopes.indexOf(scope)
  if (index >= 0) {
    createForm.scopes.splice(index, 1)
  } else {
    createForm.scopes.push(scope)
  }
}

function selectAllScopes() {
  createForm.scopes = availableScopes.value.map((s) => s.scope)
}

async function handleCreateToken() {
  let hasError = false
  if (!createForm.name.trim()) {
    formErrors.name = '请输入令牌名称'
    hasError = true
  } else {
    formErrors.name = ''
  }

  if (createForm.workspace_authorization === 'selected' && createForm.workspace_ids.length === 0) {
    formErrors.workspaces = '请至少选择一个授权工作空间'
    hasError = true
  } else {
    formErrors.workspaces = ''
  }

  if (createForm.scopes.length === 0) {
    formErrors.scopes = '请至少选择一项权限 Scope'
    hasError = true
  } else {
    formErrors.scopes = ''
  }

  if (hasError) return

  creating.value = true
  try {
    const res = await createAccessToken({
      name: createForm.name.trim(),
      expires_in_days: createForm.expires_in_days === 'never' ? null : createForm.expires_in_days,
      all_workspaces: createForm.workspace_authorization === 'all',
      workspace_ids: createForm.workspace_authorization === 'all' ? [] : createForm.workspace_ids,
      scopes: createForm.scopes,
    })
    createDialogOpen.value = false
    createdTokenSecret.value = res.token
    successDialogOpen.value = true
    await loadData()
  } catch (err) {
    Message.error(getErrorMessage(err, '创建访问令牌失败'))
  } finally {
    creating.value = false
  }
}

async function copySecret() {
  try {
    await navigator.clipboard.writeText(createdTokenSecret.value)
    Message.success('令牌已复制到剪贴板')
  } catch {
    Message.warning('复制失败，请手动选中文本进行复制')
  }
}

function openRevokeConfirm(item: ApiAccessTokenItem) {
  tokenToRevoke.value = item
  revokeDialogOpen.value = true
}

async function handleRevokeToken() {
  if (!tokenToRevoke.value) return
  revoking.value = true
  try {
    await revokeAccessToken(tokenToRevoke.value.id)
    Message.success('令牌已成功吊销')
    revokeDialogOpen.value = false
    await loadData()
  } catch (err) {
    Message.error(getErrorMessage(err, '吊销令牌失败'))
  } finally {
    revoking.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>
