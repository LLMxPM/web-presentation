/**
 * 文件功能：验证高级页面结构树使用面向内容创作者的语义名称，并识别 Runtime Kit 图片组件。
 */

import { render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import PageVisualEditLayerTree from '@/components/page-detail/visual-edit/PageVisualEditLayerTree.vue'
import type {
  PageVisualEditBinding,
  PageVisualEditComponentSchema,
  PageVisualEditNode,
} from '@/types/page-visual-edit'

describe('PageVisualEditLayerTree', () => {
  it('标题、文本和布局节点不再把源码 tag 作为主标签', () => {
    render(PageVisualEditLayerTree, {
      props: {
        root: createRoot([
          createNode('heading', 'element', 'h1', [
            createBinding('heading-text', 'text', null, '天柱骄子月——面向全国师生的免票活动介绍'),
          ]),
          createNode('paragraph', 'element', 'p', [
            createBinding('paragraph-text', 'text', null, '全国师生免票'),
          ]),
          createNode('section', 'element', 'section'),
          createNode('container', 'element', 'div'),
        ]),
        selectedNodeId: '',
        componentSchemas: {},
      },
    })

    expect(screen.getByRole('button', { name: '标题：天柱骄子月——面向全国师生的免票活动…' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '文本：全国师生免票' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '区块' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '容器' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'h1' })).toBeNull()
    expect(screen.queryByTitle('源码标签：h1')).toBeNull()
  })

  it('通过组件 schema 将本地别名识别为图片并优先展示替代文本', () => {
    const componentSchemas: Record<string, PageVisualEditComponentSchema> = {
      LocalHero: {
        source: 'runtime_kit',
        import_path: '@runtime-kit/public/components/assets/AssetImage.v1.vue',
        component_code: 'AssetImage',
        version_no: 1,
      },
    }
    render(PageVisualEditLayerTree, {
      props: {
        root: createRoot([
          createNode('hero', 'component', 'LocalHero', [
            createBinding('hero-name', 'prop', 'name', 'product-hero'),
            createBinding('hero-alt', 'prop', 'alt', '产品主图'),
          ]),
        ]),
        selectedNodeId: '',
        componentSchemas,
      },
    })

    expect(screen.getByRole('button', { name: '图片：产品主图' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'LocalHero' })).toBeNull()
  })
})

/** 创建测试用 Manifest 根节点。 */
function createRoot(children: PageVisualEditNode[]): PageVisualEditNode {
  return createNode('root', 'root', 'template', [], children)
}

/** 创建带统一结构操作约束的测试节点。 */
function createNode(
  nodeId: string,
  kind: PageVisualEditNode['kind'],
  tag: string,
  bindings: PageVisualEditBinding[] = [],
  children: PageVisualEditNode[] = [],
): PageVisualEditNode {
  return {
    node_id: nodeId,
    kind,
    tag,
    source_range: { start: 0, end: 10 },
    template_actions: {
      can_duplicate: false,
      can_delete: false,
      readonly_reason: kind === 'root' ? 'STRUCTURE_ROOT_UNSUPPORTED' : undefined,
    },
    bindings,
    children,
  }
}

/** 创建可静态读取的绑定，供图层名称提取短内容。 */
function createBinding(
  bindingId: string,
  kind: PageVisualEditBinding['kind'],
  name: string | null,
  value: string,
): PageVisualEditBinding {
  return {
    binding_id: bindingId,
    node_id: bindingId.split('-')[0],
    kind,
    name,
    value_type: 'string',
    value,
    source_range: { start: 1, end: 2 },
    editable: true,
    source: { kind: 'template-literal' },
  }
}
