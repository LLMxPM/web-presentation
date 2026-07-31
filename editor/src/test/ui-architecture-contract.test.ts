/**
 * 文件功能：约束 Editor UI 设计系统的公开边界、生产路由和最低可访问性要求。
 */
import { render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import * as patterns from '@/components/patterns'
import * as primitives from '@/components/ui'

import {
  collectUiMigrationStats,
  getNakedControlViolations,
  getRetiredUiPrimitiveReferences,
  getEditorSourceFiles,
  getLegacyGlobalClassDefinitions,
  readEditorFile,
  type UiMigrationBaseline,
} from './ui-architecture-audit'

/** 迁移完成后的精确统计；新增或删除豁免均需显式评审。 */
const UI_MIGRATION_BASELINE: UiMigrationBaseline = {
  legacyClassReferences: 0,
  nakedButtons: 15,
  nakedInputs: 26,
  nakedTextareas: 2,
  nakedSelects: 0,
}

describe('UI 架构边界', () => {
  it('Reka UI 只能由 components/ui 直接依赖', () => {
    const violations = getEditorSourceFiles()
      .filter(sourceFile => /(?:from\s*|import\s*\()["']reka-ui["']/.test(sourceFile.content))
      .filter(sourceFile => !sourceFile.relativePath.startsWith('components/ui/'))
      .map(sourceFile => sourceFile.relativePath)

    expect(violations).toEqual([])
  })

  it('生产路由仅在开发环境注册 UI Lab', () => {
    const routerSource = readEditorFile('src/router/index.ts')
    const developmentRoutesStart = routerSource.indexOf('const developmentRoutes = import.meta.env.DEV')
    const uiLabRouteStart = routerSource.indexOf("path: '/ui-lab'")
    const routesStart = routerSource.indexOf('const routes = [')

    expect(developmentRoutesStart).toBeGreaterThanOrEqual(0)
    expect(uiLabRouteStart).toBeGreaterThan(developmentRoutesStart)
    expect(uiLabRouteStart).toBeLessThan(routesStart)
    expect(routerSource).toContain('...developmentRoutes')
  })

  it('全局样式不得重新引入 1280px 的最小宽度裁切', () => {
    const violations = getEditorSourceFiles()
      .filter(sourceFile => /min-width\s*:\s*1280(?:\.0+)?px\b/i.test(sourceFile.content))
      .map(sourceFile => sourceFile.relativePath)

    expect(violations).toEqual([])
  })

  it('不得重新定义 .btn、.input 或 .card 旧全局类', () => {
    expect(getLegacyGlobalClassDefinitions()).toEqual([])
  })

  it('已退役 UI Primitive 不得在 Editor 源码、测试或脚本模板中出现', () => {
    expect(getRetiredUiPrimitiveReferences()).toEqual([])
  })

  it('Design Token 与 Pattern 必须保留稳定公开入口', () => {
    const styleSource = readEditorFile('src/style.css')
    const tailwindSource = readEditorFile('tailwind.config.js')

    for (const token of [
      '--ui-canvas',
      '--ui-surface',
      '--ui-text',
      '--ui-border',
      '--ui-accent',
      '--ui-control-h-md',
      '--ui-radius-md',
      '--ui-z-dialog',
      '--ui-z-confirm-overlay',
      '--ui-z-toast',
    ]) {
      expect(styleSource).toContain(token)
    }
    expect(tailwindSource).toContain("canvas: 'rgb(var(--ui-canvas) / <alpha-value>)'")
    expect(patterns).toMatchObject({
      CommandBar: expect.anything(),
      PageHeader: expect.anything(),
      SplitPane: expect.anything(),
      ToolPanel: expect.anything(),
    })
  })

  it('业务区裸控件仅允许已审核的路径与语义白名单', () => {
    expect(getNakedControlViolations()).toEqual([])
  })

  it('新裸业务控件会报告文件路径与行号', () => {
    const violations = getNakedControlViolations([
      ...getEditorSourceFiles(),
      { relativePath: 'views/NewBusinessView.vue', content: '<template>\n<button type="button">新增</button>\n</template>' },
    ])

    expect(violations).toContain('views/NewBusinessView.vue:2:<button> 不在原生控件白名单内')
  })

  it('旧类和原生控件数量必须匹配最终精确基线', () => {
    const stats = collectUiMigrationStats()

    expect(stats).toEqual(UI_MIGRATION_BASELINE)
  })
})

describe('UI Primitive 最低可访问性契约', () => {
  it('图标按钮必须将 label 传递为可访问名称', () => {
    render(primitives.UiIconButton, { props: { label: '关闭面板' }, slots: { default: '<span aria-hidden="true">×</span>' } })

    expect(screen.getByRole('button', { name: '关闭面板' })).toHaveAttribute('aria-label', '关闭面板')
  })

  it('加载中的按钮必须禁用重复操作并声明忙碌状态', () => {
    render(primitives.UiButton, { props: { loading: true }, slots: { default: '保存更改' } })

    const button = screen.getByRole('button', { name: '保存更改' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
  })
})
