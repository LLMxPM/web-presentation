<!--
  文件用途：提供工作空间组件的纯沙箱预览宿主页，负责读取后端下发的 previewSchema、接收父窗口状态更新并按单层页面舞台渲染目标组件。
-->
<template>
  <main class="component-preview-view">
    <section class="component-preview-page" :style="previewContentStyles">
      <div v-if="loading" class="component-preview-state component-preview-state--loading">
        正在加载组件预览...
      </div>
      <div v-else-if="errorMessage" class="component-preview-state component-preview-state--error">
        <h1>组件预览启动失败</h1>
        <p>{{ errorMessage }}</p>
      </div>
      <div v-else class="component-preview-placement" :style="placementContainerStyle">
        <div class="component-preview-placement__frame" :style="placementFrameStyle">
          <PreviewContentRenderer
            v-if="componentDefinition"
            :component-definition="componentDefinition"
            :state="previewState"
          />
        </div>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onErrorCaptured, onMounted, onUnmounted, provide, readonly, ref, shallowRef, type Component } from 'vue'

import { COMPONENT_PREVIEW_MOCKS_KEY } from '@/core/composables/useComponentPreviewMock'
import {
  COMPONENT_PREVIEW_ERROR_EVENT,
  COMPONENT_PREVIEW_READY_EVENT,
  COMPONENT_PREVIEW_RENDER_SETTLED_EVENT,
  COMPONENT_PREVIEW_UPDATE_PLACEMENT_EVENT,
  COMPONENT_PREVIEW_UPDATE_STATE_EVENT,
  buildInitialComponentPreviewState,
  clonePreviewValue,
  normalizeComponentPreviewSchema,
  normalizeComponentPreviewState,
  type ComponentPreviewErrorMessage,
  type ComponentPreviewReadyMessage,
  type ComponentPreviewRenderSettledMessage,
  type ComponentPreviewState,
  type ComponentPreviewUpdatePlacementMessage,
  type ComponentPreviewUpdateStateMessage,
} from '@/core/shared/component-preview'
import type { ComponentPreviewSchema, RuntimeComponentPreviewPlacementOptions } from '@/core/shared/runtime-preview'
import { buildPageContentScaleStyles } from '@/core/utils/page-scale'
import { getRuntimePreloadedConfig, getRuntimePreviewContext } from '@/core/utils/path'
import { importPreviewModule } from '@/core/utils/preview-module'
import {
  ackRenderScenario,
  initializeRenderReadyHost,
  markRenderPreviewMounted,
  markRenderReadyFailure,
} from '@/core/utils/render-ready'
import {
  buildPlacementContainerStyle,
  buildPlacementFrameStyle,
  normalizeComponentPreviewPlacement,
} from './placement'
import PreviewContentRenderer from './PreviewContentRenderer'

const componentDefinition = shallowRef<Component | null>(null)
const previewSchema = ref<ComponentPreviewSchema | null>(null)
const previewState = ref<ComponentPreviewState>(buildInitialComponentPreviewState(null))
const loading = ref(true)
const errorMessage = ref('')
const mockStateRef = computed(() => previewState.value.mocks)

provide(COMPONENT_PREVIEW_MOCKS_KEY, readonly(mockStateRef))

const previewContext = computed(() => getRuntimePreviewContext())
const componentPreviewConfig = computed(() => getRuntimePreloadedConfig()?.component_preview)
const parentOrigin = resolveParentOrigin()
const placementOptions = ref<Required<RuntimeComponentPreviewPlacementOptions>>(
  normalizeComponentPreviewPlacement(componentPreviewConfig.value?.placement),
)
const previewContentStyles = computed(() => buildPageContentScaleStyles())
const placementContainerStyle = computed(() => buildPlacementContainerStyle(placementOptions.value))
const placementFrameStyle = computed(() => buildPlacementFrameStyle(placementOptions.value))

/**
 * 加载组件模块、读取后端下发 schema 并向父窗口回传 ready 事件。
 */
