/* eslint-disable vue/one-component-per-file */
/** 文件功能：验证执行策略在 Vue 宿主树中的全局回退、传播、收紧与 DOM 属性。 */
import { createApp, defineComponent, h, type ComputedRef } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import {
  executionAttributes,
  initializeRuntimeExecution,
  provideRuntimeExecutionScope,
  resetRuntimeExecutionForTests,
} from './execution-scope'
import type { ExecutionContextKind, ExecutionPolicy } from './execution-policy'

afterEach(() => {
  resetRuntimeExecutionForTests()
  document.body.innerHTML = ''
})

/** 挂载外层作用域并读取最内层组件看到的策略。 */
function mountNestedScope(outer: ExecutionContextKind, inner: ExecutionContextKind): ExecutionPolicy {
  let captured: ComputedRef<ExecutionPolicy> | undefined
  const Child = defineComponent({
    setup() {
      captured = provideRuntimeExecutionScope(inner)
      return () => h('span')
    },
  })
  const Parent = defineComponent({
    setup() {
      provideRuntimeExecutionScope(outer)
      return () => h(Child)
    },
  })
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp(Parent)
  app.mount(root)
  expect(captured).toBeDefined()
  const policy = captured!.value
  app.unmount()
  return policy
}

describe('执行作用域传播', () => {
  it('没有父作用域时回退到初始化结果', () => {
    initializeRuntimeExecution('?runtimeCapture=1')
    const policy = mountNestedScope('presentation', 'presentation')
    expect(policy.kind).toBe('capture')
    expect(policy.allowMediaPlayback).toBe(false)
  })

  it('缩略图作用域收紧主画布策略并输出禁播属性', () => {
    const policy = mountNestedScope('presentation', 'thumbnail')
    expect(policy).toMatchObject({ kind: 'thumbnail', allowAutoStart: false, allowMediaPlayback: false })
    expect(executionAttributes(policy)).toEqual({
      'data-runtime-execution': 'thumbnail',
      'data-runtime-media': 'block',
    })
  })

  it('捕获作用域内的 presentation 不能重新放宽', () => {
    const policy = mountNestedScope('capture', 'presentation')
    expect(policy.kind).toBe('capture')
    expect(policy.allowAutoStart).toBe(false)
    expect(executionAttributes(policy)['data-runtime-media']).toBe('block')
  })

  it('交互预览作用域只允许手势播放', () => {
    const policy = mountNestedScope('presentation', 'interactive-preview')
    expect(policy.kind).toBe('interactive-preview')
    expect(executionAttributes(policy)['data-runtime-media']).toBe('gesture')
  })
})
