/**
 * 文件功能：封装工作空间、项目和页面资源库的 CRUD 接口访问方法。
 */
import axios from 'axios'

import { http } from '@/api/http'
import type {
  ListParams,
  PageCurrentComponentIndex,
  PageCopyToProjectPayload,
  PageItem,
  PageScreenshotBatchRefreshResponse,
  PageScreenshotJob,
  PageScreenshotJobGroup,
  PageVersionContent,
  PageVersionListItem,
  PagedResponse,
  ComponentShareExportValidationResult,
  ComponentShareImportResult,
  ComponentShareImportValidationResult,
  ProjectBuildExtraAssetsJson,
  ProjectItem,
  ProjectMenuMode,
  ProjectRouteItemWrite,
  ProjectRouteTreeResponse,
  ProjectSuggestedReferenceAssetsResponse,
  SuggestedComponentsResponse,
  WorkspaceComponentType,
  WorkspaceComponentCurrentDependencies,
  WorkspaceComponentItem,
  WorkspaceComponentReferenceUpgradePayload,
  WorkspaceComponentReferenceUpgradeResponse,
  WorkspaceComponentReferences,
  WorkspaceComponentVersionContent,
  WorkspaceComponentVersionListItem,
  WorkspaceItem,
} from '@/types/api'

/**
 * 清理列表查询参数，自动移除空字符串、null 和 undefined，避免无效筛选值传给后端。
 */
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

/** 查询工作空间列表。 */
export async function listWorkspaces(params: ListParams) {
  const { data } = await http.get<PagedResponse<WorkspaceItem>>('/workspaces', { params: buildParams(params) })
  return data
}

/** 获取单个工作空间详情。 */
export async function getWorkspace(id: number) {
  const { data } = await http.get<WorkspaceItem>(`/workspaces/${id}`)
  return data
}

/** 创建工作空间，code 由后端自动生成。 */
export async function createWorkspace(payload: {
  name: string
  description?: string | null
  status: string
  default_theme_key?: string | null
}) {
  const { data } = await http.post<WorkspaceItem>('/workspaces', payload)
  return data
}

/** 更新工作空间元数据。 */
export async function updateWorkspace(
  id: number,
  payload: Partial<{
    name: string
    description: string | null
    status: string
    default_theme_key: string | null
  }>,
) {
  const { data } = await http.patch<WorkspaceItem>(`/workspaces/${id}`, payload)
  return data
}

/** 删除工作空间。 */
export async function deleteWorkspace(id: number) {
  const { data } = await http.delete<{ message: string }>(`/workspaces/${id}`)
  return data
}

/** 触碰工作空间（更新最后访问时间）。 */
export async function touchWorkspace(id: number) {
  const { data } = await http.put<WorkspaceItem>(`/workspaces/${id}/touch`)
  return data
}

/** 查询项目列表。 */
export async function listProjects(params: ListParams & { workspace_id?: number | '' }) {
  const { data } = await http.get<PagedResponse<ProjectItem>>('/projects', { params: buildParams(params) })
  return data
}

/** 获取单个项目详情。 */
export async function getProject(id: number) {
  const { data } = await http.get<ProjectItem>(`/projects/${id}`)
  return data
}

/** 创建项目，code 由后端自动生成。 */
export async function createProject(payload: {
  workspace_id: number
  name: string
  description?: string | null
  status: string
  page_width: number
  page_height: number
  base_font_size: string
  icon_default_stroke_width: number
  show_pdf_export_button: boolean
  menu_mode: ProjectMenuMode
  theme_key?: string | null
  theme_config_yaml?: string | null
  style_spec_markdown?: string
  build_extra_assets_json?: ProjectBuildExtraAssetsJson
  suggested_component_source_style_id?: number | null
}) {
  const { data } = await http.post<ProjectItem>('/projects', payload)
  return data
}

/** 更新项目元数据。 */
export async function updateProject(
  id: number,
  payload: Partial<{
    workspace_id: number
    name: string
    description: string | null
    status: string
    page_width: number
    page_height: number
    base_font_size: string
    icon_default_stroke_width: number
    show_pdf_export_button: boolean
    menu_mode: ProjectMenuMode
    theme_key: string | null
    theme_config_yaml: string
    style_spec_markdown: string
    build_extra_assets_json: ProjectBuildExtraAssetsJson
    suggested_component_source_style_id: number | null
  }>,
) {
  const { data } = await http.patch<ProjectItem>(`/projects/${id}`, payload)
  return data
}

/** 读取项目建议引用内容资源。 */
export async function getProjectSuggestedReferenceAssets(projectId: number) {
  const { data } = await http.get<ProjectSuggestedReferenceAssetsResponse>(
    `/projects/${projectId}/suggested-reference-assets`,
  )
  return data
}

