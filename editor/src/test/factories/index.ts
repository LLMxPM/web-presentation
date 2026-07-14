/**
 * 文件功能：提供 Editor 测试中复用的轻量假数据工厂。
 */
import type { AgentScopeContext, PageItem } from '@/types/api'

/**
 * 生成默认的页面级智能体 scope。
 * @param overrides 需要覆盖的字段
 * @returns 标准化页面 scope
 */
export function createPageScope(overrides: Partial<AgentScopeContext> = {}): AgentScopeContext {
  return {
    scope_type: 'page',
    workspace_id: 11,
    project_id: 21,
    page_id: 31,
    component_id: null,
    workspace_name: 'Smoke Workspace',
    project_name: 'Smoke Project',
    page_title: 'Smoke Page',
    component_name: null,
    source: 'editor-page-detail',
    ...overrides,
  }
}

/**
 * 生成默认的页面列表项，便于页面和截图相关测试复用。
 * @param overrides 需要覆盖的字段
 * @returns 页面列表项
 */
export function createPageItem(overrides: Partial<PageItem> = {}): PageItem {
  return {
    id: 31,
    code: 'PG202605120001',
    page_content: '<template><main>Smoke Page</main></template>',
    current_version_no: 1,
    file_type: 'vue',
    title: 'Smoke Page',
    summary: '平台 smoke 页面',
    status: 'active',
    workspace_id: 11,
    workspace_name: 'Smoke Workspace',
    project_id: 21,
    project_name: 'Smoke Project',
    created_at: '2026-05-12T09:00:00Z',
    updated_at: '2026-05-12T09:00:00Z',
    created_by: 1,
    updated_by: 1,
    screenshot_url: null,
    screenshot_version_no: null,
    screenshot_config_hash: null,
    screenshot_viewport_width: null,
    screenshot_viewport_height: null,
    screenshot_is_latest: false,
    screenshot_updated_at: null,
    is_in_project_route: true,
    route_bindings: [],
    ...overrides,
  }
}
