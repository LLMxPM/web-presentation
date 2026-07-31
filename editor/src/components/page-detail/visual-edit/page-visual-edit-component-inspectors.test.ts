/**
 * 文件功能：验证专用组件检查器只按可信 component schema 身份精确匹配。
 */

import { describe, expect, it } from 'vitest'

import { resolvePageVisualEditComponentInspector } from './page-visual-edit-component-inspectors'
import type { PageVisualEditComponentSchema } from '@/types/page-visual-edit'

describe('resolvePageVisualEditComponentInspector', () => {
  it('只为 Runtime Kit AssetImage.v1 返回专用检查器', () => {
    expect(resolvePageVisualEditComponentInspector(createSchema({
      source: 'runtime_kit',
      component_code: 'AssetImage',
      version_no: 1,
    }))).toBe('asset-image-v1')
  })

  it.each([
    { source: 'workspace_component' as const, component_code: 'AssetImage', version_no: 1 },
    { source: 'runtime_kit' as const, component_code: 'AssetImage', version_no: 2 },
    { source: 'runtime_kit' as const, component_code: 'AssetVideo', version_no: 1 },
  ])('拒绝非目标 schema：$source/$component_code/v$version_no', (overrides) => {
    expect(resolvePageVisualEditComponentInspector(createSchema(overrides))).toBeNull()
  })
})

/** 构造最小组件 schema，便于逐项验证专用检查器边界。 */
function createSchema(
  overrides: Pick<PageVisualEditComponentSchema, 'source' | 'component_code' | 'version_no'>,
): PageVisualEditComponentSchema {
  return {
    ...overrides,
    import_path: '@runtime-kit/example.vue',
    props: {},
  }
}
