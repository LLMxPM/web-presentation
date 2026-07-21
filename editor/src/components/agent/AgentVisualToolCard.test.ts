/**
 * 文件功能：验证视觉工具专用卡片的分析摘要、生成进度与资源回显。
 */
import { render, screen } from '@testing-library/vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AgentVisualToolCard from '@/components/agent/AgentVisualToolCard.vue'
import type { ToolCallDetail } from '@/components/agent/agent-conversation-panel'

const routerPush = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { workspaceId: '7' } }),
  useRouter: () => ({ push: routerPush }),
}))

describe('AgentVisualToolCard', () => {
  beforeEach(() => routerPush.mockReset())

  it('展示图片理解的附件、页面截图和短摘要', () => {
    render(AgentVisualToolCard, {
      props: {
        tool: createTool({
          toolName: 'analyze_visuals',
          inputPayload: { analysis_type: 'comparison' },
          outputPayload: { summary: '第二张图片的信息层级更清晰。' },
          inputAttachments: [createAttachment(1, 'input.png')],
          outputAttachments: [createAttachment(2, 'page.png')],
        }),
      },
    })

    expect(screen.getByText('图片理解')).toBeTruthy()
    expect(screen.getByText('comparison')).toBeTruthy()
    expect(screen.getByText('第二张图片的信息层级更清晰。')).toBeTruthy()
    expect(screen.getByAltText('input.png')).toBeTruthy()
    expect(screen.getByAltText('page.png')).toBeTruthy()
  })

  it('展示图片生成结果和资源库标记', async () => {
    render(AgentVisualToolCard, {
      props: {
        tool: createTool({
          toolName: 'generate_image',
          outputPayload: { assets: [{ id: 9, name: 'hero', original_name: 'hero.png' }] },
          outputAttachments: [createAttachment(2, 'hero.png')],
        }),
      },
    })

    expect(screen.getByText('图片生成')).toBeTruthy()
    expect(screen.getByText('已生成 1 张图片，并创建工作空间资源。')).toBeTruthy()
    expect(screen.getByText('hero')).toBeTruthy()
    await screen.getByRole('button', { name: /已保存到资源库/ }).click()
    expect(routerPush).toHaveBeenCalledWith({ name: 'assets', params: { workspaceId: 7 } })
  })
})

function createTool(patch: Partial<ToolCallDetail>): ToolCallDetail {
  return {
    id: 'tool-1',
    runId: 'run-1',
    toolCallId: 'call-1',
    toolName: 'generate_image',
    status: 'completed',
    inputPayload: { operation: 'generate' },
    outputPayload: null,
    message: '',
    progress: { phase: 'completed', message: '图片已保存。' },
    source: 'event',
    createdAt: null,
    delegatedMemberRuns: [],
    attachments: [],
    inputAttachments: [],
    outputAttachments: [],
    ...patch,
  }
}

function createAttachment(id: number, originalName: string) {
  return {
    id,
    source_kind: 'tool_output' as const,
    original_name: originalName,
    content_type: 'image/png',
    file_size: 100,
    url: `/api/ai/attachments/images/${id}/content`,
    preview_available: true,
    promoted_asset_id: id + 100,
  }
}
