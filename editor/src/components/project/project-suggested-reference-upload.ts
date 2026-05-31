/**
 * 文件功能：封装项目建议资源弹窗的上传、覆盖确认和即时关联保存流程。
 */
import { computed, ref, type Ref } from 'vue'

import { uploadWorkspaceAsset } from '@/api/assets'
import { updateProjectSuggestedReferenceAssets } from '@/api/catalog'
import { getErrorCode, getErrorMessage } from '@/api/http'
import type { AssetResponse, AssetType, ProjectSuggestedReferenceAssetItem } from '@/types/api'
import { Message, createConfirm } from '@/utils/message'
import { ASSET_UPLOAD_ACCEPT } from './asset-manager'
import { type ProjectSuggestedReferenceAssetTabKey } from './project-suggested-reference-assets'

interface ProjectSuggestedReferenceUploadOptions {
  getProjectId: () => number | null
  getWorkspaceId: () => number | null
  activeAssetTypeTab: Ref<ProjectSuggestedReferenceAssetTabKey>
  assetOptions: Ref<AssetResponse[]>
  selectedAssetIds: Ref<number[]>
  savedAssets: Ref<ProjectSuggestedReferenceAssetItem[]>
  emitSaved: (items: ProjectSuggestedReferenceAssetItem[]) => void
  resolveAssetTypeLabel: (assetType: AssetType) => string
}

/**
 * 创建项目建议资源上传控制器。
 * @param options 弹窗当前项目、工作空间、资源列表和事件回调
 * @returns 上传状态、文件输入引用与事件处理函数
 */
export function useProjectSuggestedReferenceAssetUpload(options: ProjectSuggestedReferenceUploadOptions) {
  const uploading = ref(false)
  const uploadFileInput = ref<HTMLInputElement | null>(null)
  const activeUploadType = computed(() => resolveActiveUploadType())
  const uploadAccept = computed(() => activeUploadType.value ? ASSET_UPLOAD_ACCEPT[activeUploadType.value] : '')
  const uploadButtonTitle = computed(() => (
    activeUploadType.value
      ? `上传${options.resolveAssetTypeLabel(activeUploadType.value)}资源并关联到项目`
      : '请先选择图片、视频、Draw.io、Mermaid、图表或公式类型'
  ))

  /**
   * 打开文件选择器，允许用户直接上传内容资源并关联到当前项目。
   */
  function triggerUpload(): void {
    if (!options.getProjectId() || !options.getWorkspaceId() || uploading.value) {
      return
    }
    if (!activeUploadType.value) {
      Message.error('请先选择具体资源类型后再上传。')
      return
    }
    uploadFileInput.value?.click()
  }

  /**
   * 上传文件后立即写入项目建议资源关联。
   * @param event 文件输入 change 事件
   */
  async function handleUploadFileChange(event: Event): Promise<void> {
    const target = event.target as HTMLInputElement
    const files = Array.from(target.files || [])
    const assetType = activeUploadType.value
    if (!files.length || !options.getProjectId() || !options.getWorkspaceId() || !assetType) {
      target.value = ''
      return
    }

    uploading.value = true
    let firstError = ''
    const uploadedAssets: AssetResponse[] = []
    try {
      for (const file of files) {
        try {
          const uploaded = await uploadAssetWithOverwriteConfirm(file, assetType)
          if (uploaded) {
            uploadedAssets.push(uploaded)
          }
        } catch (error) {
          firstError ||= getErrorMessage(error, `上传 ${file.name} 失败。`)
        }
      }

      if (uploadedAssets.length > 0) {
        mergeAssetOptions(uploadedAssets)
        options.selectedAssetIds.value = appendUniqueAssetIds(
          options.selectedAssetIds.value,
          uploadedAssets.map(asset => asset.id),
        )
        await persistUploadedSelection(uploadedAssets.length)
      }
      if (firstError) {
        Message.error(uploadedAssets.length > 0 ? `部分资源上传失败：${firstError}` : firstError)
      }
    } finally {
      uploading.value = false
      target.value = ''
    }
  }

  /**
   * 上传单个资源；遇到同名资源时按用户确认执行覆盖。
   * @param file 待上传文件
   * @param assetType 当前标签指定的资源类型
   * @returns 上传后的资源，用户取消覆盖时返回 null
   */
  async function uploadAssetWithOverwriteConfirm(file: File, assetType: AssetType): Promise<AssetResponse | null> {
    const workspaceId = options.getWorkspaceId()
    if (!workspaceId) {
      return null
    }
    try {
      return await uploadWorkspaceAsset(workspaceId, file, assetType, [])
    } catch (error) {
      if (getErrorCode(error) !== 'ASSET_NAME_CONFLICT') {
        throw error
      }

      const conflictMessage = getErrorMessage(error, `文件 "${file.name}" 已存在，请确认是否覆盖。`)
      const confirmed = await createConfirm(
        `${conflictMessage} 覆盖后现有页面、路由、主题和预览引用会指向新文件，确认覆盖吗？`,
        '覆盖同名资源',
      )
      if (!confirmed) {
        return null
      }
      return await uploadWorkspaceAsset(workspaceId, file, assetType, [], undefined, undefined, true)
    }
  }

  /**
   * 将上传结果保存为当前项目建议资源关联，并保持弹窗打开。
   * @param uploadedCount 本次成功上传数量
   */
  async function persistUploadedSelection(uploadedCount: number): Promise<void> {
    const projectId = options.getProjectId()
    if (!projectId) {
      return
    }
    try {
      const response = await updateProjectSuggestedReferenceAssets(projectId, options.selectedAssetIds.value)
      options.savedAssets.value = response.items
      options.selectedAssetIds.value = response.items.map(asset => asset.id)
      options.emitSaved(response.items)
      Message.success(uploadedCount === 1 ? '资源已上传并关联。' : `已上传并关联 ${uploadedCount} 个资源。`)
    } catch (error) {
      Message.error(getErrorMessage(error, '资源已上传，但保存项目建议资源关联失败。'))
    }
  }

  /**
   * 合并上传资源到待选列表，确保刚上传的资源优先展示。
   * @param uploadedAssets 本次上传得到的资源
   */
  function mergeAssetOptions(uploadedAssets: AssetResponse[]): void {
    const uploadedIds = new Set(uploadedAssets.map(asset => asset.id))
    options.assetOptions.value = [
      ...uploadedAssets,
      ...options.assetOptions.value.filter(asset => !uploadedIds.has(asset.id)),
    ]
  }

  /**
   * 把当前标签转换为上传类型；全部标签不能直接作为后端 asset_type。
   * @returns 具体内容资源类型，未选择类型时返回 null
   */
  function resolveActiveUploadType(): AssetType | null {
    const activeTab = options.activeAssetTypeTab.value
    return activeTab === 'all' ? null : activeTab
  }

  return {
    uploading,
    uploadFileInput,
    uploadAccept,
    uploadButtonTitle,
    triggerUpload,
    handleUploadFileChange,
  }
}

/**
 * 保持资源 ID 顺序去重追加。
 * @param currentIds 当前选择列表
 * @param nextIds 需要追加的资源 ID
 * @returns 去重后的新选择列表
 */
function appendUniqueAssetIds(currentIds: number[], nextIds: number[]): number[] {
  const result = [...currentIds]
  const seen = new Set(result)
  for (const assetId of nextIds) {
    if (!seen.has(assetId)) {
      seen.add(assetId)
      result.push(assetId)
    }
  }
  return result
}
