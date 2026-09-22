/**
 * 文件用途：验证 visual-edit 专用预览的点击选区、安全 marker 解析、显式 origin 与普通预览隔离。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  RuntimeArtifactKind,
  RuntimePreloadedConfigBundle,
  RuntimePreviewContext,
} from '@/core/shared/runtime-preview'

import type { VisualEditSfcManifest, VisualEditTemplateNode } from '../protocol'
import { analyzeVisualEditSfc } from '../source/analyze-sfc'
import {
  VISUAL_EDIT_LOOP_ATTRIBUTE,
  VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE,
  VISUAL_EDIT_LOOP_KEY_ATTRIBUTE,
  VISUAL_EDIT_NODE_ATTRIBUTE,
} from '../instrumentation/markers'
import { registerPageVisualEditSelectionBridge } from './selection-bridge'

const ARTIFACT_ID = 'artifact-visual-edit-1'
const EDITOR_REFERRER = 'https://editor.example.com/projects/42/pages/7'
const SOURCE = `<script setup lang="ts">
const items = [{ id: 'alpha', title: '标题' }, { id: 7, title: '数字标题' }]
</script>
<template>
  <article v-for="(item, index) in items" :key="item.id">
    <a href="https://outside.example.com"><span>{{ item.title }}</span></a>
  </article>
  <FragmentCard />
</template>`

describe('registerPageVisualEditSelectionBridge', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  afterEach(() => {
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('应捕获链接内字符串 key 节点、阻止页面交互并向 referrer origin 发送精确消息', () => {
    const fixture = buildFixture()
    const postMessage = vi.fn()
    const anchor = document.createElement('a')
    const child = document.createElement('span')
    const downstreamClick = vi.fn()
    anchor.href = 'https://outside.example.com'
    anchor.className = 'canonical-class'
    anchor.style.color = 'red'
    applyLoopMarkers(anchor, fixture.anchor.nodeId, fixture.loop.nodeId, JSON.stringify('alpha'), '0')
    anchor.appendChild(child)
    anchor.addEventListener('click', downstreamClick)
    document.body.appendChild(anchor)

    const dispose = registerPageVisualEditSelectionBridge({
      preloadedConfig: fixture.config,
      previewContext: fixture.previewContext,
      referrer: EDITOR_REFERRER,
      postMessageTarget: { postMessage },
    })
    expect(dispose).not.toBeNull()
    const clickEvent = new MouseEvent('click', { bubbles: true, cancelable: true })
    child.dispatchEvent(clickEvent)

    expect(clickEvent.defaultPrevented).toBe(true)
    expect(downstreamClick).not.toHaveBeenCalled()
    expect(postMessage).toHaveBeenCalledWith({
      type: 'page-visual-edit:selection',
      payload: {
        protocolVersion: 1,
        artifactId: ARTIFACT_ID,
        nodeId: fixture.anchor.nodeId,
        instancePath: [{
          loopNodeId: fixture.loop.nodeId,
          key: 'alpha',
          index: 0,
        }],
      },
    }, 'https://editor.example.com')
    expect(anchor.className).toBe('canonical-class')
    expect(anchor.style.color).toBe('red')
    expect(document.body.children).toHaveLength(2)

    dispose?.()
    expect(document.body.children).toHaveLength(1)
    anchor.removeAttribute('href')
    anchor.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    expect(postMessage).toHaveBeenCalledTimes(1)
  })

  it('应接受有限整数 key，并在 index 缺失时不发送该字段', () => {
    const fixture = buildFixture()
    const postMessage = vi.fn()
    const marker = document.createElement('article')
    applyLoopMarkers(marker, fixture.loop.nodeId, fixture.loop.nodeId, JSON.stringify(7))
    document.body.appendChild(marker)

    const dispose = registerPageVisualEditSelectionBridge({
      preloadedConfig: fixture.config,
      previewContext: fixture.previewContext,
      referrer: EDITOR_REFERRER,
      postMessageTarget: { postMessage },
    })
    marker.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))

    expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({
      payload: expect.objectContaining({
        nodeId: fixture.loop.nodeId,
        instancePath: [{ loopNodeId: fixture.loop.nodeId, key: 7 }],
      }),
    }), 'https://editor.example.com')
    dispose?.()
  })

  it.each([
    ['unknown-node', JSON.stringify('alpha'), '0'],
    ['known-node', 'true', '0'],
    ['known-node', '1.5', '0'],
    ['known-node', 'alpha', '0'],
    ['known-node', JSON.stringify('alpha'), '-1'],
  ])('伪造或非法 marker 不应产生选区消息：%s / %s / %s', (nodeKind, rawKey, rawIndex) => {
    const fixture = buildFixture()
    const postMessage = vi.fn()
    const marker = document.createElement('div')
    applyLoopMarkers(
      marker,
      nodeKind === 'known-node' ? fixture.anchor.nodeId : 'node-forged',
      fixture.loop.nodeId,
      rawKey,
      rawIndex,
    )
    document.body.appendChild(marker)
    const dispose = registerPageVisualEditSelectionBridge({
      preloadedConfig: fixture.config,
      previewContext: fixture.previewContext,
      referrer: EDITOR_REFERRER,
      postMessageTarget: { postMessage },
    })
    const event = new MouseEvent('click', { bubbles: true, cancelable: true })
    marker.dispatchEvent(event)

    expect(event.defaultPrevented).toBe(false)
    expect(postMessage).not.toHaveBeenCalled()
    dispose?.()
  })

  it.each([
    ['普通 artifact', 'preview_artifact' as RuntimeArtifactKind, ARTIFACT_ID, 1, EDITOR_REFERRER],
    ['artifact 身份不一致', 'page_visual_edit_preview' as RuntimeArtifactKind, 'other-artifact', 1, EDITOR_REFERRER],
    ['协议不一致', 'page_visual_edit_preview' as RuntimeArtifactKind, ARTIFACT_ID, 2, EDITOR_REFERRER],
    ['referrer 缺失', 'page_visual_edit_preview' as RuntimeArtifactKind, ARTIFACT_ID, 1, ''],
    ['referrer 非法', 'page_visual_edit_preview' as RuntimeArtifactKind, ARTIFACT_ID, 1, 'not-a-url'],
  ])('%s 时不应安装 click listener', (_caseName, artifactKind, contextArtifactId, protocolVersion, referrer) => {
    const fixture = buildFixture({ artifactKind, protocolVersion })
    const addEventListener = vi.spyOn(document, 'addEventListener')
    const dispose = registerPageVisualEditSelectionBridge({
      preloadedConfig: fixture.config,
      previewContext: { ...fixture.previewContext, artifactId: contextArtifactId },
      referrer,
      postMessageTarget: { postMessage: vi.fn() },
    })

    expect(addEventListener).not.toHaveBeenCalledWith('click', expect.any(Function), true)
    expect(dispose).toBeNull()
  })

  it('组件 fragment 未透传 marker 时不伪造 DOM 选择，并降级由 Editor 图层树选择', () => {
    const fixture = buildFixture()
    const postMessage = vi.fn()
    const fragmentChild = document.createElement('div')
    fragmentChild.textContent = '组件 fragment 渲染结果'
    document.body.appendChild(fragmentChild)
    const dispose = registerPageVisualEditSelectionBridge({
      preloadedConfig: fixture.config,
      previewContext: fixture.previewContext,
      referrer: EDITOR_REFERRER,
      postMessageTarget: { postMessage },
    })

    fragmentChild.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))

    expect(postMessage).not.toHaveBeenCalled()
    dispose?.()
  })

  it('应接收可信图层选区，并高亮循环节点的全部实例或指定实例', () => {
    const fixture = buildFixture()
    const first = document.createElement('article')
    const second = document.createElement('article')
    applyLoopMarkers(first, fixture.loop.nodeId, fixture.loop.nodeId, JSON.stringify('alpha'), '0')
    applyLoopMarkers(second, fixture.loop.nodeId, fixture.loop.nodeId, JSON.stringify(7), '1')
    document.body.append(first, second)
    const dispose = registerPageVisualEditSelectionBridge({
      preloadedConfig: fixture.config,
      previewContext: fixture.previewContext,
      referrer: EDITOR_REFERRER,
      postMessageTarget: { postMessage: vi.fn() },
    })

    dispatchSelectNode(fixture.loop.nodeId, [])
    expect(document.body.querySelectorAll('[aria-hidden="true"]')).toHaveLength(2)

    dispatchSelectNode(fixture.loop.nodeId, [{
      loopNodeId: fixture.loop.nodeId,
      key: 7,
      index: 1,
    }])
    expect(document.body.querySelectorAll('[aria-hidden="true"]')).toHaveLength(1)
    dispose?.()
  })

  it('悬停应使用独立轮廓，离开后清理悬停但保留已选中轮廓', () => {
    const fixture = buildFixture()
    const postMessage = vi.fn()
    const selected = document.createElement('a')
    const hovered = document.createElement('a')
    selected.className = 'selected-canonical-class'
    hovered.className = 'hovered-canonical-class'
    hovered.style.color = 'red'
    applyLoopMarkers(selected, fixture.anchor.nodeId, fixture.loop.nodeId, JSON.stringify('alpha'), '0')
    applyLoopMarkers(hovered, fixture.anchor.nodeId, fixture.loop.nodeId, JSON.stringify(7), '1')
    document.body.append(selected, hovered)
    const dispose = registerPageVisualEditSelectionBridge({
      preloadedConfig: fixture.config,
      previewContext: fixture.previewContext,
      referrer: EDITOR_REFERRER,
      postMessageTarget: { postMessage },
    })

    selected.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    hovered.dispatchEvent(new MouseEvent('mouseover', { bubbles: true, relatedTarget: selected }))

    const selectionOverlay = document.body.querySelector<HTMLElement>('[data-page-visual-overlay="selection"]')
    const hoverOverlay = document.body.querySelector<HTMLElement>('[data-page-visual-overlay="hover"]')
    expect(selectionOverlay).not.toBeNull()
    expect(hoverOverlay).not.toBeNull()
    expect(selectionOverlay?.style.border).not.toBe(hoverOverlay?.style.border)
    expect(selectionOverlay?.style.pointerEvents).toBe('none')
    expect(hoverOverlay?.style.pointerEvents).toBe('none')
    expect(postMessage).toHaveBeenCalledTimes(1)
    expect(selected.className).toBe('selected-canonical-class')
    expect(hovered.className).toBe('hovered-canonical-class')
    expect(hovered.style.color).toBe('red')

    hovered.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: document.body }))

    expect(document.body.querySelector('[data-page-visual-overlay="hover"]')).toBeNull()
    expect(document.body.querySelector('[data-page-visual-overlay="selection"]')).not.toBeNull()
    dispose?.()
  })

  it('应拒绝来源不可信或 artifact 不匹配的主动选区消息', () => {
    const fixture = buildFixture()
    const marker = document.createElement('article')
    applyLoopMarkers(marker, fixture.loop.nodeId, fixture.loop.nodeId, JSON.stringify('alpha'), '0')
    document.body.appendChild(marker)
    const dispose = registerPageVisualEditSelectionBridge({
      preloadedConfig: fixture.config,
      previewContext: fixture.previewContext,
      referrer: EDITOR_REFERRER,
      postMessageTarget: { postMessage: vi.fn() },
    })

    window.dispatchEvent(new MessageEvent('message', {
      origin: 'https://evil.example.com',
      source: window,
      data: buildSelectNodeMessage(fixture.loop.nodeId, [], ARTIFACT_ID),
    }))
    window.dispatchEvent(new MessageEvent('message', {
      origin: 'https://editor.example.com',
      source: window,
      data: buildSelectNodeMessage(fixture.loop.nodeId, [], 'other-artifact'),
    }))
    expect(document.body.querySelector('[aria-hidden="true"]')).toBeNull()
    dispose?.()
  })
})

/** 从测试父窗口发送可信的图层节点选择消息。 */
function dispatchSelectNode(
  nodeId: string,
  instancePath: Array<{ loopNodeId: string; key: string | number; index?: number }>,
): void {
  window.dispatchEvent(new MessageEvent('message', {
    origin: 'https://editor.example.com',
    source: window,
    data: buildSelectNodeMessage(nodeId, instancePath, ARTIFACT_ID),
  }))
}

