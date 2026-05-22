/**
 * 文件功能：封装项目、页面与组件预览 artifact 的创建请求。
 */
import { http } from '@/api/http'
import type { ComponentPreviewOptions, PreviewArtifactResponse } from '@/types/api'

/**
 * 锁定当前配置并生成项目或单页面 preview artifact。
 */
export async function createProjectPreviewArtifact(projectId: number, entryRoute?: string | null) {
  const normalizedEntryRoute = String(entryRoute ?? '').trim()
  const isModuleEntry = normalizedEntryRoute.startsWith('src/views/') || normalizedEntryRoute.startsWith('@/views/')
  const payload = normalizedEntryRoute
    ? {
      entry_descriptor: isModuleEntry
        ? { entry_type: 'module', module_path: normalizedEntryRoute }
        : { entry_type: 'route', route: normalizedEntryRoute }
    }
    : {}
  const { data } = await http.post<PreviewArtifactResponse>(`/projects/${projectId}/preview-artifacts`, {
    ...payload
  })
  return data
}

/**
 * 为指定页面历史版本生成单页临时预览 artifact。
 */
export async function createPageVersionPreviewArtifact(pageId: number, versionNo: number) {
  const { data } = await http.post<PreviewArtifactResponse>(`/pages/${pageId}/versions/${versionNo}/preview-artifact`)
  return data
}

/**
 * 为组件当前版本生成一个纯沙箱预览 artifact，并返回入口预览信息。
 */
export async function createComponentPreviewArtifact(componentId: number) {
  const { data } = await http.post<PreviewArtifactResponse>(`/components/${componentId}/preview-artifacts`)
  return data
}

/**
 * 为组件指定发布版本生成一个纯沙箱预览 artifact。
 */
export async function createComponentVersionPreviewArtifact(componentId: number, versionNo: number) {
  const { data } = await http.post<PreviewArtifactResponse>(`/components/${componentId}/versions/${versionNo}/preview-artifact`)
  return data
}

/**
 * 基于未保存源码生成组件临时预览 artifact，不会写入正式版本历史。
 */
export async function createComponentPreviewArtifactFromSource(payload: {
  workspace_id: number
  component_id?: number | null
  component_name?: string | null
  content: string
  preview_schema?: string | null
  preview_options?: ComponentPreviewOptions | null
  file_type?: string
}) {
  const { data } = await http.post<PreviewArtifactResponse>('/components/preview-artifacts/from-source', payload)
  return data
}

/**
 * 为工作空间资源创建按需 Runtime 预览 artifact。
 */
export async function createAssetPreviewArtifact(workspaceId: number, assetId: number) {
  const { data } = await http.post<PreviewArtifactResponse>(
    `/workspaces/${workspaceId}/assets/${assetId}/preview-artifact`,
  )
  return data
}
