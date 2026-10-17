/**
 * 文件功能：在 Vue 宿主树中传播执行策略，并为 DOM 媒体守卫输出作用域属性。
 * 根宿主在 main.ts 中先初始化全局策略，再由各宿主用 provide 收紧子作用域。
 */
import { computed, inject, provide, shallowRef, unref, type ComputedRef, type InjectionKey, type MaybeRef } from 'vue'
import type { RuntimePreviewContext } from '@/core/shared/runtime-preview'
import {
  EXECUTION_POLICIES,
  mediaPlaybackMode,
  mergeExecutionPolicies,
  resolveExecutionContext,
  type ExecutionContextKind,
  type ExecutionPolicy,
} from './execution-policy'

const EXECUTION_POLICY_KEY: InjectionKey<ComputedRef<ExecutionPolicy>> = Symbol('runtime-execution-policy')

// 使用 shallowRef 保证初始化/测试重置后注入方能看到最新策略。
const globalPolicy = shallowRef<ExecutionPolicy>(EXECUTION_POLICIES.presentation)
const globalPolicyRef = computed(() => globalPolicy.value)

/**
 * 在应用初始化、任何组件挂载前确定本次宿主策略。
 * 传入当前地址查询和已注入的预览上下文；不读取演讲频道状态。
 */
export function initializeRuntimeExecution(
  search = '',
  previewContext?: Pick<RuntimePreviewContext, 'previewKind' | 'entryDescriptor'> | null,
): ExecutionPolicy {
  globalPolicy.value = resolveExecutionContext({ search, previewContext })
  return globalPolicy.value
}

export function getRuntimeExecutionPolicy(): ExecutionPolicy {
  return globalPolicy.value
}

/** 仅供测试重置模块级策略。 */
export function resetRuntimeExecutionForTests(): void {
  globalPolicy.value = EXECUTION_POLICIES.presentation
}

/** 读取最近的执行策略；没有宿主作用域时回退到初始化结果。 */
export function useRuntimeExecutionPolicy(): ComputedRef<ExecutionPolicy> {
  return inject(EXECUTION_POLICY_KEY, null) ?? globalPolicyRef
}

/**
 * 为当前宿主建立执行作用域。
 * 请求的上下文只能收紧父级策略，不能放宽；策略同时供子组件 inject 和 DOM 媒体守卫读取。
 */
export function provideRuntimeExecutionScope(kind: MaybeRef<ExecutionContextKind>): ComputedRef<ExecutionPolicy> {
  const parent = useRuntimeExecutionPolicy()
  const policy = computed(() => mergeExecutionPolicies(parent.value, EXECUTION_POLICIES[unref(kind)]))
  provide(EXECUTION_POLICY_KEY, policy)
  return policy
}

/** 宿主根节点属性；媒体守卫按最近的 data-runtime-media 决定是否阻断播放。 */
export function executionAttributes(policy: ExecutionPolicy): Record<string, string> {
  return {
    'data-runtime-execution': policy.kind,
    'data-runtime-media': mediaPlaybackMode(policy),
  }
}
