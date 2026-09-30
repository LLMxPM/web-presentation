/**
 * 文件功能：资源详情弹窗状态与单资源维护动作（元数据/内容/引用/替换/归档恢复删除）。
 */
import { computed, reactive, ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  archiveWorkspaceAsset,
  createAssetRenderHintBackfillJobs,
  deleteWorkspaceAsset,
  getWorkspaceAssetContent,
  previewWorkspaceAssetReferences,
  replaceWorkspaceAssetFile,
  restoreWorkspaceAsset,
  updateWorkspaceAsset,
  updateWorkspaceAssetContent,
  waitForAssetRenderHintBackfillJobGroup,
} from '@/api/assets'
import { getErrorMessage } from '@/api/http'
import { ASSET_UPLOAD_ACCEPT, getAcceptedAssetExtensionText, isAcceptedAssetFile } from '@/components/project/asset-manager'
import type {
  AssetReferenceSummary,
  AssetResponse,
} from '@/types/api'
import { createConfirm, Message } from '@/utils/message'
import { buildWorkspaceComponentsPath } from '@/utils/workspace-routes'
import {
  REFERENCE_GROUP_LABELS,
  isBackfillableAssetType,
  type AssetReferenceItem,
  type AssetView,
  type DetailTab,
} from '@/views/asset-view-options'

export interface AssetDetailOptions {
  workspaceId: Ref<number>
  activeView: Ref<AssetView>
  page: Ref<number>
  /** 列表刷新（详情保存/归档后）。 */
  onRefresh: () => Promise<void>
  onRefreshWithPageFallback: () => Promise<void>
  onRefreshTags: () => Promise<void>
  /** 列表最新资源，用于回填后同步详情。 */
  assets: Ref<AssetResponse[]>
  /** 比例回填进行中（按钮禁用）。 */
  backfillRunning: Ref<boolean>
}

/**
 * 资源详情状态簇与单资源操作。
 */
