/** 文件功能：验证组件 previewSchema 仅采用精确 PascalCase 或确定 kebab-case 本地名匹配。 */

import { describe, expect, it } from 'vitest'

import {
  resolvePageVisualEditComponentPropField,
  resolvePageVisualEditComponentSchema,
} from '@/utils/page-visual-edit'
import type { PageVisualEditComponentSchema, PageVisualEditNode } from '@/types/page-visual-edit'

const schema: PageVisualEditComponentSchema = {
  source: 'workspace_component',
  import_path: '@workspace-components/card/v/1',
  component_code: 'card',
  version_no: 1,
  props: null,
}

describe('resolvePageVisualEditComponentSchema', () => {
  it('支持精确 PascalCase 与标准 kebab-case，但不猜测 camelCase 或近似名称', () => {
    const schemas = { LocalCard: schema }

    expect(resolvePageVisualEditComponentSchema(createNode('LocalCard'), schemas)).toBe(schema)
    expect(resolvePageVisualEditComponentSchema(createNode('local-card'), schemas)).toBe(schema)
    expect(resolvePageVisualEditComponentSchema(createNode('localCard'), schemas)).toBeNull()
    expect(resolvePageVisualEditComponentSchema(createNode('localCard'), { localCard: schema })).toBeNull()
    expect(resolvePageVisualEditComponentSchema(createNode('local-card-extra'), schemas)).toBeNull()
  })

  it('prop 应精确优先，并只支持标准 kebab-case 到 camelCase', () => {
    const exactField = { type: 'string' as const, label: '精确' }
    const camelField = { type: 'boolean' as const, label: '驼峰' }
    const componentSchema: PageVisualEditComponentSchema = {
      ...schema,
      props: {
        'show-fallback': exactField,
        showFallback: camelField,
      },
    }

    expect(resolvePageVisualEditComponentPropField(componentSchema, 'show-fallback')).toBe(exactField)
    expect(resolvePageVisualEditComponentPropField({
      ...componentSchema,
      props: { showFallback: camelField },
    }, 'show-fallback')).toBe(camelField)
    expect(resolvePageVisualEditComponentPropField(componentSchema, 'Show-fallback')).toBeNull()
  })
})

/** 创建只含组件身份的测试节点。 */
function createNode(tag: string): PageVisualEditNode {
  return {
    node_id: `node-${tag}`,
    kind: 'component',
    tag,
    source_range: { start: 0, end: 10 },
    bindings: [],
    children: [],
  }
}