/** 覆盖保存项目建议引用内容资源。 */
export async function updateProjectSuggestedReferenceAssets(projectId: number, assetIds: number[]) {
  const { data } = await http.put<ProjectSuggestedReferenceAssetsResponse>(
    `/projects/${projectId}/suggested-reference-assets`,
    { asset_ids: assetIds },
  )
  return data
}

/** 读取项目建议组件快照。 */
export async function getProjectSuggestedComponents(projectId: number) {
  const { data } = await http.get<SuggestedComponentsResponse>(`/projects/${projectId}/suggested-components`)
  return data
}

/** 覆盖保存项目建议组件快照。 */
export async function updateProjectSuggestedComponents(projectId: number, componentIds: number[]) {
  const { data } = await http.put<SuggestedComponentsResponse>(
    `/projects/${projectId}/suggested-components`,
    { component_ids: componentIds },
  )
  return data
}

/** 查询项目结构化路由树。 */
export async function getProjectRoutes(projectId: number) {
  const { data } = await http.get<ProjectRouteTreeResponse>(`/projects/${projectId}/routes`)
  return data
}

/** 覆盖保存项目结构化路由树。 */
export async function replaceProjectRoutes(projectId: number, payload: { routes: ProjectRouteItemWrite[] }) {
  const { data } = await http.put<ProjectRouteTreeResponse>(`/projects/${projectId}/routes`, payload)
  return data
}

/** 删除项目。 */
export async function deleteProject(id: number) {
  const { data } = await http.delete<{ message: string }>(`/projects/${id}`)
  return data
}

/** 查询页面资源列表。 */
export async function listPages(params: ListParams & { workspace_id?: number | ''; project_id?: number | '' }) {
  const { data } = await http.get<PagedResponse<PageItem>>('/pages', { params: buildParams(params) })
  return data
}

/** 获取单个页面详情。 */
export async function getPage(id: number) {
  const { data } = await http.get<PageItem>(`/pages/${id}`)
  return data
}

/** 查询页面当前版本的组件索引。 */
export async function getPageCurrentComponentIndex(id: number) {
  const { data } = await http.get<PageCurrentComponentIndex>(`/pages/${id}/component-index`)
  return data
}

/** 查询工作空间组件列表。 */
export async function listComponents(params: ListParams & {
  workspace_id?: number | ''
  component_type?: WorkspaceComponentType | ''
  published_only?: boolean
}) {
  const { data } = await http.get<PagedResponse<WorkspaceComponentItem>>('/components', { params: buildParams(params) })
  return data
}

/** 获取单个工作空间组件详情。 */
export async function getComponent(id: number) {
  const { data } = await http.get<WorkspaceComponentItem>(`/components/${id}`)
  return data
}

/** 查询组件当前版本的源码依赖索引。 */
export async function getComponentCurrentDependencies(id: number) {
  const { data } = await http.get<WorkspaceComponentCurrentDependencies>(`/components/${id}/current-dependencies`)
  return data
}

/** 查询工作空间组件被当前页面和组件直接引用的情况。 */
export async function getComponentReferences(id: number) {
  const { data } = await http.get<WorkspaceComponentReferences>(`/components/${id}/references`)
  return data
}

/** 批量升级页面和组件草稿中的工作空间组件引用版本。 */
export async function upgradeComponentReferences(id: number, payload: WorkspaceComponentReferenceUpgradePayload) {
  const { data } = await http.post<WorkspaceComponentReferenceUpgradeResponse>(`/components/${id}/references/upgrade`, payload)
  return data
}

/** 创建工作空间组件。 */
export async function createComponent(payload: {
  workspace_id: number
  content: string
  preview_schema?: string | null
  file_type: string
  name: string
  import_name: string
  component_type?: WorkspaceComponentType
  summary?: string | null
  status: string
  change_note?: string | null
}) {
  const { data } = await http.post<WorkspaceComponentItem>('/components', payload)
  return data
}

/** 更新工作空间组件。 */
export async function updateComponent(
  id: number,
  payload: Partial<{
    workspace_id: number
    content: string
    preview_schema: string | null
    file_type: string
    name: string
    import_name: string
    component_type: WorkspaceComponentType
    summary: string | null
    status: string
    change_note: string | null
  }>,
) {
  const { data } = await http.patch<WorkspaceComponentItem>(`/components/${id}`, payload)
  return data
}

/** 发布工作空间组件当前草稿，生成正式可引用版本。 */
export async function publishComponent(
  id: number,
  payload: {
    release_name?: string | null
    change_note?: string | null
  },
) {
  const { data } = await http.post<WorkspaceComponentItem>(`/components/${id}/publish`, payload)
  return data
}

