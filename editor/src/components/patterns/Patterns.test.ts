/** 文件功能：验证通用页面、面板、筛选、选择、分割与数据状态模式的公共契约。 */
import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import CommandBar from './CommandBar.vue'
import DataState from './DataState.vue'
import FilterBar from './FilterBar.vue'
import InspectorSection from './InspectorSection.vue'
import PageHeader from './PageHeader.vue'
import PropertyRow from './PropertyRow.vue'
import SelectionToolbar from './SelectionToolbar.vue'
import SplitPane from './SplitPane.vue'
import ToolPanel from './ToolPanel.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('PageHeader 与 CommandBar', () => {
  it('应建立页面标题、说明和主要操作的稳定层级', () => {
    render(PageHeader, {
      props: { title: '组件库', description: '管理工作空间组件' },
      slots: { meta: '<span>12 项</span>', actions: '<button>新建组件</button>' },
    })

    expect(screen.getByRole('heading', { level: 1, name: '组件库' })).toBeVisible()
    expect(screen.getByText('管理工作空间组件')).toBeVisible()
    expect(screen.getByRole('button', { name: '新建组件' })).toBeVisible()
  })

  it('应为工具栏提供可访问名称和操作分区', () => {
    render(CommandBar, { props: { label: '组件操作' }, slots: { default: '<button>刷新</button>' } })
    expect(screen.getByRole('toolbar', { name: '组件操作' })).toContainElement(screen.getByRole('button', { name: '刷新' }))
  })
})

describe('FilterBar 与 ToolPanel', () => {
  it('应以表单事件上报筛选提交和重置', async () => {
    const onSubmit = vi.fn()
    const onReset = vi.fn()
    render(FilterBar, {
      props: { onSubmit, onReset },
      slots: { default: '<input aria-label="关键词" />', actions: '<button type="submit">查询</button><button type="reset">重置</button>' },
    })

    await fireEvent.click(screen.getByRole('button', { name: '查询' }))
    await fireEvent.click(screen.getByRole('button', { name: '重置' }))
    expect(onSubmit).toHaveBeenCalledOnce()
    expect(onReset).toHaveBeenCalledOnce()
  })

  it('应固定工具面板标题和工具栏，并让正文独立滚动', () => {
    render(ToolPanel, {
      props: { title: '资源库', description: '当前项目资源' },
      slots: { toolbar: '<button>上传</button>', default: '<p>资源列表</p>', footer: '<span>共 2 项</span>' },
    })

    expect(screen.getByRole('heading', { level: 2, name: '资源库' })).toBeVisible()
    expect(screen.getByRole('button', { name: '上传' })).toBeVisible()
    expect(screen.getByText('资源列表').parentElement).toHaveClass('overflow-auto')
    expect(screen.getByText('共 2 项')).toBeVisible()
  })
})

describe('InspectorSection 与 PropertyRow', () => {
  it('应支持受控折叠状态并暴露关联的内容区域', async () => {
    const onUpdate = vi.fn()
    render(InspectorSection, { props: { title: '排版', 'onUpdate:open': onUpdate }, slots: { default: '<p>字体大小</p>' } })
    const trigger = screen.getByRole('button', { name: /排版/ })

    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    await fireEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(onUpdate).toHaveBeenCalledWith(false)
  })

  it('应通过 forId 建立属性标签与控件的原生关联', () => {
    render(PropertyRow, { props: { label: '名称', forId: 'component-name', required: true, description: '用于引用' }, slots: { default: '<input id="component-name" />' } })
    expect(screen.getByLabelText('名称*')).toHaveAttribute('id', 'component-name')
    expect(screen.getByText('用于引用')).toBeVisible()
  })
})

describe('SelectionToolbar 与 SplitPane', () => {
  it('应显示选择数量并提供清除选择动作', async () => {
    const onClear = vi.fn()
    render(SelectionToolbar, { props: { count: 3, onClear }, slots: { default: '<button>删除</button>' } })
    expect(screen.getByRole('toolbar', { name: '批量操作' })).toHaveTextContent('已选择 3 项')
    await fireEvent.click(screen.getByRole('button', { name: '清除选择' }))
    expect(onClear).toHaveBeenCalledOnce()
  })

  it('应允许键盘在声明的范围内调整左右面板比例', async () => {
    const onUpdate = vi.fn()
    render(SplitPane, {
      props: { defaultSize: 30, minSize: 25, maxSize: 50, step: 10, 'onUpdate:modelValue': onUpdate },
      slots: { first: '<p>列表</p>', second: '<p>详情</p>' },
    })
    const separator = screen.getByRole('separator', { name: '调整面板大小' })
    await fireEvent.keyDown(separator, { key: 'ArrowRight' })
    await fireEvent.keyDown(separator, { key: 'End' })
    expect(onUpdate).toHaveBeenNthCalledWith(1, 40)
    expect(onUpdate).toHaveBeenNthCalledWith(2, 50)
    expect(separator).toHaveAttribute('aria-orientation', 'vertical')
  })
})

describe('DataState', () => {
  it('应在错误时提示并触发重试，在就绪时渲染业务内容', async () => {
    const onRetry = vi.fn()
    const view = render(DataState, { props: { state: 'error', onRetry }, slots: { default: '<p>列表</p>' } })
    expect(screen.getByRole('alert')).toHaveTextContent('加载失败')
    await fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledOnce()
    view.unmount()

    render(DataState, { props: { state: 'ready' }, slots: { default: '<p>列表</p>' } })
    expect(screen.getByText('列表')).toBeVisible()
  })
})