/** 构造 Editor -> Runtime 选区协议消息。 */
function buildSelectNodeMessage(
  nodeId: string,
  instancePath: Array<{ loopNodeId: string; key: string | number; index?: number }>,
  artifactId: string,
): unknown {
  return {
    type: 'page-visual-edit:select-node',
    payload: { protocolVersion: 1, artifactId, nodeId, instancePath },
  }
}

/**
 * 生成真实 Manifest 与最小 Runtime artifact/context，避免测试复制分析器节点 ID 规则。
 */
function buildFixture(options: {
  artifactKind?: RuntimeArtifactKind
  protocolVersion?: number
} = {}): {
  config: RuntimePreloadedConfigBundle
  previewContext: RuntimePreviewContext
  loop: VisualEditTemplateNode
  anchor: VisualEditTemplateNode
} {
  const manifest = analyzeVisualEditSfc(SOURCE, { modulePath: 'src/views/Selection.vue' })
  const loop = findNode(manifest, 'article')
  const anchor = findNode(manifest, 'a')
  const backendSerializedManifest = withBackendNullOptionals(manifest)
  const config: RuntimePreloadedConfigBundle = {
    manifest: {
      artifact_id: ARTIFACT_ID,
      artifact_kind: options.artifactKind || 'page_visual_edit_preview',
      tenant_id: 'tenant-1',
      preview_kind: 'page',
      owner_scope: {
        scope_type: 'project',
        workspace_id: 'workspace-1',
        project_id: 'project-1',
      },
      entry_descriptor: {
        entry_type: 'module',
        module_path: 'src/views/Selection.vue',
      },
      modules: {},
      assets: {},
      visual_edit: {
        protocol_version: (options.protocolVersion || 1) as 1,
        page_id: 'page-1',
        base_version_no: 1,
        source_hash: manifest.sourceHash,
        module_path: manifest.modulePath,
        manifest: backendSerializedManifest,
      },
    },
  }
  return {
    config,
    previewContext: {
      artifactId: ARTIFACT_ID,
      tenantId: 'tenant-1',
      previewKind: 'page',
      scopeType: 'project',
      workspaceId: 'workspace-1',
      projectId: 'project-1',
      entryDescriptor: {
        entry_type: 'module',
        module_path: 'src/views/Selection.vue',
      },
      assetBaseUrl: '/api/runtime-preview/artifacts/assets',
      traceId: 'trace-1',
    },
    loop,
    anchor,
  }
}

