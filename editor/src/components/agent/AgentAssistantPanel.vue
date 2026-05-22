<!-- 文件功能：提供统一内容助手面板入口，向下复用通用会话与 SSE 面板实现。 -->
<template>
  <AgentConversationPanel
    :workspace-id="workspaceId"
    :project-id="projectId"
    :page-id="pageId"
    :component-id="componentId"
    :page-title="pageTitle"
    :agent-id="agentId"
    :agent-display-name="agentDisplayName"
    :scope="scope"
    :route-scope="routeScope"
    :context-title="contextTitle"
    :enable-page-patch-actions="enablePagePatchActions"
    :empty-text="emptyText"
    :composer-placeholder="composerPlaceholder"
    :embedded="embedded"
    :header-scope-target="headerScopeTarget"
    :header-actions-target="headerActionsTarget"
    :route-available="routeAvailable"
    :route-unavailable-reason="routeUnavailableReason"
    :auto-create-key="autoCreateKey"
    :auto-navigate-target="autoNavigateTarget"
    @apply-suggested-content="emit('apply-suggested-content', $event)"
    @page-updated="emit('page-updated', $event)"
    @project-pages-updated="emit('project-pages-updated', $event)"
    @project-updated="emit('project-updated', $event)"
    @component-updated="emit('component-updated', $event)"
    @asset-updated="emit('asset-updated', $event)"
  />
</template>

<script setup lang="ts">
import AgentConversationPanel from '@/components/agent/AgentConversationPanel.vue'
import type { AgentMutationRefreshEvent } from '@/components/agent/agent-conversation-panel'
import type { AgentScopeContext } from '@/types/api'

interface Props {
  workspaceId: number
  projectId?: number | null
  pageId?: number | null
  componentId?: number | null
  pageTitle?: string
  agentId?: string
  agentDisplayName?: string
  scope?: AgentScopeContext | null
  routeScope?: AgentScopeContext | null
  contextTitle?: string
  enablePagePatchActions?: boolean
  emptyText?: string
  composerPlaceholder?: string
  embedded?: boolean
  headerScopeTarget?: string | null
  headerActionsTarget?: string | null
  routeAvailable?: boolean
  routeUnavailableReason?: string
  autoCreateKey?: string | number | null
  autoNavigateTarget?: string | null
}

withDefaults(defineProps<Props>(), {
  projectId: null,
  pageId: null,
  componentId: null,
  pageTitle: '',
  agentId: 'agent-coordinator',
  agentDisplayName: '内容助手',
  scope: null,
  routeScope: null,
  contextTitle: '',
  enablePagePatchActions: false,
  emptyText: '',
  composerPlaceholder: '',
  embedded: false,
  headerScopeTarget: null,
  headerActionsTarget: null,
  routeAvailable: true,
  routeUnavailableReason: '',
  autoCreateKey: null,
  autoNavigateTarget: null,
})

const emit = defineEmits<{
  'apply-suggested-content': [content: string]
  'page-updated': [event: AgentMutationRefreshEvent]
  'project-pages-updated': [event: AgentMutationRefreshEvent]
  'project-updated': [event: AgentMutationRefreshEvent]
  'component-updated': [event: AgentMutationRefreshEvent]
  'asset-updated': [event: AgentMutationRefreshEvent]
}>()
</script>
