/**
 * 文件功能：封装工作空间样式库的列表、详情与 CRUD 接口访问方法。
 */
import axios from 'axios'

import { http } from '@/api/http'
import type {
  ListParams,
  PagedResponse,
  ProjectMenuMode,
  WorkspaceStyleImportResult,
  WorkspaceStyleImportValidationResult,
  WorkspaceStyleItem,
} from '@/types/api'

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

export interface WorkspaceStylePayload {
  key: string
  name: string
  description?: string | null
  page_width: number
  page_height: number
  base_font_size: string
  icon_default_stroke_width: number
  show_pdf_export_button: boolean
  menu_mode: ProjectMenuMode
  theme_key?: string | null
  style_spec_markdown: string
}

/** 查询工作空间样式列表。 */
export async function listWorkspaceStyles(workspaceId: number, params: ListParams = { page: 1, page_size: 100 }) {
  const { data } = await http.get<PagedResponse<WorkspaceStyleItem>>(`/workspaces/${workspaceId}/styles`, {
    params: buildParams(params),
  })
  return data
}

/** 获取工作空间样式详情。 */
export async function getWorkspaceStyle(workspaceId: number, styleId: number) {
  const { data } = await http.get<WorkspaceStyleItem>(`/workspaces/${workspaceId}/styles/${styleId}`)
  return data
}

/** 创建工作空间样式。 */
export async function createWorkspaceStyle(workspaceId: number, payload: WorkspaceStylePayload) {
  const { data } = await http.post<WorkspaceStyleItem>(`/workspaces/${workspaceId}/styles`, payload)
  return data
}

/** 更新工作空间样式。 */
export async function updateWorkspaceStyle(
  workspaceId: number,
  styleId: number,
  payload: Partial<WorkspaceStylePayload>,
) {
  const { data } = await http.patch<WorkspaceStyleItem>(`/workspaces/${workspaceId}/styles/${styleId}`, payload)
  return data
}

/** 复制工作空间样式。 */
export async function copyWorkspaceStyle(
  workspaceId: number,
  styleId: number,
  payload: { key?: string | null; name?: string | null } = {},
) {
  const { data } = await http.post<WorkspaceStyleItem>(`/workspaces/${workspaceId}/styles/${styleId}/copy`, payload)
  return data
}

/** 删除工作空间样式。 */
export async function deleteWorkspaceStyle(workspaceId: number, styleId: number) {
  const { data } = await http.delete<{ message: string }>(`/workspaces/${workspaceId}/styles/${styleId}`)
  return data
}

/** 下载工作空间样式离线包。 */
export async function exportWorkspaceStylePackage(
  workspaceId: number,
  payload: { style_ids: number[] },
) {
  const response = await postDownloadBlob(`/workspaces/${workspaceId}/styles/export-package`, payload)
  return {
    blob: response.data,
    filename: resolveDownloadFilename(response.headers['content-disposition']) || 'workspace-styles.zip',
  }
}

/** 预检样式离线包。 */
export async function validateWorkspaceStylePackageImport(workspaceId: number, file: File) {
  const formData = new FormData()
  formData.append('archive', file)
  const { data } = await http.post<WorkspaceStyleImportValidationResult>(
    `/workspaces/${workspaceId}/styles/import-package/validate`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

/** 正式导入样式离线包。 */
export async function importWorkspaceStylePackage(workspaceId: number, file: File) {
  const formData = new FormData()
  formData.append('archive', file)
  const { data } = await http.post<WorkspaceStyleImportResult>(
    `/workspaces/${workspaceId}/styles/import-package`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

/**
 * 下载接口在失败时也会按 Blob 返回错误体，这里转回后端业务提示。
 */
async function postDownloadBlob(url: string, payload: unknown) {
  try {
    return await http.post<Blob>(url, payload, { responseType: 'blob' })
  } catch (error) {
    throw await normalizeDownloadError(error)
  }
}

/**
 * 将 Blob 形式的 JSON 错误体转换成普通 Error。
 */
async function normalizeDownloadError(error: unknown): Promise<Error> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    const message = await resolveBlobErrorMessage(error.response.data)
    if (message) {
      return new Error(message)
    }
  }
  return error instanceof Error ? error : new Error('下载失败。')
}

/**
 * 解析后端 AppException 返回的 Blob JSON。
 */
async function resolveBlobErrorMessage(blob: Blob): Promise<string | null> {
  const text = (await blob.text()).trim()
  if (!text) {
    return null
  }
  try {
    const data = JSON.parse(text) as unknown
    if (!isRecord(data)) {
      return text
    }
    const message = readNonEmptyString(data.message)
    if (message) {
      return message
    }
    const detail = readNonEmptyString(data.detail)
    if (detail) {
      return detail
    }
    const code = readNonEmptyString(data.code)
    return code ? `下载失败（${code}）` : text
  } catch {
    return text
  }
}

/**
 * 从 Content-Disposition 解析下载文件名。
 */
function resolveDownloadFilename(contentDisposition: unknown): string | null {
  const value = String(contentDisposition || '')
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }
  const plainMatch = value.match(/filename="?([^"]+)"?/i)
  return plainMatch?.[1] || null
}

function readNonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
