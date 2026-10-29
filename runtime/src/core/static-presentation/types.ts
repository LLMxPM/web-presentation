/** 文件功能：定义独立静态呈现声明、执行上下文与有界就绪回执。 */
import type { ExecutionContextKind } from '@/core/execution/execution-policy'

export const STATIC_PRESENTATION_UNAVAILABLE = 'STATIC_PRESENTATION_UNAVAILABLE'
export const STATIC_PRESENTATION_FAILED = 'STATIC_PRESENTATION_FAILED'
export const STATIC_PRESENTATION_TIMEOUT = 'STATIC_PRESENTATION_TIMEOUT'

export interface StaticPresentationReceipt {
  status: 'ready' | 'unsupported' | 'failed'
  code: string | null
  message: string | null
}

/** 静态执行与交互预览分开，不通过播放时刻推断海报。 */
export function isStaticExecution(kind: ExecutionContextKind | string | null | undefined): boolean {
  return kind === 'capture' || kind === 'export' || kind === 'thumbnail'
}

/** 生成允许跨桥传递的短回执，不暴露异常堆栈或任意页面对象。 */
export function staticReceipt(status: StaticPresentationReceipt['status'], message?: string, code?: string): StaticPresentationReceipt {
  return {
    status,
    code: status === 'ready' ? null : code ?? (status === 'unsupported' ? STATIC_PRESENTATION_UNAVAILABLE : STATIC_PRESENTATION_FAILED),
    message: status === 'ready' ? null : (message || '页面未提供可用的静态呈现。').slice(0, 240),
  }
}
