/**
 * 文件功能：封装项目整包构建任务的创建与查询请求。
 */

import { http, resolveApiBaseUrl } from '@/api/http'
import type { ProjectBuildAssetSummary, ProjectBuildCreateRequest, ProjectBuildJob } from '@/types/api'
import type { ProjectBuildJobAccessResponse } from '@/types/api.generated'
export type { ProjectBuildJobAccessResponse } from '@/types/api.generated'

/**
 * 创建项目整包构建任务。
 * @param projectId 项目 ID
 * @param payload 构建请求
 * @returns 新建任务
 */
export async function createProjectBuildJob(projectId: number, payload: ProjectBuildCreateRequest) {
  const { data } = await http.post<ProjectBuildJob>(`/projects/${projectId}/build-jobs`, payload)
  return data
}

export async function getProjectBuildAssetSummary(projectId: number) {
  const { data } = await http.get<ProjectBuildAssetSummary>(`/projects/${projectId}/build-assets`)
  return data
}

/**
 * 查询项目最近一次构建任务。
 * @param projectId 项目 ID
 * @returns 最近一次任务；不存在时返回 null
 */
export async function getLatestProjectBuildJob(projectId: number) {
  const { data } = await http.get<ProjectBuildJob | null>(`/projects/${projectId}/build-jobs/latest`)
  return data
}

/**
 * 查询项目构建历史。
 * @param projectId 项目 ID
 * @param limit 最大返回数量
 * @returns 构建任务列表，按时间倒序排列
 */
export async function listProjectBuildJobs(projectId: number, limit = 20) {
  const { data } = await http.get<ProjectBuildJob[]>(`/projects/${projectId}/build-jobs`, {
    params: { limit },
  })
  return data
}

/**
 * 按任务 ID 查询构建状态。
 * @param jobId 构建任务 ID
 * @returns 任务详情
 */
export async function getProjectBuildJob(jobId: number) {
  const { data } = await http.get<ProjectBuildJob>(`/build-jobs/${jobId}`)
  return data
}

/**
 * 下载指定构建任务的 ZIP 归档。
 *
 * 归档大小与用户下行带宽共同决定传输时长，不能共用 axios 的固定超时预算：
 * 这里只用 HEAD 拿明确的鉴权/存在性错误与响应头，真正的字节传输交给浏览器
 * 下载管理器——不受脚本超时约束，弱网断流后还能按 Range 继续传输。
 * @param projectId 项目 ID
 * @param jobId 构建任务 ID
 */
export async function downloadProjectBuildArtifact(projectId: number, jobId: number): Promise<void> {
  const artifactPath = `/projects/${projectId}/build-jobs/${jobId}/artifact`
  const response = await http.head(artifactPath)
  triggerArtifactDownload(
    resolveArtifactDownloadUrl(artifactPath),
    resolveArtifactFileName(response.headers['content-disposition'], projectId, jobId),
  )
}

/**
 * 拼接下载地址。
 * 优先沿用 API 基础地址，保证鉴权 Cookie 与其它请求落到同一入口；不使用后端
 * 返回的绝对下载地址，避免反向代理或内外网域名不一致时丢失登录态。
 * 合并语义与 axios 的 baseURL 一致：基础地址被显式配置成 `/`（API 挂在根路径）
 * 时，撕掉尾部斜杠后前缀为空，结果是 `/projects/...`——这与 axios 实际发出的
 * 路径相同，属于正确行为，不要在此补 `/api`，否则下载会与其它请求分叉。
 * @param artifactPath 产物接口路径
 * @returns 可由浏览器直接导航的下载地址
 */
export function resolveArtifactDownloadUrl(artifactPath: string): string {
  return `${resolveApiBaseUrl().replace(/\/+$/, '')}${artifactPath}`
}

/**
 * 创建临时 a 标签交给浏览器原生下载。
 * @param downloadUrl 产物下载地址
 * @param filename 浏览器保存时建议使用的文件名
 */
export function triggerArtifactDownload(downloadUrl: string, filename: string): void {
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

/**
 * 获取私有构建产物浏览的短期访问授权与地址。
 * @param projectId 项目 ID
 * @param jobId 构建任务 ID
 * @returns 授权与浏览地址
 */
export async function getProjectBuildJobAccess(
  projectId: number,
  jobId: number,
): Promise<ProjectBuildJobAccessResponse> {
  const { data } = await http.post<ProjectBuildJobAccessResponse>(
    `/projects/${projectId}/build-jobs/${jobId}/access`,
  )
  return data
}

/**
 * 删除指定构建任务的 ZIP 产物，构建历史记录仍会保留。
 * @param projectId 项目 ID
 * @param jobId 构建任务 ID
 */
export async function deleteProjectBuildArtifact(projectId: number, jobId: number): Promise<void> {
  await http.delete(`/projects/${projectId}/build-jobs/${jobId}/artifact`)
}

/**
 * 从响应头推导下载文件名，缺省时回落到稳定命名。
 * @param contentDisposition 响应头
 * @param projectId 项目 ID
 * @param jobId 构建任务 ID
 * @returns 文件名
 */
function resolveArtifactFileName(
  contentDisposition: string | undefined,
  projectId: number,
  jobId: number,
): string {
  const encodedMatch = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i)
  if (encodedMatch?.[1]) {
    return decodeURIComponent(encodedMatch[1])
  }

  const plainMatch = contentDisposition?.match(/filename="?([^"]+)"?/i)
  if (plainMatch?.[1]) {
    return plainMatch[1]
  }

  return `project-${projectId}-build-${jobId}.zip`
}
