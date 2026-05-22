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
    session_name: sessionName,
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

  it('页面 scope 应展示工作空间到页面的完整路径', () => {
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

    expect(resolveSessionScopePath(session)).toBe('演示工作区 / 发布会方案 / 封面页')
  })

  it('工作空间级工具入口应在路径中补充库入口名称', () => {
    const session = createSession({
      scope_type: 'workspace',
      workspace_id: 11,
      workspace_name: '演示工作区',
      source: 'editor-component-library',
    }, '组件整理')

    expect(resolveSessionScopePath(session)).toBe('演示工作区 / 组件库')
  })

  it('会话更新时间应使用简短月日时分格式', () => {
    const session = createSession({
      scope_type: 'workspace',
      workspace_id: 11,
      source: 'editor-agent-sidebar',
    })

    expect(resolveSessionSubtitle(session)).toBe('05-11 10:30')
  })

  it('组件库与资源库工作空间会话只应匹配对应库路由', () => {
    const componentLibraryScope = createScope({ source: 'editor-component-library' })
    const assetLibraryScope = createScope({ source: 'editor-asset-library' })
    const pageRouteScope = createScope({
      scope_type: 'page',
      project_id: 21,
      page_id: 31,
      page_title: '封面页',
      source: 'editor-page-detail',
    })

    expect(isRouteScopeInsideSessionScope(componentLibraryScope, pageRouteScope)).toBe(false)
    expect(isRouteScopeInsideSessionScope(assetLibraryScope, componentLibraryScope)).toBe(false)
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
