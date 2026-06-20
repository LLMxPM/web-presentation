/**
 * 文件功能：集中处理智能体会话的 scope 解析、会话选择持久化与路由定位。
 */
import type { AgentScopeContext, AgentSessionItem } from '@/types/api'
import { APP_TIMEZONE } from '@/utils/timezone'

export interface ScopeSummary {
  typeLabel: string
  title: string
  colorClass: string
}

const scopeTypeLabelMap: Record<AgentScopeContext['scope_type'], string> = {
  workspace: '工作空间',
  project: '项目',
  page: '页面',
  component: '组件',
}

const scopeTypeColorClassMap: Record<AgentScopeContext['scope_type'], string> = {
  workspace: 'border-slate-200 bg-slate-50 text-slate-500',
  project: 'border-emerald-200 bg-emerald-50 text-emerald-600',
  page: 'border-sky-200 bg-sky-50 text-sky-600',
  component: 'border-violet-200 bg-violet-50 text-violet-600',
}

const workspaceSourceLabelMap: Record<string, string> = {
  'editor-component-library': '组件库',
  'editor-asset-library': '资源库',
  'editor-theme-font-library': '主题与字体',
}

const routeBoundWorkspaceSources = new Set([
  'editor-component-library',
  'editor-asset-library',
  'editor-theme-font-library',
])

/**
 * 生成当前 scope 的本地会话选择 key，避免不同页面、项目和侧栏入口互相覆盖。
 */
export function buildSelectedSessionStorageKey(scopeValue: AgentScopeContext, agentIdValue: string) {
  return [
    'agent-session',
    'v2',
    agentIdValue,
    scopeValue.scope_type,
    scopeValue.workspace_id,
    scopeValue.project_id ?? '',
    scopeValue.page_id ?? '',
    scopeValue.component_id ?? '',
    scopeValue.source || '',
  ].map(normalizeSessionStoragePart).join(':')
}

/**
 * 读取当前 scope 上一次选中的 session_id，并只迁移指向当前 canonical 路由的旧 key。
 */
export function getSelectedSession(scopeValue: AgentScopeContext, agentIdValue: string, sessions: AgentSessionItem[]) {
  const persistedSessionId = localStorage.getItem(buildSelectedSessionStorageKey(scopeValue, agentIdValue)) ?? ''
  const persistedSession = sessions.find(item => item.session_id === persistedSessionId)
  if (persistedSession && isSessionTargetCurrentScope(persistedSession, scopeValue)) {
    return persistedSessionId
  }

  const legacySessionId = localStorage.getItem(buildLegacySelectedSessionStorageKey(scopeValue, agentIdValue)) ?? ''
  const legacySession = sessions.find(item => item.session_id === legacySessionId)
  if (legacySession && isSessionTargetCurrentScope(legacySession, scopeValue)) {
    setSelectedSession(scopeValue, agentIdValue, legacySessionId)
    return legacySessionId
  }

  return ''
}

/**
 * 记录当前 scope 选中的 session_id。
 */
export function setSelectedSession(scopeValue: AgentScopeContext, agentIdValue: string, sessionId: string) {
  localStorage.setItem(buildSelectedSessionStorageKey(scopeValue, agentIdValue), sessionId)
}

/**
 * 读取当前工作空间和智能体最近活跃的会话。
 */
export function getSelectedWorkspaceSession(scopeValue: AgentScopeContext, agentIdValue: string, sessions: AgentSessionItem[]) {
  const persistedSessionId = localStorage.getItem(buildWorkspaceSelectedSessionStorageKey(scopeValue, agentIdValue)) ?? ''
  const persistedSession = sessions.find(item => item.session_id === persistedSessionId)
  if (!persistedSession) {
    return ''
  }
  const sessionScope = resolveSessionScope(persistedSession)
  return sessionScope?.workspace_id === scopeValue.workspace_id ? persistedSessionId : ''
}

/**
 * 记录当前工作空间和智能体最近活跃的会话。
 */
export function setSelectedWorkspaceSession(scopeValue: AgentScopeContext, agentIdValue: string, sessionId: string) {
  localStorage.setItem(buildWorkspaceSelectedSessionStorageKey(scopeValue, agentIdValue), sessionId)
}

/**
 * 从 session metadata 中恢复工作范围，兼容旧会话缺少 scope_type 的数据。
 */
