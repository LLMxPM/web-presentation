// 文件功能：绑定窄资源摘要的研究 builder，复用已验证的依赖编译器，不复制 DOM 编排 API。
import { compile } from '../motion-story/plan'
import type { Draft } from '../motion-story/types'
import type { ResourceBuilder, ResourceSummary } from './api-types'

/** 仅允许旁白、片段、裁切视频的语义轨道，所有时长仍来自已准备的资源。 */
export function resourcePlan(assets: ResourceSummary): ResourceBuilder {
  const drafts: Draft[] = []
  const builder: ResourceBuilder = {
    voice(id) { drafts.push({ id, type: 'voice', target: 'voice', start: { atMs: 0 } }); return builder },
    clip(id, clipRef, start) { drafts.push({ id, type: 'clip', target: 'model', clipRef, start }); return builder },
    video(id, trim, start) { drafts.push({ id, type: 'video', target: 'video', ...trim, start }); return builder },
    build() { return compile(assets, drafts) },
  }
  return builder
}
