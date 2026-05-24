/**
 * 文件功能：验证组件预览工作台会按来源调用工作空间组件或 Runtime Kit 的预览 API。
 */
import { defineComponent, h, nextTick } from 'vue'
import { fireEvent, render, waitFor } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ComponentPreviewWorkbench from '@/components/component-preview/ComponentPreviewWorkbench.vue'
import type { ComponentPreviewWorkbenchSource } from '@/components/component-preview/component-preview-workbench'
import type { ComponentPreviewOptions, RuntimeKitComponentCapabilityItem } from '@/types/api'

type WorkspacePreviewWorkbenchSource = Extract<ComponentPreviewWorkbenchSource, { kind: 'workspace-draft' }>

const getWorkspaceMock = vi.fn()
const createComponentPreviewArtifactFromSourceMock = vi.fn()
const createRuntimeKitComponentPreviewArtifactMock = vi.fn()

vi.mock('@/api/catalog', () => ({
  getWorkspace: (...args: unknown[]) => getWorkspaceMock(...args),
}))

vi.mock('@/api/preview', () => ({
  createComponentPreviewArtifactFromSource: (...args: unknown[]) => createComponentPreviewArtifactFromSourceMock(...args),
}))

vi.mock('@/api/runtime-kit', () => ({
  createRuntimeKitComponentPreviewArtifact: (...args: unknown[]) => createRuntimeKitComponentPreviewArtifactMock(...args),
}))

const runtimeKitItem: RuntimeKitComponentCapabilityItem = {
  kind: 'component',
  base_name: 'AssetImage',
  version_no: 1,
  name: 'AssetImage.v1',
  import_path: '@runtime-kit/public/components/assets/AssetImage.v1.vue',
  category: 'asset',
  description: '按资源逻辑名渲染图片。',
  display_name: '图片资源渲染',
  summary: '渲染 render_type=image 的工作空间图片资源。',
  tags: ['image'],
  previewable: true,
  preview_schema: {
    props: {
      name: {
        type: 'string',
        label: '资源名',
        default: '',
      },
      fallback: {
        type: 'string',
        label: '兜底 URL',
        default: '',
      },
    },
  },
  preview_options: {
    page: {
      width: 1280,
      height: 720,
      base_font_size: '16px',
      icon_default_stroke_width: 2,
      theme_key: null,
      theme_config_yaml: null,
    },
    placement: {
      width_mode: 'percent',
      width_value: 80,
      height_mode: 'auto',
      height_value: null,
      horizontal_align: 'center',
      vertical_align: 'center',
      padding: 32,
    },
  },
  usage: [],
  returns: null,
  return_example: [],
  constraints: [],
  audiences: ['agent'],
  manifest_version: '1.0.0',
}