export function resolveSessionScope(session: AgentSessionItem): AgentScopeContext | null {
  const metadata = session.metadata ?? {}
  const workspaceId = toNumberOrNull(metadata.workspace_id)
  if (!workspaceId) {
    return null
  }
  const projectId = toNumberOrNull(metadata.project_id)
  const pageId = toNumberOrNull(metadata.page_id)
  const componentId = toNumberOrNull(metadata.component_id)
  const rawScopeType = String(metadata.scope_type || '')
  const scopeType = ['workspace', 'project', 'page', 'component'].includes(rawScopeType)
    ? rawScopeType as AgentScopeContext['scope_type']
    : pageId
      ? 'page'
      : componentId
        ? 'component'
        : projectId
          ? 'project'
          : 'workspace'
  return {
    scope_type: scopeType,
    workspace_id: workspaceId,
    project_id: projectId,
    page_id: pageId,
    component_id: componentId,
    workspace_name: toTextOrNull(metadata.workspace_name),
    project_name: toTextOrNull(metadata.project_name),
    page_title: toTextOrNull(metadata.page_title),
    component_name: toTextOrNull(metadata.component_name),
    source: toTextOrNull(metadata.source) || resolveDefaultSessionSource(session.agent_id),
  }
}

/**
 * 返回会话列表里的主标题，优先使用用户可编辑的会话名称。
 */
export function resolveSessionDisplayName(session: AgentSessionItem): string {
  const sessionName = session.session_name?.trim()
  if (sessionName) {
    return sessionName
  }
  const sessionScope = resolveSessionScope(session)
  if (!sessionScope) {
    return '未命名会话'
  }
  return `${resolveScopeTitle(sessionScope) || '未命名范围'} 会话`
}

/**
 * 返回 session 对应的最下级上下文名称，供旧入口和兼容展示复用。
 */
export function resolveSessionScopeName(session: AgentSessionItem): string {
  const sessionScope = resolveSessionScope(session)
  if (!sessionScope) {
    return session.session_name || '未命名会话'
  }
  if (sessionScope.scope_type === 'component') {
    return sessionScope.component_name || session.session_name || `组件 #${sessionScope.component_id}`
  }
  if (sessionScope.scope_type === 'page') {
    return sessionScope.page_title || session.session_name || `页面 #${sessionScope.page_id}`
  }
  if (sessionScope.scope_type === 'project') {
    return sessionScope.project_name || session.session_name || `项目 #${sessionScope.project_id}`
  }
  return sessionScope.workspace_name || session.session_name || `工作空间 #${sessionScope.workspace_id}`
}

/**
 * 返回 session 的完整业务范围路径，而不是只展示当前 scope 末级名称。
 */
export function resolveSessionScopePath(session: AgentSessionItem): string {
  const sessionScope = resolveSessionScope(session)
  if (!sessionScope) {
    return '未知范围'
  }
  return buildScopePathParts(sessionScope).join(' / ')
}

/**
 * 将智能体 scope 转换为顶部展示用的类型和名称。
 */
export function resolveScopeSummary(scopeValue: AgentScopeContext, fallbackTitle: string): ScopeSummary {
  return {
    typeLabel: scopeTypeLabelMap[scopeValue.scope_type],
    title: resolveScopeTitle(scopeValue) || fallbackTitle || '未命名范围',
    colorClass: scopeTypeColorClassMap[scopeValue.scope_type],
  }
}

/**
 * 生成 scope tooltip，未选择会话时避免展示空类型占位。
 */
export function formatScopeTooltip(label: string, summary: ScopeSummary): string {
  return summary.typeLabel ? `${label}：${summary.typeLabel} · ${summary.title}` : `${label}：${summary.title}`
}

/**
 * 返回 session 更新时间文案。
 */
export function resolveSessionSubtitle(session: AgentSessionItem): string {
  return formatBriefSessionTime(session.updated_at || session.created_at)
}

/**
 * 判断当前路由 scope 是否落在 session 工作范围内。
 */
