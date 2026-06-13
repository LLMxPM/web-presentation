/**
 * 文件功能：验证基础弹窗的规格 preset、头部扩展与关闭行为。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { fireEvent, render, screen } from '@testing-library/vue'
import { afterEach, describe, expect, it } from 'vitest'

import BaseDialog from './BaseDialog.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('BaseDialog', () => {
  it('应渲染统一尺寸、内容区 preset 与头部扩展插槽', () => {
    render(BaseDialog, {
      props: {
        modelValue: true,
        title: '测试弹窗',
        description: '测试说明',
        size: 'workbench',
        bodyPreset: 'immersive',
      },
      slots: {
        default: '<div>弹窗内容</div>',
        footer: '<button type="button">保存</button>',
        'header-extra': '<button type="button">更多操作</button>',
      },
    })

    const shell = document.body.querySelector('[data-dialog-size="workbench"]')
    const body = document.body.querySelector('.dialog-body--immersive')

    expect(shell).toHaveAttribute('data-dialog-body-preset', 'immersive')
    expect(body).toBeInTheDocument()
    expect(screen.getByText('测试说明')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '更多操作' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '保存' })).toBeInTheDocument()
  })

  it('显式关闭头部时不应渲染标题栏', () => {
    render(BaseDialog, {
      props: {
        modelValue: true,
        title: '隐藏头部',
        showHeader: false,
      },
      slots: {
        default: '<div>仅保留内容</div>',
      },
    })

    expect(screen.queryByText('隐藏头部')).not.toBeInTheDocument()
    expect(screen.getByText('仅保留内容')).toBeInTheDocument()
  })

  it('应允许通过 panelStyle 强制覆盖面板外观', () => {
    render(BaseDialog, {
      props: {
        modelValue: true,
        title: '透明面板',
        panelStyle: {
          background: 'transparent',
        },
      },
      slots: {
        default: '<div>沉浸式内容</div>',
      },
    })

    const panel = document.body.querySelector('.dialog-panel')
    expect(panel).toHaveStyle({ background: 'transparent' })
  })

  it('应支持点击遮罩与按下 Esc 关闭弹窗', async () => {
    const overlayView = render(BaseDialog, {
      props: {
        modelValue: true,
        title: '遮罩关闭',
      },
      slots: {
        default: '<div>内容</div>',
      },
    })

    const overlay = document.body.querySelector('.dialog-shell > button')
    expect(overlay).toBeInstanceOf(HTMLButtonElement)
    await fireEvent.click(overlay as HTMLButtonElement)
    expect(overlayView.emitted()['update:modelValue']).toEqual([[false]])

    document.body.innerHTML = ''

    const keyboardView = render(BaseDialog, {
      props: {
        modelValue: true,
        title: '键盘关闭',
      },
      slots: {
        default: '<div>内容</div>',
      },
    })

    await fireEvent.keyDown(window, { key: 'Escape' })
    expect(keyboardView.emitted()['update:modelValue']).toEqual([[false]])
  })

  it('源码中应保留小屏笔记本的响应式压缩规则', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/components/ui/BaseDialog.vue'), 'utf-8')

    expect(source).toContain('--dialog-target-height')
    expect(source).toContain('@media (max-height: 820px)')
    expect(source).toContain('@media (max-width: 1024px)')
    expect(source).toContain('--dialog-shell-gap')
  })
})
