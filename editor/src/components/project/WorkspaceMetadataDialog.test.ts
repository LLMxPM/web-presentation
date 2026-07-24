/** 文件功能：验证工作空间元数据弹窗的回填、校验、提交与关闭行为。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'

import WorkspaceMetadataDialog from './WorkspaceMetadataDialog.vue'
import type { WorkspaceItem } from '@/types/api'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('WorkspaceMetadataDialog', () => {
  it('打开时应回填当前工作空间的名称与描述', () => {
    renderDialog({ workspace: createWorkspace() })

    expect(screen.getByLabelText(/工作空间名称/)).toHaveValue('产品演示')
    expect(screen.getByLabelText(/工作空间描述/)).toHaveValue('面向客户的演示内容')
  })

  it('名称为空时应显示必填错误且不提交', async () => {
    const view = renderDialog()

    await fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(screen.getByRole('alert')).toHaveTextContent('请输入工作空间名称')
    expect(view.emitted('submit')).toBeUndefined()
  })

  it('应提交修剪后的名称与可空描述', async () => {
    const view = renderDialog()

    await fireEvent.update(screen.getByLabelText(/工作空间名称/), '  新工作空间  ')
    await fireEvent.update(screen.getByLabelText(/工作空间描述/), '  新描述  ')
    await fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(view.emitted('submit')).toEqual([[
      { name: '新工作空间', description: '新描述' },
    ]])
  })

  it('加载中应禁用保存，取消应请求关闭弹窗', async () => {
    const view = renderDialog({ loading: true })

    expect(screen.getByRole('button', { name: '保存' })).toBeDisabled()
    await fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(view.emitted('update:modelValue')).toEqual([[false]])
  })
})

/** 构造满足接口约束的工作空间测试数据。 */
function createWorkspace(): WorkspaceItem {
  return {
    id: 1,
    code: 'WS_DEMO',
    name: '产品演示',
    description: '面向客户的演示内容',
    status: 'active',
    last_opened_at: null,
    default_theme_key: null,
    created_at: '2026-07-24T00:00:00Z',
    updated_at: '2026-07-24T00:00:00Z',
    created_by: 1,
    updated_by: 1,
  }
}

/** 渲染处于打开状态的弹窗，并允许覆盖默认输入。 */
function renderDialog(overrides: Partial<{
  workspace: WorkspaceItem | null
  loading: boolean
}> = {}) {
  return render(WorkspaceMetadataDialog, {
    props: {
      modelValue: true,
      workspace: null,
      loading: false,
      ...overrides,
    },
    global: {
      stubs: { teleport: true },
    },
  })
}
