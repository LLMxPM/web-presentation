/**
 * 文件功能：封装项目整包构建任务的创建与查询请求。
 */

import { http } from '@/api/http'
import type { ProjectBuildAssetSummary, ProjectBuildCreateRequest, ProjectBuildJob } from '@/types/api'

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
 * @param projectId 项目 ID
 * @param jobId 构建任务 ID
 */
export async function downloadProjectBuildArtifact(projectId: number, jobId: number): Promise<void> {
  const response = await http.get<Blob>(`/projects/${projectId}/build-jobs/${jobId}/artifact`, {
    responseType: 'blob',
  })
  const downloadUrl = window.URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = resolveArtifactFileName(response.headers['content-disposition'], projectId, jobId)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(downloadUrl)
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