export function useAssetDetail(options: AssetDetailOptions) {
  const router = useRouter()
  const detailAsset = ref<AssetResponse | null>(null)
  const selectedAsset = ref<AssetResponse | null>(null)
  const detailTab = ref<DetailTab>('basic')
  const contentDraft = ref('')
  const originalContent = ref('')
  const referenceSummary = ref<AssetReferenceSummary | null>(null)
  const referencesLoading = ref(false)
  const saving = ref(false)
  const replacingAsset = ref<AssetResponse | null>(null)
  const replaceFileInput = ref<HTMLInputElement | null>(null)
  const editForm = reactive({
    name: '',
    original_name: '',
    description: '',
    approx_aspect_ratio: '',
  })
  const editTagsText = ref('')
  const originalApproxAspectRatioText = ref('')

  const canSaveContent = computed(() => (
    Boolean(detailAsset.value?.content_editable)
    && detailAsset.value?.status === 'active'
    && !detailAsset.value?.history_kind
    && contentDraft.value.trim() !== ''
    && contentDraft.value !== originalContent.value
  ))

  const referenceItems = computed<AssetReferenceItem[]>(() => {
    return (referenceSummary.value?.references || []).map(item => ({
      kind: String(item.kind || ''),
      id: Number(item.id),
      component_id: item.component_id == null ? undefined : Number(item.component_id),
      name: item.name == null ? undefined : String(item.name),
      version_no: item.version_no == null ? undefined : Number(item.version_no),
    }))
  })

  const referenceGroups = computed(() => {
    return Object.entries(REFERENCE_GROUP_LABELS)
      .map(([kind, label]) => ({
        kind,
        label,
        items: referenceItems.value.filter(item => item.kind === kind),
      }))
      .filter(group => group.items.length > 0)
  })

  const referenceCountText = computed(() => {
    if (referencesLoading.value) return '检查中'
    if (!referenceSummary.value?.has_references) return '0'
    return String(
      referenceSummary.value.page_count
      + referenceSummary.value.component_count
      + referenceSummary.value.component_version_count
      + referenceSummary.value.theme_count
      + referenceSummary.value.font_count,
    )
  })

  const activeReplaceAccept = computed(() => {
    const assetType = replacingAsset.value?.asset_type || detailAsset.value?.asset_type
    return assetType ? ASSET_UPLOAD_ACCEPT[assetType] : ''
  })

  const canRecalculateDetailAspectRatio = computed(() => {
    const asset = detailAsset.value
    return Boolean(
      asset
      && asset.status === 'active'
      && !asset.history_kind
      && isBackfillableAssetType(asset.asset_type)
      && (!asset.approx_aspect_ratio || asset.aspect_ratio_source === 'auto')
    )
  })

  function syncEditForm(asset: AssetResponse): void {
    editForm.name = asset.name
    editForm.original_name = asset.original_name
    editForm.description = asset.description ?? ''
    editForm.approx_aspect_ratio = asset.approx_aspect_ratio ?? ''
    originalApproxAspectRatioText.value = editForm.approx_aspect_ratio
    editTagsText.value = (asset.tags ?? []).join(', ')
  }

  async function openAssetDetail(asset: AssetResponse): Promise<void> {
    selectedAsset.value = asset
    detailAsset.value = asset
    detailTab.value = 'basic'
    syncEditForm(asset)
    referenceSummary.value = null
    contentDraft.value = ''
    originalContent.value = ''
    await Promise.all([loadContent(), loadReferences()])
  }

  function closeAssetDetail(): void {
    detailAsset.value = null
  }

  function handleDetailDialogVisibleChange(value: boolean): void {
    if (!value) {
      closeAssetDetail()
    }
  }

  async function loadContent(): Promise<void> {
    const asset = detailAsset.value
    if (!Number.isFinite(options.workspaceId.value) || !asset?.content_editable) return
    try {
      const result = await getWorkspaceAssetContent(options.workspaceId.value, asset.id)
      contentDraft.value = result.content
      originalContent.value = result.content
    } catch (error) {
      Message.error(getErrorMessage(error, '读取资源内容失败'))
    }
  }

  async function loadReferences(): Promise<void> {
    const asset = detailAsset.value || selectedAsset.value
    if (!Number.isFinite(options.workspaceId.value) || !asset) return
    referencesLoading.value = true
    try {
      referenceSummary.value = await previewWorkspaceAssetReferences(options.workspaceId.value, asset.id)
    } catch (error) {
      Message.error(getErrorMessage(error, '读取引用关系失败'))
    } finally {
      referencesLoading.value = false
    }
  }

  function normalizeTags(value: string): string[] {
    return value.split(/[,，]/).map(item => item.trim()).filter(Boolean)
  }

  function normalizeAspectRatioText(value: string): string {
    return value.trim()
  }

  function buildAspectRatioUpdateValue(): string | null | undefined {
    const nextValue = normalizeAspectRatioText(editForm.approx_aspect_ratio)
    const previousValue = normalizeAspectRatioText(originalApproxAspectRatioText.value)
    if (nextValue === previousValue) return undefined
    return nextValue || null
  }

  async function saveAssetMetadata(): Promise<void> {
    if (!Number.isFinite(options.workspaceId.value) || !detailAsset.value) return
    if (!editForm.name.trim() || !editForm.original_name.trim()) {
      Message.error('资源 name 和展示文件名不能为空')
      return
    }
    saving.value = true
    try {
      const approxAspectRatio = buildAspectRatioUpdateValue()
      const updated = await updateWorkspaceAsset(
        options.workspaceId.value,
        detailAsset.value.id,
        editForm.name.trim(),
        editForm.original_name.trim(),
        normalizeTags(editTagsText.value),
        editForm.description.trim() || null,
        approxAspectRatio,
      )
      Message.success('资源信息已保存')
      detailAsset.value = updated
      selectedAsset.value = updated
      syncEditForm(updated)
      await Promise.all([options.onRefresh(), options.onRefreshTags()])
    } catch (error) {
      Message.error(getErrorMessage(error, '保存资源信息失败'))
    } finally {
      saving.value = false
    }
  }

  async function saveContent(): Promise<void> {
    if (!Number.isFinite(options.workspaceId.value) || !detailAsset.value || !canSaveContent.value) return
    saving.value = true
    try {
      const updated = await updateWorkspaceAssetContent(options.workspaceId.value, detailAsset.value.id, {
        content: contentDraft.value,
        change_note: '资源库页面写入内容',
      })
      Message.success('资源内容已写入，写入前副本已自动归档')
      detailAsset.value = updated
      selectedAsset.value = updated
      originalContent.value = contentDraft.value
      await options.onRefresh()
    } catch (error) {
      Message.error(getErrorMessage(error, '写入资源内容失败'))
    } finally {
      saving.value = false
    }
  }

  async function archiveDetailAsset(): Promise<void> {
    const asset = detailAsset.value || selectedAsset.value
    if (!Number.isFinite(options.workspaceId.value) || !asset) return
    try {
      await archiveWorkspaceAsset(options.workspaceId.value, asset.id)
      Message.success('资源已归档，现有引用仍可用')
      closeAssetDetail()
      await options.onRefresh()
    } catch (error) {
      Message.error(getErrorMessage(error, '归档资源失败'))
    }
  }

  async function restoreDetailAsset(): Promise<void> {
    const asset = detailAsset.value || selectedAsset.value
    if (!Number.isFinite(options.workspaceId.value) || !asset) return
    try {
      const restored = await restoreWorkspaceAsset(options.workspaceId.value, asset.id)
      Message.success('资源已恢复')
      options.activeView.value = 'active'
      options.page.value = 1
      await options.onRefresh()
      await openAssetDetail(restored)
    } catch (error) {
      Message.error(getErrorMessage(error, '恢复资源失败'))
    }
  }

  async function deleteDetailAsset(): Promise<void> {
    const asset = detailAsset.value || selectedAsset.value
    if (!Number.isFinite(options.workspaceId.value) || !asset) return
    await loadReferences()
    if (referenceSummary.value?.has_references) {
      Message.error('资源仍存在引用，不能删除')
      return
    }
    const confirmed = await createConfirm(`确认删除资源「${asset.name}」吗？该操作只允许无引用归档资源。`, '删除资源')
    if (!confirmed) return
    try {
      await deleteWorkspaceAsset(options.workspaceId.value, asset.id)
      Message.success('资源已删除')
      closeAssetDetail()
      selectedAsset.value = null
      await options.onRefreshWithPageFallback()
    } catch (error) {
      Message.error(getErrorMessage(error, '删除资源失败'))
    }
  }

  function triggerReplace(asset: AssetResponse): void {
    replacingAsset.value = asset
    replaceFileInput.value?.click()
  }

  async function handleReplaceFileChange(event: Event): Promise<void> {
    const target = event.target as HTMLInputElement
    const file = target.files?.[0]
    const asset = replacingAsset.value
    if (!file || !asset || !Number.isFinite(options.workspaceId.value)) {
      target.value = ''
      replacingAsset.value = null
      return
    }
    if (!isAcceptedAssetFile(file, asset.asset_type)) {
      Message.warning(`${asset.asset_type}资源仅支持 ${getAcceptedAssetExtensionText(asset.asset_type)} 文件。`)
      target.value = ''
      replacingAsset.value = null
      return
    }
    const confirmed = await createConfirm(`确认用 "${file.name}" 替换资源 "${asset.name}" 当前文件吗？`, '替换资源文件')
    if (!confirmed) {
      target.value = ''
      replacingAsset.value = null
      return
    }
    try {
      const updated = await replaceWorkspaceAssetFile(options.workspaceId.value, asset.id, file)
      Message.success('资源文件已替换')
      detailAsset.value = updated
      selectedAsset.value = updated
      await options.onRefresh()
    } catch (error) {
      Message.error(getErrorMessage(error, '替换资源文件失败'))
    } finally {
      target.value = ''
      replacingAsset.value = null
    }
  }

  async function recalculateDetailAssetAspectRatio(): Promise<void> {
    const asset = detailAsset.value
    if (!Number.isFinite(options.workspaceId.value) || !asset || !isBackfillableAssetType(asset.asset_type)) return
    options.backfillRunning.value = true
    try {
      let group = await createAssetRenderHintBackfillJobs(options.workspaceId.value, {
        asset_types: [asset.asset_type],
        asset_ids: [asset.id],
        mode: 'apply',
        overwrite_manual: false,
      })
      if (group.requested_count > 0) {
        group = await waitForAssetRenderHintBackfillJobGroup(group.job_group_id)
      }
      Message.success(`资源比例完成：可更新 ${group.succeeded_count} 个`)
      await options.onRefresh()
      syncDetailAssetAfterBackfill()
    } catch (error) {
      Message.error(getErrorMessage(error, '重新计算资源比例失败。'))
    } finally {
      options.backfillRunning.value = false
    }
  }

  function syncDetailAssetAfterBackfill(): void {
    if (!detailAsset.value) return
    const refreshed = options.assets.value.find(asset => asset.id === detailAsset.value?.id)
    if (refreshed) {
      detailAsset.value = refreshed
      selectedAsset.value = refreshed
      syncEditForm(refreshed)
    }
  }

  function closeDetailIfSelected(assetIds: number[]): void {
    if (detailAsset.value && assetIds.includes(detailAsset.value.id)) {
      closeAssetDetail()
    }
    if (selectedAsset.value && assetIds.includes(selectedAsset.value.id)) {
      selectedAsset.value = null
    }
  }

  function resolveAssetStatusBadgeText(asset: AssetResponse): string {
    if (asset.history_kind) return '历史副本'
    return asset.status === 'archived' ? '已归档' : '启用'
  }

  function canEditAssetAspectRatio(asset: AssetResponse): boolean {
    return ['image', 'icon', 'video', 'drawio', 'mermaid', 'formula'].includes(asset.asset_type)
  }

  function formatAssetAspectRatio(asset: AssetResponse): string {
    return asset.approx_aspect_ratio || '-'
  }

  function formatAspectRatioSource(source: string | null | undefined): string {
    if (source === 'auto') return '自动'
    if (source === 'manual') return '人工'
    if (source === 'agent') return '内容助手'
    return '-'
  }

  function formatReferenceName(item: AssetReferenceItem): string {
    if (item.kind === 'component_version') {
      return `${item.name || '组件'} v${item.version_no || '-'}`
    }
    return item.name || `${item.kind} #${item.id}`
  }

  function canOpenReference(item: AssetReferenceItem): boolean {
    return item.kind === 'component'
  }

  function goToReference(item: AssetReferenceItem): void {
    if (!canOpenReference(item)) return
    if (item.kind === 'component') {
      void router.push(buildWorkspaceComponentsPath(options.workspaceId.value, item.id))
    }
  }

  return {
    detailAsset,
    selectedAsset,
    detailTab,
    contentDraft,
    originalContent,
    referenceSummary,
    referencesLoading,
    saving,
    replacingAsset,
    replaceFileInput,
    editForm,
    editTagsText,
    canSaveContent,
    referenceGroups,
    referenceCountText,
    activeReplaceAccept,
    canRecalculateDetailAspectRatio,
    openAssetDetail,
    closeAssetDetail,
    handleDetailDialogVisibleChange,
    loadContent,
    loadReferences,
    saveAssetMetadata,
    saveContent,
    archiveDetailAsset,
    restoreDetailAsset,
    deleteDetailAsset,
    triggerReplace,
    handleReplaceFileChange,
    recalculateDetailAssetAspectRatio,
    syncDetailAssetAfterBackfill,
    closeDetailIfSelected,
    resolveAssetStatusBadgeText,
    canEditAssetAspectRatio,
    formatAssetAspectRatio,
    formatAspectRatioSource,
    formatReferenceName,
    canOpenReference,
    goToReference,
  }
}

export type AssetDetailController = ReturnType<typeof useAssetDetail>