/** 查询组件版本历史。 */
export async function listComponentVersions(id: number) {
  const { data } = await http.get<WorkspaceComponentVersionListItem[]>(`/components/${id}/versions`)
  return data
}

/** 查询单个组件版本的完整源码。 */
export async function getComponentVersionContent(id: number, versionNo: number) {
  const { data } = await http.get<WorkspaceComponentVersionContent>(`/components/${id}/versions/${versionNo}`)
  return data
}

/** 下载工作空间组件离线分享包。 */
export async function exportComponentPackage(payload: {
  workspace_id: number
  component_ids: number[]
  manual_asset_names?: string[]
}) {
  const response = await postDownloadBlob('/components/export-package', payload)
  return {
    blob: response.data,
    filename: resolveDownloadFilename(response.headers['content-disposition']) || 'workspace-components.zip',
  }
}

/** 预检工作空间组件离线分享包导出资源。 */
export async function validateComponentPackageExport(payload: {
  workspace_id: number
  component_ids: number[]
  manual_asset_names?: string[]
}) {
  const { data } = await http.post<ComponentShareExportValidationResult>('/components/export-package/validate', payload)
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
 * 将 Blob 形式的 JSON 错误体转换成普通 Error，供页面统一展示明确原因。
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

function readNonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** 预检组件离线分享包。 */
export async function validateComponentPackageImport(workspaceId: number, file: File) {
  const formData = new FormData()
  formData.append('workspace_id', String(workspaceId))
  formData.append('archive', file)
  const { data } = await http.post<ComponentShareImportValidationResult>('/components/import-package/validate', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

/** 正式导入组件离线分享包。 */
export async function importComponentPackage(workspaceId: number, file: File) {
  const formData = new FormData()
  formData.append('workspace_id', String(workspaceId))
  formData.append('archive', file)
  const { data } = await http.post<ComponentShareImportResult>('/components/import-package', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
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

/** 将指定组件发布版本恢复到草稿区。 */
export async function restoreComponentVersionToDraft(
  id: number,
  versionNo: number,
  payload: { change_note?: string | null },
) {
  const { data } = await http.post<WorkspaceComponentItem>(`/components/${id}/versions/${versionNo}/restore-to-draft`, payload)
  return data
}

/** 删除工作空间组件。 */
export async function deleteComponent(id: number) {
  const { data } = await http.delete<{ message: string }>(`/components/${id}`)
  return data
}

/** 创建页面资源，code 由后端自动生成。 */
export async function createPage(payload: {
  page_content: string
  file_type: string
  title: string
  summary?: string | null
  speaker_notes?: string | null
  status: string
  workspace_id?: number | null
  project_id?: number | null
}) {
  const { data } = await http.post<PageItem>('/pages', payload)
  return data
}

/** 更新页面资源元数据。 */
export async function updatePage(
  id: number,
  payload: Partial<{
    page_content: string
    file_type: string
    change_note: string | null
    title: string
    summary: string | null
    speaker_notes: string | null
    status: string
    workspace_id: number | null
    project_id: number | null
  }>,
) {
  const { data } = await http.patch<PageItem>(`/pages/${id}`, payload)
  return data
}

/** 将页面复制到同工作空间内的另一个项目。 */
export async function copyPageToProject(id: number, payload: PageCopyToProjectPayload) {
  const { data } = await http.post<PageItem>(`/pages/${id}/copy-to-project`, payload)
  return data
}

/** 查询页面版本历史。 */
export async function listPageVersions(id: number) {
  const { data } = await http.get<PageVersionListItem[]>(`/pages/${id}/versions`)
  return data
}

/** 查询单个页面版本的完整源码。 */
export async function getPageVersionContent(id: number, versionNo: number) {
  const { data } = await http.get<PageVersionContent>(`/pages/${id}/versions/${versionNo}`)
  return data
}

/** 将指定页面版本提升为重点快照。 */
export async function createPageSnapshot(id: number, versionNo: number, payload: { snapshot_name?: string | null }) {
  const { data } = await http.post<PageVersionContent>(`/pages/${id}/versions/${versionNo}/snapshot`, payload)
  return data
}

/** 恢复指定页面版本为当前最新版本。 */
export async function restorePageVersion(id: number, versionNo: number, payload: { change_note?: string | null }) {
  const { data } = await http.post<PageItem>(`/pages/${id}/versions/${versionNo}/restore`, payload)
  return data
}

/** 为指定页面生成并保存截图。 */
export async function savePageScreenshot(
  id: number,
  payload: { viewport_width?: number; viewport_height?: number } = {},
) {
  const job = await createPageScreenshotJob(id, payload)
  const completedJob = await waitForPageScreenshotJob(job.id)
  if (completedJob.status === 'failed') {
    throw new Error(completedJob.error_message || '页面截图任务执行失败。')
  }
  return await getPage(id)
}

/** 为指定页面创建或复用截图队列任务。 */
export async function createPageScreenshotJob(
  id: number,
  payload: { viewport_width?: number; viewport_height?: number } = {},
) {
  const { data } = await http.post<PageScreenshotJob>(`/pages/${id}/screenshot-jobs`, payload)
  return data
}

/** 批量刷新指定项目中缺失或已过期的页面截图。 */
export async function batchRefreshPageScreenshots(projectId: number) {
  const { data } = await http.post<PageScreenshotBatchRefreshResponse>(
    '/pages/batch-refresh-screenshots',
    { project_id: projectId },
    { timeout: 120000 },
  )
  return data
}

/** 为指定项目中缺失或已过期的页面截图创建任务组。 */
export async function batchRefreshPageScreenshotJobs(projectId: number) {
  const { data } = await http.post<PageScreenshotJobGroup>(
    '/pages/batch-refresh-screenshot-jobs',
    { project_id: projectId },
  )
  return data
}

/** 查询单个页面截图任务。 */
export async function getPageScreenshotJob(jobId: number) {
  const { data } = await http.get<PageScreenshotJob>(`/page-screenshot-jobs/${jobId}`)
  return data
}

/** 查询页面截图任务组聚合进度。 */
export async function getPageScreenshotJobGroup(groupId: string) {
  const { data } = await http.get<PageScreenshotJobGroup>(`/page-screenshot-job-groups/${groupId}`)
  return data
}

/** 等待页面截图任务进入终态。 */
export async function waitForPageScreenshotJob(
  jobId: number,
  options: { timeoutMs?: number; intervalMs?: number } = {},
) {
  const timeoutMs = options.timeoutMs ?? 120000
  const intervalMs = options.intervalMs ?? 1000
  const deadlineAt = Date.now() + timeoutMs
  while (Date.now() <= deadlineAt) {
    const job = await getPageScreenshotJob(jobId)
    if (!isPageScreenshotJobActive(job.status)) {
      return job
    }
    await sleep(intervalMs)
  }
  throw new Error('页面截图任务等待超时。')
}

/** 等待页面截图任务组进入终态。 */
export async function waitForPageScreenshotJobGroup(
  groupId: string,
  options: {
    timeoutMs?: number
    intervalMs?: number
    onProgress?: (group: PageScreenshotJobGroup) => void
  } = {},
) {
  const timeoutMs = options.timeoutMs ?? 180000
  const intervalMs = options.intervalMs ?? 1000
  const deadlineAt = Date.now() + timeoutMs
  while (Date.now() <= deadlineAt) {
    const group = await getPageScreenshotJobGroup(groupId)
    options.onProgress?.(group)
    if (!isPageScreenshotJobGroupActive(group.status)) {
      return group
    }
    await sleep(intervalMs)
  }
  throw new Error('页面截图任务组等待超时。')
}

/** 判断截图任务是否仍在执行链路中。 */
function isPageScreenshotJobActive(status: PageScreenshotJob['status']): boolean {
  return status === 'pending' || status === 'running'
}

/** 判断截图任务组是否仍在执行链路中。 */
function isPageScreenshotJobGroupActive(status: PageScreenshotJobGroup['status']): boolean {
  return status === 'pending' || status === 'running'
}

/** 延迟指定毫秒。 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, Math.max(0, ms)))
}

/** 将指定页面的最新截图打包为 ZIP 并触发浏览器下载。 */
export async function downloadPageScreenshotsArchive(pageIds: number[]): Promise<void> {
  const response = await http.post<Blob>(
    '/pages/batch-download-screenshots',
    { page_ids: pageIds },
    { responseType: 'blob', timeout: 120000 },
  )
  const downloadUrl = window.URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = resolvePageScreenshotsArchiveFileName(response.headers['content-disposition'])
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(downloadUrl)
}

/**
 * 从响应头推导截图压缩包文件名，缺省时回落到稳定命名。
 * @param contentDisposition 后端下载响应头
 */
function resolvePageScreenshotsArchiveFileName(contentDisposition: string | undefined): string {
  const encodedMatch = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i)
  if (encodedMatch?.[1]) {
    return decodeURIComponent(encodedMatch[1])
  }

  const plainMatch = contentDisposition?.match(/filename="?([^"]+)"?/i)
  if (plainMatch?.[1]) {
    return plainMatch[1]
  }

  return 'page-screenshots.zip'
}

/** 删除页面资源。 */
export async function deletePage(id: number) {
  const { data } = await http.delete<{ message: string }>(`/pages/${id}`)
  return data
}
