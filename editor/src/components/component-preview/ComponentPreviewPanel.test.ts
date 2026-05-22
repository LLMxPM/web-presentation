/**
 * 文件功能：验证组件预览参数面板的横向模式与紧凑内容渲染。
 */
import { defineComponent, h } from 'vue'
import { render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import ComponentPreviewPanel from '@/components/component-preview/ComponentPreviewPanel.vue'
import {
  buildInitialComponentPreviewState,
  type ComponentPreviewSchema,
} from '@/types/component-preview'

describe('ComponentPreviewPanel', () => {
  it('横向模式 loading 状态应压缩为提示条', () => {
    renderPanel({
      loading: true,
      schema: null,
    })

    expect(screen.getByText('预览参数')).toBeInTheDocument()
    expect(screen.getByText('正在读取 previewSchema...')).toBeInTheDocument()
  })

  it('横向模式无 schema 时应展示静态预览提示', () => {
    renderPanel({
      loading: false,
      schema: null,
    })

    expect(screen.getByText('当前组件未导出 previewSchema，只能查看静态预览。')).toBeInTheDocument()
  })

  it('横向模式不应再把 presets 渲染为 tab', () => {
    const schema: ComponentPreviewSchema = {
      props: {
        title: {
          type: 'string',
          label: '标题',
          default: '示例标题',
        },
      },
      presets: [
        {
          key: 'default',
          label: '默认状态',
          props: {
            title: '默认标题',
          },
        },
      ],
    }

    renderPanel({
      loading: false,
      schema,
    })

    expect(screen.getByText('标题')).toBeInTheDocument()
    expect(screen.queryByText('Presets')).not.toBeInTheDocument()
    expect(screen.queryByText('默认状态')).not.toBeInTheDocument()
  })

  it('紧凑内容模式应只渲染当前 active panel', () => {
    const schema: ComponentPreviewSchema = {
      props: {
        title: {
          type: 'string',
          label: '标题',
          default: '示例标题',
        },
      },
      slots: {
        default: {
          label: '默认插槽',
          default: [],
        },
      },
    }

    renderPanel({
      loading: false,
      schema,
      compactBody: true,
      activePanel: 'slots',
    })

    expect(screen.getByText('默认插槽')).toBeInTheDocument()
    expect(screen.queryByText('标题')).not.toBeInTheDocument()
  })
})

function renderPanel(options: {
  loading: boolean
  schema: ComponentPreviewSchema | null
  compactBody?: boolean
  activePanel?: 'props' | 'slots' | 'mocks'
}) {
  return render(ComponentPreviewPanel, {
    props: {
      horizontal: true,
      compactBody: options.compactBody,
      activePanel: options.activePanel,
      loading: options.loading,
      schema: options.schema,
      state: buildInitialComponentPreviewState(options.schema),
    },
    global: {
      stubs: {
        MonacoCodeEditor: defineComponent({
          name: 'MonacoCodeEditor',
          props: {
            modelValue: {
              type: String,
              default: '',
            },
          },
          setup(props) {
            return () => h('textarea', { value: props.modelValue })
          },
        }),
      },
    },
  })
}
