/**
 * 文件功能：以确定性 API 桩覆盖统一内容助手的图片上传、视觉状态、工具 SSE 回显与刷新快照恢复。
 */
import { expect, test, type Page, type Route } from '@playwright/test'

import { loginAsAdmin } from '../helpers/auth'
import { openFirstPage, openFirstProject, waitForWorkspaceHome } from '../helpers/navigation'

const pixelDataUrl = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgAAAAAgAB4iG8MwAAAABJRU5ErkJggg=='

test('local 图片应经视觉工具卡回显并在刷新后保持一致', async ({ page }) => {
  await loginAsAdmin(page)
  await installVisualAiApiStub(page)
  await waitForWorkspaceHome(page)
  await openFirstProject(page)
  await openFirstPage(page)
  await openAgentSidebar(page)

  const fileInput = page.locator('[data-testid="agent-sidebar-panel"] input[type="file"]')
  await fileInput.setInputFiles([
    {
      name: 'reference-a.png',
      mimeType: 'image/png',
      buffer: Buffer.from(pixelDataUrl.split(',')[1], 'base64'),
    },
    {
      name: 'reference-b.png',
      mimeType: 'image/png',
      buffer: Buffer.from(pixelDataUrl.split(',')[1], 'base64'),
    },
  ])
  await expect(page.getByAltText('reference-a.png')).toBeVisible()
  await expect(page.getByAltText('reference-b.png')).toBeVisible()
  await expect(page.getByText('已添加 2/10 张')).toBeVisible()

  const composer = page.locator('[data-testid="agent-sidebar-panel"] textarea')
  await composer.fill('先分析这张参考图，再生成一张蓝色主视觉。')
  await page.locator('[data-testid="agent-sidebar-panel"]').getByRole('button', { name: /发送/ }).click()

  const panel = page.locator('[data-testid="agent-sidebar-panel"]')
  await expectVisualToolResult(panel)

  await page.reload()
  await openAgentSidebar(page)
  await expectVisualToolResult(panel)
})

test('内容助手在资源库页面仍应展示视觉能力并允许上传参考图', async ({ page }) => {
  await loginAsAdmin(page)
  await installVisualAiApiStub(page)
  await waitForWorkspaceHome(page)
  await page.locator('[data-testid="workspace-dock-assets"]').click()
  await expect(page.locator('[data-testid="assets-view"]')).toBeVisible()
  await openAgentSidebar(page)

  const panel = page.locator('[data-testid="agent-sidebar-panel"]')
  const contentAgentTab = panel.getByRole('tab', { name: '内容助手', exact: true })
  await expect(contentAgentTab).toHaveAttribute('aria-selected', 'true')
  await expect(panel.getByRole('tab')).toHaveCount(1)

  const visualStatus = panel.getByRole('region', { name: '视觉工具状态' })
  await expect(visualStatus.getByTitle('analyze_visuals 已配置，可按需分析附件、工作空间图片资源或页面截图')).toBeVisible()
  await expect(visualStatus.getByTitle('generate_image 已配置，可生成或编辑图片并保存到资源库')).toBeVisible()
  await expect(panel.getByLabel('上传图片')).toBeEnabled()
})

/** 确保全局 AI 侧栏处于打开状态，兼容刷新后保留用户偏好。 */
async function openAgentSidebar(page: Page) {
  const panel = page.locator('[data-testid="agent-sidebar-panel"]')
  if (!await panel.isVisible()) {
    await page.locator('[data-testid="agent-floating-trigger"]').click()
  }
  await expect(panel).toBeVisible()
}

/** 展开已完成的工具组与图片生成卡片，并验证视觉工具产物。 */
async function expectVisualToolResult(panel: ReturnType<Page['locator']>) {
  const toolGroup = panel.locator('details.tool-call-group')
  await expect(toolGroup).toBeVisible()
  await toolGroup.locator(':scope > summary').click()

  const generationCard = panel.locator('details.visual-tool-details').filter({ hasText: '图片生成' })
  await expect(panel.getByText('图片理解', { exact: true })).toBeVisible()
  await expect(generationCard).toBeVisible()
  await generationCard.locator(':scope > summary').click()
  await expect(generationCard.getByText('hero_visual', { exact: true })).toBeVisible()
  await expect(generationCard.getByRole('button', { name: /已保存到资源库/ })).toBeVisible()
}

