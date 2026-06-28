/**
 * 文件功能：与后端 Workspace 静态资产接口交互。
 */
import axios from 'axios'

import { http } from '@/api/http'
import type {
  AssetBatchOperationResponse,
  AssetContentPreviewResponse,
  AssetContentResponse,
  AssetPackageImportResult,
  AssetReferenceSummary,
  AssetResponse,
  AssetRole,
  AssetType,
  ListParams,
  PagedResponse,
  RecordStatus,
  WorkspaceFontConfigItem,
} from '@/types/api'

export interface ListWorkspaceAssetsOptions {
  assetType?: AssetType
  excludeAssetType?: AssetType
  assetRole?: AssetRole
  renderType?: AssetType
  status?: RecordStatus | null
  includeHistory?: boolean
  historyOnly?: boolean
  tag?: string
  page?: number
  page_size?: number
  keyword?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}

export interface ListWorkspaceAssetTagsOptions {
  assetType?: AssetType
  excludeAssetType?: AssetType
  status?: RecordStatus | null
  includeHistory?: boolean
  historyOnly?: boolean
}

/**
 * 清理通用列表查询参数，避免空字符串被序列化为非法筛选值。
 */
function buildListParams(params: ListParams): Record<string, string | number | undefined> {
  return {
    page: params.page,
    page_size: params.page_size,
    keyword: params.keyword || undefined,
    status: params.status || undefined,
    sort_by: params.sort_by,
    sort_order: params.sort_order,
  }
}

export async function uploadWorkspaceAsset(
  workspaceId: number, 
  file: File, 
  assetType: AssetType = 'icon', 
  tags: string[] = [],
  name?: string,
  description?: string,
  overwrite = false,
): Promise<AssetResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('asset_type', assetType)
  formData.append('tags', JSON.stringify(tags))
  if (overwrite) {
    formData.append('overwrite', 'true')
  }
  if (name !== undefined) {
    formData.append('name', name)
  }
  if (description !== undefined) {
    formData.append('description', description)
  }

  const { data } = await http.post<AssetResponse>(`/workspaces/${workspaceId}/assets/upload`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return data
}

export async function listWorkspaceAssets(
  workspaceId: number,
  assetTypeOrOptions?: AssetType | ListWorkspaceAssetsOptions,
): Promise<PagedResponse<AssetResponse>> {
  const params: Record<string, string> = {}
  const options: ListWorkspaceAssetsOptions = typeof assetTypeOrOptions === 'string'
    ? { assetType: assetTypeOrOptions }
    : assetTypeOrOptions ?? {}
  params.page = String(options.page ?? 1)
  params.page_size = String(options.page_size ?? 100)
  if (options.assetType) {
    params.asset_type = options.assetType
  }
  if (options.excludeAssetType) {
    params.exclude_asset_type = options.excludeAssetType
  }
  if (options.assetRole) {
    params.asset_role = options.assetRole
  }
  if (options.renderType) {
    params.render_type = options.renderType
  }
  if (options.status !== undefined && options.status !== null) {
    params.status = options.status
  }
  if (options.includeHistory !== undefined) {
    params.include_history = String(options.includeHistory)
  }
  if (options.historyOnly !== undefined) {
    params.history_only = String(options.historyOnly)
  }
  if (options.keyword) {
    params.keyword = options.keyword
  }
  if (options.tag) {
    params.tag = options.tag
  }
  if (options.sort_by) {
    params.sort_by = options.sort_by
  }
  if (options.sort_order) {
    params.sort_order = options.sort_order
  }
  const { data } = await http.get<PagedResponse<AssetResponse>>(`/workspaces/${workspaceId}/assets`, { params })
  return data
}

export async function listWorkspaceAssetTags(
  workspaceId: number,
  options: ListWorkspaceAssetTagsOptions = {},
): Promise<string[]> {
  const params: Record<string, string> = {}
  if (options.assetType) {
    params.asset_type = options.assetType
  }
  if (options.excludeAssetType) {
    params.exclude_asset_type = options.excludeAssetType
  }
  if (options.status !== undefined && options.status !== null) {
    params.status = options.status
  }
  if (options.includeHistory !== undefined) {
    params.include_history = String(options.includeHistory)
  }
  if (options.historyOnly !== undefined) {
    params.history_only = String(options.historyOnly)
  }
  const { data } = await http.get<string[]>(`/workspaces/${workspaceId}/assets/tags`, { params })
  return data
}

