/**
 * 文件功能：验证组件库 import 语句生成规则。
 */
import { describe, expect, it } from 'vitest'

import {
  buildRuntimeKitComponentImportUsage,
  buildWorkspaceComponentImportUsage,
  toValidImportIdentifier,
} from '@/utils/component-import'

describe('component import helpers', () => {
  it('为已发布工作空间组件生成 import 语句', () => {
    const usage = buildWorkspaceComponentImportUsage({
      code: 'CMP20260503001',
      name: 'Sales Card',
      import_name: 'SalesMetricCard',
      current_version_no: 3,
    })

    expect(usage).toEqual({
      importPath: '@workspace-components/CMP20260503001/v/3',
      importStatement: "import SalesMetricCard from '@workspace-components/CMP20260503001/v/3'",
    })
  })

  it('中文组件名配合引用名时应使用引用名', () => {
    const usage = buildWorkspaceComponentImportUsage({
      code: 'CMP20260503001',
      name: '统计卡片',
      import_name: 'SalesStatsCard',
      current_version_no: 1,
    })

    expect(usage?.importStatement).toBe("import SalesStatsCard from '@workspace-components/CMP20260503001/v/1'")
  })

  it('未发布工作空间组件不生成 import 语句', () => {
    const usage = buildWorkspaceComponentImportUsage({
      code: 'CMP20260503001',
      name: 'Draft Card',
      import_name: 'DraftCard',
      current_version_no: 0,
    })

    expect(usage).toBeNull()
  })

  it('为 Runtime Kit 组件能力生成 import 语句', () => {
    const usage = buildRuntimeKitComponentImportUsage({
      kind: 'component',
      base_name: 'DefaultContainer',
      name: 'DefaultContainer.v1',
      display_name: '默认容器',
      import_path: '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue',
    })

    expect(usage).toEqual({
      importPath: '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue',
      importStatement: "import DefaultContainer from '@runtime-kit/public/components/page/layout/DefaultContainer.v1.vue'",
    })
  })

  it('Runtime Kit 非组件能力不生成默认 import 语句', () => {
    const usage = buildRuntimeKitComponentImportUsage({
      kind: 'util',
      base_name: 'formatDate',
      name: 'formatDate.v1',
      display_name: '日期格式化',
      import_path: '@runtime-kit/public/utils/format-date',
    })

    expect(usage).toBeNull()
  })

  it('数字开头的名称会加 Component 前缀', () => {
    expect(toValidImportIdentifier('2026 KPI card')).toBe('Component2026KPICard')
  })
})