/** 安装只覆盖 AI 接口的确定性桩，页面、项目与认证仍使用真实 smoke 环境。 */
async function installVisualAiApiStub(page: Page) {
  const agentId = 'agent-coordinator'
  let session: Record<string, unknown> | null = null
  let completed = false
  let scope = { scope_type: 'page', workspace_id: 1, project_id: 1, page_id: 1, source: 'editor-page-detail' }
  const inputAttachments = [
    attachment(11, 'user_upload', 'reference-a.png', null),
    attachment(13, 'user_upload', 'reference-b.png', null),
  ]
  const outputAttachment = attachment(12, 'tool_output', 'hero.png', 91)
  let uploadIndex = 0

  await page.route('**/api/ai/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (path.endsWith('/api/ai/agents')) {
      scope = {
        scope_type: url.searchParams.get('scope_type') || 'page',
        workspace_id: Number(url.searchParams.get('workspace_id')),
        project_id: Number(url.searchParams.get('project_id')),
        page_id: Number(url.searchParams.get('page_id')),
        source: url.searchParams.get('source') || 'editor-page-detail',
      }
      return json(route, [{
        id: agentId,
        name: '内容助手',
        icon: 'content-spark',
        summary: '视觉工具 smoke',
        default_session_name: '视觉工具会话',
        capabilities: ['图片理解', '图片生成'],
        scope_type: 'workspace',
        entry_kind: 'agent',
        available: true,
        llm_slot: 'agent_coordinator',
        llm_binding_ready: true,
        bound_llm_name: 'Smoke Chat',
        bound_provider_label: 'OpenAI',
        image_analysis_available: true,
        image_analysis_unavailable_reason: null,
        image_generation_available: true,
        image_generation_unavailable_reason: null,
        scope,
      }])
    }
    if (path.endsWith('/api/ai/llm-configs')) return json(route, [chatModel()])
    if (path.endsWith('/api/ai/llm-slots')) return json(route, [chatSlot()])
    if (path.endsWith('/api/ai/sessions') && request.method() === 'GET') return json(route, session ? [session] : [])
    if (path.endsWith('/api/ai/sessions') && request.method() === 'POST') {
      const body = request.postDataJSON() as { workspace_id: number }
      expect(body.workspace_id).toBe(scope.workspace_id)
      session = sessionItem(scope, agentId)
      return json(route, session, 201)
    }
    if (path.includes('/attachments/images') && request.method() === 'POST') {
      const uploaded = inputAttachments[Math.min(uploadIndex, inputAttachments.length - 1)]
      uploadIndex += 1
      return json(route, uploaded, 201)
    }
    if (path.endsWith('/runs/stream') && request.method() === 'POST') {
      expect((request.postDataJSON() as { image_attachment_ids: number[] }).image_attachment_ids).toEqual([11, 13])
      completed = true
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: visualSse(inputAttachments, outputAttachment),
      })
    }
    if (path.endsWith('/runtime')) return json(route, runtimeSnapshot(session || sessionItem(scope, agentId), completed, inputAttachments, outputAttachment))
    return route.fallback()
  })
}

/** 返回前端 SSE 解析器可直接消费的完整视觉任务事件。 */
function visualSse(inputAttachments: Record<string, unknown>[], outputAttachment: Record<string, unknown>) {
  const visualInputs = inputAttachments.map(item => ({ source_type: 'attachment', attachment_id: item.id }))
  const events = [
    runEvent('run.started', 0, {}),
    runEvent('tool.started', 1, {
      tool_call_id: 'analyze-1', tool_name: 'analyze_visuals',
      tool_args: { inputs: visualInputs, instruction: '分析图片', analysis_type: 'general' },
      input_attachments: inputAttachments,
    }),
    runEvent('tool.completed', 2, {
      tool_call_id: 'analyze-1', tool_name: 'analyze_visuals',
      result: { summary: '参考图为蓝色横向主视觉。', items: [{ source: { source_type: 'attachment', attachment_id: 11 }, description: '蓝色横幅' }] },
    }),
    runEvent('message.delta', 3, {}, '已完成图片分析。'),
    runEvent('tool.started', 4, {
      tool_call_id: 'generate-1', tool_name: 'generate_image',
      tool_args: { operation: 'generate', prompt: '蓝色主视觉' },
    }),
    runEvent('tool.progress', 5, {
      tool_call_id: 'generate-1', tool_name: 'generate_image', phase: 'saving', message: '正在保存到资源库。',
    }),
    runEvent('tool.completed', 6, {
      tool_call_id: 'generate-1', tool_name: 'generate_image', output_attachments: [outputAttachment],
      result: { job_id: 'ai-image-job-smoke', assets: [{ id: 91, name: 'hero_visual', original_name: 'hero.png' }] },
    }),
    runEvent('run.completed', 7, {}, '视觉任务完成。'),
  ]
  return events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
}

