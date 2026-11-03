/**
 * 文件功能：验证开源与许可弹窗的许可入口、标签页分组、备注的 Tooltip 呈现方式与关闭交互。
 */
import { nextTick } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import OpenSourceInfoDialog from './OpenSourceInfoDialog.vue'
import { OPEN_SOURCE_GROUPS, PROJECT_LICENSES } from './open-source-notices'

describe('OpenSourceInfoDialog', () => {
  it('应展示项目双许可入口', () => {
    render(OpenSourceInfoDialog, { props: { open: true } })

    expect(screen.getByRole('heading', { name: '本项目许可' })).toBeTruthy()
    for (const entry of PROJECT_LICENSES) {
      expect(screen.getByRole('link', { name: new RegExp(entry.title) })).toHaveAttribute('href', entry.href)
    }
  })

  it('应按标签页分组展示依赖，且备注只通过 Tooltip 触发按钮暴露', async () => {
    render(OpenSourceInfoDialog, { props: { open: true } })

    for (const group of OPEN_SOURCE_GROUPS) {
      expect(screen.getByRole('tab', { name: group.title })).toBeTruthy()
    }
    expect(screen.getByText('Vue 3')).toBeTruthy()

    await fireEvent.mouseDown(screen.getByRole('tab', { name: '渲染与导出' }), { button: 0 })
    await nextTick()

    expect(screen.getByText('GSAP')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'GSAP 许可说明' })).toBeTruthy()
    // 备注不得以正文形式展开在列表中。
    expect(screen.queryByText(/不属于 OSI 定义的开源协议/)).toBeNull()
  })

  it('关闭按钮应请求收起弹窗', async () => {
    const view = render(OpenSourceInfoDialog, { props: { open: true } })

    await fireEvent.click(screen.getByRole('button', { name: '关闭' }))

    expect(view.emitted()['update:open']).toEqual([[false]])
  })

  it('非标开源协议的依赖必须提供备注内容', () => {
    const items = OPEN_SOURCE_GROUPS.flatMap(group => group.items)
    const nonStandard = items.filter(item => item.name === 'GSAP' || item.name === 'psycopg')

    expect(nonStandard).toHaveLength(2)
    for (const item of nonStandard) {
      expect(item.note?.length).toBeGreaterThan(0)
    }
  })
})
