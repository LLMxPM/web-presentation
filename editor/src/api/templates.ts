/**
 * 文件功能：封装项目模板包的导出、导入预检、正式导入与临时预览接口。
 */
import axios from 'axios'

import { http } from '@/api/http'
import type {
  PreviewArtifactResponse,
  ProjectTemplateExportRequest,
  ProjectTemplateExportValidationResult,
  ProjectTemplateImportResult,
  ProjectTemplateImportValidationResult,
} from '@/types/api'

const TEMPLATE_PACKAGE_EXPORT_TIMEOUT_MS = 10 * 60 * 1000
const TEMPLATE_PACKAGE_UPLOAD_TIMEOUT_MS = 3 * 60 * 1000

/** 预检项目模板包导出内容。 */
export async function validateProjectTemplatePackageExport(
  projectId: number,
  payload: ProjectTemplateExportRequest,
) {
  const { data } = await http.post<ProjectTemplateExportValidationResult>(
    `/projects/${projectId}/template-package/export/validate`,
    payload,
  )
  return data
}

/** 导出项目模板包 ZIP。 */
export async function exportProjectTemplatePackage(
  projectId: number,
  payload: ProjectTemplateExportRequest,
) {
  const response = await postDownloadBlob(`/projects/${projectId}/template-package/export`, payload)
  return {
    blob: response.data,
    filename: resolveDownloadFilename(response.headers['content-disposition']) || 'project-template.wptemplate.zip',
  }
}

/** 预检上传的项目模板包。 */
export async function validateProjectTemplatePackageImport(workspaceId: number, file: File) {
  const { data } = await postTemplateArchive<ProjectTemplateImportValidationResult>(
    `/workspaces/${workspaceId}/template-packages/import/validate`,
    file,
  )
  return data
}

/** 正式导入上传的项目模板包。 */
export async function importProjectTemplatePackage(workspaceId: number, file: File) {
  const { data } = await postTemplateArchive<ProjectTemplateImportResult>(
    `/workspaces/${workspaceId}/template-packages/import`,
    file,
  )
  return data
}

/** 为上传的项目模板包生成临时预览 artifact。 */
export async function createProjectTemplatePackagePreviewArtifact(workspaceId: number, file: File) {
  const { data } = await postTemplateArchive<PreviewArtifactResponse>(
    `/workspaces/${workspaceId}/template-packages/preview-artifact`,
    file,
  )
  return data
}

/**
 * 以 multipart/form-data 上传模板 ZIP，字段名与后端保持一致。
 * @param url 后端接口路径
 * @param file 上传的模板包文件
 */
async function postTemplateArchive<T>(url: string, file: File) {
  const formData = new FormData()
  formData.append('archive', file)
  return await http.post<T>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: TEMPLATE_PACKAGE_UPLOAD_TIMEOUT_MS,
  })
}

/**
 * 下载接口在失败时也会按 Blob 返回错误体，这里转回后端业务提示。
 */
async function postDownloadBlob(url: string, payload: unknown) {
  try {
    return await http.post<Blob>(url, payload, {
      responseType: 'blob',
      timeout: TEMPLATE_PACKAGE_EXPORT_TIMEOUT_MS,
    })
  } catch (error) {
    throw await normalizeDownloadError(error)
  }
}

/**
 * 将 Blob 形式的 JSON 错误体转换成普通 Error。
 */
async function normalizeDownloadError(error: unknown): Promise<Error> {
  if (axios.isAxiosError(error) && error.code === 'ECONNABORTED') {
    return new Error('项目导出耗时较长，前端请求已超时。请稍后重试，或先刷新页面截图后再导出。')
  }
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
