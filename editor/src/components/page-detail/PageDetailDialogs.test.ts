/**
 * 文件功能：验证页面详情弹窗收口到 UiDialog 后仍保留尺寸预设与 modelValue 关闭协议。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'

import PageScreenshotDialog from './PageScreenshotDialog.vue'
import PageSnapshotDialog from './PageSnapshotDialog.vue'
import PageUsageDialog from './PageUsageDialog.vue'
import PageVersionHistoryDialog from './PageVersionHistoryDialog.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('PageScreenshotDialog', () => {
  it('应使用 wide + editor 规格，并将关闭状态回传给 modelValue', async () => {
    const view = render(PageScreenshotDialog, {
      props: {
        modelValue: true,
        pageTitle: '封面',
        screenshotUrl: null,
        screenshotVersionNo: null,
        screenshotIsLatest: true,
        screenshotUpdatedAt: null,
        screenshotPending: false,
        screenshotDisabled: false,
      },
    })

    expect(document.body.querySelector('[data-dialog-size="wide"]')).toHaveAttribute('data-dialog-body-preset', 'editor')
    await fireEvent.click(screen.getByRole('button', { name: '关闭封面 · 页面截图' }))
    expect(view.emitted()['update:modelValue']).toEqual([[false]])
  })
})

describe('PageSnapshotDialog', () => {
  it('应使用 compact 规格，并保留取消关闭协议', async () => {
    const view = render(PageSnapshotDialog, {
      props: {
        modelValue: true,
        versionLabel: 'v3',
        snapshotName: '',
        loading: false,
      },
    })

    expect(document.body.querySelector('[data-dialog-size="compact"]')).toHaveAttribute('data-dialog-body-preset', 'auto')
    await fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(view.emitted()['update:modelValue']).toEqual([[false]])
  })
})

describe('PageVersionHistoryDialog', () => {
  it('应使用 canvas + split 规格，并将关闭状态回传给 modelValue', async () => {
    const view = render(PageVersionHistoryDialog, {
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
    })

    expect(document.body.querySelector('[data-dialog-size="canvas"]')).toHaveAttribute('data-dialog-body-preset', 'split')
    await fireEvent.click(screen.getByRole('button', { name: '关闭版本历史' }))
    expect(view.emitted()['update:modelValue']).toEqual([[false]])
  })
})

describe('PageUsageDialog', () => {
  it('应使用 wide + auto 规格，并将关闭状态回传给 modelValue', async () => {
    const view = render(PageUsageDialog, {
      props: {
        modelValue: true,
        componentIndexLoading: false,
        usedComponentNames: [],
        usedResourceItems: [],
      },
    })

    expect(document.body.querySelector('[data-dialog-size="wide"]')).toHaveAttribute('data-dialog-body-preset', 'auto')
    await fireEvent.click(screen.getByRole('button', { name: '关闭组件与资源' }))
    expect(view.emitted()['update:modelValue']).toEqual([[false]])
  })
})