export async function createWorkspaceAssetContent(
  workspaceId: number,
  payload: {
    asset_type: AssetType
    name: string
    original_name: string
    content: string
    description?: string | null
    tags?: string[]
    approx_aspect_ratio?: string | null
  },
): Promise<AssetResponse> {
  const { data } = await http.post<AssetResponse>(`/workspaces/${workspaceId}/assets/content`, payload)
  return data
}

export async function getWorkspaceAssetContent(
  workspaceId: number,
  assetId: number,
): Promise<AssetContentResponse> {
  const { data } = await http.get<AssetContentResponse>(`/workspaces/${workspaceId}/assets/${assetId}/content`)
  return data
}

export async function previewWorkspaceAssetContentDiff(
  workspaceId: number,
  assetId: number,
  content: string,
): Promise<AssetContentPreviewResponse> {
  const { data } = await http.post<AssetContentPreviewResponse>(
    `/workspaces/${workspaceId}/assets/${assetId}/content/preview`,
    { content },
  )
  return data
}

export async function updateWorkspaceAssetContent(
  workspaceId: number,
  assetId: number,
  payload: {
    content: string
    change_note?: string | null
  },
): Promise<AssetResponse> {
  const { data } = await http.put<AssetResponse>(`/workspaces/${workspaceId}/assets/${assetId}/content`, payload)
  return data
}

export async function updateWorkspaceAsset(
  workspaceId: number,
  assetId: number,
  name?: string,
  originalName?: string,
  tags?: string[],
  description?: string | null,
  approxAspectRatio?: string | null,
): Promise<AssetResponse> {
  const payload: any = {}
  if (name !== undefined) payload.name = name
  if (originalName !== undefined) payload.original_name = originalName
  if (tags !== undefined) payload.tags = tags
  if (description !== undefined) payload.description = description
  if (approxAspectRatio !== undefined) payload.approx_aspect_ratio = approxAspectRatio

  const { data } = await http.put<AssetResponse>(`/workspaces/${workspaceId}/assets/${assetId}`, payload)
  return data
}

/**
 * 使用新文件替换指定资源的物理内容，保留后端资源记录和逻辑引用。
 * @param workspaceId 工作空间 ID
 * @param assetId 当前要替换的资源 ID
 * @param file 新文件对象
 * @returns 替换后的资源详情
 */
export async function replaceWorkspaceAssetFile(
  workspaceId: number,
  assetId: number,
  file: File,
): Promise<AssetResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const { data } = await http.post<AssetResponse>(`/workspaces/${workspaceId}/assets/${assetId}/replace`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return data
}

export async function copyWorkspaceAsset(
  workspaceId: number,
  assetId: number,
  payload: Partial<{
    name: string
    original_name: string
    description: string | null
    tags: string[]
    status: RecordStatus
    archive_reason: string | null
  }> = {},
): Promise<AssetResponse> {
  const { data } = await http.post<AssetResponse>(`/workspaces/${workspaceId}/assets/${assetId}/copy`, payload)
  return data
}

export async function archiveWorkspaceAsset(
  workspaceId: number,
  assetId: number,
  archiveReason?: string | null,
): Promise<AssetResponse> {
  const { data } = await http.post<AssetResponse>(`/workspaces/${workspaceId}/assets/${assetId}/archive`, {
    archive_reason: archiveReason ?? null,
  })
  return data
}

export async function batchArchiveWorkspaceAssets(
  workspaceId: number,
  assetIds: number[],
  archiveReason?: string | null,
): Promise<AssetBatchOperationResponse> {
  const { data } = await http.post<AssetBatchOperationResponse>(`/workspaces/${workspaceId}/assets/batch-archive`, {
    asset_ids: assetIds,
    archive_reason: archiveReason ?? null,
  })
  return data
}

export async function restoreWorkspaceAsset(
  workspaceId: number,
  assetId: number,
  restoreReason?: string | null,
): Promise<AssetResponse> {
  const { data } = await http.post<AssetResponse>(`/workspaces/${workspaceId}/assets/${assetId}/restore`, {
    restore_reason: restoreReason ?? null,
  })
  return data
}

