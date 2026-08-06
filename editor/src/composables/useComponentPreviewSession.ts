/**
 * 文件功能：封装组件预览 artifact、iframe 通信、预览配置和缩放视口状态，供工作空间组件与 Runtime Kit 复用。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { getWorkspace } from '@/api/catalog'
import type { ComponentPreviewOptions, PreviewArtifactResponse } from '@/types/api'
import type { RuntimePreviewStatus } from '@/types/runtime-preview'
import {
  COMPONENT_PREVIEW_ERROR_EVENT,
  COMPONENT_PREVIEW_READY_EVENT,
  COMPONENT_PREVIEW_UPDATE_PLACEMENT_EVENT,
  COMPONENT_PREVIEW_UPDATE_STATE_EVENT,
  buildInitialComponentPreviewState,
  cloneComponentPreviewState,
  type ComponentPreviewErrorMessage,
  type ComponentPreviewReadyMessage,
  type ComponentPreviewSchema,
  type ComponentPreviewState,
  type ComponentPreviewUpdatePlacementMessage,
  type ComponentPreviewUpdateStateMessage,
} from '@/types/component-preview'
import {
  buildDefaultComponentPreviewOptions,
  cloneComponentPreviewOptions,
  isSamePreviewPageOptions,
  normalizeComponentPreviewOptions,
} from '@/components/component-preview/preview-config'
import { calculateContainScale, useObservedViewportSize } from '@/composables/useObservedViewportSize'

export interface ComponentPreviewSessionPrepareOptions {
  workspaceId: number | null
  baseOptions?: ComponentPreviewOptions | null
  zeroPaddingPreview?: boolean
}

const PREVIEW_SLOW_DELAY_MS = 8000
const PREVIEW_TIMEOUT_MS = 30000

/**
 * 创建组件预览会话状态，并在组件生命周期内监听 Runtime 宿主页 ready 消息。
 */