async function bootstrapComponentPreview(): Promise<void> {
  const previewConfig = componentPreviewConfig.value
  const artifactId = previewContext.value?.artifactId
  if (!previewConfig || !previewConfig.component_import_path || !artifactId) {
    const message = '缺少组件预览上下文或目标组件路径。'
    errorMessage.value = message
    notifyParentError(message)
    loading.value = false
    return
  }

  try {
    loading.value = true
    placementOptions.value = normalizeComponentPreviewPlacement(previewConfig.placement)
    const importedModule = await importPreviewModule(previewConfig.component_import_path)
    componentDefinition.value = resolveModuleComponent(importedModule)
    previewSchema.value = normalizeComponentPreviewSchema(previewConfig.schema)
    previewState.value = buildInitialComponentPreviewState(previewSchema.value)
    loading.value = false
    await waitForRenderSettled()
    if (errorMessage.value) {
      return
    }
    notifyParentReady()
    notifyParentRenderSettled()
  } catch (error) {
    const message = resolvePreviewErrorMessage(error)
    errorMessage.value = message
    notifyParentError(message)
    loading.value = false
  }
}

/**
 * 等待 Vue 更新和两帧浏览器绘制，供自动诊断可靠读取最终 DOM。
 */
async function waitForRenderSettled(): Promise<void> {
  await nextTick()
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  })
}

/**
 * 从动态模块对象中解析 Vue 组件。
 * @param module 动态导入返回的模块对象或组件本身
 * @returns Vue 组件定义
 */
function resolveModuleComponent(module: unknown): Component {
  if (module && typeof module === 'object' && 'default' in module) {
    const defaultExport = (module as { default?: unknown }).default
    if (defaultExport) {
      return defaultExport as Component
    }
  }

  return module as Component
}

/**
 * 向父窗口发送组件预览就绪事件。
 */
function notifyParentReady(): void {
  const artifactId = previewContext.value?.artifactId
  const previewConfig = componentPreviewConfig.value
  if (!artifactId || !previewConfig || typeof window === 'undefined' || !window.parent) {
    return
  }

  const readyMessage: ComponentPreviewReadyMessage = {
    type: COMPONENT_PREVIEW_READY_EVENT,
    payload: {
      version: 1,
      artifactId,
      schema: clonePreviewValue(previewSchema.value),
      defaultState: clonePreviewValue(previewState.value),
      componentMeta: {
        code: previewConfig.runtime_kit_component_name || previewConfig.component_code || previewConfig.component_import_path,
        versionNo: previewConfig.component_version_no,
        displayName: previewConfig.display_name
          || previewConfig.runtime_kit_component_name
          || previewConfig.component_code
          || previewConfig.component_import_path,
        source: previewConfig.component_source,
        runtimeKitComponentName: previewConfig.runtime_kit_component_name,
        runtimeKitManifestVersion: previewConfig.runtime_kit_manifest_version,
      },
    },
  }
  // 编辑器开发环境常通过不同 origin 加载预览 iframe，且 iframe 配置了 same-origin referrer policy，
  // 此时子窗口无法通过 document.referrer 推断父窗口 origin。这里退回 "*"，由父窗口继续按 event.origin
  // 校验消息来源，避免 previewSchema ready 事件被静默丢弃。
  window.parent.postMessage(readyMessage, parentOrigin || '*')
  // 同步写入 render-ready.v1 宿主协议，供远程 Renderer 组件诊断等待场景回执。
  void markComponentRenderReady()
}

/**
 * 解析 render-ready.v1 元数据；input_digest 来自导航查询串，供 Renderer 硬核对。
 */
function resolveRenderReadyMeta(): { artifactId: string | null; inputDigest: string | null } {
  const params = new URLSearchParams(typeof window === 'undefined' ? '' : window.location.search)
  return {
    artifactId: previewContext.value?.artifactId || params.get('artifact'),
    inputDigest: params.get('input_digest'),
  }
}