/**
 * 模拟 Backend model_dump：没有循环的节点会显式携带 loopContext: null。
 */
function withBackendNullOptionals(manifest: VisualEditSfcManifest): unknown {
  const serialized = JSON.parse(JSON.stringify(manifest)) as Record<string, unknown>
  const appendNullLoopContext = (rawNode: unknown): void => {
    if (!rawNode || typeof rawNode !== 'object' || Array.isArray(rawNode)) {
      return
    }
    const node = rawNode as Record<string, unknown>
    if (!Object.prototype.hasOwnProperty.call(node, 'loopContext')) {
      node.loopContext = null
    }
    if (Array.isArray(node.children)) {
      node.children.forEach(appendNullLoopContext)
    }
  }
  appendNullLoopContext(serialized.root)
  return serialized
}

/**
 * 为测试元素写入与 Runtime 插桩一致的单层实例 marker。
 */
function applyLoopMarkers(
  element: Element,
  nodeId: string,
  loopNodeId: string,
  rawKey: string,
  rawIndex?: string,
): void {
  element.setAttribute(VISUAL_EDIT_NODE_ATTRIBUTE, nodeId)
  element.setAttribute(VISUAL_EDIT_LOOP_ATTRIBUTE, loopNodeId)
  element.setAttribute(VISUAL_EDIT_LOOP_KEY_ATTRIBUTE, rawKey)
  if (rawIndex !== undefined) {
    element.setAttribute(VISUAL_EDIT_LOOP_INDEX_ATTRIBUTE, rawIndex)
  }
}

/**
 * 查找测试所需的模板节点。
 */
function findNode(manifest: VisualEditSfcManifest, tag: string): VisualEditTemplateNode {
  const visit = (node: VisualEditTemplateNode): VisualEditTemplateNode | undefined => {
    if (node.tag === tag) {
      return node
    }
    return node.children.map(visit).find(Boolean)
  }
  const node = visit(manifest.root)
  if (!node) {
    throw new Error(`测试 Manifest 缺少 ${tag} 节点。`)
  }
  return node
}