export function isRouteScopeInsideSessionScope(sessionScope: AgentScopeContext, routeScope: AgentScopeContext): boolean {
  if (sessionScope.workspace_id !== routeScope.workspace_id) {
    return false
  }
  if (sessionScope.scope_type === 'workspace') {
    return isWorkspaceSourceInsideSessionScope(sessionScope, routeScope)
  }
  if (sessionScope.scope_type === 'project') {
    return routeScope.project_id !== null && routeScope.project_id !== undefined
      && routeScope.project_id === sessionScope.project_id
  }
  if (sessionScope.scope_type === 'page') {
    return routeScope.page_id !== null && routeScope.page_id !== undefined
      && routeScope.page_id === sessionScope.page_id
  }
  if (sessionScope.source === 'editor-component-library' && routeScope.source === 'editor-component-library') {
    return true
  }
  return routeScope.component_id !== null && routeScope.component_id !== undefined
    && routeScope.component_id === sessionScope.component_id
}

/**
 * 判断会话跳转目标是否就是当前路由 scope 的 canonical 目标。
 */
export function isSessionTargetCurrentScope(session: AgentSessionItem, scopeValue: AgentScopeContext): boolean {
  const sessionTarget = buildSessionRouteLocation(session)
  const scopeTarget = buildScopeRouteLocation(scopeValue)
  return sessionTarget !== null && sessionTarget === scopeTarget
}

/**
 * 从会话列表中选择当前路由目标下最近更新的会话。
 */
export function findLatestSessionForScope(sessions: AgentSessionItem[], scopeValue: AgentScopeContext): AgentSessionItem | null {
  const matchedSessions = sessions.filter(session => isSessionTargetCurrentScope(session, scopeValue))
  if (!matchedSessions.length) {
    return null
  }
  return [...matchedSessions].sort((left, right) => (
    resolveSessionUpdatedTime(right) - resolveSessionUpdatedTime(left)
  ))[0] ?? null
}

/**
 * 为 session 工作范围生成跳转入口。
 */
export function buildSessionRouteLocation(session: AgentSessionItem): string | null {
  const sessionScope = resolveSessionScope(session)
  if (!sessionScope) {
    return null
  }
  if (sessionScope.scope_type === 'workspace' && session.agent_id === 'component-manager') {
    return `/workspaces/${sessionScope.workspace_id}/components`
  }
  if (sessionScope.scope_type === 'workspace' && session.agent_id === 'resource-manager') {
    return `/workspaces/${sessionScope.workspace_id}/assets`
  }
  return buildScopeRouteLocation(sessionScope)
}

/**
 * 为业务 scope 生成唯一的前端 canonical 路由。
 */
export function buildScopeRouteLocation(scopeValue: AgentScopeContext): string | null {
  if (!scopeValue.workspace_id) {
    return null
  }
  if (scopeValue.scope_type === 'page' && scopeValue.project_id && scopeValue.page_id) {
    return `/workspaces/${scopeValue.workspace_id}/projects/${scopeValue.project_id}/pages/${scopeValue.page_id}`
  }
  if (scopeValue.scope_type === 'project' && scopeValue.project_id) {
    return `/workspaces/${scopeValue.workspace_id}/projects/${scopeValue.project_id}/pages`
  }
  if (scopeValue.scope_type === 'component') {
    return `/workspaces/${scopeValue.workspace_id}/components`
  }
  if (scopeValue.scope_type === 'workspace' && scopeValue.source === 'editor-component-library') {
    return `/workspaces/${scopeValue.workspace_id}/components`
  }
  if (scopeValue.scope_type === 'workspace' && scopeValue.source === 'editor-asset-library') {
    return `/workspaces/${scopeValue.workspace_id}/assets`
  }
  if (scopeValue.scope_type === 'workspace' && scopeValue.source === 'editor-theme-font-library') {
    return `/workspaces/${scopeValue.workspace_id}/themes`
  }
  return `/workspaces/${scopeValue.workspace_id}/home`
}

/**
 * 生成旧版 workspace 级 key，仅用于安全迁移历史选择。
 */
function buildLegacySelectedSessionStorageKey(scopeValue: AgentScopeContext, agentIdValue: string) {
  return [
    'agent-session',
    agentIdValue,
    scopeValue.workspace_id,
  ].map(normalizeSessionStoragePart).join(':')
}

/**
 * 生成工作空间级最近活跃会话 key，不随页面或项目路由变化。
 */
