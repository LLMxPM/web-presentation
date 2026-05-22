/**
 * 文件功能：验证组件预览参数 Dock 的 preset radio、tab 展开和抽屉交互。
 */
import { defineComponent, h, ref } from 'vue'
import { fireEvent, render, screen } from '@testing-library/vue'
import { describe, expect, it } from 'vitest'

import ComponentPreviewParameterDock from '@/components/component-preview/ComponentPreviewParameterDock.vue'
import {
  buildInitialComponentPreviewState,
  type ComponentPreviewSchema,
  type ComponentPreviewState,
} from '@/types/component-preview'

describe('ComponentPreviewParameterDock', () => {
  it('preset 应渲染为 radio，且不作为 tab 出现', () => {
    renderDock()

    expect(screen.getByLabelText('自定义')).toBeInTheDocument()
    expect(screen.getByLabelText('默认状态')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Presets/i })).not.toBeInTheDocument()
  })

  it('选择 preset 不应展开抽屉，也不应切换 active tab', async () => {
    renderDock()

    await fireEvent.click(screen.getByLabelText('默认状态'))

    expect(screen.getByLabelText('默认状态')).toBeChecked()
    expect(screen.queryByText('标题')).not.toBeInTheDocument()
    expect(screen.getByTitle('展开预览参数')).toHaveAttribute('aria-expanded', 'false')
  })

  it('点击 tab 应展开抽屉并渲染对应内容', async () => {
    renderDock()

    await fireEvent.click(screen.getByRole('button', { name: /Slots 1/i }))

    expect(screen.getByTitle('展开预览参数')).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('默认插槽')).toBeInTheDocument()
    expect(screen.queryByText('标题')).not.toBeInTheDocument()
  })

  it('抽屉开关按钮应按当前 tab 展开和收起', async () => {
    renderDock()
    const toggleButton = screen.getByTitle('展开预览参数')

    await fireEvent.click(toggleButton)
    expect(toggleButton).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('标题')).toBeInTheDocument()

    await fireEvent.click(toggleButton)
    expect(toggleButton).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('标题')).not.toBeInTheDocument()
  })

  it('抽屉展开后选择 preset 不应切换当前 tab', async () => {
    renderDock()

    await fireEvent.click(screen.getByRole('button', { name: /Slots 1/i }))
    await fireEvent.click(screen.getByLabelText('默认状态'))

    expect(screen.getByLabelText('默认状态')).toBeChecked()
    expect(screen.getByText('默认插槽')).toBeInTheDocument()
    expect(screen.queryByText('标题')).not.toBeInTheDocument()
  })

  it('手动修改字段后 radio 应回到自定义', async () => {
    renderDock()

    await fireEvent.click(screen.getByLabelText('默认状态'))
    await fireEvent.click(screen.getByRole('button', { name: /Props 1/i }))
    await fireEvent.update(screen.getByDisplayValue('默认标题'), '手动标题')

    expect(screen.getByLabelText('自定义')).toBeChecked()
    expect(screen.getByDisplayValue('手动标题')).toBeInTheDocument()
  })

  it('预览启动失败时应展示错误并禁用抽屉', () => {
    renderDock({
      schema: null,
      errorMessage: 'Element is missing end tag.',
    })

    expect(screen.getByText('组件预览启动失败：Element is missing end tag.')).toBeInTheDocument()
    expect(screen.getByTitle('展开预览参数')).toBeDisabled()
  })
})

function renderDock(options: {
  schema?: ComponentPreviewSchema | null
  initialState?: ComponentPreviewState
  errorMessage?: string
} = {}) {
  const schema = options.schema === undefined ? createSchema() : options.schema
  const initialState = options.initialState ?? buildInitialComponentPreviewState(schema)

  return render(defineComponent({
    name: 'ComponentPreviewParameterDockTestHost',
    setup() {
      const state = ref<ComponentPreviewState>(initialState)
      return () => h(ComponentPreviewParameterDock, {
        loading: false,
        errorMessage: options.errorMessage,
        schema,
        state: state.value,
        'onUpdate:state': (nextState: ComponentPreviewState) => {
          state.value = nextState
        },
      })
    },
  }), {
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

function createSchema(): ComponentPreviewSchema {
  return {
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
}
