/**
 * 文件功能：封装 Runtime Kit 内建组件能力目录和只读预览接口。
 */
import { http } from '@/api/http'
import type {
  ComponentPreviewOptions,
  PreviewArtifactResponse,
  RuntimeKitCapabilityKind,
  RuntimeKitComponentCapabilityItem,
  RuntimeKitComponentCapabilityListResponse,
} from '@/types/api'

/** 查询 Runtime Kit 内建组件能力列表。 */
export async function listRuntimeKitComponents(params: {
  keyword?: string
  category?: string
  kind?: RuntimeKitCapabilityKind
  previewable?: boolean
} = {}) {
  const { data } = await http.get<RuntimeKitComponentCapabilityListResponse>('/runtime-kit/components', {
    params: {
      keyword: params.keyword || undefined,
      category: params.category || undefined,
      kind: params.kind || undefined,
      previewable: typeof params.previewable === 'boolean' ? params.previewable : undefined,
    },
  })
  return data
}

/** 读取单个 Runtime Kit 内建组件能力详情。 */
export async function getRuntimeKitComponent(name: string) {
  const { data } = await http.get<RuntimeKitComponentCapabilityItem>(`/runtime-kit/components/${encodeURIComponent(name)}`)
  return data
}

/** 为 Runtime Kit 内建组件能力创建只读组件预览 artifact。 */
export async function createRuntimeKitComponentPreviewArtifact(
  name: string,
  payload: {
    workspace_id: number
    preview_options?: ComponentPreviewOptions | null
  },
) {
  const { data } = await http.post<PreviewArtifactResponse>(
    `/runtime-kit/components/${encodeURIComponent(name)}/preview-artifacts`,
    payload,
  )
  return data
}