function buildWorkspaceSelectedSessionStorageKey(scopeValue: AgentScopeContext, agentIdValue: string) {
  return [
    'agent-session',
    'v3',
    'workspace-active',
    agentIdValue,
    scopeValue.workspace_id,
  ].map(normalizeSessionStoragePart).join(':')
}

/**
 * 兼容旧会话缺少 source 的数据，库助手按自身默认工作区入口恢复范围。
 */
function resolveDefaultSessionSource(agentId: string): string {
  if (agentId === 'component-manager') {
    return 'editor-component-library'
  }
  if (agentId === 'resource-manager') {
    return 'editor-asset-library'
  }
  return 'editor-agent-sidebar'
}

/**
 * 工作空间级组件库、资源库和主题字体会话只覆盖对应库路由，避免助手跨页面继续运行。
 */
function isWorkspaceSourceInsideSessionScope(sessionScope: AgentScopeContext, routeScope: AgentScopeContext): boolean {
  if (!routeBoundWorkspaceSources.has(sessionScope.source)) {
    return true
  }
  return routeScope.source === sessionScope.source
}

/**
 * 规整 localStorage key 片段，避免空值和冒号造成 key 碰撞。
 */
function normalizeSessionStoragePart(value: unknown): string {
  return encodeURIComponent(String(value ?? ''))
}

/**
 * 优先使用 scope 内的业务名称，没有名称时回退到稳定 ID。
 */
function resolveScopeTitle(scopeValue: AgentScopeContext): string {
  if (scopeValue.scope_type === 'component') {
    return scopeValue.component_name || formatScopeId('组件', scopeValue.component_id)
  }
  if (scopeValue.scope_type === 'page') {
    return scopeValue.page_title || formatScopeId('页面', scopeValue.page_id)
  }
  if (scopeValue.scope_type === 'project') {
    return scopeValue.project_name || formatScopeId('项目', scopeValue.project_id)
  }
  return scopeValue.workspace_name || formatScopeId('工作空间', scopeValue.workspace_id)
}

/**
 * 按工作空间、项目和目标对象顺序生成完整 scope 路径。
 */
function buildScopePathParts(scopeValue: AgentScopeContext): string[] {
  const parts = [
    scopeValue.workspace_name || formatScopeId('工作空间', scopeValue.workspace_id),
  ]
  const workspaceSourceLabel = workspaceSourceLabelMap[scopeValue.source]
  if (workspaceSourceLabel && (scopeValue.scope_type === 'workspace' || scopeValue.scope_type === 'component')) {
    parts.push(workspaceSourceLabel)
  }
  if (scopeValue.scope_type === 'project' || scopeValue.scope_type === 'page') {
    parts.push(scopeValue.project_name || formatScopeId('项目', scopeValue.project_id))
  }
  if (scopeValue.scope_type === 'page') {
    parts.push(scopeValue.page_title || formatScopeId('页面', scopeValue.page_id))
  }
  if (scopeValue.scope_type === 'component') {
    parts.push(scopeValue.component_name || formatScopeId('组件', scopeValue.component_id))
  }
  return parts.filter(Boolean)
}

/**
 * 在缺少业务名称时生成可识别的 scope 文案。
 */
function formatScopeId(label: string, id: number | null | undefined): string {
  return id === null || id === undefined ? '' : `${label} #${id}`
}

/**
 * 解析会话更新时间，缺失或非法时降级为 0。
 */
function resolveSessionUpdatedTime(session: AgentSessionItem): number {
  const timestamp = Date.parse(session.updated_at || session.created_at || '')
  return Number.isFinite(timestamp) ? timestamp : 0
}

/**
 * 将会话时间压缩为列表内适合一行展示的月日时分。
 */
function formatBriefSessionTime(value: string | null | undefined): string {
  if (!value) {
    return '刚刚'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '刚刚'
  }
  const parts = new Intl.DateTimeFormat('en-CA', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: APP_TIMEZONE,
  }).formatToParts(date)
  const month = parts.find(part => part.type === 'month')?.value ?? ''
  const day = parts.find(part => part.type === 'day')?.value ?? ''
  const hour = parts.find(part => part.type === 'hour')?.value ?? ''
  const minute = parts.find(part => part.type === 'minute')?.value ?? ''
  return `${month}-${day} ${hour}:${minute}`
}

function toNumberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

function toTextOrNull(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null
  }
  const text = String(value).trim()
  return text || null
}
