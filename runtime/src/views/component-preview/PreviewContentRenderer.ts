/**
 * 文件用途：将组件预览状态转换为真实的 Vue 渲染树，负责 props 与声明式 slot 节点的组装。
 */

import {
  defineAsyncComponent,
  defineComponent,
  h,
  type Component,
  type PropType,
  type SlotsType,
  type VNodeChild,
} from 'vue'

import type {
  ComponentPreviewSlotNode,
} from '@/core/shared/runtime-preview'
import type { ComponentPreviewState } from '@/core/shared/component-preview'
import { importPreviewModule } from '@/core/utils/preview-module'

const slotComponentCache = new Map<string, ReturnType<typeof defineAsyncComponent>>()

/**
 * 组件预览内容渲染器。
 */
const PreviewContentRenderer = defineComponent({
  name: 'PreviewContentRenderer',
  props: {
    componentDefinition: {
      type: Object as PropType<Component>,
      required: true,
    },
    state: {
      type: Object as PropType<ComponentPreviewState>,
      required: true,
    },
  },
  slots: Object as SlotsType<Record<string, () => VNodeChild[]>>,
  setup(props) {
    /**
     * 渲染单个声明式 slot 节点。
     * @param node slot 节点定义
     * @param nodeIndex 当前节点索引
     * @returns VNode 或文本
     */
    function renderSlotNode(node: ComponentPreviewSlotNode, nodeIndex: number): VNodeChild {
      if (!node || typeof node !== 'object') {
        return null
      }

      if (node.type === 'text') {
        return node.value || ''
      }

      if (node.type === 'html') {
        return h('div', {
          key: `slot-html-${nodeIndex}`,
          innerHTML: node.value || '',
        })
      }

      if (node.type === 'component') {
        const asyncComponent = resolveSlotAsyncComponent(node.component)
        const childSlots = node.children?.length
          ? { default: () => renderSlotNodes(node.children) }
          : undefined
        return h(asyncComponent, {
          key: `slot-component-${nodeIndex}`,
          ...(node.props || {}),
        }, childSlots)
      }

      return null
    }

    /**
     * 渲染 slot 节点数组。
     * @param nodes slot 节点数组
     * @returns 渲染结果
     */
    function renderSlotNodes(nodes: ComponentPreviewSlotNode[] | undefined): VNodeChild[] {
      return (nodes || []).map((node, index) => renderSlotNode(node, index))
    }

    /**
     * 组装目标组件的 slots 对象。
     * @returns slots 渲染函数映射
     */
    function buildRuntimeSlots(): Record<string, () => VNodeChild[]> {
      return Object.fromEntries(
        Object.entries(props.state.slots || {}).map(([slotName, slotNodes]) => [
          slotName,
          () => renderSlotNodes(slotNodes),
        ]),
      )
    }

    return () => h(
      props.componentDefinition,
      props.state.props || {},
      buildRuntimeSlots(),
    )
  },
})

/**
 * 解析并缓存 slot 中引用的异步组件。
 * @param modulePath 组件模块路径
 * @returns 异步组件定义
 */
function resolveSlotAsyncComponent(modulePath: string) {
  const cacheKey = String(modulePath || '').trim()
  const cachedComponent = slotComponentCache.get(cacheKey)
  if (cachedComponent) {
    return cachedComponent
  }

  const asyncComponent = defineAsyncComponent(async () => {
    const module = await importPreviewModule(cacheKey)
    return resolveModuleComponent(module)
  })
  slotComponentCache.set(cacheKey, asyncComponent)
  return asyncComponent
}

/**
 * 从动态模块对象中解析 Vue 组件。
 * @param module 动态导入返回的模块对象或组件本身
 * @returns Vue 组件定义
 */
function resolveModuleComponent(module: unknown): Component {
  if (module && typeof module === 'object' && 'default' in module) {
    const defaultExport = (module as { default?: unknown }).default
    if (defaultExport) {
      return defaultExport as Component
    }
  }

  return module as Component
}

export default PreviewContentRenderer