/**
 * 注册场景切换桥并标记组件预览已挂载。
 */
async function markComponentRenderReady(): Promise<void> {
  const meta = resolveRenderReadyMeta()
  initializeRenderReadyHost(meta)
  window.__RENDER_APPLY_SCENARIO__ = applyRenderScenario
  await markRenderPreviewMounted(meta)
}

/**
 * 按场景 key / 覆盖字段组装完整预览状态。
 */
function resolveScenarioState(
  scenarioKey: string,
  input: {
    state?: unknown
    props?: Record<string, unknown> | null
    slots?: Record<string, unknown> | null
    mocks?: Record<string, unknown> | null
  },
): ComponentPreviewState {
  const schema = previewSchema.value
  const preset = schema?.presets?.find((item) => item.key === scenarioKey)
  const base = buildInitialComponentPreviewState(schema)
  const activePresetKey = scenarioKey === 'default' ? null : scenarioKey
  const rawState = input.state
  if (rawState && typeof rawState === 'object' && !Array.isArray(rawState)) {
    const candidate = rawState as Record<string, unknown>
    if ('props' in candidate || 'slots' in candidate || 'mocks' in candidate || 'activePresetKey' in candidate) {
      return {
        ...normalizeComponentPreviewState(candidate),
        activePresetKey,
      }
    }
  }
  return normalizeComponentPreviewState({
    props: {
      ...base.props,
      ...(preset?.props || {}),
      ...((input.props && typeof input.props === 'object' ? input.props : null) || {}),
    },
    slots: {
      ...base.slots,
      ...(preset?.slots || {}),
      ...((input.slots && typeof input.slots === 'object' ? input.slots : null) || {}),
    },
    mocks: {
      ...base.mocks,
      ...(preset?.mocks || {}),
      ...((input.mocks && typeof input.mocks === 'object' ? input.mocks : null) || {}),
    },
    activePresetKey,
  })
}

/**
 * 供 Renderer 诊断脚本调用的场景切换入口；成功/失败都会写 render-ready 回执。
 */
async function applyRenderScenario(input: {
  scenarioKey: string
  profileKey: string
  requestId: string
  state?: unknown
  props?: Record<string, unknown> | null
  slots?: Record<string, unknown> | null
  mocks?: Record<string, unknown> | null
}): Promise<{ requestId: string; ok: boolean; scenarioKey: string }> {
  const scenarioKey = input.scenarioKey || 'default'
  try {
    previewState.value = resolveScenarioState(scenarioKey, input)
    await waitForRenderSettled()
    const ok = !errorMessage.value
    ackRenderScenario({ requestId: input.requestId, scenarioKey, ok })
    return { requestId: input.requestId, ok, scenarioKey }
  } catch {
    ackRenderScenario({ requestId: input.requestId, scenarioKey, ok: false })
    return { requestId: input.requestId, ok: false, scenarioKey }
  }
}

/**
 * 向父窗口发送组件预览失败事件，避免 Editor 参数栏长期停留在读取 schema 状态。
 * @param message 预览启动失败原因
 */
function notifyParentError(message: string): void {
  const artifactId = previewContext.value?.artifactId
  if (!artifactId || typeof window === 'undefined' || !window.parent) {
    return
  }

  const errorPayload: ComponentPreviewErrorMessage = {
    type: COMPONENT_PREVIEW_ERROR_EVENT,
    payload: {
      version: 1,
      artifactId,
      message,
    },
  }
  window.parent.postMessage(errorPayload, parentOrigin || '*')
  // 启动/渲染异常视为协议初始化失败，供 Renderer 立即结束等待。
  markRenderReadyFailure(message)
}

/**
 * 通知父窗口当前预览状态已经完成 Vue 更新和浏览器绘制。
 * @param requestId 状态切换请求标识，用于自动诊断匹配响应
 */
