/** 文件功能：定义整页过渡的 Runtime 配置契约。 */
export interface PageTransitionConfig {
  effect: 'none' | 'fade' | 'push'
  durationMs: number
}
