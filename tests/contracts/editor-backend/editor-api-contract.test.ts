/**
 * 文件功能：校验 editor BFF 客户端继续向 backend 使用稳定的关键路径与查询参数约定。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const aiClientSource = readFileSync(resolve(process.cwd(), 'editor/src/api/ai.ts'), 'utf-8')
const buildsClientSource = readFileSync(resolve(process.cwd(), 'editor/src/api/builds.ts'), 'utf-8')
const previewClientSource = readFileSync(resolve(process.cwd(), 'editor/src/api/preview.ts'), 'utf-8')

describe('editor-backend API contract', () => {
  it('AI 会话继续与取消应继续通过 active-run 路径访问 backend', () => {
    expect(aiClientSource).toContain('/ai/sessions/${sessionId}/active-run/continue')
    expect(aiClientSource).toContain('/ai/sessions/${sessionId}/active-run/cancel')
  })

  it('项目构建查询应继续使用项目级列表和 build-jobs 详情路径', () => {
    expect(buildsClientSource).toContain('/projects/${projectId}/build-jobs')
    expect(buildsClientSource).toContain('/build-jobs/${jobId}')
  })

  it('项目、页面、组件与资源预览都应继续走 preview artifact 协议', () => {
    expect(previewClientSource).toContain('/projects/${projectId}/preview-artifacts')
    expect(previewClientSource).toContain('/pages/${pageId}/versions/${versionNo}/preview-artifact')
    expect(previewClientSource).toContain('/components/${componentId}/preview-artifacts')
    expect(previewClientSource).toContain('/workspaces/${workspaceId}/assets/${assetId}/preview-artifact')
  })
})
