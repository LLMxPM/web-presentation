/** 文件功能：以真实渲染证据完成首次与上下文恢复就绪，不把历史帧当成新上下文成功。 */
import type { Ref } from 'vue'
/** 回执受当前加载令牌围栏约束，迟到帧不会复活旧实例。 */
export function createModelFirstFrameReady(options: {
    state: Ref<'loading' | 'ready' | 'error'>; message: Ref<string>
    isCurrent(token: number): boolean; hasRenderProof(): boolean; waitForFrame(): Promise<void>; requestRender(): void
  }) {
  /**
   * 标记就绪：仅当真实渲染过一帧后生效。
   * @param token 本次加载令牌
   */
  async function markReady(token: number): Promise<void> {
    await options.waitForFrame()
    if (!options.isCurrent(token) || !options.hasRenderProof()) {
      return
    }
    options.state.value = 'ready'
    options.message.value = ''
  }

  /**
   * WebGL 上下文恢复后的就绪门禁：等待真实渲染出新的一帧才回到 ready。
   *
   * 与首次加载不同，恢复后的 rAF 可能先于调度渲染触发，且历史 hasRenderedFrame
   * 无法证明恢复后的绘制成功，因此这里循环等待并主动补排帧；超时则保持 error 态。
   * @param token 恢复时的加载令牌
   */
  async function markReadyAfterRenderedFrame(token: number): Promise<void> {
    for (let attempt = 0; attempt < 5; attempt += 1) {
      await options.waitForFrame()
      if (!options.isCurrent(token)) {
        return
      }
      if (options.hasRenderProof()) {
        options.state.value = 'ready'
        options.message.value = ''
        return
      }
      options.requestRender()
    }
    if (options.isCurrent(token)) {
      options.state.value = 'error'
      options.message.value = 'WebGL 上下文已恢复，但未能完成渲染，请刷新后重试。'
    }
  }

  return { markReady, markReadyAfterRenderedFrame }
}