export function useComponentPreviewSession() {
  const previewLoading = ref(false)
  const previewStatus = ref<RuntimePreviewStatus>('idle')
  const previewUrl = ref('')
  const previewArtifactId = ref('')
  const previewRefreshToken = ref(0)
  const workspacePreviewDefaultConfig = ref<ComponentPreviewOptions>(buildDefaultComponentPreviewOptions())
  const previewBaseConfig = ref<ComponentPreviewOptions>(buildDefaultComponentPreviewOptions())
  const previewConfigDraft = ref<ComponentPreviewOptions>(buildDefaultComponentPreviewOptions())
  const previewAppliedConfig = ref<ComponentPreviewOptions>(buildDefaultComponentPreviewOptions())
  const previewErrorMessage = ref('')
  const previewSchema = ref<ComponentPreviewSchema | null>(null)
  const previewState = ref<ComponentPreviewState>(buildInitialComponentPreviewState(null))
  const hasPreviewStateSnapshot = ref(false)
  const previewComponentMeta = ref<ComponentPreviewReadyMessage['payload']['componentMeta'] | null>(null)
  const previewFrameRef = ref<HTMLIFrameElement | null>(null)
  let previewRequestSeq = 0
  let previewLifecycleSeq = 0
  let previewSlowTimer: number | null = null
  let previewTimeoutTimer: number | null = null
  const {
    viewportRef: previewViewportRef,
    viewportSize: previewViewportSize,
    observeViewport,
    disconnectViewportObserver,
  } = useObservedViewportSize({ subtractPadding: true })

  const previewTargetOrigin = computed(() => {
    if (!previewUrl.value) return ''
    try {
      return new URL(previewUrl.value).origin
    } catch {
      return ''
    }
  })

  const previewFrameUrl = computed(() => {
    if (!previewUrl.value) return ''
    try {
      const nextUrl = new URL(previewUrl.value)
      nextUrl.searchParams.set('t', String(previewRefreshToken.value))
      return nextUrl.toString()
    } catch {
      return ''
    }
  })

  const previewFrameScale = computed(() => calculateContainScale({
    viewportWidth: previewViewportSize.width,
    viewportHeight: previewViewportSize.height,
    contentWidth: previewConfigDraft.value.page.width,
    contentHeight: previewConfigDraft.value.page.height,
  }))

  const previewFrameStageStyle = computed(() => ({
    width: `${previewConfigDraft.value.page.width * previewFrameScale.value}px`,
    height: `${previewConfigDraft.value.page.height * previewFrameScale.value}px`,
  }))

  const previewFrameContainerStyle = computed(() => ({
    width: `${previewConfigDraft.value.page.width}px`,
    height: `${previewConfigDraft.value.page.height}px`,
    background: '#ffffff',
    transform: `scale(${previewFrameScale.value})`,
    transformOrigin: 'top left',
  }))

  const hasPendingPageChanges = computed(() => !isSamePreviewPageOptions(
    previewConfigDraft.value.page,
    previewAppliedConfig.value.page,
  ))

  watch(
    () => previewConfigDraft.value.placement,
    () => {
      syncPreviewPlacementToIframe()
    },
    { deep: true },
  )

  onMounted(async () => {
    window.addEventListener('message', handleWindowMessage)
    await nextTick()
    observeViewport()
  })

  onUnmounted(() => {
    window.removeEventListener('message', handleWindowMessage)
    disconnectViewportObserver()
    previewLifecycleSeq += 1
    clearPreviewLifecycleTimers()
  })

  /**
   * 按工作空间默认主题和可选基线配置准备预览选项。
   * @param options 工作空间与组件预览基线
   */
  async function preparePreviewConfig(options: ComponentPreviewSessionPrepareOptions): Promise<void> {
    previewLoading.value = true
    beginPreviewLoading('generating')
    const fallbackOptions = buildDefaultComponentPreviewOptions()
    if (options.zeroPaddingPreview) {
      fallbackOptions.placement.padding = 0
    }
    if (!options.workspaceId) {
      applyBaseOptions(fallbackOptions, options.baseOptions)
      return
    }

    try {
      const workspace = await getWorkspace(options.workspaceId)
      const defaultOptions = buildDefaultComponentPreviewOptions(workspace.default_theme_key)
      if (options.zeroPaddingPreview) {
        defaultOptions.placement.padding = 0
      }
      applyBaseOptions(defaultOptions, options.baseOptions)
    } catch {
      if (options.zeroPaddingPreview) {
        fallbackOptions.placement.padding = 0
      }
      applyBaseOptions(fallbackOptions, options.baseOptions)
    }
  }

  /**
   * 执行一次预览 artifact 创建，并刷新 iframe 地址。
   * @param loader 实际创建 artifact 的函数
   */
  async function runPreview(loader: () => Promise<PreviewArtifactResponse>): Promise<PreviewArtifactResponse | null> {
    const requestSeq = previewRequestSeq + 1
    previewRequestSeq = requestSeq
    previewLoading.value = true
    beginPreviewLoading('generating')
    previewErrorMessage.value = ''
    previewSchema.value = null
    previewComponentMeta.value = null
    let previewResponse: PreviewArtifactResponse
    try {
      previewResponse = await loader()
    } catch (error) {
      if (requestSeq !== previewRequestSeq) {
        return null
      }
      throw error
    }
    if (requestSeq !== previewRequestSeq) {
      return null
    }
    previewUrl.value = previewResponse.preview_url
    previewArtifactId.value = previewResponse.artifact_id
    previewAppliedConfig.value = cloneComponentPreviewOptions(previewConfigDraft.value)
    refreshPreviewFrame()
    return previewResponse
  }

  /**
   * 重置为当前预览对象声明的基线配置。
   */
  function resetPreviewConfigDraft(): void {
    previewConfigDraft.value = cloneComponentPreviewOptions(previewBaseConfig.value)
  }

  /**
   * 仅回滚需要重建 artifact 的页面配置，保留组件占位调试状态。
   */
  function resetPendingPageConfig(): void {
    previewConfigDraft.value = {
      ...previewConfigDraft.value,
      page: cloneComponentPreviewOptions(previewAppliedConfig.value).page,
    }
  }

  /**
   * 清空当前预览会话，避免不同组件之间串用状态。
   */
  function resetPreviewState(): void {
    previewRequestSeq += 1
    previewLoading.value = false
    previewStatus.value = 'idle'
    previewUrl.value = ''
    previewArtifactId.value = ''
    previewRefreshToken.value = 0
    workspacePreviewDefaultConfig.value = buildDefaultComponentPreviewOptions()
    previewBaseConfig.value = buildDefaultComponentPreviewOptions()
    previewConfigDraft.value = buildDefaultComponentPreviewOptions()
    previewAppliedConfig.value = buildDefaultComponentPreviewOptions()
    previewErrorMessage.value = ''
    previewSchema.value = null
    previewState.value = buildInitialComponentPreviewState(null)
    hasPreviewStateSnapshot.value = false
    previewComponentMeta.value = null
    previewLifecycleSeq += 1
    clearPreviewLifecycleTimers()
  }

  /**
   * 主动刷新 iframe 地址，强制浏览器重载当前预览页。
   */
  function refreshPreviewFrame(): void {
    if (!previewUrl.value) {
      return
    }
    previewRefreshToken.value = Date.now()
    previewLoading.value = true
    beginPreviewLoading('loading')
  }

  /**
   * 启动组件 artifact 或 iframe 的等待周期，并在弱网阈值后更新用户反馈。
   * @param status 当前等待阶段
   */
  function beginPreviewLoading(status: 'generating' | 'loading'): void {
    clearPreviewLifecycleTimers()
    const lifecycleSeq = previewLifecycleSeq + 1
    previewLifecycleSeq = lifecycleSeq
    previewStatus.value = status
    previewSlowTimer = window.setTimeout(() => {
      if (lifecycleSeq !== previewLifecycleSeq) return
      previewStatus.value = 'slow'
    }, PREVIEW_SLOW_DELAY_MS)
    previewTimeoutTimer = window.setTimeout(() => {
      if (lifecycleSeq !== previewLifecycleSeq) return
      previewStatus.value = 'error'
      previewLoading.value = false
      previewErrorMessage.value = '组件预览加载超过 30 秒，可以重新生成预览。'
      clearPreviewLifecycleTimers()
    }, PREVIEW_TIMEOUT_MS)
  }

  /** 清理组件预览生命周期计时器。 */
  function clearPreviewLifecycleTimers(): void {
    if (previewSlowTimer !== null) window.clearTimeout(previewSlowTimer)
    if (previewTimeoutTimer !== null) window.clearTimeout(previewTimeoutTimer)
    previewSlowTimer = null
    previewTimeoutTimer = null
  }

  /**
   * 把当前组件预览切换到错误终态，供 artifact 请求失败与 Runtime error 共用。
   * @param message 用户可读错误
   */
  function markPreviewError(message: string): void {
    previewLifecycleSeq += 1
    clearPreviewLifecycleTimers()
    previewStatus.value = 'error'
    previewLoading.value = false
    previewErrorMessage.value = message
  }

  /**
   * 将调参状态同步到 Runtime 宿主页。
   * @param nextState 最新调参状态
   */
  function handlePreviewStateChange(nextState: ComponentPreviewState): void {
    previewState.value = cloneComponentPreviewState(nextState)
    hasPreviewStateSnapshot.value = true
    if (!previewArtifactId.value || !previewFrameRef.value?.contentWindow || !previewTargetOrigin.value) {
      return
    }

    const message: ComponentPreviewUpdateStateMessage = {
      type: COMPONENT_PREVIEW_UPDATE_STATE_EVENT,
      payload: {
        version: 1,
        artifactId: previewArtifactId.value,
        state: cloneComponentPreviewState(previewState.value),
      },
    }
    previewFrameRef.value.contentWindow.postMessage(message, previewTargetOrigin.value)
  }

  /**
   * 将组件占位配置同步到 iframe，无需重新创建 artifact。
   */
  function syncPreviewPlacementToIframe(): void {
    if (!previewArtifactId.value || !previewFrameRef.value?.contentWindow || !previewTargetOrigin.value) {
      return
    }

    const message: ComponentPreviewUpdatePlacementMessage = {
      type: COMPONENT_PREVIEW_UPDATE_PLACEMENT_EVENT,
      payload: {
        version: 1,
        artifactId: previewArtifactId.value,
        placement: normalizeComponentPreviewOptions(previewConfigDraft.value).placement,
      },
    }
    previewFrameRef.value.contentWindow.postMessage(message, previewTargetOrigin.value)
  }

  /**
   * 处理 Runtime 宿主页 ready 消息并初始化调参面板。
   * @param event postMessage 事件
   */
  function handleWindowMessage(event: MessageEvent<unknown>): void {
    if (!previewTargetOrigin.value || event.origin !== previewTargetOrigin.value) {
      return
    }
    if (!event.data || typeof event.data !== 'object') {
      return
    }

    const message = event.data as Partial<ComponentPreviewReadyMessage | ComponentPreviewErrorMessage>
    if (message.type === COMPONENT_PREVIEW_READY_EVENT) {
      if (message.payload?.version !== 1 || message.payload?.artifactId !== previewArtifactId.value) {
        return
      }

      previewErrorMessage.value = ''
      previewSchema.value = message.payload.schema ?? null
      previewComponentMeta.value = message.payload.componentMeta
      syncPreviewPlacementToIframe()
      if (hasPreviewStateSnapshot.value) {
        handlePreviewStateChange(previewState.value)
      } else {
        previewState.value = cloneComponentPreviewState(message.payload.defaultState)
      }
      previewLoading.value = false
      previewStatus.value = 'ready'
      previewLifecycleSeq += 1
      clearPreviewLifecycleTimers()
      return
    }

    if (message.type !== COMPONENT_PREVIEW_ERROR_EVENT) {
      return
    }
    if (message.payload?.version !== 1 || message.payload?.artifactId !== previewArtifactId.value) {
      return
    }

    markPreviewError(normalizePreviewErrorMessage(message.payload.message))
    previewSchema.value = null
    previewComponentMeta.value = null
  }

  /**
   * 归一化 Runtime 回传的预览启动错误，保证界面始终有可展示文本。
   * @param message Runtime 回传的原始错误
   */
  function normalizePreviewErrorMessage(message: unknown): string {
    return typeof message === 'string' && message.trim() ? message.trim() : '组件预览启动失败。'
  }

  function applyBaseOptions(defaultOptions: ComponentPreviewOptions, baseOptions?: ComponentPreviewOptions | null): void {
    const normalizedBaseOptions = baseOptions
      ? normalizeComponentPreviewOptions(baseOptions, defaultOptions.page.theme_key)
      : cloneComponentPreviewOptions(defaultOptions)
    workspacePreviewDefaultConfig.value = cloneComponentPreviewOptions(defaultOptions)
    previewBaseConfig.value = cloneComponentPreviewOptions(normalizedBaseOptions)
    previewConfigDraft.value = cloneComponentPreviewOptions(normalizedBaseOptions)
    previewAppliedConfig.value = cloneComponentPreviewOptions(normalizedBaseOptions)
  }

  return {
    hasPendingPageChanges,
    previewAppliedConfig,
    previewArtifactId,
    previewBaseConfig,
    previewComponentMeta,
    previewConfigDraft,
    previewErrorMessage,
    previewFrameContainerStyle,
    previewFrameRef,
    previewFrameStageStyle,
    previewFrameUrl,
    previewLoading,
    previewStatus,
    previewSchema,
    previewState,
    previewViewportRef,
    workspacePreviewDefaultConfig,
    handlePreviewStateChange,
    markPreviewError,
    observeViewport,
    preparePreviewConfig,
    refreshPreviewFrame,
    resetPendingPageConfig,
    resetPreviewConfigDraft,
    resetPreviewState,
    runPreview,
  }
}