function notifyParentRenderSettled(requestId?: string): void {
  const artifactId = previewContext.value?.artifactId
  if (!artifactId || typeof window === 'undefined' || !window.parent) {
    return
  }

  const settledMessage: ComponentPreviewRenderSettledMessage = {
    type: COMPONENT_PREVIEW_RENDER_SETTLED_EVENT,
    payload: {
      version: 1,
      artifactId,
      requestId,
      activePresetKey: previewState.value.activePresetKey,
    },
  }
  window.parent.postMessage(settledMessage, parentOrigin || '*')
}

/**
 * 归一化动态导入或渲染启动阶段抛出的错误信息。
 * @param error 原始错误
 * @returns 用户可读的错误摘要
 */
function resolvePreviewErrorMessage(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '未知组件预览错误。'
}

/**
 * 监听父窗口发来的预览状态或占位更新消息。
 * @param event postMessage 事件
 */
async function handleWindowMessage(event: MessageEvent<unknown>): Promise<void> {
  const artifactId = previewContext.value?.artifactId
  if (!artifactId || !event.data || typeof event.data !== 'object') {
    return
  }
  if (parentOrigin && event.origin !== parentOrigin) {
    return
  }

  const statePayload = event.data as Partial<ComponentPreviewUpdateStateMessage>
  if (statePayload.type === COMPONENT_PREVIEW_UPDATE_STATE_EVENT) {
    if (statePayload.payload?.version !== 1 || statePayload.payload?.artifactId !== artifactId) {
      return
    }

    previewState.value = normalizeComponentPreviewState(statePayload.payload.state)
    await waitForRenderSettled()
    if (errorMessage.value) {
      return
    }
    notifyParentRenderSettled(statePayload.payload.requestId)
    return
  }

  const placementPayload = event.data as Partial<ComponentPreviewUpdatePlacementMessage>
  if (placementPayload.type !== COMPONENT_PREVIEW_UPDATE_PLACEMENT_EVENT) {
    return
  }
  if (placementPayload.payload?.version !== 1 || placementPayload.payload?.artifactId !== artifactId) {
    return
  }

  placementOptions.value = normalizeComponentPreviewPlacement(placementPayload.payload.placement)
}

onErrorCaptured((error) => {
  const message = resolvePreviewErrorMessage(error)
  errorMessage.value = message
  loading.value = false
  notifyParentError(message)
  return false
})

/**
 * 解析父窗口来源，用于限制 postMessage 的发送和接收域。
 * @returns 父窗口 origin；无法解析时返回空串
 */
function resolveParentOrigin(): string {
  if (typeof document === 'undefined') {
    return ''
  }
  try {
    return document.referrer ? new URL(document.referrer).origin : ''
  } catch {
    return ''
  }
}

onMounted(() => {
  window.addEventListener('message', handleWindowMessage)
  // 尽早暴露协议与场景切换桥，避免 Renderer 在 ready 前核对 inputDigest 或调用场景切换时能力缺失。
  const meta = resolveRenderReadyMeta()
  initializeRenderReadyHost(meta)
  window.__RENDER_APPLY_SCENARIO__ = applyRenderScenario
  void bootstrapComponentPreview()
})

onUnmounted(() => {
  window.removeEventListener('message', handleWindowMessage)
})
</script>

<style scoped>
.component-preview-view {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #ffffff;
}

.component-preview-page {
  width: 100%;
  height: 100%;
  overflow: auto;
  background: #ffffff;
}

.component-preview-placement {
  min-width: 100%;
  min-height: 100%;
  box-sizing: border-box;
  display: flex;
}

.component-preview-placement__frame {
  box-sizing: border-box;
  max-width: 100%;
  max-height: 100%;
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
}

.component-preview-state {
  width: 100%;
  height: 100%;
  min-height: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #475569;
}

.component-preview-state--loading {
  font-size: 16px;
  font-weight: 600;
}

.component-preview-state--error h1 {
  margin: 0 0 12px;
  font-size: 28px;
  color: #b91c1c;
}

.component-preview-state--error p {
  max-width: 720px;
  margin: 0;
  line-height: 1.8;
}
</style>
