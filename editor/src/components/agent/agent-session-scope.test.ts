/**
 * 文件功能：验证智能体会话选择面板使用会话名和完整 scope 路径。
 */
import { describe, expect, it } from 'vitest'

import {
  isRouteScopeInsideSessionScope,
  resolveSessionDisplayName,
  resolveSessionScopePath,
  resolveSessionSubtitle,
} from '@/components/agent/agent-session-scope'
import type { AgentScopeContext, AgentSessionItem } from '@/types/api'

function createSession(metadata: Record<string, unknown>, sessionName = '页面排版优化'): AgentSessionItem {
  return {
    session_id: 'session-1',
    agent_id: 'agent-coordinator',
    workspace_id: 11,
    session_name: sessionName,
    focus_mode: 'follow_route',
    pinned_project_id: null,
    work_scope_mode: 'workspace',
    allowed_project_ids: [],
    focus_version: 0,
    created_at: '2026-05-11T10:00:00+08:00',
    updated_at: '2026-05-11T10:30:00+08:00',
    metadata,
  }
}

function createScope(overrides: Partial<AgentScopeContext>): AgentScopeContext {
  return {
    scope_type: 'workspace',
    workspace_id: 11,
    project_id: null,
    page_id: null,
    component_id: null,
    workspace_name: '演示工作区',
    project_name: null,
    page_title: null,
    component_name: null,
    source: 'editor-agent-sidebar',
    ...overrides,
  }
}

describe('agent-session-scope', () => {
  it('会话列表主标题应优先展示会话名称', () => {
    const session = createSession({
      scope_type: 'page',
      workspace_id: 11,
      workspace_name: '演示工作区',
      project_id: 21,
      project_name: '发布会方案',
      page_id: 31,
      page_title: '封面页',
      source: 'editor-page-detail',
    })

    expect(resolveSessionDisplayName(session)).toBe('页面排版优化')
  })

  it('会话路径只展示稳定的工作空间授权边界', () => {
    const session = createSession({
      scope_type: 'page',
      workspace_id: 11,
      workspace_name: '演示工作区',
      project_id: 21,
      project_name: '发布会方案',
      page_id: 31,
      page_title: '封面页',
      source: 'editor-page-detail',
    })

    expect(resolveSessionScopePath(session)).toBe('工作空间 #11')
  })

  it('旧 metadata 中的库入口不再改变会话路径', () => {
    const session = createSession({
      scope_type: 'workspace',
      workspace_id: 11,
      workspace_name: '演示工作区',
      source: 'editor-component-library',
    }, '组件整理')

    expect(resolveSessionScopePath(session)).toBe('工作空间 #11')
  })

  it('会话更新时间应使用简短月日时分格式', () => {
    const session = createSession({
      scope_type: 'workspace',
      workspace_id: 11,
      source: 'editor-agent-sidebar',
    })

    expect(resolveSessionSubtitle(session)).toBe('05-11 10:30')
  })

  it('同一工作空间内的所有路由都属于同一会话边界', () => {
    const componentLibraryScope = createScope({ source: 'editor-component-library' })
    const assetLibraryScope = createScope({ source: 'editor-asset-library' })
    const pageRouteScope = createScope({
      scope_type: 'page',
      project_id: 21,
      page_id: 31,
      page_title: '封面页',
      source: 'editor-page-detail',
    })

    expect(isRouteScopeInsideSessionScope(componentLibraryScope, pageRouteScope)).toBe(true)
    expect(isRouteScopeInsideSessionScope(assetLibraryScope, componentLibraryScope)).toBe(true)
    expect(isRouteScopeInsideSessionScope(componentLibraryScope, createScope({ source: 'editor-component-library' }))).toBe(true)
  })

  it('历史组件详情会话在组件库路由内仍可继续展示', () => {
    const componentSessionScope = createScope({
      scope_type: 'component',
      component_id: 99,
      component_name: '销售卡片',
      source: 'editor-component-library',
    })
    const componentLibraryRouteScope = createScope({ source: 'editor-component-library' })

    expect(isRouteScopeInsideSessionScope(componentSessionScope, componentLibraryRouteScope)).toBe(true)
  })
})
