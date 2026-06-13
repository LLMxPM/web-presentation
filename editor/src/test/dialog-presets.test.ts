/**
 * 文件功能：验证代表性业务弹窗已经收口到统一的 BaseDialog 规格。
 */
import { render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ComponentPreviewDialog from '@/components/component-preview/ComponentPreviewDialog.vue'
import PageVersionHistoryDialog from '@/components/page-detail/PageVersionHistoryDialog.vue'
import ProjectBuildDialog from '@/components/project/ProjectBuildDialog.vue'
import SuggestedComponentsDialog from '@/components/project/SuggestedComponentsDialog.vue'
import FontEditorDialog from '@/components/theme/FontEditorDialog.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('dialog presets', () => {
  it('小型表单弹窗应使用 compact + auto', () => {
    render(FontEditorDialog, {
      props: {
        modelValue: true,
        editingFont: null,
        fontAssets: [],
      },
    })

    const shell = document.body.querySelector('[data-dialog-size="compact"]')
    expect(shell).toHaveAttribute('data-dialog-body-preset', 'auto')
    expect(screen.getByText('注册字体')).toBeInTheDocument()
  })

  it('中型选择弹窗应使用 wide + dense', () => {
    render(SuggestedComponentsDialog, {
      props: {
        modelValue: true,
        workspaceId: null,
        targetId: null,
        title: '建议组件',
        unavailableText: '当前对象不可配置',
        loadSuggestedComponents: vi.fn(),
        updateSuggestedComponents: vi.fn(),
        loadErrorMessage: '加载失败',
        saveErrorMessage: '保存失败',
        successMessage: '保存成功',
      },
      global: {
        stubs: {
          SuggestedComponentsSelectorPanel: {
            template: '<div data-testid="suggested-components-selector-panel" />',
          },
        },
      },
    })

    const shell = document.body.querySelector('[data-dialog-size="wide"]')
    expect(shell).toHaveAttribute('data-dialog-body-preset', 'dense')
    expect(screen.getByText('当前对象不可配置')).toBeInTheDocument()
  })

  it('大型配置弹窗应使用 canvas + editor', () => {
    render(ProjectBuildDialog, {
      props: {
        modelValue: true,
        workspaceId: null,
      },
      global: {
        stubs: {
          ProjectBuildSettingsPanel: {
            template: '<div data-testid="project-build-settings-panel" />',
          },
          ProjectBuildResourceIssuePanel: {
            template: '<div data-testid="project-build-resource-issue-panel" />',
          },
          ProjectBuildExtraAssetsPanel: {
            template: '<div data-testid="project-build-extra-assets-panel" />',
          },
          ProjectBuildHistoryPanel: {
            template: '<div data-testid="project-build-history-panel" />',
          },
        },
      },
    })

    const shell = document.body.querySelector('[data-dialog-size="canvas"]')
    expect(shell).toHaveAttribute('data-dialog-body-preset', 'editor')
    expect(screen.getByTestId('project-build-dialog')).toBeInTheDocument()
  })

  it('分栏详情弹窗应使用 canvas + split', () => {
    render(PageVersionHistoryDialog, {
      props: {
        modelValue: true,
        loading: false,
        versions: [],
        historyPanel: null,
        panelTitle: '历史预览',
        panelSubtitle: '无版本',
        currentContent: '',
        versionContentMap: {},
        historyPanelPreviewFrameUrl: '',
        editorLanguage: 'typescript',
        editorTheme: 'light',
        previewingRuntimeVersionNo: null,
        previewVersionPending: false,
        previewVersionNo: null,
        snapshotPending: false,
        pendingSnapshotVersionNo: null,
        restorePending: false,
        restoringVersionNo: null,
      },
      global: {
        stubs: {
          MonacoDiffViewer: {
            template: '<div data-testid="monaco-diff-viewer" />',
          },
          RuntimePreviewFrame: {
            template: '<div data-testid="runtime-preview-frame" />',
          },
        },
      },
    })

    const shell = document.body.querySelector('[data-dialog-size="canvas"]')
    expect(shell).toHaveAttribute('data-dialog-body-preset', 'split')
    expect(screen.getByText('当前页面还没有可展示的版本历史。')).toBeInTheDocument()
  })

  it('沉浸式预览弹窗应使用 workbench + immersive', () => {
    render(ComponentPreviewDialog, {
      props: {
        modelValue: true,
      },
      slots: {
        default: '<div>预览内容</div>',
      },
    })

    const shell = document.body.querySelector('[data-dialog-size="workbench"]')
    expect(shell).toHaveAttribute('data-dialog-body-preset', 'immersive')
    expect(screen.getByText('预览内容')).toBeInTheDocument()
  })
})