export async function previewWorkspaceAssetReferences(
  workspaceId: number,
  assetId: number,
): Promise<AssetReferenceSummary> {
  const { data } = await http.get<AssetReferenceSummary>(`/workspaces/${workspaceId}/assets/${assetId}/references`)
  return data
}

export async function deleteWorkspaceAsset(workspaceId: number, assetId: number): Promise<void> {
  await http.delete(`/workspaces/${workspaceId}/assets/${assetId}`)
}

export async function batchDeleteWorkspaceAssets(
  workspaceId: number,
  assetIds: number[],
): Promise<AssetBatchOperationResponse> {
  const { data } = await http.post<AssetBatchOperationResponse>(`/workspaces/${workspaceId}/assets/batch-delete`, {
    asset_ids: assetIds,
  })
  return data
}

export async function exportWorkspaceAssetPackage(
  workspaceId: number,
  assetIds: number[],
): Promise<{ blob: Blob; filename: string }> {
  const response = await postDownloadBlob(`/workspaces/${workspaceId}/assets/export-package`, {
    asset_ids: assetIds,
  })
  return {
    blob: response.data,
    filename: resolveDownloadFilename(response.headers['content-disposition']) || 'workspace-assets.zip',
  }
}

export async function importWorkspaceAssetPackage(
  workspaceId: number,
  file: File,
): Promise<AssetPackageImportResult> {
  const formData = new FormData()
  formData.append('archive', file)
  const { data } = await http.post<AssetPackageImportResult>(
    `/workspaces/${workspaceId}/assets/import-package`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

export async function listWorkspaceFonts(
  workspaceId: number,
  params: ListParams = { page: 1, page_size: 100 },
): Promise<PagedResponse<WorkspaceFontConfigItem>> {
  const { data } = await http.get<PagedResponse<WorkspaceFontConfigItem>>(`/workspaces/${workspaceId}/fonts`, {
    params: buildListParams(params),
  })
  return data
}

export async function createWorkspaceFont(
  workspaceId: number,
  payload: {
    asset_id: number
    font_family: string
    font_format?: string | null
    font_weight: string
    font_style: string
    font_display: string
    status: 'active' | 'archived'
  },
): Promise<WorkspaceFontConfigItem> {
  const { data } = await http.post<WorkspaceFontConfigItem>(`/workspaces/${workspaceId}/fonts`, payload)
  return data
}

export async function updateWorkspaceFont(
  workspaceId: number,
  fontId: number,
  payload: Partial<{
    font_family: string
    font_format: string
    font_weight: string
    font_style: string
    font_display: string
    status: 'active' | 'archived'
  }>,
): Promise<WorkspaceFontConfigItem> {
  const { data } = await http.patch<WorkspaceFontConfigItem>(`/workspaces/${workspaceId}/fonts/${fontId}`, payload)
  return data
}

export async function deleteWorkspaceFont(
  workspaceId: number,
  fontId: number,
  options: { deleteAsset?: boolean } = {},
): Promise<void> {
  await http.delete(`/workspaces/${workspaceId}/fonts/${fontId}`, {
    params: {
      delete_asset: options.deleteAsset ? 'true' : undefined,
    },
  })
}

export async function deleteWorkspaceFontAsset(workspaceId: number, assetId: number): Promise<void> {
  await http.delete(`/workspaces/${workspaceId}/font-assets/${assetId}`)
}

/**
 * 下载接口失败时可能返回 Blob JSON，这里转换成普通 Error 供 UI 展示。
 */
async function postDownloadBlob(url: string, payload: unknown) {
  try {
    return await http.post<Blob>(url, payload, { responseType: 'blob' })
  } catch (error) {
    throw await normalizeDownloadError(error)
  }
}

/**
 * 归一化下载接口错误，优先读取后端业务错误详情。
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
 * 从 Blob JSON 中解析后端错误文案。
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
    return readNonEmptyString(data.message)
      || readNonEmptyString(data.detail)
      || (readNonEmptyString(data.code) ? `下载失败（${readNonEmptyString(data.code)}）` : text)
  } catch {
    return text
  }
}

/**
 * 从 Content-Disposition 响应头解析下载文件名。
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
