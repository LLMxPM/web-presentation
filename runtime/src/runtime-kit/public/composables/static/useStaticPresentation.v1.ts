/** 文件功能：公开独立静态呈现声明，供页面为截图、缩略图和导出显式准备可读内容。 */
import { computed, onBeforeUnmount, onMounted, shallowReadonly, shallowRef, toValue, type MaybeRefOrGetter } from 'vue'
import { useRuntimeExecutionPolicy } from '@/core/execution/execution-scope'
import { registerStaticPresentation } from '@/core/static-presentation/registry'
import { isStaticExecution, staticReceipt, STATIC_PRESENTATION_TIMEOUT, type StaticPresentationReceipt } from '@/core/static-presentation/types'

export interface UseStaticPresentationOptions {
  root: MaybeRefOrGetter<HTMLElement | null | undefined>
  /** default 使用可读默认态；poster 由模板或 prepare 提供独立海报；unsupported 明确不可呈现。 */
  mode: 'default' | 'poster' | 'unsupported'
  reason?: string
  /** 仅在静态上下文执行；必须响应 signal，不能自行播放动画或媒体。 */
  prepare?: (context: { signal: AbortSignal }) => void | Promise<void>
  timeoutMs?: number
}

/** 声明与时间轴无关的静态态；isStatic 可用于模板分支和 mounted 副作用的显式守卫。 */
export function useStaticPresentation(options: UseStaticPresentationOptions) {
  const execution = useRuntimeExecutionPolicy()
  const isStatic = computed(() => isStaticExecution(execution.value.kind))
  const state = shallowRef<StaticPresentationReceipt | null>(null)
  const controller = new AbortController()
  let disposed = false
  let timer: ReturnType<typeof setTimeout> | undefined
  let resolveReady!: (result: StaticPresentationReceipt) => void
  const ready = new Promise<StaticPresentationReceipt>(resolve => { resolveReady = resolve })
  const unregister = registerStaticPresentation({ root: () => toValue(options.root), ready })

  /** 提交当前实例的回执；卸载后的异步结果不再污染后续页面的就绪状态。 */
  function finish(result: StaticPresentationReceipt): void {
    if (disposed) return
    state.value = result
    resolveReady(result)
  }

  onMounted(async () => {
    if (!isStatic.value) { finish(staticReceipt('ready')); return }
    if (!(toValue(options.root) instanceof HTMLElement)) { finish(staticReceipt('failed', '静态呈现缺少页面根节点。')); return }
    if (!['default', 'poster', 'unsupported'].includes(options.mode)) { finish(staticReceipt('failed', '静态呈现 mode 非法。')); return }
    if (options.mode === 'unsupported') { finish(staticReceipt('unsupported', options.reason)); return }
    try {
      const result = await Promise.race([
        Promise.resolve().then(() => options.prepare?.({ signal: controller.signal })).then(() => staticReceipt('ready')),
        new Promise<StaticPresentationReceipt>(resolve => {
          timer = setTimeout(() => {
            controller.abort()
            resolve(staticReceipt('failed', '静态呈现准备超时。', STATIC_PRESENTATION_TIMEOUT))
          }, Math.max(1, Math.min(options.timeoutMs ?? 25000, 25000)))
        }),
      ])
      finish(result)
    } catch {
      finish(staticReceipt('failed', '静态呈现准备失败。'))
    } finally {
      clearTimeout(timer)
    }
  })

  onBeforeUnmount(() => {
    disposed = true
    clearTimeout(timer)
    controller.abort()
    unregister()
    resolveReady(staticReceipt('ready'))
  })
  return { isStatic, state: shallowReadonly(state), ready }
}