/** 构造刷新后与实时 SSE 等价的运行时快照。 */
function runtimeSnapshot(
  session: Record<string, unknown>,
  completed: boolean,
  inputAttachments: Record<string, unknown>[],
  outputAttachment: Record<string, unknown>,
) {
  return {
    session,
    timeline_items: completed ? [
      toolTimeline('analyze-1', 'analyze_visuals', {
        inputs: inputAttachments.map(item => ({ source_type: 'attachment', attachment_id: item.id })), instruction: '分析图片', analysis_type: 'general',
      }, { summary: '参考图为蓝色横向主视觉。' }, inputAttachments, []),
      toolTimeline('generate-1', 'generate_image', {
        operation: 'generate', prompt: '蓝色主视觉',
      }, { job_id: 'ai-image-job-smoke', assets: [{ id: 91, name: 'hero_visual', original_name: 'hero.png' }] }, [], [outputAttachment]),
    ] : [],
    member_runs: [], context_status: null, active_run: null, last_run: null,
    pending_requirement: null, event_index: completed ? 7 : -1, pending_attachments: completed ? [] : inputAttachments,
  }
}

function toolTimeline(
  callId: string,
  name: string,
  input: Record<string, unknown>,
  output: Record<string, unknown>,
  inputAttachments: Record<string, unknown>[],
  outputAttachments: Record<string, unknown>[],
) {
  return {
    id: `tool-${callId}`, session_id: 'session-visual-smoke', run_id: 'run-visual-smoke', kind: 'tool',
    role: null, event_index: 1, order_index: name === 'analyze_visuals' ? 0 : 1, content: null, status: 'completed',
    tool: {
      tool_call_id: callId, tool_name: name, status: 'completed', input_payload: input, output_payload: output,
      message: '', progress: { phase: 'completed', message: '已完成。' },
      input_attachments: inputAttachments, output_attachments: outputAttachments,
    },
    attachments: outputAttachments, source: 'event', created_at: '2026-07-20T10:00:00+08:00',
  }
}

function runEvent(event: string, sequence: number, data: Record<string, unknown>, content: string | null = null) {
  return { event, run_id: 'run-visual-smoke', session_id: 'session-visual-smoke', content, data, sequence, event_index: sequence }
}

function attachment(id: number, sourceKind: string, originalName: string, assetId: number | null) {
  return {
    id, source_kind: sourceKind, original_name: originalName, content_type: 'image/png', file_size: 68,
    width: 1, height: 1, url: pixelDataUrl, preview_available: true, promoted_asset_id: assetId,
  }
}

function sessionItem(metadata: Record<string, unknown>, agentId = 'agent-coordinator') {
  return {
    session_id: 'session-visual-smoke', agent_id: agentId, session_name: '视觉工具会话',
    workspace_id: Number(metadata.workspace_id), focus_mode: 'follow_route', pinned_project_id: null,
    work_scope_mode: 'workspace', allowed_project_ids: [], focus_version: 0,
    created_at: '2026-07-20T10:00:00+08:00', updated_at: '2026-07-20T10:00:00+08:00', metadata: {},
  }
}

function chatModel() {
  return {
    id: 7, scope: 'global', owner_user_id: null, editable: false, name: 'Smoke Chat', provider_config_id: 1,
    provider_config_name: 'Smoke OpenAI', provider_key: 'openai', provider_label: 'OpenAI', model_id: 'gpt-4.1-mini',
    model_type: 'chat', base_url: null, thinking_enabled: false, thinking_effort: null, supports_image_input: false,
    context_window_tokens: 128000, max_output_tokens: 32000, history_token_ratio: 0.5, compression_target_ratio: 0.1,
    advanced_config_json: {}, status: 'active', has_api_key: true, api_key_masked: 'sk-****', created_at: null, updated_at: null,
  }
}

function chatSlot() {
  return {
    slot: 'agent_coordinator',
    slot_label: '内容助手',
    llm_config_id: 7, llm_config_name: 'Smoke Chat',
    provider_key: 'openai', provider_label: 'OpenAI', model_id: 'gpt-4.1-mini', model_type: 'chat',
    binding_ready: true, supports_image_input: false, inherited_from_global: true,
  }
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}
