/**
 * 文件功能：验证视觉工具专用卡片的分析摘要、生成进度与资源回显。
 */
import { fireEvent, render, screen } from '@testing-library/vue'
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

  it('展示限制高度的图片理解缩略图，并在当前页面打开统一预览', async () => {
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
    expect(screen.getByText('图片对比')).toBeTruthy()
    expect(screen.queryByText('comparison')).toBeNull()
    expect(screen.getByText('第二张图片的信息层级更清晰。')).toBeTruthy()
    const inputImage = screen.getByAltText('input.png')
    expect(inputImage.closest('button')).toHaveClass('h-16')
    expect(screen.getByAltText('page.png')).toBeTruthy()

    await fireEvent.click(screen.getByRole('button', { name: '预览图片 input.png' }))
    expect(screen.getByRole('button', { name: '关闭图片预览' })).toBeTruthy()
    expect(screen.getAllByAltText('input.png')).toHaveLength(2)
    expect(document.querySelector('a[target="_blank"]')).toBeNull()
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
    expect(screen.getByAltText('hero.png')).toHaveClass('h-32', 'max-h-32')
    await screen.getByRole('button', { name: /已保存到资源库/ }).click()
    expect(routerPush).toHaveBeenCalledWith({ name: 'assets', params: { workspaceId: 7 } })
  })

  it('失败的图片生成不应渲染已落库的输出图片或资源标记', () => {
    render(AgentVisualToolCard, {
      props: {
        tool: createTool({
          status: 'error',
          message: '智能体运行中断。',
          outputPayload: { assets: [{ id: 9, name: 'partial-hero', original_name: 'partial-hero.png' }] },
          outputAttachments: [createAttachment(2, 'partial-hero.png')],
        }),
      },
    })

    expect(screen.getByText('失败')).toBeTruthy()
    expect(screen.queryByAltText('partial-hero.png')).toBeNull()
    expect(screen.queryByText('partial-hero')).toBeNull()
    expect(screen.queryByRole('button', { name: /已保存到资源库/ })).toBeNull()
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
