/** 文件功能：定义整页过渡的 Runtime 配置契约。 */
export interface PageTransitionConfig {
  effect: 'none' | 'fade' | 'push'
  durationMs: number
}

/** 整页过渡完成信号；generation 用于丢弃旧页迟到的完成事件。 */
export interface TransitionSettledEvent {
  path: string
  generation: number
}

/** 页面停留与翻页推进配置。 */
export interface PageAdvanceConfig {
  mode: 'manual' | 'timer'
  delayMs: number
}
