// @vitest-environment jsdom

/**
 * 文件用途：验证 DataTable 使用 CSS Grid 渲染，并按表格样式层合并行、列和单元格样式。
 */

import { createApp, type App } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import DataTable, { type RuntimeTableStyleLayers } from './DataTable.v1.vue'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('DataTable', () => {
  it('应使用 div 和统一 cell role 渲染，不输出 HTML table', () => {
    const { app, host } = mountDataTable({
      rows: [
        ['区域', '收入'],
        ['华东', '128 万'],
      ],
      class: 'w-full h-72 text-sm rounded-lg overflow-hidden',
    })

    const root = host.querySelector('[data-runtime-kit-table="v1"]') as HTMLElement
    const cells = Array.from(host.querySelectorAll('[data-runtime-kit-table-cell="v1"]'))

    expect(host.querySelector('table')).toBeNull()
    expect(root.getAttribute('role')).toBe('table')
    expect(root.getAttribute('aria-rowcount')).toBe('2')
    expect(root.getAttribute('aria-colcount')).toBe('2')
    expect(root.classList.contains('h-72')).toBe(true)
    expect(cells).toHaveLength(4)
    expect(cells.map(cell => cell.getAttribute('role'))).toEqual(['cell', 'cell', 'cell', 'cell'])

    app.unmount()
  })

  it('默认宽高应填满父容器', () => {
    const { app, host } = mountDataTable({
      rows: [
        ['维度', 'Q1'],
        ['收入', '100'],
      ],
    })

    const root = host.querySelector('[data-runtime-kit-table="v1"]') as HTMLElement

    expect(root.style.width).toBe('100%')
    expect(root.style.height).toBe('100%')

    app.unmount()
  })

  it('顶层 width 和 height 应支持 number 与 string 输入', () => {
    const { app, host } = mountDataTable({
      rows: [
        ['指标', 'Q1'],
        ['收入', '128 万'],
      ],
      width: 320,
      height: '18rem',
    })

    const root = host.querySelector('[data-runtime-kit-table="v1"]') as HTMLElement

    expect(root.style.width).toBe('320px')
    expect(root.style.height).toBe('18rem')

    app.unmount()
  })

  it('顶层 width 和 height 应优先于透传 style 中的同名字段', () => {
    const { app, host } = mountDataTable({
      rows: [
        ['指标', 'Q1'],
        ['收入', '128 万'],
      ],
      width: 320,
      height: 240,
      style: {
        width: '999px',
        height: '999px',
        backgroundColor: 'rgb(240, 249, 255)',
      },
    })

    const root = host.querySelector('[data-runtime-kit-table="v1"]') as HTMLElement

    expect(root.style.width).toBe('320px')
    expect(root.style.height).toBe('240px')
    expect(root.style.backgroundColor).toBe('rgb(240, 249, 255)')

    app.unmount()
  })

  it('应按 cell、列、行、单元格对象、显式单元格样式的顺序覆盖', () => {
    const styles: RuntimeTableStyleLayers = {
      cell: {
        class: 'text-sm bg-white font-normal',
        style: { color: '#111111' },
        border: { color: '#e2e8f0', width: 1, style: 'solid' },
      },
      columns: {
        1: {
          class: 'text-right bg-blue-50',
          width: 160,
          style: { color: '#222222' },
        },
      },
      rows: {
        0: {
          class: 'font-semibold bg-slate-100',
          height: 48,
          style: { color: '#333333' },
        },
      },
      cells: {
        '0,1': {
          class: 'bg-green-50 text-xs',
          style: { color: '#00aa00' },
          border: { color: '#111111', width: 3, style: 'dashed' },
        },
      },
    }
    const { app, host } = mountDataTable({
      rows: [
        ['指标', { text: '收入', class: 'bg-red-50 text-lg', style: { color: '#ff0000' } }],
        ['Q2', '128 万'],
      ],
      styles,
    })

    const root = host.querySelector('[data-runtime-kit-table="v1"]') as HTMLElement
    const target = host.querySelector('[data-row-index="0"][data-column-index="1"]') as HTMLElement

    expect(root.style.gridTemplateColumns).toBe('minmax(0, 1fr) 160px')
    expect(root.style.gridTemplateRows).toBe('48px minmax(0, 1fr)')
    expect(target.classList.contains('font-semibold')).toBe(true)
    expect(target.classList.contains('text-right')).toBe(true)
    expect(target.classList.contains('bg-green-50')).toBe(true)
    expect(target.classList.contains('bg-red-50')).toBe(false)
    expect(target.classList.contains('bg-blue-50')).toBe(false)
    expect(target.classList.contains('bg-slate-100')).toBe(false)
    expect(target.classList.contains('text-xs')).toBe(true)
    expect(target.classList.contains('text-lg')).toBe(false)
    expect(target.style.color).toBe('rgb(0, 170, 0)')
    expect(target.style.borderTop).toBe('3px dashed rgb(17, 17, 17)')
    expect(target.style.borderRight).toBe('3px dashed rgb(17, 17, 17)')
    expect(target.style.borderBottom).toBe('3px dashed rgb(17, 17, 17)')
    expect(target.style.borderLeft).toBe('3px dashed rgb(17, 17, 17)')

    app.unmount()
  })

  it('显式行列样式应独立于语义配置存在', () => {
    const { app, host } = mountDataTable({
      rows: [
        ['维度', 'Q1'],
        ['收入', '100'],
      ],
      styles: {
        rows: {
          0: {
            class: 'font-semibold',
          },
        },
        columns: {
          0: {
            class: 'text-primary',
          },
        },
      },
    })

    const topLeft = host.querySelector('[data-row-index="0"][data-column-index="0"]') as HTMLElement
    const firstColumnBody = host.querySelector('[data-row-index="1"][data-column-index="0"]') as HTMLElement

    expect(topLeft.getAttribute('role')).toBe('cell')
    expect(firstColumnBody.getAttribute('role')).toBe('cell')
    expect(topLeft.className).toContain('font-semibold')
    expect(firstColumnBody.className).toContain('text-primary')

    app.unmount()
  })

  it('应支持全表无边框', () => {
    const { app, host } = mountDataTable({
      rows: [
        ['A', 'B'],
        ['C', 'D'],
      ],
      styles: {
        table: {
          border: { style: 'none' },
        },
      },
    })

    const cells = Array.from(host.querySelectorAll('[data-runtime-kit-table-cell="v1"]')) as HTMLElement[]

    cells.forEach(cell => {
      expect(cell.style.borderTopStyle).toBe('none')
      expect(cell.style.borderRightStyle).toBe('none')
      expect(cell.style.borderBottomStyle).toBe('none')
      expect(cell.style.borderLeftStyle).toBe('none')
    })

    app.unmount()
  })

  it('单元格级 outer 应以当前单元格自身作为区域', () => {
    const { app, host } = mountDataTable({
      rows: [
        ['A', 'B'],
        ['C', 'D'],
      ],
      styles: {
        table: {
          border: { style: 'none' },
        },
        cells: {
          '1,1': {
            border: {
              outer: { color: '#7c3aed', width: 2, style: 'dotted' },
            },
          },
        },
      },
    })

    const target = host.querySelector('[data-row-index="1"][data-column-index="1"]') as HTMLElement
    const neighbor = host.querySelector('[data-row-index="1"][data-column-index="0"]') as HTMLElement

    expect(target.style.borderTop).toBe('2px dotted rgb(124, 58, 237)')
    expect(target.style.borderRight).toBe('2px dotted rgb(124, 58, 237)')
    expect(target.style.borderBottom).toBe('2px dotted rgb(124, 58, 237)')
    expect(target.style.borderLeft).toBe('2px dotted rgb(124, 58, 237)')
    expect(neighbor.style.borderRightStyle).toBe('none')

    app.unmount()
  })

  it('应支持整个表格的外框和内部边框', () => {
    const { app, host } = mountDataTable({
      rows: [
        ['A', 'B'],
        ['C', 'D'],
      ],
      styles: {
        table: {
          border: {
            outer: { color: '#111111', width: 3, style: 'solid' },
            inner: { color: '#888888', width: 1, style: 'dashed' },
          },
        },
      },
    })

    const topLeft = host.querySelector('[data-row-index="0"][data-column-index="0"]') as HTMLElement
    const topRight = host.querySelector('[data-row-index="0"][data-column-index="1"]') as HTMLElement
    const bottomLeft = host.querySelector('[data-row-index="1"][data-column-index="0"]') as HTMLElement
    const bottomRight = host.querySelector('[data-row-index="1"][data-column-index="1"]') as HTMLElement

    expect(topLeft.style.borderTop).toBe('3px solid rgb(17, 17, 17)')
    expect(topLeft.style.borderLeft).toBe('3px solid rgb(17, 17, 17)')
    expect(topLeft.style.borderRight).toBe('1px dashed rgb(136, 136, 136)')
    expect(topLeft.style.borderBottom).toBe('1px dashed rgb(136, 136, 136)')
    expect(topRight.style.borderRight).toBe('3px solid rgb(17, 17, 17)')
    expect(bottomLeft.style.borderBottom).toBe('3px solid rgb(17, 17, 17)')
    expect(bottomRight.style.borderRight).toBe('3px solid rgb(17, 17, 17)')
    expect(bottomRight.style.borderBottom).toBe('3px solid rgb(17, 17, 17)')

    app.unmount()
  })

  it('应支持行、列和单元格的区域边框覆盖', () => {
    const styles: RuntimeTableStyleLayers = {
      table: {
        border: {
          all: 'none',
          outer: { color: '#222222', width: 1, style: 'solid' },
        },
      },
      rows: {
        1: {
          border: {
            top: { color: '#0f766e', width: 2, style: 'solid' },
            bottom: { color: '#0f766e', width: 2, style: 'solid' },
            innerVertical: { color: '#0f766e', width: 1, style: 'dotted' },
          },
        },
      },
      columns: {
        2: {
          border: {
            outer: { color: '#2563eb', width: 2, style: 'dashed' },
            innerHorizontal: { color: '#2563eb', width: 1, style: 'solid' },
          },
        },
      },
      cells: {
        '1,2': {
          border: {
            left: { color: '#dc2626', width: 4, style: 'solid' },
            right: 'none',
          },
        },
      },
    }
    const { app, host } = mountDataTable({
      rows: [
        ['A', 'B', 'C'],
        ['D', 'E', 'F'],
        ['G', 'H', 'I'],
      ],
      styles,
    })

    const rowCell = host.querySelector('[data-row-index="1"][data-column-index="1"]') as HTMLElement
    const columnTop = host.querySelector('[data-row-index="0"][data-column-index="2"]') as HTMLElement
    const target = host.querySelector('[data-row-index="1"][data-column-index="2"]') as HTMLElement

    expect(rowCell.style.borderTop).toBe('2px solid rgb(15, 118, 110)')
    expect(rowCell.style.borderBottom).toBe('2px solid rgb(15, 118, 110)')
    expect(rowCell.style.borderRight).toBe('1px dotted rgb(15, 118, 110)')
    expect(columnTop.style.borderLeft).toBe('2px dashed rgb(37, 99, 235)')
    expect(columnTop.style.borderRight).toBe('2px dashed rgb(37, 99, 235)')
    expect(columnTop.style.borderBottom).toBe('1px solid rgb(37, 99, 235)')
    expect(target.style.borderLeft).toBe('4px solid rgb(220, 38, 38)')
    expect(target.style.borderRightStyle).toBe('none')

    app.unmount()
  })
})

/**
 * 挂载 DataTable 测试实例。
 * @param props 组件 props
 */
function mountDataTable(props: Record<string, unknown>): { app: App<Element>, host: HTMLElement } {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const app = createApp(DataTable, props)
  app.mount(host)
  return { app, host }
}
