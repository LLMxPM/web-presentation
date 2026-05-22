/**
 * 文件功能：封装工作空间主题库的列表、详情与 CRUD 接口访问方法。
 */
import { http } from '@/api/http'
import type { ListParams, PagedResponse, ThemePalette, WorkspaceThemeItem } from '@/types/api'

function buildParams<T extends object>(params: ListParams & T) {
  const { page, page_size, keyword, status, sort_by, sort_order, ...rest } = params
  const normalizedRest = Object.fromEntries(
    Object.entries(rest).filter(([, value]) => value !== '' && value !== null && value !== undefined),
  )

  return {
    ...normalizedRest,
    page,
    page_size,
    keyword: keyword || undefined,
    status: status || undefined,
    sort_by: sort_by ?? 'updated_at',
    sort_order: sort_order ?? 'desc',
  }
}

export interface WorkspaceThemePayload {
  key: string
  name: string
  description?: string | null
  logo_asset_id?: number | null
  invert_logo_asset_id?: number | null
  project_icon_asset_id?: number | null
  heading_font_id?: number | null
  body_font_id?: number | null
  code_font_id?: number | null
  palette: ThemePalette
}

/** 查询工作空间主题列表。 */
export async function listWorkspaceThemes(workspaceId: number, params: ListParams = { page: 1, page_size: 100 }) {
  const { data } = await http.get<PagedResponse<WorkspaceThemeItem>>(`/workspaces/${workspaceId}/themes`, {
    params: buildParams(params),
  })
  return data
}

/** 获取工作空间主题详情。 */
export async function getWorkspaceTheme(workspaceId: number, themeId: number) {
  const { data } = await http.get<WorkspaceThemeItem>(`/workspaces/${workspaceId}/themes/${themeId}`)
  return data
}

/** 创建工作空间主题。 */
export async function createWorkspaceTheme(workspaceId: number, payload: WorkspaceThemePayload) {
  const { data } = await http.post<WorkspaceThemeItem>(`/workspaces/${workspaceId}/themes`, payload)
  return data
}

/** 更新工作空间主题。 */
export async function updateWorkspaceTheme(
  workspaceId: number,
  themeId: number,
  payload: Partial<WorkspaceThemePayload>,
) {
  const { data } = await http.patch<WorkspaceThemeItem>(`/workspaces/${workspaceId}/themes/${themeId}`, payload)
  return data
}

/** 复制工作空间主题。 */
export async function copyWorkspaceTheme(
  workspaceId: number,
  themeId: number,
  payload: { key?: string | null; name?: string | null } = {},
) {
  const { data } = await http.post<WorkspaceThemeItem>(`/workspaces/${workspaceId}/themes/${themeId}/copy`, payload)
  return data
}

/** 删除工作空间主题。 */
export async function deleteWorkspaceTheme(workspaceId: number, themeId: number) {
  const { data } = await http.delete<{ message: string }>(`/workspaces/${workspaceId}/themes/${themeId}`)
  return data
}
