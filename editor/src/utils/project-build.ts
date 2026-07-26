/**
 * 文件功能：提供项目整包构建的 baseUrl 规范化与校验逻辑。
 */

import type { ProjectBuildJob, ProjectBuildStatus } from '@/types/api'

/**
 * 规范化项目整包构建使用的部署基路径。
 * @param rawBaseUrl 原始输入值
 * @returns 规范化后的 baseUrl
 */
export function normalizeProjectBuildBaseUrl(rawBaseUrl: string | null | undefined): string {
  const normalized = String(rawBaseUrl || '').trim()
  if (!normalized || normalized === '.' || normalized === './') {
    return './'
  }

  if (/^https?:\/\//i.test(normalized) || normalized.startsWith('//')) {
    throw new Error('部署基路径不能是完整 URL 或双斜杠路径。')
  }

  if (!normalized.startsWith('/')) {
    throw new Error('部署基路径仅支持 ./ 或以 / 开头。')
  }

  return normalized.endsWith('/') ? normalized : `${normalized}/`
}

/**
 * 构建状态展示元信息。
 * @param status 构建状态
 * @returns 展示所需的文案与样式
 */
export function getProjectBuildStatusMeta(status: ProjectBuildStatus | null | undefined) {
  if (status === 'succeeded') {
    return {
      label: '构建成功',
      badgeClass: 'border-success-border bg-success-muted text-success-strong',
      dotClass: 'bg-success',
    }
  }

  if (status === 'failed') {
    return {
      label: '构建失败',
      badgeClass: 'border-danger-border bg-danger-muted text-danger-strong',
      dotClass: 'bg-danger',
    }
  }

  if (status === 'running') {
    return {
      label: '构建中',
      badgeClass: 'border-info-border bg-info-muted text-info-strong',
      dotClass: 'bg-info',
    }
  }

  return {
    label: '排队中',
    badgeClass: 'border-warning-border bg-warning-muted text-warning-strong',
    dotClass: 'bg-warning',
  }
}

/**
 * 判断构建状态是否仍在执行链路中。
 * @param status 构建状态
 * @returns 是否不可再次提交构建
 */
export function isProjectBuildStatusActive(status: ProjectBuildStatus | null | undefined): boolean {
  return status === 'pending' || status === 'running'
}

/**
 * 判断构建任务是否仍在执行链路中。
 * @param job 构建任务
 * @returns 是否不可再次提交构建
 */
export function isProjectBuildJobActive(job: ProjectBuildJob | null | undefined): boolean {
  return isProjectBuildStatusActive(job?.status)
}

/**
 * 格式化构建产物体积，便于在列表中快速识别。
 * @param sizeBytes 产物字节数
 * @returns 友好的体积文案
 */
export function formatProjectBuildArtifactSize(sizeBytes: number | null | undefined): string {
  if (sizeBytes == null || sizeBytes < 0) {
    return '未生成'
  }

  if (sizeBytes < 1024) {
    return `${sizeBytes} B`
  }

  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`
  }

  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * 判断当前构建任务是否已有可下载归档。
 * @param job 构建任务
 * @returns 是否可下载
 */
export function canDownloadProjectBuildArtifact(job: ProjectBuildJob): boolean {
  return Boolean(job.artifact_download_url)
}

/**
 * 判断当前构建任务是否已有可打开的公开静态站点入口。
 * @param job 构建任务
 * @returns 是否可打开
 */
export function canOpenProjectBuildArtifact(job: ProjectBuildJob): boolean {
  return Boolean(job.artifact_proxy_url)
}