describe('ComponentPreviewWorkbench', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
    getWorkspaceMock.mockResolvedValue({ id: 11, default_theme_key: null })
    createComponentPreviewArtifactFromSourceMock.mockResolvedValue(createPreviewResponse())
    createRuntimeKitComponentPreviewArtifactMock.mockResolvedValue(createPreviewResponse())
  })

  it('workspace-draft 来源应调用源码预览 artifact API', async () => {
    const source: ComponentPreviewWorkbenchSource = {
      kind: 'workspace-draft',
      workspaceId: 11,
      componentId: 99,
      componentName: '销售卡片',
      content: '<template><div /></template>',
      previewSchema: '{"props":{}}',
      isDraftPreview: true,
    }

    renderWorkbench(source)

    await waitFor(() => {
      expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledWith(expect.objectContaining({
        workspace_id: 11,
        component_id: 99,
        component_name: '销售卡片',
        content: '<template><div /></template>',
        preview_schema: '{\n  "props": {}\n}',
      }))
    })
    expect(createRuntimeKitComponentPreviewArtifactMock).not.toHaveBeenCalled()
  })

  it('runtime-kit 来源应调用 Runtime Kit 预览 artifact API', async () => {
    const source: ComponentPreviewWorkbenchSource = {
      kind: 'runtime-kit',
      workspaceId: 11,
      item: runtimeKitItem,
    }

    renderWorkbench(source)

    await waitFor(() => {
      expect(createRuntimeKitComponentPreviewArtifactMock).toHaveBeenCalledWith('AssetImage.v1', expect.objectContaining({
        workspace_id: 11,
        preview_options: expect.objectContaining({
          page: expect.objectContaining({ width: 1280, height: 720 }),
        }),
      }))
    })
    expect(createComponentPreviewArtifactFromSourceMock).not.toHaveBeenCalled()
  })

  it('页面尺寸或主题变化应防抖自动重建预览 artifact', async () => {
    const { findByTitle, getByText } = renderWorkbench(createWorkspaceSource(), {
      ComponentPreviewReleaseToolbar: createReleaseToolbarUpdater(),
    })

    await waitFor(() => {
      expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledTimes(1)
    })
    await findByTitle('component-preview')

    vi.useFakeTimers()
    await fireEvent.click(getByText('更新页面'))
    await nextTick()
    expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(499)
    expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1)
    expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledTimes(2)
  })

  it('组件占位变化不应重建预览 artifact', async () => {
    const { findByTitle, getByText } = renderWorkbench(createWorkspaceSource(), {
      ComponentPreviewPlacementToolbar: createPlacementToolbarUpdater(),
    })

    await waitFor(() => {
      expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledTimes(1)
    })
    await findByTitle('component-preview')

    vi.useFakeTimers()
    await fireEvent.click(getByText('更新占位'))
    await nextTick()
    await vi.advanceTimersByTimeAsync(700)
    expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledTimes(1)
  })

  it('整页模板默认预览留白应为 0', async () => {
    renderWorkbench({
      ...createWorkspaceSource(),
      componentType: '整页模板',
    })

    await waitFor(() => {
      expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledWith(expect.objectContaining({
        preview_options: expect.objectContaining({
          placement: expect.objectContaining({ padding: 0 }),
        }),
      }))
    })
  })

  it('布局容器默认预览留白应为 0', async () => {
    renderWorkbench({
      ...createWorkspaceSource(),
      componentType: '布局容器',
    })

    await waitFor(() => {
      expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledWith(expect.objectContaining({
        preview_options: expect.objectContaining({
          placement: expect.objectContaining({ padding: 0 }),
        }),
      }))
    })
  })

  it('普通内容区块默认预览应保留常规边距', async () => {
    renderWorkbench({
      ...createWorkspaceSource(),
      componentType: '内容区块',
    })

    await waitFor(() => {
      expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledWith(expect.objectContaining({
        preview_options: expect.objectContaining({
          placement: expect.not.objectContaining({ padding: 0 }),
        }),
      }))
    })
  })

  it('简化态应隐藏占位工具条并保留完整态入口', async () => {
    const { queryByText, getByTitle } = renderWorkbench(createWorkspaceSource(), {}, { simplified: true })

    await waitFor(() => {
      expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledTimes(1)
    })

    expect(queryByText('placement')).not.toBeInTheDocument()
    expect(getByTitle('弹窗预览')).toBeInTheDocument()
  })

  it('完整预览弹窗应保留组件操作入口', async () => {
    const { getByTitle, getAllByRole } = render(ComponentPreviewWorkbench, {
      props: {
        source: createWorkspaceSource(),
        simplified: true,
      },
      slots: {
        'component-actions': () => h('button', { type: 'button' }, '编辑组件'),
      },
      global: {
        stubs: {
          ComponentPreviewParameterDock: true,
          ComponentPreviewPlacementToolbar: true,
          ComponentPreviewReleaseToolbar: true,
        },
      },
    })

    await waitFor(() => {
      expect(createComponentPreviewArtifactFromSourceMock).toHaveBeenCalledTimes(1)
    })
    expect(getAllByRole('button', { name: '编辑组件' })).toHaveLength(1)

    await fireEvent.click(getByTitle('弹窗预览'))

    await waitFor(() => {
      expect(getAllByRole('button', { name: '编辑组件' })).toHaveLength(2)
    })
  })
})

function renderWorkbench(
  source: ComponentPreviewWorkbenchSource,
  stubs: Record<string, unknown> = {},
  props: { simplified?: boolean } = {},
) {
  return render(ComponentPreviewWorkbench, {
    props: {
      source,
      ...props,
    },
    global: {
      stubs: {
        ComponentPreviewParameterDock: true,
        ComponentPreviewPlacementToolbar: stubs.ComponentPreviewPlacementToolbar || defineComponent({
          name: 'ComponentPreviewPlacementToolbar',
          setup() {
            return () => h('div', 'placement')
          },
        }),
        ComponentPreviewReleaseToolbar: stubs.ComponentPreviewReleaseToolbar || defineComponent({
          name: 'ComponentPreviewReleaseToolbar',
          setup() {
            return () => h('div', 'release')
          },
        }),
      },
    },
  })
}

function createWorkspaceSource(): WorkspacePreviewWorkbenchSource {
  return {
    kind: 'workspace-draft',
    workspaceId: 11,
    componentId: 99,
    componentName: '销售卡片',
    content: '<template><div /></template>',
    previewSchema: '{"props":{}}',
    isDraftPreview: true,
  }
}

function createReleaseToolbarUpdater() {
  return defineComponent({
    name: 'ComponentPreviewReleaseToolbar',
    props: {
      modelValue: {
        type: Object,
        required: true,
      },
    },
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      return () => h('button', {
        type: 'button',
        onClick: () => {
          const nextOptions = cloneOptions(props.modelValue as ComponentPreviewOptions)
          nextOptions.page.width += 10
          emit('update:modelValue', nextOptions)
        },
      }, '更新页面')
    },
  })
}

function createPlacementToolbarUpdater() {
  return defineComponent({
    name: 'ComponentPreviewPlacementToolbar',
    props: {
      modelValue: {
        type: Object,
        required: true,
      },
    },
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      return () => h('button', {
        type: 'button',
        onClick: () => {
          const nextOptions = cloneOptions(props.modelValue as ComponentPreviewOptions)
          nextOptions.placement.padding += 4
          emit('update:modelValue', nextOptions)
        },
      }, '更新占位')
    },
  })
}

function cloneOptions(value: ComponentPreviewOptions): ComponentPreviewOptions {
  return JSON.parse(JSON.stringify(value)) as ComponentPreviewOptions
}

function createPreviewResponse() {
  return {
    preview_url: 'http://localhost/preview/component',
    artifact_id: 'artifact-1',
    preview_kind: 'component',
    entry_descriptor: {
      entry_type: 'component_host',
    },
    viewport_width: 1920,
    viewport_height: 1080,
  }
}
